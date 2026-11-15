"""Tests for the fixes of EatFresh 0.3.0 after the independent review.

1. Same plan, same state: signed photo paths are reused until shortly
   before they run out.
2. Parallel callers share one fetch of the meal plan.
3. ``search_collection`` has ``limit`` and ``total``.
4. An unknown recipe id loads the recipe list at most every few seconds.
5. ``search_collection`` works when only the meal plan fails.
"""

from __future__ import annotations

import asyncio
from http import HTTPStatus
import time
from typing import Any
from unittest.mock import MagicMock, patch

import aiohttp
import pytest
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.eatfresh.const import IMAGE_SIGN_RENEW_BEFORE
from custom_components.eatfresh.errors import KitchenOwlAuthError, KitchenOwlError
from custom_components.eatfresh.image_proxy import DATA_SIGNED, sign_photo
from custom_components.eatfresh.kitchenowl import KitchenOwlClient

from .test_kitchenowl import BASE, TOKEN, _recipe_gets
from .test_v030 import (  # noqa: F401  (fixed_today: today is 2026-11-18)
    RECIPES,
    SENSOR,
    TODAY,
    call,
    fixed_today,
    plan,
    refresh,
)


def sensor_changes(hass: HomeAssistant) -> list[Event]:
    """Collect the state_changed events of the sensor "Today"."""
    events: list[Event] = []

    def listener(event: Event) -> None:
        if event.data["entity_id"] == SENSOR:
            events.append(event)

    hass.bus.async_listen("state_changed", listener)
    return events


# ------------------------------------------------- 1. no new state every minute


async def test_sensor_keeps_state_with_photo(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    hass_client_no_auth,
) -> None:
    """Five updates with the same plan (and a photo today) write nothing new."""
    mock_client.list_planner.return_value = plan((11, "Soup", TODAY))
    await refresh(init_integration)
    image = hass.states.get(SENSOR).attributes["recipes"][0]["image"]
    assert image and "authSig=" in image
    events = sensor_changes(hass)

    # One update a minute (in the past, so the paths stay valid): signing anew
    # would give a new path every time.
    start = time.time() - 600
    for minute in range(5):
        with patch("time.time", return_value=start + 60 * minute):
            await refresh(init_integration)
    assert events == []
    assert hass.states.get(SENSOR).attributes["recipes"][0]["image"] == image

    # The photo loads through the address of the attribute, without a header.
    client = await hass_client_no_auth()
    resp = await client.get(image)
    assert resp.status == HTTPStatus.OK
    assert await resp.read() == b"\xff\xd8photo"
    mock_client.fetch_photo.assert_awaited_with("p11.jpg")


async def test_sensor_renews_photo_before_expiry(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    hass_client_no_auth,
) -> None:
    """Shortly before the signed path runs out, a new one comes (one state)."""
    mock_client.list_planner.return_value = plan((11, "Soup", TODAY))
    await refresh(init_integration)
    old = hass.states.get(SENSOR).attributes["recipes"][0]["image"]
    cache = hass.data[DATA_SIGNED]
    # Let the stored path be nearly used up.
    nearly = time.time() + IMAGE_SIGN_RENEW_BEFORE.total_seconds() - 60
    for key, (signed, _exp) in list(cache.items()):
        cache[key] = (signed, int(nearly))
    events = sensor_changes(hass)
    with patch("homeassistant.components.http.auth.time.time", return_value=time.time() - 1):
        await refresh(init_integration)
    new = hass.states.get(SENSOR).attributes["recipes"][0]["image"]
    assert new != old
    assert len(events) == 1
    await refresh(init_integration)
    assert len(events) == 1

    client = await hass_client_no_auth()
    resp = await client.get(new)
    assert resp.status == HTTPStatus.OK


async def test_signed_path_reused_and_bounded(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The same photo keeps its path; other photos get their own."""
    first = sign_photo(hass, "a.jpg")
    assert sign_photo(hass, "a.jpg") == first
    assert sign_photo(hass, "b.jpg") != first
    # The sensor signs for the content user, which is the default outside a
    # connection, so both share the entry.
    assert sign_photo(hass, "a.jpg", content_user=True) == first


# ------------------------------------------------ 2. one shared planner fetch


async def test_parallel_get_planner_fetches_once(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """20 parallel calls with an old plan send one request to KitchenOwl."""
    release = asyncio.Event()

    async def slow_planner(_household: int) -> list[dict[str, Any]]:
        await release.wait()
        return plan((11, "Soup", TODAY))

    mock_client.list_planner.side_effect = slow_planner
    init_integration.runtime_data.coordinator.fetched_at = None
    before = mock_client.list_planner.await_count
    tasks = [
        hass.async_create_task(call(hass, "get_planner")) for _ in range(20)
    ]
    tasks.append(hass.async_create_task(call(hass, "search_collection")))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(*tasks)
    assert mock_client.list_planner.await_count == before + 1
    assert all(r["entries"][0]["recipe_id"] == 11 for r in results[:20])


async def test_parallel_get_planner_shares_the_error(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A failed shared fetch fails every waiting call; the next one tries again."""
    release = asyncio.Event()

    async def broken(_household: int) -> list[dict[str, Any]]:
        await release.wait()
        raise KitchenOwlError("500")

    mock_client.list_planner.side_effect = broken
    init_integration.runtime_data.coordinator.fetched_at = None
    before = mock_client.list_planner.await_count
    tasks = [hass.async_create_task(call(hass, "get_planner")) for _ in range(5)]
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert all(isinstance(r, HomeAssistantError) for r in results)
    assert mock_client.list_planner.await_count == before + 1

    mock_client.list_planner.side_effect = None
    mock_client.list_planner.return_value = []
    await call(hass, "get_planner")
    assert mock_client.list_planner.await_count == before + 2


# ------------------------------------------------------- 3. limit and total


async def test_search_collection_limit(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    many = [
        {**RECIPES[1], "id": 100 + n, "name": f"Bread {n}"} for n in range(60)
    ]
    mock_client.list_recipes.return_value = many
    response = await call(hass, "search_collection")
    assert len(response["recipes"]) == 50
    assert response["total"] == 60
    response = await call(hass, "search_collection", query="bread 1", limit=3)
    assert [r["name"] for r in response["recipes"]] == ["Bread 1", "Bread 10", "Bread 11"]
    assert response["total"] == 11
    response = await call(hass, "search_collection", query="nothing")
    assert response == {"recipes": [], "total": 0}


@pytest.mark.parametrize("limit", [0, 201, "many"])
async def test_search_collection_limit_invalid(
    hass: HomeAssistant, init_integration: MockConfigEntry, limit: Any
) -> None:
    with pytest.raises(vol.Invalid):
        await call(hass, "search_collection", limit=limit)


# -------------------------------------- 4. unknown id: no reload on every call


async def test_fresh_recipe_ids_at_most_every_few_seconds(mock) -> None:
    """Repeated lookups of an unknown id reuse a list of the last seconds."""
    mock.get(f"{BASE}/api/household/1/recipe", payload=[], repeat=True)
    async with aiohttp.ClientSession() as session:
        client = KitchenOwlClient(session, BASE, TOKEN)
        clock = [1000.0]
        with patch(
            "custom_components.eatfresh.kitchenowl.time.monotonic",
            side_effect=lambda: clock[0],
        ):
            for _ in range(10):
                assert 99 not in await client.recipe_ids(1)
                assert 99 not in await client.recipe_ids(1, fresh=True)
            assert _recipe_gets(mock) == 1
            clock[0] += 6
            await client.recipe_ids(1, fresh=True)
            assert _recipe_gets(mock) == 2
            # Without ``fresh`` the list is reused for longer.
            clock[0] += 60
            await client.recipe_ids(1)
            assert _recipe_gets(mock) == 2


# ---------------------------------------- 5. search without the meal plan


async def test_search_collection_without_planner(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_client.list_recipes.return_value = [dict(r) for r in RECIPES]
    mock_client.list_planner.side_effect = KitchenOwlError("500")
    init_integration.runtime_data.coordinator.fetched_at = None
    response = await call(hass, "search_collection", query="tomaten")
    assert [r["recipe_id"] for r in response["recipes"]] == [11, 13]
    assert all(r["planned_dates"] == [] for r in response["recipes"])
    assert response["total"] == 2


async def test_search_collection_planner_auth_error_still_fails(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A rejected token is never hidden: the action fails and reauth starts."""
    mock_client.list_recipes.return_value = [dict(r) for r in RECIPES]
    mock_client.list_planner.side_effect = KitchenOwlAuthError("401")
    init_integration.runtime_data.coordinator.fetched_at = None
    with pytest.raises(HomeAssistantError) as exc:
        await call(hass, "search_collection")
    assert exc.value.translation_key == "kitchenowl_auth"
