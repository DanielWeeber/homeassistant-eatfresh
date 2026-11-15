"""Tests for the WebSocket commands added in EatFresh 0.2.0."""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.util import dt as dt_util

from custom_components.eatfresh.errors import KitchenOwlAuthError, KitchenOwlError
from custom_components.eatfresh.runtime import build_week, clean_tags, week_start_of

from .conftest import RECIPE_HOST, make_recipe
from .test_websocket_api import WS


@pytest.fixture
async def ws(init_integration: MockConfigEntry, hass_ws_client) -> WS:
    """Return a connected WebSocket helper (with the config entry)."""
    helper = WS(await hass_ws_client())
    helper.entry = init_integration  # type: ignore[attr-defined]
    return helper


def expire_planner(ws: WS) -> None:
    """Make the next ``eatfresh/planner`` load the plan from KitchenOwl."""
    ws.entry.runtime_data.coordinator.fetched_at = None  # type: ignore[attr-defined]


def plan(*entries: tuple[int, str, date | None]) -> list[dict[str, Any]]:
    """Return meal plan entries like KitchenOwlClient.list_planner."""
    return [
        {"recipe_id": rid, "name": name, "photo": f"p{rid}.jpg", "date": day}
        for rid, name, day in entries
    ]


# ----- collection -------------------------------------------------------


async def test_collection_hides_and_shows(ws: WS, mock_client: MagicMock) -> None:
    msg = await ws.call("eatfresh/collection")
    recipes = msg["result"]["recipes"]
    assert [r["kitchenowl_id"] for r in recipes] == [11, 12]
    # "Suppe" is a canonical category: named in the language of HA (English).
    assert recipes[0]["tags"] == ["Soup"]
    assert recipes[0]["hidden"] is False
    assert recipes[0]["image"].startswith("/api/eatfresh/image?")

    assert (await ws.call("eatfresh/collection/hide", kitchenowl_id=11))["result"] == {}
    msg = await ws.call("eatfresh/collection")
    assert [r["kitchenowl_id"] for r in msg["result"]["recipes"]] == [12]
    msg = await ws.call("eatfresh/collection", include_hidden=True)
    assert [(r["kitchenowl_id"], r["hidden"]) for r in msg["result"]["recipes"]] == [
        (11, True),
        (12, False),
    ]

    assert (await ws.call("eatfresh/collection/unhide", kitchenowl_id=11))["success"]
    msg = await ws.call("eatfresh/collection")
    assert [r["kitchenowl_id"] for r in msg["result"]["recipes"]] == [11, 12]
    # Hiding never touches KitchenOwl.
    mock_client.set_recipe_tags.assert_not_awaited()


async def test_hide_rejects_bad_ids(ws: WS) -> None:
    msg = await ws.call("eatfresh/collection/hide", kitchenowl_id=0)
    assert msg["error"]["code"] == "invalid_format"
    msg = await ws.call("eatfresh/collection/unhide", kitchenowl_id="x")
    assert msg["error"]["code"] == "invalid_format"


async def test_hidden_favorite_is_no_favorite_until_new_heart(
    ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Hidden recipes lose the heart in search and recipe; a heart shows them."""
    msg = await ws.call("eatfresh/favorite", key="fakea:r1")
    assert msg["result"]["kitchenowl_id"] == 42
    await ws.call("eatfresh/collection/hide", kitchenowl_id=42)

    msg = await ws.call("eatfresh/recipe", key="fakea:r1")
    assert msg["result"]["favorite"] is False
    assert msg["result"]["kitchenowl_id"] is None
    msg = await ws.call("eatfresh/search", query="soup")
    assert all(hit["favorite"] is False for hit in msg["result"]["hits"])
    msg = await ws.call("eatfresh/favorites")
    assert msg["result"]["favorites"] == []

    msg = await ws.call("eatfresh/favorite", key="fakea:r1")
    assert msg["result"]["kitchenowl_id"] == 42
    assert msg["result"]["created"] is False
    assert not init_integration.runtime_data.store.is_hidden(42)
    msg = await ws.call("eatfresh/recipe", key="fakea:r1")
    assert msg["result"]["favorite"] is True
    assert mock_client.create_recipe.await_count == 1


async def test_undo_of_automatic_save_ends_in_a_consistent_state(
    ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The panel's "Undo": heart off, then hide. A later heart shows it again."""
    store = init_integration.runtime_data.store
    msg = await ws.call("eatfresh/favorite", key="fakea:r1")
    assert msg["result"] == {"kitchenowl_id": 42, "created": True, "tags": []}

    # Undo, in the order of the panel: unfavorite, then hide.
    assert (await ws.call("eatfresh/unfavorite", key="fakea:r1"))["result"] == {}
    assert (await ws.call("eatfresh/collection/hide", kitchenowl_id=42))["result"] == {}
    assert store.is_hidden(42)
    assert store.get("fakea:r1") is None
    msg = await ws.call("eatfresh/recipe", key="fakea:r1")
    assert msg["result"]["favorite"] is False
    assert msg["result"]["kitchenowl_id"] is None
    assert (await ws.call("eatfresh/favorites"))["result"]["favorites"] == []
    mock_client.delete_recipe.assert_not_called()

    # The recipe is still in KitchenOwl: a new heart finds it and shows it again.
    mock_client.find_by_source.return_value = 42
    msg = await ws.call("eatfresh/favorite", key="fakea:r1")
    assert msg["result"]["kitchenowl_id"] == 42
    assert msg["result"]["created"] is False
    assert not store.is_hidden(42)
    assert mock_client.create_recipe.await_count == 1


async def test_heart_on_hidden_recipe_found_in_kitchenowl(
    ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The heart finds a hidden recipe by source address and shows it again."""
    init_integration.runtime_data.store.async_hide(11)
    mock_client.find_by_source.return_value = 11
    msg = await ws.call("eatfresh/favorite", key="fakea:soup")
    assert msg["result"] == {"kitchenowl_id": 11, "created": False, "tags": ["Soup"]}
    assert not init_integration.runtime_data.store.is_hidden(11)


async def test_heart_sends_only_categories_as_tags(
    hass: HomeAssistant,
    ws: WS,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Keywords of the source are not sent; only canonical categories."""
    hass.config.language = "de"
    recipe = make_recipe("fakea", "r9")
    recipe.title = "Vegane Linsensuppe"
    recipe.tags = ["Hauptgericht", "Schnell", "Herbst", "Linsen"]
    init_integration.runtime_data.sources["fakea"].get.side_effect = None
    init_integration.runtime_data.sources["fakea"].get.return_value = recipe

    msg = await ws.call("eatfresh/favorite", key="fakea:r9")
    assert msg["success"]
    sent = mock_client.create_recipe.await_args.args[1]
    # "Vegane" in the title is no reason for "Vegan" (only a whole tag is).
    assert sent.tags == ["Hauptspeise", "Suppe"]
    assert sent.title == "Vegane Linsensuppe"


async def test_heart_answer_without_tags_when_listing_fails(
    ws: WS, mock_client: MagicMock
) -> None:
    mock_client.list_recipes.side_effect = KitchenOwlError("500")
    msg = await ws.call("eatfresh/favorite", key="fakea:r1")
    assert msg["result"] == {"kitchenowl_id": 42, "created": True, "tags": []}


async def test_collection_recipe(
    hass: HomeAssistant, ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The recipe comes from KitchenOwl only, never from the recipe page."""
    mock_client.get_recipe.return_value = {
        "id": 11,
        "household_id": 1,
        "name": "Soup",
        "description": "Warm and quick.\n\n1. Cut.\n2. Cook.",
        "photo": "abc123.jpg",
        "source": f"https://{RECIPE_HOST}/fakea/soup",
        "time": 25,
        "yields": 4,
        "items": [{"name": "Carrots", "description": "2"}],
        "tags": [{"name": "Suppe"}],
    }
    init_integration.runtime_data.store.async_hide(11)
    msg = await ws.call("eatfresh/collection/recipe", kitchenowl_id=11)
    assert msg["success"], msg
    result = msg["result"]
    assert result["kitchenowl_id"] == 11
    assert result["hidden"] is True
    assert result["tags"] == ["Soup"]
    recipe = result["recipe"]
    assert recipe["key"] == "kitchenowl:11"
    assert recipe["title"] == "Soup"
    assert recipe["image"].startswith("/api/eatfresh/image?")
    assert "photo=abc123.jpg" in recipe["image"]
    assert recipe["url"] == f"https://{RECIPE_HOST}/fakea/soup"
    assert [item["name"] for item in recipe["ingredients"]] == ["Carrots"]
    mock_client.get_recipe.assert_awaited_once_with(11)
    for source in init_integration.runtime_data.sources.values():
        source.get.assert_not_awaited()
        source.get_by_url.assert_not_awaited()


async def test_collection_recipe_of_other_household(
    ws: WS, mock_client: MagicMock
) -> None:
    mock_client.get_recipe.return_value = {"id": 11, "household_id": 9, "name": "X"}
    msg = await ws.call("eatfresh/collection/recipe", kitchenowl_id=11)
    assert msg["error"]["code"] == "not_found"


async def test_collection_recipe_errors(ws: WS, mock_client: MagicMock) -> None:
    mock_client.get_recipe.side_effect = KitchenOwlError("404")
    msg = await ws.call("eatfresh/collection/recipe", kitchenowl_id=11)
    assert msg["error"]["code"] == "kitchenowl_error"


async def test_set_tags(hass: HomeAssistant, ws: WS, mock_client: MagicMock) -> None:
    """Tags are cleaned; canonical names follow the language of Home Assistant."""
    hass.config.language = "de"
    msg = await ws.call(
        "eatfresh/collection/set_tags",
        kitchenowl_id=11,
        tags=["Dessert", " Schnell ", "schnell", "", "Mein  Liebling"],
    )
    assert msg["result"] == {"tags": ["Nachspeise", "Schnell", "Mein Liebling"]}
    mock_client.set_recipe_tags.assert_awaited_once_with(
        11, ["Nachspeise", "Schnell", "Mein Liebling"]
    )

    msg = await ws.call("eatfresh/collection/set_tags", kitchenowl_id=11, tags=[])
    assert msg["result"] == {"tags": []}

    msg = await ws.call(
        "eatfresh/collection/set_tags", kitchenowl_id=11, tags=["x" * 65]
    )
    assert msg["error"]["code"] == "invalid_format"


async def test_set_tags_auth_error_starts_reauth(
    hass: HomeAssistant, ws: WS, mock_client: MagicMock, init_integration: MockConfigEntry
) -> None:
    mock_client.set_recipe_tags.side_effect = KitchenOwlAuthError("401")
    msg = await ws.call("eatfresh/collection/set_tags", kitchenowl_id=11, tags=["A"])
    assert msg["error"]["code"] == "kitchenowl_auth"
    await hass.async_block_till_done()
    assert any(
        flow["context"]["source"] == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )


@pytest.mark.parametrize(
    ("language", "first"), [("de", "Vorspeise"), ("en", "Starter")]
)
async def test_tags(
    hass: HomeAssistant, ws: WS, mock_client: MagicMock, language: str, first: str
) -> None:
    hass.config.language = language
    msg = await ws.call("eatfresh/tags")
    assert msg["result"]["categories"][0] == first
    assert len(msg["result"]["categories"]) == 10
    soup = "Suppe" if language == "de" else "Soup"
    assert msg["result"]["tags"] == [soup, "Schnell"]
    mock_client.list_tags.assert_awaited_once_with(1)


def test_clean_tags_limits() -> None:
    assert clean_tags([f"t{i}" for i in range(40)]) == [f"t{i}" for i in range(30)]
    assert clean_tags(["a" * 80]) == ["a" * 64]
    assert clean_tags([None, 3, "ok"]) == ["ok"]  # type: ignore[list-item]


# ----- meal plan --------------------------------------------------------


def test_week_logic() -> None:
    assert week_start_of(date(2026, 11, 15)) == date(2026, 11, 9)  # Sunday
    assert week_start_of(date(2026, 11, 16)) == date(2026, 11, 16)  # Monday
    week = build_week(
        plan(
            (1, "A", date(2026, 11, 9)),
            (2, "B", date(2026, 11, 15)),
            (3, "C", date(2026, 11, 16)),
            (4, "D", None),
            (1, "A", date(2026, 11, 11)),
        )
        + [{"recipe_id": "bad", "date": None}],
        date(2026, 11, 12),
    )
    assert week.week_start == date(2026, 11, 9)
    assert [day for day, _ in week.days][0] == date(2026, 11, 9)
    assert [day for day, _ in week.days][-1] == date(2026, 11, 15)
    assert len(week.days) == 7
    assert [e["recipe_id"] for e in week.unscheduled] == [4]
    # Recipe 1 is planned on two days: it is cooked (and bought) twice.
    assert week.recipe_ids == [1, 1, 2]


async def test_planner_current_week(
    hass: HomeAssistant,
    ws: WS,
    mock_client: MagicMock,
) -> None:
    """The week starts on Monday in the time zone of Home Assistant."""
    await hass.config.async_set_time_zone("Europe/Berlin")
    # Sunday 23:30 UTC is already Monday in Berlin.
    moment = dt_util.parse_datetime("2026-11-15 23:30:00+00:00")
    with patch(
        "custom_components.eatfresh.runtime.dt_util.now",
        side_effect=lambda: dt_util.as_local(moment),
    ):
        await _check_current_week(ws, mock_client)


async def _check_current_week(ws: WS, mock_client: MagicMock) -> None:
    expire_planner(ws)
    mock_client.list_planner.return_value = plan(
        (11, "Soup", date(2026, 11, 16)),
        (12, "Bread", date(2026, 11, 22)),
        (13, "Old", date(2026, 11, 15)),
        (14, "Later", None),
    )
    msg = await ws.call("eatfresh/planner")
    result = msg["result"]
    assert result["week_start"] == "2026-11-16"
    assert result["today"] == "2026-11-16"
    assert [day["date"] for day in result["days"]] == [
        f"2026-11-{n}" for n in range(16, 23)
    ]
    assert result["days"][0]["entries"][0]["kitchenowl_id"] == 11
    assert result["days"][0]["entries"][0]["name"] == "Soup"
    assert "photo=p11.jpg" in result["days"][0]["entries"][0]["image"]
    assert result["days"][6]["entries"][0]["kitchenowl_id"] == 12
    assert sum(len(day["entries"]) for day in result["days"]) == 2
    assert result["unscheduled"][0]["kitchenowl_id"] == 14


async def test_planner_given_week(ws: WS, mock_client: MagicMock) -> None:
    mock_client.list_planner.return_value = plan((11, "Soup", date(2026, 12, 2)))
    msg = await ws.call("eatfresh/planner", week_start="2026-11-30")
    assert msg["result"]["week_start"] == "2026-11-30"
    # ``today`` is always the current day, whatever week was asked for.
    assert msg["result"]["today"] == dt_util.now().date().isoformat()
    assert msg["result"]["days"][2]["entries"][0]["kitchenowl_id"] == 11
    # Another day stands for its week.
    msg = await ws.call("eatfresh/planner", week_start="2026-12-03")
    assert msg["result"]["week_start"] == "2026-11-30"
    msg = await ws.call("eatfresh/planner", week_start="next week")
    assert msg["error"]["code"] == "invalid_format"


async def test_planner_updates_entities(
    hass: HomeAssistant, ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Reading the plan in the panel also refreshes calendar and sensor."""
    coordinator = init_integration.runtime_data.coordinator
    coordinator.fetched_at = None
    mock_client.list_planner.return_value = plan((11, "Soup", None))
    await ws.call("eatfresh/planner")
    assert coordinator.data == plan((11, "Soup", None))


async def test_planner_errors(ws: WS, mock_client: MagicMock) -> None:
    expire_planner(ws)
    mock_client.list_planner.side_effect = KitchenOwlError("500")
    msg = await ws.call("eatfresh/planner")
    assert msg["error"]["code"] == "kitchenowl_error"


async def test_planner_add_and_remove_refresh(
    ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    calls_before = mock_client.list_planner.await_count
    msg = await ws.call("eatfresh/planner/add", kitchenowl_id=11, date="2026-11-18")
    assert msg["result"] == {}
    mock_client.add_planner_entry.assert_awaited_once_with(1, 11, date(2026, 11, 18))
    assert mock_client.list_planner.await_count == calls_before + 1

    msg = await ws.call("eatfresh/planner/remove", kitchenowl_id=11, date="2026-11-18")
    assert msg["result"] == {}
    msg = await ws.call("eatfresh/planner/remove", kitchenowl_id=12)
    assert msg["result"] == {}
    assert mock_client.remove_planner_entry.await_args_list == [
        call(1, 11, date(2026, 11, 18)),
        call(1, 12, None),
    ]
    assert mock_client.list_planner.await_count == calls_before + 3

    msg = await ws.call("eatfresh/planner/add", kitchenowl_id=11, date="18.11.2026")
    assert msg["error"]["code"] == "invalid_format"
    msg = await ws.call("eatfresh/planner/add", kitchenowl_id=11)
    assert msg["error"]["code"] == "invalid_format"


async def test_planner_add_error_still_refreshes(
    ws: WS, mock_client: MagicMock
) -> None:
    calls_before = mock_client.list_planner.await_count
    mock_client.add_planner_entry.side_effect = KitchenOwlError("500")
    msg = await ws.call("eatfresh/planner/add", kitchenowl_id=11, date="2026-11-18")
    assert msg["error"]["code"] == "kitchenowl_error"
    assert mock_client.list_planner.await_count == calls_before + 1


async def test_planner_shopping_list(ws: WS, mock_client: MagicMock) -> None:
    """Each planned day counts: a recipe on two days goes on the list twice.

    Undated recipes and other weeks stay off.
    """
    mock_client.list_planner.return_value = plan(
        (11, "Soup", date(2026, 11, 16)),
        (12, "Bread", date(2026, 11, 17)),
        (11, "Soup", date(2026, 11, 20)),
        (13, "Other week", date(2026, 11, 24)),
        (14, "No day", None),
    )
    mock_client.add_recipe_to_shoppinglist.side_effect = [3, 5, 3]
    msg = await ws.call("eatfresh/planner/shopping_list", week_start="2026-11-16")
    result = msg["result"]
    assert (result["added"], result["recipes"]) == (11, 3)
    assert dt_util.parse_datetime(result["at"]) is not None
    assert mock_client.add_recipe_to_shoppinglist.await_args_list == [
        call(2, 11),
        call(2, 12),
        call(2, 11),
    ]


async def test_planner_shopping_list_empty_week(ws: WS, mock_client: MagicMock) -> None:
    msg = await ws.call("eatfresh/planner/shopping_list", week_start="2026-11-16")
    assert msg["result"] == {"added": 0, "recipes": 0, "at": None}
    mock_client.add_recipe_to_shoppinglist.assert_not_awaited()


async def test_planner_shopping_list_partial(ws: WS, mock_client: MagicMock) -> None:
    mock_client.list_planner.return_value = plan(
        (11, "Soup", date(2026, 11, 16)),
        (12, "Bread", date(2026, 11, 17)),
        (13, "Cake", date(2026, 11, 18)),
    )
    mock_client.list_recipes.return_value.append({"id": 13, "name": "Cake", "tags": []})
    mock_client.add_recipe_to_shoppinglist.side_effect = [3, KitchenOwlError("500")]
    msg = await ws.call("eatfresh/planner/shopping_list", week_start="2026-11-16")
    error = msg["error"]
    assert error["code"] == "kitchenowl_error"
    assert error["translation_key"] == "shopping_list_partial"
    assert error["translation_placeholders"]["added_recipes"] == "1"
    assert error["translation_placeholders"]["total"] == "3"
    assert error["translation_placeholders"]["added"] == "3"


async def test_new_commands_when_not_loaded(
    hass: HomeAssistant, init_integration: MockConfigEntry, hass_ws_client
) -> None:
    await hass.config_entries.async_unload(init_integration.entry_id)
    ws = WS(await hass_ws_client())
    for msg_type, extra in (
        ("eatfresh/planner", {}),
        ("eatfresh/tags", {}),
        ("eatfresh/collection/hide", {"kitchenowl_id": 1}),
    ):
        msg = await ws.call(msg_type, **extra)
        assert msg["error"]["code"] == "not_loaded"


async def test_recipe_to_model_is_used(ws: WS, mock_client: MagicMock) -> None:
    """The panel sees exactly what recipe_to_model makes of KitchenOwl data."""
    with patch(
        "custom_components.eatfresh.runtime.kitchenowl_module.recipe_to_model",
        return_value=make_recipe("kitchenowl", "11"),
    ) as convert:
        msg = await ws.call("eatfresh/collection/recipe", kitchenowl_id=11)
    convert.assert_called_once_with({"id": 11, "name": "Soup"})
    assert msg["result"]["recipe"]["key"] == "kitchenowl:11"
