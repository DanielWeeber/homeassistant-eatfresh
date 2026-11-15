"""Second round of fixes for 0.2.0: findings A to F of the review."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eatfresh.categories import suggest_categories
from custom_components.eatfresh.errors import KitchenOwlError
from custom_components.eatfresh.kitchenowl import normalize_source
from custom_components.eatfresh.models import Recipe
from custom_components.eatfresh.sources.jsonld import canonical_address
from custom_components.eatfresh.store import FavoritesStore

from .test_websocket_api import WS

WEEK = "2026-11-16"


@pytest.fixture
async def ws(init_integration: MockConfigEntry, hass_ws_client) -> WS:
    """Return a connected WebSocket helper."""
    return WS(await hass_ws_client())


def plan(*entries: tuple[int, str, date | None]) -> list[dict[str, Any]]:
    return [
        {"recipe_id": rid, "name": name, "photo": None, "date": day}
        for rid, name, day in entries
    ]


# ----- A. two calls at the same time --------------------------------------


async def test_week_to_list_at_the_same_time_sends_once(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    hass_ws_client,
) -> None:
    mock_client.list_planner.return_value = plan((11, "Soup", date(2026, 11, 16)))

    async def slow_add(list_id: int, recipe_id: int) -> int:
        for _ in range(5):
            await asyncio.sleep(0)
        return 3

    mock_client.add_recipe_to_shoppinglist.side_effect = slow_add
    one = WS(await hass_ws_client())
    two = WS(await hass_ws_client())
    first, second = await asyncio.gather(
        one.call("eatfresh/planner/shopping_list", week_start=WEEK),
        two.call("eatfresh/planner/shopping_list", week_start="2026-11-18"),
    )
    results = sorted(
        (first["result"], second["result"]), key=lambda r: "already_added_at" in r
    )
    assert results[0]["added"] == 3
    assert results[1] == {
        "added": 0,
        "recipes": 0,
        "already_added_at": results[0]["at"],
    }
    assert mock_client.add_recipe_to_shoppinglist.await_count == 1


async def test_week_lock_is_released_after_an_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    data = init_integration.runtime_data
    mock_client.list_planner.return_value = plan((11, "Soup", date(2026, 11, 16)))
    mock_client.add_recipe_to_shoppinglist.side_effect = KitchenOwlError("500")
    with pytest.raises(KitchenOwlError):
        await data.async_planner_shopping_list(date(2026, 11, 16))
    assert data._week_locks == {}  # noqa: SLF001

    # Cancelled while sending: the lock is gone as well.
    started = asyncio.Event()

    async def hang(list_id: int, recipe_id: int) -> int:
        started.set()
        await asyncio.Event().wait()
        return 0

    mock_client.add_recipe_to_shoppinglist.side_effect = hang
    task = hass.async_create_task(data.async_planner_shopping_list(date(2026, 11, 16)))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert data._week_locks == {}  # noqa: SLF001

    mock_client.add_recipe_to_shoppinglist.side_effect = None
    result = await asyncio.wait_for(
        data.async_planner_shopping_list(date(2026, 11, 16)), 2
    )
    assert result["added"] == 3


# ----- B. canonical address only for the same page ------------------------

PAGE = "https://blog.example.de/linsensuppe/"


@pytest.mark.parametrize(
    "candidate",
    [
        "https://blog.example.de/",
        "https://blog.example.de",
        "/",
        "https://blog.example.de/rezepte/",
        "https://blog.example.de/linsensuppe/zutaten/",
        "https://blog.example.de/andere-suppe/",
        "https://blog.example.de/Linsensuppe/",
        "https://blog.example.de/?p=12",
    ],
)
def test_canonical_of_another_page_is_ignored(candidate: str) -> None:
    assert canonical_address(PAGE, candidate) == PAGE
    assert canonical_address(PAGE, None, {"url": candidate}) == PAGE
    assert canonical_address(PAGE, None, {"mainEntityOfPage": candidate}) == PAGE


@pytest.mark.parametrize(
    "candidate",
    [
        "https://www.blog.example.de/linsensuppe/",
        "http://blog.example.de/linsensuppe",
        "https://blog.example.de/linsensuppe/amp/",
        "https://blog.example.de/linsensuppe/?utm_source=x",
    ],
)
def test_canonical_of_the_same_page_is_taken(candidate: str) -> None:
    assert canonical_address(PAGE, candidate) == candidate


def test_bad_canonical_falls_back_to_the_next_candidate() -> None:
    good = "https://www.blog.example.de/linsensuppe/"
    assert canonical_address(PAGE, "https://blog.example.de/", {"url": good}) == good


# ----- C. a second try after a partial transfer sends only the rest ------


async def test_retry_after_partial_sends_only_the_rest(
    hass: HomeAssistant, ws: WS, mock_client: MagicMock
) -> None:
    mock_client.list_planner.return_value = plan(
        (11, "Soup", date(2026, 11, 16)),
        (12, "Bread", date(2026, 11, 17)),
        (11, "Soup", date(2026, 11, 19)),
    )
    mock_client.add_recipe_to_shoppinglist.side_effect = [3, KitchenOwlError("500")]
    msg = await ws.call("eatfresh/planner/shopping_list", week_start=WEEK)
    assert msg["error"]["translation_key"] == "shopping_list_partial"

    # The week counts as transferred: the next try asks first.
    msg = await ws.call("eatfresh/planner/shopping_list", week_start=WEEK)
    assert "already_added_at" in msg["result"]

    mock_client.add_recipe_to_shoppinglist.reset_mock(side_effect=True)
    mock_client.add_recipe_to_shoppinglist.return_value = 2
    msg = await ws.call("eatfresh/planner/shopping_list", week_start=WEEK, confirm=True)
    assert msg["result"]["recipes"] == 2
    assert msg["result"]["added"] == 4
    sent = [c.args[1] for c in mock_client.add_recipe_to_shoppinglist.await_args_list]
    assert sent == [12, 11]

    # After a full transfer, a confirmed try sends the whole week again.
    mock_client.add_recipe_to_shoppinglist.reset_mock()
    msg = await ws.call("eatfresh/planner/shopping_list", week_start=WEEK, confirm=True)
    assert msg["result"]["recipes"] == 3
    assert mock_client.add_recipe_to_shoppinglist.await_count == 3


async def test_partial_week_survives_a_restart(hass: HomeAssistant) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    store.async_set_week_list_time(date(2026, 11, 16), done=["2026-11-16:11"])
    saved = store._data_to_save()  # noqa: SLF001
    assert saved["week_list_done"] == {"2026-11-16": ["2026-11-16:11"]}
    with patch("homeassistant.helpers.storage.Store.async_load") as load:
        load.return_value = {**saved, "week_list_done": {**saved["week_list_done"], "x": 1}}
        again = FavoritesStore(hass)
        await again.async_load()
    assert again.week_list_done(date(2026, 11, 16)) == {"2026-11-16:11"}
    again.async_set_week_list_time(date(2026, 11, 16))
    assert again.week_list_done(date(2026, 11, 16)) == set()


# ----- D. tags with punctuation are no whole tag -------------------------


@pytest.mark.parametrize("tag", ["vegan?", "Vegan!", "#vegan", "vegetarisch?", "#Veggie"])
def test_tag_with_punctuation_is_not_vegan(tag: str) -> None:
    recipe = Recipe(source="jsonld", id="x", url="https://example.com/x", title="Rezept", tags=[tag])
    assert suggest_categories(recipe, "de") == []


@pytest.mark.parametrize(
    ("tag", "expected"),
    [("Vegan", ["Vegetarisch", "Vegan"]), (" vegane  Küche ", ["Vegetarisch", "Vegan"])],
)
def test_clean_whole_tag_still_counts(tag: str, expected: list[str]) -> None:
    recipe = Recipe(source="jsonld", id="x", url="https://example.com/x", title="Rezept", tags=[tag])
    assert suggest_categories(recipe, "de") == expected


# ----- E. more spellings of one address ----------------------------------


@pytest.mark.parametrize(
    "variant",
    [
        "https://example.com/k%C3%BCrbis-suppe",
        "https://example.com/k%c3%bcrbis-suppe/",
        "https://example.com/kürbis-suppe?ref=pin",
        "https://example.com/kürbis-suppe?share=1&utm_source=x",
    ],
)
def test_more_spellings_are_equal(variant: str) -> None:
    assert normalize_source(variant) == normalize_source("https://example.com/kürbis-suppe")


@pytest.mark.parametrize(
    "variant",
    [
        "https://example.com/kürbis-suppe?id=2",
        "https://example.com/kürbis-suppe?p=2",
        "https://example.com/kürbis-suppe?s=2",
        "https://example.com/kürbis-suppe?recipe=2",
        "https://example.com/a%2Fb",
    ],
)
def test_distinguishing_parameters_stay(variant: str) -> None:
    assert normalize_source(variant) != normalize_source("https://example.com/kürbis-suppe")
    assert normalize_source("https://example.com/a%2Fb") != normalize_source(
        "https://example.com/a/b"
    )


# ----- F. week_lists keeps the last transfers, not the latest weeks ------


async def test_old_week_transferred_now_is_kept(hass: HomeAssistant) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    for offset in range(30):
        store.async_set_week_list_time(date(2026, 1, 5) + timedelta(weeks=offset))
    old = date(2025, 6, 2)
    when = store.async_set_week_list_time(old)
    assert store.week_list_time(old) == when
    assert len(store._week_lists) == 26  # noqa: SLF001
