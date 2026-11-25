"""Tests for the EatFresh actions."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.eatfresh.const import DOMAIN
from custom_components.eatfresh.errors import (
    KitchenOwlAuthError,
    KitchenOwlError,
    SourceBlocked,
    SourceError,
)

from .conftest import RECIPE_HOST

URL = f"https://{RECIPE_HOST}/fakea/r7"


async def _import(hass: HomeAssistant, url: str = URL) -> dict:
    return await hass.services.async_call(
        DOMAIN, "import_recipe", {"url": url}, blocking=True, return_response=True
    )


async def test_import_recipe(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Import creates the recipe once and marks it as favorite."""
    assert await _import(hass) == {
        "kitchenowl_id": 42,
        "title": "Test recipe r7",
        "created": True,
    }
    assert init_integration.runtime_data.store.is_favorite("fakea:r7")
    assert await _import(hass) == {
        "kitchenowl_id": 42,
        "title": "Test recipe r7",
        "created": False,
    }
    assert mock_client.create_recipe.await_count == 1


async def test_import_existing_in_kitchenowl(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A recipe with the same source URL in KitchenOwl is reused."""
    mock_client.find_by_source.return_value = 5
    response = await _import(hass)
    assert response["kitchenowl_id"] == 5 and response["created"] is False
    mock_client.create_recipe.assert_not_awaited()


async def test_add_recipe_to_shopping_list(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Ingredients go onto the configured list."""
    response = await hass.services.async_call(
        DOMAIN,
        "add_recipe_to_shopping_list",
        {"recipe_id": 11},
        blocking=True,
        return_response=True,
    )
    assert response == {"added": 3}
    # 0.5.0: the recipe is read first (its yields is the base); unknown
    # yields here, so nothing is scaled.
    mock_client.add_recipe_to_shoppinglist.assert_awaited_once_with(
        2, 11, recipe={"id": 11, "name": "Soup"}, servings=None
    )


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (KitchenOwlAuthError("401"), "kitchenowl_auth"),
        (KitchenOwlError("500"), "kitchenowl_error"),
    ],
)
async def test_kitchenowl_errors(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    error: Exception,
    key: str,
) -> None:
    """KitchenOwl errors become HomeAssistantError with a translation key."""
    mock_client.add_recipe_to_shoppinglist.side_effect = error
    with pytest.raises(HomeAssistantError) as exc:
        await hass.services.async_call(
            DOMAIN,
            "add_recipe_to_shopping_list",
            {"recipe_id": 11},
            blocking=True,
            return_response=True,
        )
    assert exc.value.translation_key == key
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    # Only a rejected token starts the reauthentication.
    assert len(flows) == (1 if key == "kitchenowl_auth" else 0)


@pytest.mark.parametrize(
    ("error", "key"),
    [(SourceBlocked("429"), "source_blocked"), (SourceError("x"), "source_error")],
)
async def test_source_errors(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    error: Exception,
    key: str,
) -> None:
    """Source errors become HomeAssistantError."""
    init_integration.runtime_data.sources["fakea"].get_by_url.side_effect = error
    with pytest.raises(HomeAssistantError) as exc:
        await _import(hass)
    assert exc.value.translation_key == key


async def test_invalid_input(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Schemas reject bad input."""
    with pytest.raises(vol.Invalid):
        await _import(hass, "not a url")
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "add_recipe_to_shopping_list",
            {"recipe_id": 0},
            blocking=True,
            return_response=True,
        )


async def test_not_loaded(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Actions stay registered but refuse to work when unloaded."""
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    assert hass.services.has_service(DOMAIN, "import_recipe")
    with pytest.raises(ServiceValidationError) as exc:
        await _import(hass)
    assert exc.value.translation_key == "not_loaded"
