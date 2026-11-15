"""Tests for the fixes after the review of EatFresh 0.2.0."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eatfresh.categories import suggest_categories
from custom_components.eatfresh.const import DOMAIN, STORAGE_KEY
from custom_components.eatfresh.kitchenowl import normalize_source
from custom_components.eatfresh.models import Recipe
from custom_components.eatfresh.store import FavoritesStore

from .conftest import RECIPE_HOST, make_recipe
from .test_websocket_api import WS

SOUP = f"https://{RECIPE_HOST}/fakea/soup"


@pytest.fixture
async def ws(init_integration: MockConfigEntry, hass_ws_client) -> WS:
    """Return a connected WebSocket helper."""
    return WS(await hass_ws_client())


def plan(*entries: tuple[int, str, date | None]) -> list[dict[str, Any]]:
    return [
        {"recipe_id": rid, "name": name, "photo": None, "date": day}
        for rid, name, day in entries
    ]


def no_reauth(hass: HomeAssistant) -> bool:
    return not any(
        flow["context"]["source"] == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )


# ----- 1. one recipe per page, however the link is written ---------------


@pytest.mark.parametrize(
    "variant",
    [
        "https://www.example.com/rezept/suppe/",
        "http://example.com/rezept/suppe",
        "example.com/rezept/suppe/",
        "//EXAMPLE.com/rezept/suppe",
        "https://example.com:443/rezept/suppe/",
        "https://example.com/rezept/suppe/?utm_source=pinterest&utm_medium=social",
        "https://example.com/rezept/suppe?fbclid=IwAR0abc",
        "https://example.com/rezept/suppe?gclid=1&gbraid=2&msclkid=3&mc_cid=4",
        "https://example.com/rezept/suppe/amp/",
        "https://example.com/amp/rezept/suppe/",
        "https://example.com/rezept/suppe/?amp=1",
        "https://example.com/rezept/suppe/#recipe",
        "  https://www.example.com/rezept/suppe/amp/?UTM_Campaign=x#jump  ",
    ],
)
def test_spellings_of_one_address_are_equal(variant: str) -> None:
    assert normalize_source(variant) == normalize_source("https://example.com/rezept/suppe")


def test_real_parameters_still_count() -> None:
    assert normalize_source("https://example.com/r?id=2") != normalize_source(
        "https://example.com/r?id=3"
    )
    assert normalize_source("https://example.com/r?id=2&utm_source=x&b=1") == (
        normalize_source("https://example.com/r?b=1&id=2")
    )
    assert normalize_source("https://example.com/a") != normalize_source(
        "https://example.org/a"
    )
    assert normalize_source("https://shop.example.com/a") != normalize_source(
        "https://example.com/a"
    )
    assert normalize_source("") == ""


async def test_favorite_of_0_1_0_is_found_by_other_spellings(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """A favorite saved by 0.1.0 (exact pasted text) is still found."""
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {
            "favorites": {
                "jsonld:https://www.example.com/kuerbissuppe/": {
                    "source": "jsonld",
                    "id": "https://www.example.com/kuerbissuppe/",
                    "url": "https://www.example.com/kuerbissuppe/",
                    "title": "Kürbissuppe",
                    "image": None,
                    "kitchenowl_id": 7,
                    "added_at": "2026-11-01T10:00:00+00:00",
                }
            }
        },
    }
    store = FavoritesStore(hass)
    await store.async_load()
    for url in (
        "https://www.example.com/kuerbissuppe/",
        "https://example.com/kuerbissuppe",
        "https://example.com/kuerbissuppe/?utm_source=pinterest",
        "https://www.example.com/kuerbissuppe/amp/",
    ):
        found = store.find_by_url(url)
        assert found is not None, url
        assert found[1]["kitchenowl_id"] == 7


async def test_heart_with_tracking_link_reuses_favorite(
    ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Search heart first, then the same page pasted from a phone app."""
    data = init_integration.runtime_data
    msg = await ws.call("eatfresh/favorite", key="fakea:r1")
    assert msg["result"]["created"] is True
    url = data.store.get("fakea:r1")["url"]
    pasted = url.replace("https://", "http://www.") + "/amp/?utm_source=app&fbclid=1"
    pasted_recipe = make_recipe("jsonld", pasted)
    pasted_recipe.url = pasted
    lookups = mock_client.find_by_source.await_count
    kitchenowl_id, created = await data.async_save_recipe(pasted_recipe)
    assert (kitchenowl_id, created) == (42, False)
    assert mock_client.create_recipe.await_count == 1
    assert mock_client.find_by_source.await_count == lookups


async def test_two_hearts_with_different_spellings_create_one_recipe(
    init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The lock uses the same normalization as the search in the store."""
    data = init_integration.runtime_data
    release = asyncio.Event()

    async def slow_create(household_id: int, recipe: Recipe) -> int:
        await release.wait()
        return 77

    mock_client.create_recipe.side_effect = slow_create
    first = make_recipe("fakea", "x1")
    first.url = "https://www.recipes.example.com/x?utm_source=a"
    second = make_recipe("jsonld", "https://recipes.example.com/x/")
    second.url = "https://recipes.example.com/x/"
    tasks = [
        asyncio.create_task(data.async_save_recipe(first)),
        asyncio.create_task(data.async_save_recipe(second)),
    ]
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(*tasks)
    assert sorted(results) == [(77, False), (77, True)]
    assert mock_client.create_recipe.await_count == 1


async def test_find_by_source_matches_other_spelling() -> None:
    """The client compares KitchenOwl sources with the same normalization."""
    from custom_components.eatfresh.kitchenowl import KitchenOwlClient  # noqa: PLC0415

    client = KitchenOwlClient(MagicMock(), "https://kitchenowl.example.com", "t")

    async def recipes(household_id: int) -> list[dict]:
        return [
            {"id": 5, "source": "https://www.example.com/kuerbissuppe/"},
            {"id": 6, "source": None},
        ]

    with patch.object(client, "_cached_recipes", side_effect=recipes):
        assert (
            await client.find_by_source(
                1, "http://example.com/kuerbissuppe/amp/?utm_source=pinterest#x"
            )
            == 5
        )
        assert await client.find_by_source(1, "https://example.com/other/") is None


# ----- 2. vegetarian and vegan only when the source says so --------------


def _recipe(title: str = "Rezept", tags: list[str] | None = None) -> Recipe:
    return Recipe(source="t", id="1", url="", title=title, tags=tags or [])


@pytest.mark.parametrize(
    ("title", "tags", "expected"),
    [
        ("Schnitzel", ["Vegane Alternativen"], []),
        ("Gulasch", ["vegetarisch möglich"], []),
        ("Veggie-Burger mit Bacon", [], []),
        ("Vegetarische Lasagne", [], ["Pasta"]),
        ("Linsen-Eintopf", ["Vegan oder vegetarisch?"], ["Suppe"]),
        ("Gemüsecurry", ["Nicht vegetarisch"], []),
        ("Gemüsecurry", ["Vegetarisch"], ["Vegetarisch"]),
        ("Gemüsecurry", ["vegetarische Rezepte"], ["Vegetarisch"]),
        ("Gemüsecurry", ["Veggie"], ["Vegetarisch"]),
        ("Gemüsecurry", ["VEGAN"], ["Vegetarisch", "Vegan"]),
        ("Gemüsecurry", ["Vegane Rezepte"], ["Vegetarisch", "Vegan"]),
        # The diet of the recipe data arrives as such a tag.
        ("Curry", ["Vegetarian"], ["Vegetarisch"]),
    ],
)
def test_vegetarian_and_vegan_need_a_whole_tag(
    title: str, tags: list[str], expected: list[str]
) -> None:
    assert suggest_categories(_recipe(title, tags), "de") == expected


# ----- 3. ids of other households -----------------------------------------


@pytest.mark.parametrize(
    ("command", "args"),
    [
        ("eatfresh/collection/set_tags", {"tags": ["A"]}),
        ("eatfresh/planner/add", {"date": "2026-11-18"}),
        ("eatfresh/collection/hide", {}),
        ("eatfresh/collection/recipe", {}),
    ],
)
async def test_foreign_id_changes_nothing(
    hass: HomeAssistant,
    ws: WS,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    command: str,
    args: dict[str, Any],
) -> None:
    msg = await ws.call(command, kitchenowl_id=99, **args)
    assert msg["error"]["code"] == "not_found"
    await hass.async_block_till_done()
    assert no_reauth(hass)
    mock_client.set_recipe_tags.assert_not_awaited()
    mock_client.add_planner_entry.assert_not_awaited()
    mock_client.get_recipe.assert_not_awaited()
    assert not init_integration.runtime_data.store.is_hidden(99)
    # A missing id is looked up once more in a fresh list.
    assert mock_client.recipe_ids.await_args_list[-1].kwargs == {"fresh": True}


async def test_foreign_id_on_shopping_list(
    hass: HomeAssistant, ws: WS, mock_client: MagicMock
) -> None:
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11, 99])
    assert msg["error"]["code"] == "not_found"
    mock_client.add_recipe_to_shoppinglist.assert_not_awaited()
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "add_recipe_to_shopping_list",
            {"recipe_id": 99},
            blocking=True,
            return_response=True,
        )
    assert err.value.translation_key == "not_in_collection"
    mock_client.add_recipe_to_shoppinglist.assert_not_awaited()
    await hass.async_block_till_done()
    assert no_reauth(hass)


async def test_own_ids_still_work(ws: WS, mock_client: MagicMock) -> None:
    assert (await ws.call("eatfresh/collection/hide", kitchenowl_id=11))["success"]
    msg = await ws.call("eatfresh/collection/set_tags", kitchenowl_id=12, tags=["A"])
    assert msg["result"] == {"tags": ["A"]}
    msg = await ws.call("eatfresh/planner/add", kitchenowl_id=12, date="2026-11-18")
    assert msg["success"]


async def test_recipe_added_in_kitchenowl_meanwhile_is_accepted(
    ws: WS, mock_client: MagicMock
) -> None:
    """The cached list may miss a new recipe: the fresh list has it."""

    async def ids(household_id: int, *, fresh: bool = False) -> set[int]:
        return {11, 12, 50} if fresh else {11, 12}

    mock_client.recipe_ids.side_effect = ids
    msg = await ws.call("eatfresh/planner/add", kitchenowl_id=50, date="2026-11-18")
    assert msg["success"]


async def test_unhide_of_unknown_id_is_harmless(
    ws: WS, init_integration: MockConfigEntry
) -> None:
    assert (await ws.call("eatfresh/collection/unhide", kitchenowl_id=99))["success"]
    assert init_integration.runtime_data.store.hidden_ids() == set()


# ----- 4. the ingredients of a week only once without asking -------------


async def test_week_to_list_twice_asks(
    hass: HomeAssistant,
    ws: WS,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    hass_ws_client,
) -> None:
    mock_client.list_planner.return_value = plan(
        (11, "Soup", date(2026, 11, 16)), (11, "Soup", date(2026, 11, 19))
    )
    first = await ws.call("eatfresh/planner/shopping_list", week_start="2026-11-16")
    at = first["result"]["at"]
    assert first["result"]["recipes"] == 2
    assert mock_client.add_recipe_to_shoppinglist.await_count == 2

    # A second window (another device or person) is asked as well.
    other = WS(await hass_ws_client())
    msg = await other.call("eatfresh/planner/shopping_list", week_start="2026-11-18")
    assert msg["result"] == {"added": 0, "recipes": 0, "already_added_at": at}
    assert mock_client.add_recipe_to_shoppinglist.await_count == 2
    week = await other.call("eatfresh/planner", week_start="2026-11-16")
    assert week["result"]["shopping_list_at"] == at
    week = await other.call("eatfresh/planner", week_start="2026-11-23")
    assert week["result"]["shopping_list_at"] is None

    msg = await other.call(
        "eatfresh/planner/shopping_list", week_start="2026-11-16", confirm=True
    )
    assert msg["result"]["recipes"] == 2
    assert msg["result"]["at"] >= at
    assert mock_client.add_recipe_to_shoppinglist.await_count == 4


async def test_week_list_time_is_stored(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    when = store.async_set_week_list_time(date(2026, 11, 16))
    assert store.week_list_time(date(2026, 11, 16)) == when
    await hass.async_block_till_done()
    with patch("homeassistant.helpers.storage.Store.async_load") as load:
        load.return_value = {"favorites": {}, "week_lists": {"2026-11-16": when, "x": 1}}
        again = FavoritesStore(hass)
        await again.async_load()
    assert again.week_list_time(date(2026, 11, 16)) == when
    for offset in range(40):
        store.async_set_week_list_time(date(2026, 1, 5) + timedelta(weeks=offset))
    assert len(store._week_lists) == 26  # noqa: SLF001


# ----- 5. days in sensible years only -------------------------------------


@pytest.mark.parametrize(
    ("command", "args"),
    [
        ("eatfresh/planner", {"week_start": "9999-12-31"}),
        ("eatfresh/planner", {"week_start": "1999-12-31"}),
        ("eatfresh/planner", {"week_start": "20261116"}),
        ("eatfresh/planner/add", {"kitchenowl_id": 11, "date": "0001-01-01"}),
        ("eatfresh/planner/add", {"kitchenowl_id": 11, "date": "2101-01-01"}),
        ("eatfresh/planner/remove", {"kitchenowl_id": 11, "date": "0001-01-01"}),
        ("eatfresh/planner/shopping_list", {"week_start": "9999-12-27"}),
    ],
)
async def test_days_outside_the_years_are_refused(
    ws: WS, mock_client: MagicMock, command: str, args: dict[str, Any]
) -> None:
    msg = await ws.call(command, **args)
    assert msg["error"]["code"] == "invalid_format"
    mock_client.add_planner_entry.assert_not_awaited()
    mock_client.remove_planner_entry.assert_not_awaited()


async def test_days_at_the_edges_are_accepted(ws: WS, mock_client: MagicMock) -> None:
    assert (await ws.call("eatfresh/planner", week_start="2000-01-03"))["success"]
    assert (await ws.call("eatfresh/planner", week_start="2100-12-27"))["success"]


# ----- 6. a broken store does not stop the start -------------------------


@pytest.mark.parametrize("part", ["favorites", "hidden", "week_lists"])
async def test_store_part_of_wrong_type(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
    part: str,
) -> None:
    data: dict[str, Any] = {"favorites": {}, "hidden": {}}
    data[part] = [{"kitchenowl_id": 1}]
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 2,
        "key": STORAGE_KEY,
        "data": data,
    }
    store = FavoritesStore(hass)
    with caplog.at_level(logging.WARNING):
        await store.async_load()
    assert store.items() == []
    assert store.hidden_ids() == set()
    assert f"Ignoring {part}" in caplog.text


async def test_integration_starts_with_favorites_as_list(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    init_integration: MockConfigEntry,
) -> None:
    """Set up again with a broken file: the entry loads."""
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 2,
        "key": STORAGE_KEY,
        "data": {"favorites": ["broken"], "hidden": "broken"},
    }
    assert await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.LOADED
    assert init_integration.runtime_data.store.items() == []


# ----- 7. categories: baking, and one chip per category -------------------


@pytest.mark.parametrize(
    ("title", "tags", "expected"),
    [
        ("Pfannkuchen", [], []),
        ("Pancakes mit Ahornsirup", [], []),
        ("Fluffy pancakes", ["Pancakes"], []),
        ("Butterbrot mit Schnittlauch", [], []),
        ("Kartoffelpuffer", ["Reibekuchen"], []),
        ("Crab cakes", [], []),
        ("Apfelkuchen", [], ["Backen"]),
        ("Bananenbrot", [], ["Backen"]),
        ("Cupcakes", [], ["Backen"]),
        ("Pfannkuchen", ["Frühstück"], ["Frühstück"]),
    ],
)
def test_baking_is_not_everything_with_kuchen(
    title: str, tags: list[str], expected: list[str]
) -> None:
    assert suggest_categories(_recipe(title, tags), "de") == expected


async def test_categories_of_both_languages_are_one_chip(
    hass: HomeAssistant, ws: WS, mock_client: MagicMock
) -> None:
    hass.config.language = "de"
    mock_client.list_tags.return_value = ["Suppe", "Soup", "Dessert", "Schnell"]
    mock_client.list_recipes.return_value = [
        {"id": 11, "name": "A", "tags": ["Soup", "Schnell"]},
        {"id": 12, "name": "B", "tags": ["Suppe", "Soup"]},
    ]
    msg = await ws.call("eatfresh/tags")
    assert msg["result"]["tags"] == ["Suppe", "Nachspeise", "Schnell"]
    msg = await ws.call("eatfresh/collection")
    assert [r["tags"] for r in msg["result"]["recipes"]] == [
        ["Suppe", "Schnell"],
        ["Suppe"],
    ]


# ----- 8. gaps in the tests ------------------------------------------------


async def test_heart_by_action_shows_hidden_recipe_again(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The action import_recipe goes through the saving path itself."""
    store = init_integration.runtime_data.store
    url = f"https://{RECIPE_HOST}/fakea/r7"
    await hass.services.async_call(
        DOMAIN, "import_recipe", {"url": url}, blocking=True, return_response=True
    )
    store.async_hide(42)
    result = await hass.services.async_call(
        DOMAIN, "import_recipe", {"url": url}, blocking=True, return_response=True
    )
    assert result["created"] is False
    assert not store.is_hidden(42)


async def test_heart_by_action_shows_recipe_found_in_kitchenowl(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Not a favorite yet, found by its source in KitchenOwl and hidden."""
    store = init_integration.runtime_data.store
    store.async_hide(11)
    mock_client.find_by_source.return_value = 11
    result = await hass.services.async_call(
        DOMAIN,
        "import_recipe",
        {"url": f"https://{RECIPE_HOST}/fakea/r7"},
        blocking=True,
        return_response=True,
    )
    assert result["kitchenowl_id"] == 11
    assert not store.is_hidden(11)
    mock_client.create_recipe.assert_not_awaited()


async def test_heart_by_link_shows_hidden_recipe_again(
    ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A pasted link (other spelling) of a hidden favorite shows it again."""
    data = init_integration.runtime_data
    await ws.call("eatfresh/favorite", key="fakea:r1")
    url = data.store.get("fakea:r1")["url"]
    data.store.async_hide(42)
    pasted = f"{url}/?utm_source=app"
    data.sources["jsonld"].get.side_effect = None
    recipe = make_recipe("jsonld", pasted)
    recipe.url = pasted
    data.sources["jsonld"].get.return_value = recipe
    msg = await ws.call("eatfresh/favorite", key=f"jsonld:{pasted}")
    assert msg["result"]["kitchenowl_id"] == 42
    assert msg["result"]["created"] is False
    assert not data.store.is_hidden(42)
    assert mock_client.create_recipe.await_count == 1


async def test_tag_count_is_limited_in_the_schema(
    ws: WS, mock_client: MagicMock
) -> None:
    tags = [f"t{i}" for i in range(30)]
    msg = await ws.call("eatfresh/collection/set_tags", kitchenowl_id=11, tags=tags)
    assert msg["success"]
    msg = await ws.call(
        "eatfresh/collection/set_tags", kitchenowl_id=11, tags=[*tags, "t30"]
    )
    assert msg["error"]["code"] == "invalid_format"
    msg = await ws.call(
        "eatfresh/collection/set_tags", kitchenowl_id=11, tags=["x" * 64]
    )
    assert msg["success"]
    msg = await ws.call(
        "eatfresh/collection/set_tags", kitchenowl_id=11, tags=["x" * 65]
    )
    assert msg["error"]["code"] == "invalid_format"
    assert mock_client.set_recipe_tags.await_count == 2


# ----- 9. the current week comes from the coordinator for 60 s ------------


async def test_current_week_reuses_fresh_plan(
    ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    coordinator = init_integration.runtime_data.coordinator
    today = dt_util.now().date()
    mock_client.list_planner.return_value = plan((11, "Soup", today))
    await coordinator.async_refresh()
    fetches = mock_client.list_planner.await_count

    for _ in range(3):
        msg = await ws.call("eatfresh/planner")
        assert any(day["entries"] for day in msg["result"]["days"])
    assert mock_client.list_planner.await_count == fetches

    # Another week is always loaded.
    await ws.call("eatfresh/planner", week_start=(today + timedelta(days=7)).isoformat())
    assert mock_client.list_planner.await_count == fetches + 1

    # A change through EatFresh refreshes at once; the next read uses it.
    mock_client.list_planner.return_value = plan((11, "Soup", today), (12, "Bread", today))
    await ws.call("eatfresh/planner/add", kitchenowl_id=12, date=today.isoformat())
    fetches = mock_client.list_planner.await_count
    msg = await ws.call("eatfresh/planner")
    names = [e["name"] for day in msg["result"]["days"] for e in day["entries"]]
    assert names == ["Soup", "Bread"]
    assert mock_client.list_planner.await_count == fetches

    # Older than 60 s: loaded again.
    later = coordinator.fetched_at + 61
    with patch("custom_components.eatfresh.coordinator.time.monotonic", return_value=later):
        await ws.call("eatfresh/planner")
    assert mock_client.list_planner.await_count == fetches + 1


async def test_week_to_list_never_uses_the_cache(
    ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    await init_integration.runtime_data.coordinator.async_refresh()
    fetches = mock_client.list_planner.await_count
    await ws.call("eatfresh/planner/shopping_list")
    assert mock_client.list_planner.await_count == fetches + 1


async def test_failed_refresh_is_no_cache(
    ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    from custom_components.eatfresh.errors import KitchenOwlError  # noqa: PLC0415

    coordinator = init_integration.runtime_data.coordinator
    mock_client.list_planner.side_effect = KitchenOwlError("500")
    await coordinator.async_refresh()
    msg = await ws.call("eatfresh/planner")
    assert msg["error"]["code"] == "kitchenowl_error"


# ----- 10. days planned in the KitchenOwl app ------------------------------


def app_cooking_date(day: date) -> int:
    """What the KitchenOwl app 0.8.1 sends for a day picked in its calendar.

    ``DateTime.utc(picked.year, picked.month, picked.day)
    .millisecondsSinceEpoch`` (``pages/recipe_page.dart`` and
    ``pages/household_page/planner.dart``): midnight UTC of the local day.
    """
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)


@pytest.mark.parametrize(
    "day",
    [
        date(2026, 3, 28),  # day before the change to summer time
        date(2026, 3, 29),  # change to summer time in Germany
        date(2026, 7, 15),  # summer time
        date(2026, 10, 25),  # change back to winter time
        date(2026, 11, 16),  # winter time
    ],
)
async def test_day_from_the_app_is_the_same_day(day: date) -> None:
    from custom_components.eatfresh.kitchenowl import (  # noqa: PLC0415
        KitchenOwlClient,
        _day_to_ms,
    )

    client = KitchenOwlClient(MagicMock(), "https://kitchenowl.example.com", "t")
    answer = [
        {"recipe_id": 1, "cooking_date": app_cooking_date(day), "recipe": {"name": "A"}}
    ]
    with patch.object(client, "_request", return_value=answer):
        entries = await client.list_planner(1)
    assert entries[0]["date"] == day
    # EatFresh writes exactly what the app writes.
    assert _day_to_ms(day) == app_cooking_date(day)
