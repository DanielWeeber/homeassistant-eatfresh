"""Tests for EatFresh 0.5.0: servings (Kern A)."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import aiohttp
import pytest
import voluptuous as vol
import yaml
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eatfresh.const import CONF_DEFAULT_SERVINGS, DOMAIN
from custom_components.eatfresh.errors import KitchenOwlError
from custom_components.eatfresh.kitchenowl import (
    KitchenOwlClient,
    shopping_items,
    yields_of,
)
from custom_components.eatfresh.runtime import (
    default_servings,
    entry_servings,
    plan_item,
    scalable_start,
)

from .test_websocket_api import WS

BASE = "https://kitchenowl.example.com"
TODAY = date(2026, 11, 18)
MONDAY = date(2026, 11, 16)
SENSOR = "sensor.eatfresh_today"


def recipe(yields: Any = 4, items: list[dict[str, Any]] | None = None) -> dict:
    """Return a full KitchenOwl recipe like ``get_recipe``."""
    return {
        "id": 11,
        "name": "Soup",
        "yields": yields,
        "household_id": 1,
        "items": items
        if items is not None
        else [
            {"id": 1, "name": "Mehl", "description": "500g", "optional": False},
            {"id": 2, "name": "Tomaten", "description": "1 Dose", "optional": False},
            {"id": 3, "name": "Salz", "description": "", "optional": True},
            {"id": 4, "name": "Eier", "description": "2", "optional": False},
        ],
    }


def entry(
    rid: int, day: date | None, yields: int | None = None, base: int | None = 4
) -> dict[str, Any]:
    """Return a meal plan entry like ``list_planner`` (0.5.0)."""
    return {
        "recipe_id": rid,
        "name": f"R{rid}",
        "photo": None,
        "date": day,
        "yields": yields,
        "base": base,
    }


@pytest.fixture(autouse=True)
def fixed_today() -> Any:
    """Make today 2026-11-18, 12:00 in the time zone of Home Assistant."""

    def now() -> Any:
        return dt_util.as_local(dt_util.start_of_local_day(TODAY) + timedelta(hours=12))

    with patch("custom_components.eatfresh.runtime.dt_util.now", side_effect=now):
        yield


@pytest.fixture
async def ws(init_integration: MockConfigEntry, hass_ws_client) -> WS:
    helper = WS(await hass_ws_client())
    helper.entry = init_integration  # type: ignore[attr-defined]
    return helper


def set_default(hass: HomeAssistant, entry_: MockConfigEntry, value: int) -> None:
    hass.config_entries.async_update_entry(
        entry_, options={**entry_.options, CONF_DEFAULT_SERVINGS: value}
    )


# ----- pure helpers -----------------------------------------------------


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({}, 3),
        ({CONF_DEFAULT_SERVINGS: 5}, 5),
        ({CONF_DEFAULT_SERVINGS: 4.0}, 4),
        ({CONF_DEFAULT_SERVINGS: 0}, 1),
        ({CONF_DEFAULT_SERVINGS: 40}, 12),
        ({CONF_DEFAULT_SERVINGS: "x"}, 3),
        ({CONF_DEFAULT_SERVINGS: None}, 3),
    ],
)
def test_default_servings(options: dict, expected: int) -> None:
    assert default_servings(options) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (4, 4),
        (4.0, 4),
        (0, None),
        (-2, None),
        (None, None),
        ("4", None),
        (True, None),
        (2.5, None),
        (float("nan"), None),
    ],
)
def test_yields_of(value: Any, expected: int | None) -> None:
    assert yields_of(value) == expected


def test_scalable_start() -> None:
    assert scalable_start(4, 3) == 3
    assert scalable_start(12, 3) == 12
    assert scalable_start(99, 3) == 99
    assert scalable_start(100, 3) is None
    assert scalable_start(None, 3) is None


def test_entry_servings_and_plan_item() -> None:
    assert entry_servings(entry(11, TODAY, yields=6), 3) == 6
    assert entry_servings(entry(11, TODAY), 3) == 3
    assert entry_servings(entry(11, TODAY, base=1), 3) == 1
    assert entry_servings(entry(11, TODAY, base=None), 3) is None
    # An entry of 0.4.1 (no yields, no base) has no servings.
    assert entry_servings({"recipe_id": 11, "date": TODAY}, 3) is None
    assert plan_item(TODAY, entry(11, TODAY), 2) == {
        "date": "2026-11-18",
        "recipe_id": 11,
        "name": "R11",
        "servings": 2,
    }


def test_shopping_items_factor_one_keeps_texts() -> None:
    odd = [
        {
            "id": 1,
            "name": "Mehl",
            "description": " 500 g  (gesiebt) ",
            "optional": False,
        },
        {"id": 2, "name": "Salz", "description": None},
    ]
    for servings in (None, 4):
        items = shopping_items(recipe(4, odd), servings)
        assert [item for item, _ in items] == [
            {
                "id": 1,
                "name": "Mehl",
                "description": " 500 g  (gesiebt) ",
                "optional": False,
            },
            {"id": 2, "name": "Salz", "description": "", "optional": False},
        ]
        assert not any(scaled.scaled for _, scaled in items)
    # Unknown base: nothing scaled either.
    items = shopping_items(recipe(None, odd), 8)
    assert items[0][0]["description"] == " 500 g  (gesiebt) "


def test_shopping_items_scales() -> None:
    items = shopping_items(recipe(4), 3)
    assert [item["description"] for item, _ in items] == ["375g", "1 Dose", "", "2"]
    scaled = [s for _, s in items]
    assert scaled[1].rounded_from == "0.75"
    assert scaled[1].packages == (("Dose", 1, 0.75),)
    # Items without id or name are left out, like before.
    assert shopping_items({"yields": 4, "items": [{"name": "x"}, {"id": 1}]}, 3) == []


# ----- KitchenOwl client --------------------------------------------------


@pytest.fixture
async def client():
    async with aiohttp.ClientSession() as session:
        yield KitchenOwlClient(session, BASE, "secret-token")


def last_json(mock, method: str) -> Any:
    for (req_method, _url), calls in reversed(list(mock.requests.items())):
        if req_method == method:
            return calls[-1].kwargs.get("json")
    raise AssertionError(f"no {method}")


async def test_list_planner_yields_and_base(client, mock) -> None:
    mock.get(
        f"{BASE}/api/household/1/planner",
        payload=[
            {
                "recipe_id": 7,
                "cooking_date": 1795392000000,
                "yields": 2,
                "recipe": {"id": 7, "name": "A", "yields": 4},
            },
            {
                "recipe_id": 8,
                "cooking_date": 1795392000000,
                "yields": None,
                "recipe": {"id": 8, "name": "B", "yields": 0},
            },
            {
                "recipe_id": 9,
                "cooking_date": 1795392000000,
                "recipe": {"id": 9, "name": "C"},
            },
        ],
    )
    entries = await client.list_planner(1)
    assert [(e["yields"], e["base"]) for e in entries] == [
        (2, 4),
        (None, None),
        (None, None),
    ]


async def test_add_planner_entry_sends_yields_only_when_given(client, mock) -> None:
    url = f"{BASE}/api/household/1/planner/recipe"
    mock.post(url, payload={})
    await client.add_planner_entry(1, 7, date(2026, 11, 18), yields=3)
    assert last_json(mock, "POST") == {
        "recipe_id": 7,
        "cooking_date": 1794960000000,
        "yields": 3,
    }
    mock.post(url, payload={})
    await client.add_planner_entry(1, 7, date(2026, 11, 18))
    assert "yields" not in last_json(mock, "POST")


async def test_add_recipe_to_shoppinglist_scales(client, mock) -> None:
    mock.get(f"{BASE}/api/recipe/11", payload=recipe(4))
    mock.post(f"{BASE}/api/shoppinglist/5/recipeitems", payload={"msg": "DONE"})
    assert await client.add_recipe_to_shoppinglist(5, 11, servings=8) == 4
    assert [i["description"] for i in last_json(mock, "POST")["items"]] == [
        "1000g",
        "2 Dose",
        "",
        "4",
    ]


async def test_recipe_summary_reuses_list(client, mock) -> None:
    mock.get(
        f"{BASE}/api/household/1/recipe",
        payload=[{"id": 7, "name": "A", "yields": 4}],
    )
    assert (await client.recipe_summary(1, 7))["yields"] == 4
    assert await client.recipe_summary(1, 8) is None
    assert len(mock.requests) == 1


# ----- options ----------------------------------------------------------


async def test_options_default_servings(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    schema = result["data_schema"].schema
    key = next(k for k in schema if k == CONF_DEFAULT_SERVINGS)
    assert key.default() == 3
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"sources": ["fakea"], CONF_DEFAULT_SERVINGS: 5.0}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options[CONF_DEFAULT_SERVINGS] == 5
    await hass.async_block_till_done()
    assert init_integration.runtime_data.default_servings == 5


# ----- collection recipe --------------------------------------------------


async def test_collection_recipe_start_value(ws: WS, mock_client: MagicMock) -> None:
    mock_client.get_recipe.return_value = recipe(4)
    msg = await ws.call("eatfresh/collection/recipe", kitchenowl_id=11)
    result = msg["result"]
    assert result["portions"] == {
        "servings": 3,
        "base": 4,
        "default": 3,
        "start": 3,
        "scalable": True,
    }
    assert result["recipe"]["servings"] == 3
    ingredients = result["recipe"]["ingredients"]
    assert [i["raw"] for i in ingredients] == [
        "375g Mehl",
        "1 Dose Tomaten",
        "Salz",
        "2 Eier",
    ]
    assert [i["portion"] for i in ingredients] == [
        {"scaled": True, "rounded_from": None},
        {"scaled": True, "rounded_from": "0.75"},
        {"scaled": False, "rounded_from": None},
        {"scaled": True, "rounded_from": "1.5"},
    ]
    # KitchenOwl is never written because of servings.
    mock_client.set_recipe_tags.assert_not_awaited()
    mock_client.restore_recipe_items.assert_not_awaited()


async def test_collection_recipe_with_servings(ws: WS, mock_client: MagicMock) -> None:
    mock_client.get_recipe.return_value = recipe(4)
    msg = await ws.call("eatfresh/collection/recipe", kitchenowl_id=11, servings=4)
    result = msg["result"]
    assert result["portions"]["servings"] == 4
    assert [i["raw"] for i in result["recipe"]["ingredients"]] == [
        "500g Mehl",
        "1 Dose Tomaten",
        "Salz",
        "2 Eier",
    ]
    assert not any(i["portion"]["scaled"] for i in result["recipe"]["ingredients"])
    msg = await ws.call("eatfresh/collection/recipe", kitchenowl_id=11, servings=8)
    assert msg["result"]["recipe"]["servings"] == 8
    assert msg["result"]["recipe"]["ingredients"][0]["raw"] == "1000g Mehl"
    for bad in (0, 100, "x"):
        msg = await ws.call(
            "eatfresh/collection/recipe", kitchenowl_id=11, servings=bad
        )
        assert msg["error"]["code"] == "invalid_format"


@pytest.mark.parametrize(
    ("yields", "portions", "shown"),
    [
        (
            None,
            {
                "servings": None,
                "base": None,
                "default": 3,
                "start": None,
                "scalable": False,
            },
            None,
        ),
        (
            12,
            {"servings": 12, "base": 12, "default": 3, "start": 12, "scalable": True},
            12,
        ),
        (1, {"servings": 1, "base": 1, "default": 3, "start": 1, "scalable": True}, 1),
        (
            150,
            {
                "servings": 150,
                "base": 150,
                "default": 3,
                "start": 150,
                "scalable": False,
            },
            150,
        ),
    ],
)
async def test_collection_recipe_start_rules(
    ws: WS, mock_client: MagicMock, yields: Any, portions: dict, shown: Any
) -> None:
    mock_client.get_recipe.return_value = recipe(yields)
    # ``servings`` is ignored when the recipe is not scalable.
    msg = await ws.call("eatfresh/collection/recipe", kitchenowl_id=11, servings=6)
    result = msg["result"]
    if portions["scalable"]:
        assert result["portions"]["servings"] == 6
    else:
        assert result["portions"] == portions
        assert result["recipe"]["servings"] == shown
        assert result["recipe"]["ingredients"][0]["raw"] == "500g Mehl"
    msg = await ws.call("eatfresh/collection/recipe", kitchenowl_id=11)
    assert msg["result"]["portions"] == portions


async def test_collection_recipe_default_option(
    hass: HomeAssistant, ws: WS, mock_client: MagicMock
) -> None:
    set_default(hass, ws.entry, 2)
    await hass.async_block_till_done()
    mock_client.get_recipe.return_value = recipe(4)
    msg = await ws.call("eatfresh/collection/recipe", kitchenowl_id=11)
    assert msg["result"]["portions"]["default"] == 2
    assert msg["result"]["recipe"]["ingredients"][0]["raw"] == "250g Mehl"


async def test_collection_recipe_scales_remembered_missing(
    ws: WS, mock_client: MagicMock
) -> None:
    store = ws.entry.runtime_data.store
    # Learn the full recipe, then KitchenOwl loses an ingredient.
    mock_client.get_recipe.return_value = recipe(4)
    await ws.call("eatfresh/collection/recipe", kitchenowl_id=11)
    assert store.recipe_ingredients(11)
    full = recipe(4)
    full["items"] = [i for i in full["items"] if i["name"] != "Mehl"]
    mock_client.get_recipe.return_value = full
    msg = await ws.call("eatfresh/collection/recipe", kitchenowl_id=11, servings=2)
    result = msg["result"]
    assert result["missing"] == ["Mehl"]
    raws = [i["raw"] for i in result["recipe"]["ingredients"]]
    assert "250g Mehl" in raws
    assert len(result["recipe"]["ingredients"]) == 4


# ----- shopping list ------------------------------------------------------


async def test_shopping_list_add_servings(ws: WS, mock_client: MagicMock) -> None:
    mock_client.get_recipe.return_value = recipe(4)
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11], servings=6)
    assert msg["result"] == {"added": 3}
    kwargs = mock_client.add_recipe_to_shoppinglist.await_args.kwargs
    assert kwargs["servings"] == 6
    assert kwargs["recipe"]["id"] == 11
    # Without servings the start value counts (default 3 of base 4).
    await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11])
    assert mock_client.add_recipe_to_shoppinglist.await_args.kwargs["servings"] == 3
    # Unknown base: nothing to scale.
    mock_client.get_recipe.return_value = recipe(None)
    await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11])
    assert mock_client.add_recipe_to_shoppinglist.await_args.kwargs["servings"] is None
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11], servings=0)
    assert msg["error"]["code"] == "invalid_format"


async def test_shopping_list_add_real_client_texts(
    ws: WS, mock_client: MagicMock
) -> None:
    """The texts sent are those of ``shopping_items`` (real client method)."""
    sent: list[Any] = []

    async def add(list_id, recipe_id, recipe=None, servings=None):
        items = shopping_items(recipe, servings)
        sent.append([item["description"] for item, _ in items])
        return len(items)

    mock_client.add_recipe_to_shoppinglist.side_effect = add
    mock_client.get_recipe.return_value = recipe(4)
    await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11], servings=4)
    await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11], servings=2)
    assert sent == [["500g", "1 Dose", "", "2"], ["250g", "1 Dose", "", "1"]]


# ----- meal plan ------------------------------------------------------------


async def test_planner_week_servings(ws: WS, mock_client: MagicMock) -> None:
    mock_client.list_planner.return_value = [
        entry(11, TODAY, yields=5),
        entry(12, TODAY, base=None),
        entry(11, None),
    ]
    ws.entry.runtime_data.coordinator.fetched_at = None
    msg = await ws.call("eatfresh/planner")
    result = msg["result"]
    assert result["default_servings"] == 3
    day = next(d for d in result["days"] if d["date"] == TODAY.isoformat())
    assert [(e["kitchenowl_id"], e["servings"], e["base"]) for e in day["entries"]] == [
        (11, 5, 4),
        (12, None, None),
    ]
    assert result["unscheduled"][0]["servings"] == 3


async def test_planner_add_sends_start_value(ws: WS, mock_client: MagicMock) -> None:
    msg = await ws.call("eatfresh/planner/add", kitchenowl_id=11, date="2026-11-20")
    assert msg["success"]
    mock_client.add_planner_entry.assert_awaited_once_with(
        1, 11, date(2026, 11, 20), yields=3
    )
    mock_client.list_planner.reset_mock()
    await ws.call(
        "eatfresh/planner/add", kitchenowl_id=11, date="2026-11-21", servings=7
    )
    assert mock_client.add_planner_entry.await_args.kwargs == {"yields": 7}
    # Written and refreshed before the answer.
    assert mock_client.list_planner.await_count == 1
    # Recipe 12 has no yields: no number is sent.
    await ws.call("eatfresh/planner/add", kitchenowl_id=12, date="2026-11-21")
    assert mock_client.add_planner_entry.await_args.args == (1, 12, date(2026, 11, 21))
    assert mock_client.add_planner_entry.await_args.kwargs == {}
    # The base came from the cached recipe list, no recipe was read.
    mock_client.get_recipe.assert_not_awaited()


async def test_set_servings_removes_and_plans_again(
    ws: WS, mock_client: MagicMock
) -> None:
    mock_client.list_planner.return_value = [entry(11, TODAY, yields=3)]
    coordinator = ws.entry.runtime_data.coordinator
    with patch.object(
        coordinator, "async_refresh", wraps=coordinator.async_refresh
    ) as refresh:
        msg = await ws.call(
            "eatfresh/planner/set_servings",
            kitchenowl_id=11,
            date="2026-11-18",
            servings=5,
        )
    assert msg["result"] == {}
    mock_client.remove_planner_entry.assert_awaited_once_with(1, 11, TODAY)
    mock_client.add_planner_entry.assert_awaited_once_with(1, 11, TODAY, yields=5)
    assert refresh.await_count == 1


async def test_set_servings_same_number_changes_nothing(
    ws: WS, mock_client: MagicMock
) -> None:
    mock_client.list_planner.return_value = [entry(11, TODAY, yields=4)]
    msg = await ws.call(
        "eatfresh/planner/set_servings", kitchenowl_id=11, date="2026-11-18", servings=4
    )
    assert msg["success"]
    mock_client.remove_planner_entry.assert_not_awaited()
    mock_client.add_planner_entry.assert_not_awaited()


async def test_set_servings_restores_old_number_on_error(
    ws: WS, mock_client: MagicMock
) -> None:
    mock_client.list_planner.return_value = [entry(11, TODAY, yields=3)]
    mock_client.add_planner_entry.side_effect = [KitchenOwlError("500"), None]
    msg = await ws.call(
        "eatfresh/planner/set_servings", kitchenowl_id=11, date="2026-11-18", servings=5
    )
    assert msg["error"]["code"] == "kitchenowl_error"
    assert [c.kwargs for c in mock_client.add_planner_entry.await_args_list] == [
        {"yields": 5},
        {"yields": 3},
    ]


async def test_set_servings_restores_entry_without_number(
    ws: WS, mock_client: MagicMock
) -> None:
    mock_client.list_planner.return_value = [entry(11, TODAY)]
    mock_client.add_planner_entry.side_effect = [
        KitchenOwlError("500"),
        KitchenOwlError("x"),
    ]
    msg = await ws.call(
        "eatfresh/planner/set_servings", kitchenowl_id=11, date="2026-11-18", servings=5
    )
    # Changed after the review: both failed, so the entry is gone and the
    # error says so (it was the first error, kitchenowl_error, before).
    assert msg["error"]["code"] == "plan_entry_lost"
    assert "missing from the meal plan" in msg["error"]["message"]
    assert mock_client.add_planner_entry.await_args_list[1].kwargs == {}


async def test_set_servings_checks(ws: WS, mock_client: MagicMock) -> None:
    mock_client.list_planner.return_value = [entry(11, TODAY)]
    msg = await ws.call(
        "eatfresh/planner/set_servings", kitchenowl_id=11, date="2026-11-19", servings=5
    )
    assert msg["error"]["code"] == "not_found"
    msg = await ws.call(
        "eatfresh/planner/set_servings", kitchenowl_id=99, date="2026-11-18", servings=5
    )
    assert msg["error"]["code"] == "not_found"
    for bad in (0, 100):
        msg = await ws.call(
            "eatfresh/planner/set_servings",
            kitchenowl_id=11,
            date="2026-11-18",
            servings=bad,
        )
        assert msg["error"]["code"] == "invalid_format"
    msg = await ws.call(
        "eatfresh/planner/set_servings", kitchenowl_id=11, date="2026-11-18"
    )
    assert msg["error"]["code"] == "invalid_format"
    mock_client.remove_planner_entry.assert_not_awaited()


async def test_week_to_list_uses_servings_of_each_entry(
    ws: WS, mock_client: MagicMock
) -> None:
    mock_client.get_recipe.return_value = recipe(4)
    mock_client.list_planner.return_value = [
        entry(11, MONDAY, yields=6),
        entry(11, TODAY),
        entry(12, TODAY, base=None),
    ]
    msg = await ws.call("eatfresh/planner/shopping_list", week_start="2026-11-16")
    assert msg["result"]["recipes"] == 3
    calls = mock_client.add_recipe_to_shoppinglist.await_args_list
    assert [(c.args[1], c.kwargs["servings"]) for c in calls] == [
        (11, 6),
        (11, 3),
        # Unknown base in the plan: the start value of the recipe read (4 -> 3).
        (12, 3),
    ]
    # A later change of the servings does not touch the list.
    mock_client.add_recipe_to_shoppinglist.reset_mock()
    await ws.call(
        "eatfresh/planner/set_servings", kitchenowl_id=11, date="2026-11-18", servings=2
    )
    mock_client.add_recipe_to_shoppinglist.assert_not_awaited()


# ----- actions and sensor -------------------------------------------------


async def call(hass: HomeAssistant, action: str, **data: Any) -> Any:
    return await hass.services.async_call(
        DOMAIN, action, data, blocking=True, return_response=True
    )


async def test_actions_servings(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_client.get_recipe.return_value = recipe(4)
    await call(hass, "add_recipe_to_shopping_list", recipe_id=11, servings=8)
    assert mock_client.add_recipe_to_shoppinglist.await_args.kwargs["servings"] == 8
    await call(hass, "add_recipe_to_shopping_list", recipe_id=11)
    assert mock_client.add_recipe_to_shoppinglist.await_args.kwargs["servings"] == 3
    await call(hass, "plan_recipe", recipe_id=11, date="2026-11-20", servings=6)
    assert mock_client.add_planner_entry.await_args.kwargs == {"yields": 6}
    await call(hass, "plan_recipe", recipe_id=11, date="2026-11-21")
    assert mock_client.add_planner_entry.await_args.kwargs == {"yields": 3}
    with pytest.raises(vol.Invalid):
        await call(hass, "plan_recipe", recipe_id=11, date="2026-11-21", servings=0)


async def test_get_planner_and_sensor_servings(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_client.list_planner.return_value = [
        entry(11, TODAY, yields=5),
        entry(11, TODAY + timedelta(days=1)),
        entry(12, None, base=1),
    ]
    coordinator = init_integration.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    response = await call(hass, "get_planner")
    assert [e["servings"] for e in response["entries"]] == [5, 3]
    assert response["unscheduled"] == [{"recipe_id": 12, "name": "R12", "servings": 1}]
    state = hass.states.get(SENSOR)
    assert state.attributes["recipes"][0]["servings"] == 5
    assert [e["servings"] for e in state.attributes["week"]] == [5, 3]


# ----- after the review (0.5.0) -----------------------------------------------------


async def test_set_servings_refused_with_an_entry_without_day(
    ws: WS, mock_client: MagicMock, hass: HomeAssistant
) -> None:
    """KitchenOwl would drop the entry without a day: nothing is written."""
    mock_client.list_planner.return_value = [
        entry(11, TODAY, yields=3),
        entry(11, None),
    ]
    mock_client.list_planner.reset_mock()
    msg = await ws.call(
        "eatfresh/planner/set_servings", kitchenowl_id=11, date="2026-11-18", servings=5
    )
    assert msg["error"]["code"] == "unscheduled_entry"
    assert "without a day" in msg["error"]["message"]
    mock_client.remove_planner_entry.assert_not_awaited()
    mock_client.add_planner_entry.assert_not_awaited()
    # One read for the change, one refresh of calendar and sensor: no extra
    # read for the check (the same as a change that goes through).
    assert mock_client.list_planner.await_count == 2
    mock_client.list_planner.return_value = [entry(11, TODAY, yields=3)]
    mock_client.list_planner.reset_mock()
    await ws.call(
        "eatfresh/planner/set_servings", kitchenowl_id=11, date="2026-11-18", servings=5
    )
    assert mock_client.list_planner.await_count == 2
    hass.config.language = "de"
    mock_client.list_planner.return_value = [entry(11, TODAY, 3), entry(11, None)]
    msg = await ws.call(
        "eatfresh/planner/set_servings", kitchenowl_id=11, date="2026-11-18", servings=6
    )
    assert msg["error"]["message"].startswith("Dieses Rezept steht zusätzlich ohne Tag")


async def test_set_servings_other_recipe_without_day_is_fine(
    ws: WS, mock_client: MagicMock
) -> None:
    mock_client.list_planner.return_value = [entry(11, TODAY, 3), entry(12, None)]
    msg = await ws.call(
        "eatfresh/planner/set_servings", kitchenowl_id=11, date="2026-11-18", servings=5
    )
    assert msg["success"], msg
    mock_client.add_planner_entry.assert_awaited_once_with(1, 11, TODAY, yields=5)


async def test_set_servings_finishes_when_the_caller_is_cancelled(
    ws: WS, mock_client: MagicMock
) -> None:
    """Removed, then the caller goes: planning again still happens."""
    data = ws.entry.runtime_data
    mock_client.list_planner.return_value = [entry(11, TODAY, yields=3)]
    removed = asyncio.Event()

    async def remove(*args: Any) -> None:
        removed.set()

    async def add(*args: Any, **kwargs: Any) -> None:
        await asyncio.sleep(0.05)

    mock_client.remove_planner_entry.side_effect = remove
    mock_client.add_planner_entry.side_effect = add
    caller = asyncio.ensure_future(data.async_planner_set_servings(11, TODAY, 5))
    await removed.wait()
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert data._servings_lock.locked()  # the change itself goes on
    for _ in range(50):
        if not data._servings_tasks:
            break
        await asyncio.sleep(0.01)
    mock_client.add_planner_entry.assert_awaited_once_with(1, 11, TODAY, yields=5)
    assert not data._servings_lock.locked()
    assert not data._servings_tasks
    # The next change runs normally.
    mock_client.list_planner.return_value = [entry(11, TODAY, yields=5)]
    await data.async_planner_set_servings(11, TODAY, 2)
    assert mock_client.add_planner_entry.await_args.kwargs == {"yields": 2}


async def test_set_servings_lost_entry_releases_the_lock(
    ws: WS, mock_client: MagicMock
) -> None:
    mock_client.list_planner.return_value = [entry(11, TODAY, yields=3)]
    mock_client.add_planner_entry.side_effect = KitchenOwlError("down")
    msg = await ws.call(
        "eatfresh/planner/set_servings", kitchenowl_id=11, date="2026-11-18", servings=5
    )
    assert msg["error"]["code"] == "plan_entry_lost"
    assert mock_client.remove_planner_entry.await_count == 1
    assert [c.kwargs for c in mock_client.add_planner_entry.await_args_list] == [
        {"yields": 5},
        {"yields": 3},
    ]
    assert not ws.entry.runtime_data._servings_lock.locked()


BIG = 150  # yields of a recipe that is not scalable (above 99)


async def test_servings_dropped_when_not_scalable(
    hass: HomeAssistant, ws: WS, mock_client: MagicMock
) -> None:
    """yields 150, servings 3: every way leaves the amount texts as they are."""
    sent: list[list[str]] = []

    async def add(list_id, recipe_id, recipe=None, servings=None):
        items = shopping_items(recipe, servings)
        sent.append([item["description"] for item, _ in items])
        return len(items)

    mock_client.add_recipe_to_shoppinglist.side_effect = add
    mock_client.get_recipe.return_value = recipe(BIG)
    texts = ["500g", "1 Dose", "", "2"]
    # The panel and the action.
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11], servings=3)
    assert msg["success"], msg
    await call(hass, "add_recipe_to_shopping_list", recipe_id=11, servings=3)
    # The week: an entry with its own number below 150.
    mock_client.list_planner.return_value = [entry(11, MONDAY, yields=3, base=BIG)]
    msg = await ws.call("eatfresh/planner/shopping_list", week_start="2026-11-16")
    assert msg["success"], msg
    assert sent == [texts, texts, texts]
    # The week shows no servings for it (no counter).
    ws.entry.runtime_data.coordinator.fetched_at = None
    week = (await ws.call("eatfresh/planner"))["result"]
    day = next(d for d in week["days"] if d["date"] == MONDAY.isoformat())
    assert day["entries"][0]["servings"] is None
    # Planning drops the number.
    mock_client.recipe_summary.side_effect = None
    mock_client.recipe_summary.return_value = {"id": 11, "yields": BIG}
    await ws.call(
        "eatfresh/planner/add", kitchenowl_id=11, date="2026-11-20", servings=3
    )
    assert mock_client.add_planner_entry.await_args.kwargs == {}
    await call(hass, "plan_recipe", recipe_id=11, date="2026-11-21", servings=3)
    assert mock_client.add_planner_entry.await_args.kwargs == {}


def test_shopping_items_drops_servings_when_not_scalable() -> None:
    for base in (BIG, 100, 1000):
        items = shopping_items(recipe(base), 3)
        assert [item["description"] for item, _ in items] == ["500g", "1 Dose", "", "2"]
        assert not any(scaled.scaled for _, scaled in items)
    # 99 is still scalable.
    items = shopping_items(recipe(99), 33)
    assert items[0][0]["description"] != "500g"


@pytest.mark.parametrize("bad", [True, False, "3", 2.5, 3.0, 3.7, None])
async def test_servings_must_be_a_whole_number(
    hass: HomeAssistant, ws: WS, mock_client: MagicMock, bad: Any
) -> None:
    """WebSocket: only an int. Actions: also 3.0 (templates), never 2.5."""
    mock_client.list_planner.return_value = [entry(11, TODAY, yields=3)]
    for command, extra in (
        ("eatfresh/collection/recipe", {"kitchenowl_id": 11}),
        ("eatfresh/shopping_list/add", {"kitchenowl_ids": [11]}),
        ("eatfresh/planner/add", {"kitchenowl_id": 11, "date": "2026-11-20"}),
        ("eatfresh/planner/set_servings", {"kitchenowl_id": 11, "date": "2026-11-18"}),
    ):
        msg = await ws.call(command, **extra, servings=bad)
        assert msg["error"]["code"] == "invalid_format", (command, bad)
    mock_client.add_recipe_to_shoppinglist.assert_not_awaited()
    mock_client.add_planner_entry.assert_not_awaited()
    mock_client.remove_planner_entry.assert_not_awaited()
    for action, extra in (
        ("add_recipe_to_shopping_list", {"recipe_id": 11}),
        ("plan_recipe", {"recipe_id": 11, "date": "2026-11-20"}),
    ):
        if bad == 3.0 and not isinstance(bad, bool):
            await call(hass, action, **extra, servings=bad)
        else:
            with pytest.raises(vol.Invalid):
                await call(hass, action, **extra, servings=bad)
    if bad != 3.0 or isinstance(bad, bool):
        mock_client.add_recipe_to_shoppinglist.assert_not_awaited()
        mock_client.add_planner_entry.assert_not_awaited()


async def test_actions_take_a_whole_float_as_int(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """3.0 from a template arrives at the core as the int 3."""
    mock_client.get_recipe.return_value = recipe(4)
    await call(hass, "add_recipe_to_shopping_list", recipe_id=11, servings=6.0)
    servings = mock_client.add_recipe_to_shoppinglist.await_args.kwargs["servings"]
    assert (servings, type(servings)) == (6, int)
    await call(hass, "plan_recipe", recipe_id=11, date="2026-11-20", servings=5.0)
    yields = mock_client.add_planner_entry.await_args.kwargs["yields"]
    assert (yields, type(yields)) == (5, int)
    for bad in (0.0, 100.0):
        with pytest.raises(vol.Invalid):
            await call(
                hass, "plan_recipe", recipe_id=11, date="2026-11-20", servings=bad
            )


async def test_servings_as_yaml_gives_them(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """``servings: 4`` in a script (YAML) arrives as an int and goes through."""
    data = yaml.safe_load("recipe_id: 11\nservings: 4\n")
    assert type(data["servings"]) is int
    mock_client.get_recipe.return_value = recipe(4)
    await call(hass, "add_recipe_to_shopping_list", **data)
    assert mock_client.add_recipe_to_shoppinglist.await_args.kwargs["servings"] == 4
