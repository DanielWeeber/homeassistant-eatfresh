"""Tests for the EatFresh config flow and options flow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eatfresh.const import (
    CONF_ACCEPT_CHEFKOCH,
    CONF_HOUSEHOLD_ID,
    CONF_SHOPPINGLIST_ID,
    CONF_SOURCES,
    CONF_TOKEN,
    CONF_URL,
    DOMAIN,
)
from custom_components.eatfresh.errors import KitchenOwlAuthError, KitchenOwlError

from .conftest import KITCHENOWL_URL, TOKEN

pytestmark = pytest.mark.usefixtures("patch_client", "mock_sources", "panel_dir")


async def _start(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def test_full_flow(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Address and token, then household and shopping list."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: f" {KITCHENOWL_URL}/ ", CONF_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "household"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOUSEHOLD_ID: "5"}
    )
    assert result["step_id"] == "shoppinglist"
    mock_client.list_shoppinglists.assert_awaited_once_with(5)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SHOPPINGLIST_ID: "3"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "EatFresh"
    assert result["data"] == {
        CONF_URL: KITCHENOWL_URL,
        CONF_TOKEN: TOKEN,
        CONF_HOUSEHOLD_ID: 5,
        CONF_SHOPPINGLIST_ID: 3,
    }
    assert result["result"].unique_id == "5"
    await hass.async_block_till_done()


async def test_single_household_is_skipped(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """With one household the household step is skipped."""
    mock_client.list_households.return_value = [{"id": 1, "name": "Home"}]
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: KITCHENOWL_URL, CONF_TOKEN: TOKEN}
    )
    assert result["step_id"] == "shoppinglist"
    mock_client.list_shoppinglists.assert_awaited_once_with(1)


@pytest.mark.parametrize(
    ("side_effect", "households", "error"),
    [
        (KitchenOwlAuthError("401"), None, "invalid_auth"),
        (KitchenOwlError("down"), None, "cannot_connect"),
        (RuntimeError("boom"), None, "unknown"),
        (None, [], "no_households"),
    ],
)
async def test_user_errors_and_recovery(
    hass: HomeAssistant,
    mock_client: MagicMock,
    side_effect: Exception | None,
    households: list | None,
    error: str,
) -> None:
    """Errors are shown on the form, and the flow can recover."""
    original = mock_client.list_households.return_value
    mock_client.get_user.side_effect = side_effect
    if households is not None:
        mock_client.list_households.return_value = households
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: KITCHENOWL_URL, CONF_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_client.get_user.side_effect = None
    mock_client.list_households.return_value = original
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: KITCHENOWL_URL, CONF_TOKEN: TOKEN}
    )
    assert result["step_id"] == "household"


async def test_invalid_url(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """A URL without scheme is rejected before any request."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: "kitchenowl.example.com", CONF_TOKEN: TOKEN}
    )
    assert result["errors"] == {CONF_URL: "invalid_url"}
    mock_client.get_user.assert_not_awaited()


async def test_household_errors(hass: HomeAssistant, mock_client: MagicMock) -> None:
    """Errors while loading shopping lists."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: KITCHENOWL_URL, CONF_TOKEN: TOKEN}
    )
    mock_client.list_shoppinglists.return_value = []
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOUSEHOLD_ID: "1"}
    )
    assert result["errors"] == {"base": "no_shoppinglists"}

    mock_client.list_shoppinglists.side_effect = KitchenOwlError("down")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOUSEHOLD_ID: "1"}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    mock_client.list_shoppinglists.side_effect = KitchenOwlAuthError("403")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOUSEHOLD_ID: "1"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_auth"


async def test_single_instance(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Only one entry is allowed."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_reauth(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A new token replaces the old one."""
    result = await init_integration.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    mock_client.get_user.side_effect = KitchenOwlAuthError("401")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "bad"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    mock_client.get_user.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "new-token"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert init_integration.data[CONF_TOKEN] == "new-token"
    await hass.async_block_till_done()


async def test_options_default_and_save(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The options form lists searchable sources with defaults and saves."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] is FlowResultType.FORM
    schema = result["data_schema"].schema
    sources_key = next(key for key in schema if key == CONF_SOURCES)
    assert sources_key.default() == ["fakea", "fakeb"]
    options = schema[sources_key].config["options"]
    assert [option["value"] for option in options] == ["fakea", "fakeb", "chefkoch"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SOURCES: ["fakeb"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options == {
        CONF_SOURCES: ["fakeb"],
        CONF_ACCEPT_CHEFKOCH: False,
        # Not in the form input: the default of the form (one minute).
        "planner_interval": 1,
    }
    await hass.async_block_till_done()
    assert set(init_integration.runtime_data.sources) == {"fakeb", "jsonld"}


async def test_options_chefkoch_needs_checkbox(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Chefkoch can only be turned on with the extra checkbox."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SOURCES: ["fakea", "chefkoch"]}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_ACCEPT_CHEFKOCH: "chefkoch_terms"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SOURCES: ["fakea", "chefkoch"], CONF_ACCEPT_CHEFKOCH: True},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert "chefkoch" in init_integration.runtime_data.sources
