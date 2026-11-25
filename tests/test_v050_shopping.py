"""EatFresh 0.5.0: the shopping list in groups, ticking off, categories.

Ticking off takes an entry off the KitchenOwl list (the item and the
recipes stay), "back on the list" adds it again with ``recipeitems``,
entries surely in the Picnic cart leave the list after 3 days, and the
category of an item is written to KitchenOwl only where the contract
allows it. HTTP and KitchenOwl are faked, no network.
"""

from __future__ import annotations

import ast
import asyncio
import re
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eatfresh import picnic
from custom_components.eatfresh.const import (
    CONF_WRITE_CATEGORIES,
    DONE_DAYS,
    MAX_CATEGORY_WRITES,
    STORAGE_KEY,
)
from custom_components.eatfresh.departments import DEPARTMENTS, OTHER
from custom_components.eatfresh.errors import KitchenOwlError
from custom_components.eatfresh.runtime import ShopGroups, category_department
from custom_components.eatfresh.store import FavoritesStore

from .test_kitchenowl import BASE, client, last_request, session  # noqa: F401
from .test_websocket_api import WS

PACKAGE = Path(__file__).resolve().parents[1] / "custom_components" / "eatfresh"

DAIRY = {"id": 9, "name": "🥛 Milchprodukte", "default_key": "dairy"}
FREEZER = {"id": 8, "name": "❄️ Tiefgekühlt", "default_key": "freezer"}
OWN = {"id": 21, "name": "Tierbedarf", "default_key": None}

RECIPE = {
    "id": 11,
    "name": "Soup",
    "yields": 4,
    "items": [
        {"id": 201, "name": "Tomaten", "description": "2 Dosen", "optional": False},
        {"id": 202, "name": "Butter", "description": "50g", "optional": False},
        {"id": 203, "name": "Salz", "description": "1 Prise", "optional": False},
    ],
}


@pytest.fixture
def rows(mock_client: MagicMock) -> list[dict[str, Any]]:
    """The shopping list as KitchenOwl has it (change it in a test)."""
    current = [
        {"id": 201, "name": "Tomaten", "description": "2 Dose", "category": None},
        {"id": 202, "name": "Butter", "description": "250g", "category": DAIRY},
        {"id": 203, "name": "Salz", "description": "", "category": None},
        {"id": 204, "name": "Seife", "description": "1", "category": OWN},
    ]
    mock_client.list_shoppinglist_items = AsyncMock(
        side_effect=lambda list_id: [dict(row) for row in current]
    )
    mock_client.list_categories = AsyncMock(
        return_value=[dict(FREEZER), dict(DAIRY), dict(OWN)]
    )
    mock_client.get_recipe = AsyncMock(return_value=RECIPE)

    async def remove(list_id: int, item_id: int) -> None:
        current[:] = [row for row in current if row["id"] != item_id]

    mock_client.remove_from_shoppinglist = AsyncMock(side_effect=remove)
    return current


@pytest.fixture
async def ws(
    init_integration: MockConfigEntry, hass_ws_client, rows: list[dict[str, Any]]
) -> WS:
    helper = WS(await hass_ws_client())
    helper.entry = init_integration  # type: ignore[attr-defined]
    return helper


def store_of(ws: WS) -> FavoritesStore:
    return ws.entry.runtime_data.store  # type: ignore[attr-defined]


def item_of(result: dict[str, Any], item_id: int) -> dict[str, Any]:
    return next(item for item in result["items"] if item["item_id"] == item_id)


def set_write(hass: HomeAssistant, ws: WS, on: bool) -> None:
    entry = ws.entry  # type: ignore[attr-defined]
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_WRITE_CATEGORIES: on}
    )


# ----- the KitchenOwl client --------------------------------------------------


async def test_client_list_rows_carry_the_category(client, mock):  # noqa: F811
    mock.get(
        f"{BASE}/api/shoppinglist/5/items",
        payload=[
            {
                "id": 1,
                "name": "Milch",
                "category_id": 9,
                "category": dict(DAIRY, ordering=3),
            },
            {"id": 2, "name": "Brot", "category_id": 7},
            {"id": 3, "name": "Salz", "category_id": None},
            {"id": 4, "name": "Seife", "category": {"id": "x", "name": "kaputt"}},
        ],
    )
    rows = await client.list_shoppinglist_items(5)
    assert [row["category"] for row in rows] == [
        DAIRY,
        {"id": 7, "name": "", "default_key": None},
        None,
        None,
    ]


async def test_client_take_off_and_put_back(client, mock):  # noqa: F811
    mock.delete(f"{BASE}/api/shoppinglist/5/item", payload={"msg": "DONE"})
    await client.remove_from_shoppinglist(5, 201)
    url, kwargs = last_request(mock, "DELETE")
    assert str(url) == f"{BASE}/api/shoppinglist/5/item"
    assert kwargs["json"] == {"item_id": 201}

    mock.post(f"{BASE}/api/shoppinglist/5/recipeitems", payload={"msg": "DONE"})
    await client.add_item_to_shoppinglist(5, 201, "Tomaten", "2 Dose")
    url, kwargs = last_request(mock, "POST")
    assert str(url) == f"{BASE}/api/shoppinglist/5/recipeitems"
    assert kwargs["json"] == {
        "items": [
            {"id": 201, "name": "Tomaten", "description": "2 Dose", "optional": False}
        ]
    }


async def test_client_get_item(client, mock):  # noqa: F811
    mock.get(
        f"{BASE}/api/item/201",
        payload={"id": 201, "name": "Tomaten", "category_id": None},
    )
    assert await client.get_item(201) == {
        "id": 201,
        "name": "Tomaten",
        "category": None,
    }
    mock.get(f"{BASE}/api/item/202", status=404, body="Requested resource not found")
    assert await client.get_item(202) is None
    mock.get(f"{BASE}/api/item/203", status=500, body="boom")
    with pytest.raises(KitchenOwlError):
        await client.get_item(203)


async def test_client_categories(client, mock):  # noqa: F811
    mock.get(
        f"{BASE}/api/household/1/category",
        payload=[
            {"id": 3, "name": "B", "default_key": "drinks", "ordering": 2},
            {"id": 1, "name": "A", "default_key": None, "ordering": 0},
            {"id": "x", "name": "kaputt"},
            {"id": 2, "name": "C", "ordering": 0},
        ],
    )
    assert await client.list_categories(1) == [
        {"id": 1, "name": "A", "default_key": None},
        {"id": 2, "name": "C", "default_key": None},
        {"id": 3, "name": "B", "default_key": "drinks"},
    ]
    mock.post(
        f"{BASE}/api/household/1/category",
        payload={"id": 11, "name": "🧂 Gewürze, Öl und Soßen", "default_key": None},
    )
    created = await client.create_category(1, "🧂 Gewürze, Öl und Soßen")
    assert created == {
        "id": 11,
        "name": "🧂 Gewürze, Öl und Soßen",
        "default_key": None,
    }
    _url, kwargs = last_request(mock, "POST")
    assert kwargs["json"] == {"name": "🧂 Gewürze, Öl und Soßen"}

    mock.post(f"{BASE}/api/item/201", payload={"id": 201}, repeat=True)
    await client.set_item_category(201, 11)
    url, kwargs = last_request(mock, "POST")
    assert str(url) == f"{BASE}/api/item/201"
    assert kwargs["json"] == {"category": {"id": 11}}
    await client.set_item_category(201, None)
    assert last_request(mock, "POST")[1]["json"] == {"category": None}


def _delete_calls() -> list[tuple[str, str]]:
    """Return (file, function) of every DELETE request in the package."""
    found: list[tuple[str, str]] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(func):
                if isinstance(node, ast.Constant) and node.value == "DELETE":
                    found.append((path.name, func.name))
    return found


def test_no_item_is_ever_deleted() -> None:
    """The code has no call that deletes an item (or a recipe, or a category).

    Deleting an item in KitchenOwl takes it out of every recipe. The only
    DELETE requests take a meal plan entry or a list entry off.
    """
    assert sorted(set(_delete_calls())) == [
        ("kitchenowl.py", "remove_from_shoppinglist"),
        ("kitchenowl.py", "remove_planner_entry"),
    ]
    source = (PACKAGE / "kitchenowl.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for func in ast.walk(tree):
        if isinstance(func, ast.AsyncFunctionDef) and func.name in (
            "remove_from_shoppinglist",
            "remove_planner_entry",
        ):
            text = ast.get_source_segment(source, func) or ""
            assert "/api/item" not in text
            assert "/api/recipe" not in text
            assert "/category" not in text
    for path in PACKAGE.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"DELETE[^\n]*/api/item", text), path.name
        assert not re.search(r"\.delete\(", text), path.name


# ----- groups -------------------------------------------------------------------


def test_category_department() -> None:
    assert category_department(None) is None
    assert category_department(DAIRY) == "dairy"
    assert category_department({"id": 4, "name": "🥬 Obst und Gemüse"}) == (
        "fruits_vegetables"
    )
    assert category_department(OWN) == "ko:21"


def test_groups_order_and_names() -> None:
    groups = ShopGroups([FREEZER, DAIRY, OWN], [], "de")
    departments = groups.departments()
    keys = [row["key"] for row in departments]
    assert keys == [*[key for key in DEPARTMENTS if key != OTHER], "ko:21", OTHER]
    names = {row["key"]: row["name"] for row in departments}
    # The name of the KitchenOwl category where there is one.
    assert names["dairy"] == "🥛 Milchprodukte"
    assert names["freezer"] == "❄️ Tiefgekühlt"
    assert names["ko:21"] == "Tierbedarf"
    assert names["spices"] == "🧂 Gewürze, Öl und Soßen"
    assert names[OTHER] == "🛒 Sonstiges"
    english = {
        row["key"]: row["name"] for row in ShopGroups(None, [], "en").departments()
    }
    assert english["dairy"] == "🥛 Dairy and eggs"


async def test_shopping_has_groups_and_done(ws: WS, hass: HomeAssistant) -> None:
    hass.config.language = "de"
    store_of(ws).async_set_shop_department("Salz", "spices")
    msg = await ws.call("eatfresh/shopping")
    assert msg["success"], msg
    result = msg["result"]
    assert result["done"] == []
    assert result["done_days"] == DONE_DAYS == 3
    assert result["departments"][-2:] == [
        {"key": "ko:21", "name": "Tierbedarf"},
        {"key": OTHER, "name": "🛒 Sonstiges"},
    ]
    assert [item_of(result, i)["department"] for i in (201, 202, 203, 204)] == [
        "fruits_vegetables",  # classify: no category in KitchenOwl
        "dairy",  # default_key of the category
        "spices",  # own choice
        "ko:21",  # foreign category: a group of its own
    ]


async def test_own_choice_wins_over_kitchenowl(ws: WS) -> None:
    store_of(ws).async_set_shop_department("butter", "refrigerated")
    store_of(ws).async_set_shop_department("Seife", "ko:999")  # gone category
    result = (await ws.call("eatfresh/shopping"))["result"]
    assert item_of(result, 202)["department"] == "refrigerated"
    assert item_of(result, 204)["department"] == "ko:21"


async def test_shopping_without_categories(
    ws: WS, mock_client: MagicMock, hass: HomeAssistant
) -> None:
    """Reading the categories fails: the list still comes."""
    hass.config.language = "de"
    mock_client.list_categories.side_effect = KitchenOwlError("down")
    msg = await ws.call("eatfresh/shopping")
    assert msg["success"], msg
    names = {row["key"]: row["name"] for row in msg["result"]["departments"]}
    assert names["dairy"] == "🥛 Milchprodukte"  # from the row of the list
    assert names["freezer"] == "❄️ Tiefkühl"  # department_name
    assert item_of(msg["result"], 202)["department"] == "dairy"


async def test_categories_are_read_seldom(
    ws: WS, mock_client: MagicMock, freezer: FrozenDateTimeFactory
) -> None:
    for _ in range(3):
        assert (await ws.call("eatfresh/shopping"))["success"]
    assert mock_client.list_categories.await_count == 1
    with patch("custom_components.eatfresh.runtime.time.monotonic", return_value=1e12):
        assert (await ws.call("eatfresh/shopping"))["success"]
    assert mock_client.list_categories.await_count == 2


# ----- ticking off ----------------------------------------------------------------


async def test_check_takes_the_entry_off(
    ws: WS, mock_client: MagicMock, rows: list[dict[str, Any]]
) -> None:
    store = store_of(ws)
    store.async_add_list_exact(201, [("Dose", 2, 1.5)])
    msg = await ws.call("eatfresh/shopping/check", item_id=201)
    assert msg["success"], msg
    assert msg["result"] == {}
    mock_client.remove_from_shoppinglist.assert_awaited_once_with(2, 201)
    assert store.list_exact(201) is None
    result = (await ws.call("eatfresh/shopping"))["result"]
    assert [item["item_id"] for item in result["items"]] == [202, 203, 204]
    assert len(result["done"]) == 1
    done = result["done"][0]
    assert {k: done[k] for k in ("item_id", "name", "description", "department")} == {
        "item_id": 201,
        "name": "Tomaten",
        "description": "2 Dose",
        "department": "fruits_vegetables",
    }
    # Back on the list through a new recipe: not in "done" at the same time.
    rows.append(
        {"id": 201, "name": "Tomaten", "description": "1 Dose", "category": None}
    )
    result = (await ws.call("eatfresh/shopping"))["result"]
    assert result["done"] == []
    assert store.shop_done(201) is not None


async def test_check_not_on_list(ws: WS, mock_client: MagicMock) -> None:
    msg = await ws.call("eatfresh/shopping/check", item_id=999)
    assert msg["error"]["code"] == "not_on_list"
    assert msg["error"]["message"] == "The entry is no longer on the shopping list."
    mock_client.remove_from_shoppinglist.assert_not_awaited()
    assert store_of(ws).shop_done(999) is None


async def test_check_error_keeps_everything(ws: WS, mock_client: MagicMock) -> None:
    store_of(ws).async_set_picnic_sent(201, "s1", 1)
    mock_client.remove_from_shoppinglist.side_effect = KitchenOwlError("down")
    msg = await ws.call("eatfresh/shopping/check", item_id=201)
    assert msg["error"]["code"] == "kitchenowl_error"
    assert store_of(ws).shop_done(201) is None
    assert store_of(ws).picnic_sent(201) is not None


@pytest.mark.parametrize("uncertain", [False, True])
async def test_check_in_the_cart_never_calls_picnic(ws: WS, uncertain: bool) -> None:
    store_of(ws).async_set_picnic_sent(201, "s1", 2, uncertain=uncertain)
    with (
        patch.object(picnic, "async_remove", AsyncMock()) as remove,
        patch.object(picnic, "async_add", AsyncMock()) as add,
        patch.object(picnic, "async_cart", AsyncMock()) as cart,
    ):
        msg = await ws.call("eatfresh/shopping/check", item_id=201)
    assert msg["success"], msg
    assert store_of(ws).picnic_sent(201) is None
    remove.assert_not_awaited()
    add.assert_not_awaited()
    cart.assert_not_awaited()


async def test_uncheck_puts_back_what_was_read(ws: WS, mock_client: MagicMock) -> None:
    await ws.call("eatfresh/shopping/check", item_id=201)
    mock_client.get_item.side_effect = lambda item_id: {
        "id": item_id,
        "name": "Tomaten",
        "category": None,
    }
    msg = await ws.call("eatfresh/shopping/uncheck", item_id=201)
    assert msg["success"], msg
    assert msg["result"] == {}
    mock_client.add_item_to_shoppinglist.assert_awaited_once_with(
        2, 201, "Tomaten", "2 Dose"
    )
    assert store_of(ws).shop_done(201) is None


async def test_uncheck_gone_item_keeps_the_entry(
    ws: WS, mock_client: MagicMock
) -> None:
    await ws.call("eatfresh/shopping/check", item_id=201)
    mock_client.get_item.side_effect = lambda item_id: None
    msg = await ws.call("eatfresh/shopping/uncheck", item_id=201)
    assert msg["error"]["code"] == "item_gone"
    assert "no longer exists" in msg["error"]["message"]
    mock_client.add_item_to_shoppinglist.assert_not_awaited()
    assert store_of(ws).shop_done(201) is not None


async def test_uncheck_message_in_german(
    ws: WS, mock_client: MagicMock, hass: HomeAssistant
) -> None:
    hass.config.language = "de"
    msg = await ws.call("eatfresh/shopping/uncheck", item_id=201)
    assert msg["error"]["code"] == "not_done"
    assert msg["error"]["message"] == "Dieser Eintrag ist nicht unter „Erledigt“."


async def test_uncheck_error_keeps_the_entry(ws: WS, mock_client: MagicMock) -> None:
    await ws.call("eatfresh/shopping/check", item_id=201)
    mock_client.add_item_to_shoppinglist.side_effect = KitchenOwlError("down")
    msg = await ws.call("eatfresh/shopping/uncheck", item_id=201)
    assert msg["error"]["code"] == "kitchenowl_error"
    assert store_of(ws).shop_done(201) is not None


async def test_done_falls_away_after_three_days(
    ws: WS, freezer: FrozenDateTimeFactory
) -> None:
    await ws.call("eatfresh/shopping/check", item_id=203)
    freezer.tick(timedelta(days=2, hours=23))
    assert len((await ws.call("eatfresh/shopping"))["result"]["done"]) == 1
    freezer.tick(timedelta(hours=2))
    assert (await ws.call("eatfresh/shopping"))["result"]["done"] == []
    msg = await ws.call("eatfresh/shopping/uncheck", item_id=203)
    assert msg["error"]["code"] == "not_done"


async def test_done_newest_first(ws: WS, freezer: FrozenDateTimeFactory) -> None:
    await ws.call("eatfresh/shopping/check", item_id=203)
    freezer.tick(timedelta(minutes=1))
    await ws.call("eatfresh/shopping/check", item_id=201)
    done = (await ws.call("eatfresh/shopping"))["result"]["done"]
    assert [row["item_id"] for row in done] == [201, 203]


@pytest.mark.parametrize("command", ["check", "uncheck"])
async def test_check_limits(ws: WS, command: str) -> None:
    for item_id in (0, -1, "x", None):
        msg = await ws.call(f"eatfresh/shopping/{command}", item_id=item_id)
        assert msg["error"]["code"] == "invalid_format"


# ----- moving into another group ------------------------------------------------


async def test_set_department_writes_existing_category(
    ws: WS, mock_client: MagicMock
) -> None:
    msg = await ws.call(
        "eatfresh/shopping/set_department",
        item_id=201,
        name="Tomaten",
        department="dairy",
    )
    assert msg["success"], msg
    mock_client.set_item_category.assert_awaited_once_with(201, 9)
    mock_client.create_category.assert_not_awaited()
    assert store_of(ws).shop_department("tomaten") == "dairy"
    result = (await ws.call("eatfresh/shopping"))["result"]
    assert item_of(result, 201)["department"] == "dairy"


async def test_set_department_creates_a_missing_category_once(
    ws: WS, mock_client: MagicMock, hass: HomeAssistant
) -> None:
    hass.config.language = "de"
    created: list[dict[str, Any]] = []

    async def create(household_id: int, name: str) -> dict[str, Any]:
        await asyncio.sleep(0.01)
        row = {"id": 50 + len(created), "name": name, "default_key": None}
        created.append(row)
        mock_client.list_categories.return_value = [
            *mock_client.list_categories.return_value,
            row,
        ]
        return row

    mock_client.create_category.side_effect = create
    # Both at the same time: sent first, answers read afterwards.
    for item_id, name in ((203, "Salz"), (201, "Pfeffer")):
        await ws.client.send_json_auto_id(
            {
                "type": "eatfresh/shopping/set_department",
                "item_id": item_id,
                "name": name,
                "department": "spices",
            }
        )
    answers = [await ws.client.receive_json() for _ in range(2)]
    assert all(answer["success"] for answer in answers), answers
    assert [row["name"] for row in created] == ["🧂 Gewürze, Öl und Soßen"]
    mock_client.create_category.assert_awaited_once_with(1, "🧂 Gewürze, Öl und Soßen")
    assert sorted(c.args for c in mock_client.set_item_category.await_args_list) == [
        (201, 50),
        (203, 50),
    ]
    names = {
        r["key"]: r["name"]
        for r in (await ws.call("eatfresh/shopping"))["result"]["departments"]
    }
    assert names["spices"] == "🧂 Gewürze, Öl und Soßen"


async def test_set_department_other_and_foreign(ws: WS, mock_client: MagicMock) -> None:
    msg = await ws.call(
        "eatfresh/shopping/set_department", item_id=202, name="Butter", department=OTHER
    )
    assert msg["success"], msg
    mock_client.set_item_category.assert_awaited_with(202, None)
    msg = await ws.call(
        "eatfresh/shopping/set_department",
        item_id=202,
        name="Butter",
        department="ko:21",
    )
    assert msg["success"], msg
    mock_client.set_item_category.assert_awaited_with(202, 21)
    msg = await ws.call(
        "eatfresh/shopping/set_department",
        item_id=202,
        name="Butter",
        department="ko:77",
    )
    assert msg["error"]["code"] == "unknown_department"
    assert store_of(ws).shop_department("Butter") == "ko:21"


@pytest.mark.parametrize("department", ["", "milk", "ko:", "ko:0", "ko:x", 5, None])
async def test_set_department_limits(ws: WS, department: Any) -> None:
    msg = await ws.call(
        "eatfresh/shopping/set_department",
        item_id=202,
        name="Butter",
        department=department,
    )
    assert msg["error"]["code"] == "invalid_format"


async def test_set_department_error_changes_nothing(
    ws: WS, mock_client: MagicMock
) -> None:
    mock_client.set_item_category.side_effect = KitchenOwlError("down")
    msg = await ws.call(
        "eatfresh/shopping/set_department",
        item_id=202,
        name="Butter",
        department="spices",
    )
    assert msg["error"]["code"] == "kitchenowl_error"
    assert store_of(ws).shop_department("Butter") is None


async def test_set_department_with_option_off_writes_nothing(
    ws: WS, mock_client: MagicMock, hass: HomeAssistant
) -> None:
    set_write(hass, ws, False)
    msg = await ws.call(
        "eatfresh/shopping/set_department",
        item_id=201,
        name="Tomaten",
        department="spices",
    )
    assert msg["success"], msg
    assert store_of(ws).shop_department("Tomaten") == "spices"
    mock_client.set_item_category.assert_not_awaited()
    mock_client.create_category.assert_not_awaited()
    mock_client.list_categories.assert_not_awaited()


# ----- categories after a transfer ------------------------------------------------


async def test_transfer_writes_missing_categories(
    ws: WS, mock_client: MagicMock, hass: HomeAssistant
) -> None:
    hass.config.language = "de"
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11])
    assert msg["success"], msg
    await hass.async_block_till_done(wait_background_tasks=True)
    # Tomaten has no category: fruits and vegetables (created). Butter has
    # one: untouched. Salz: spices (created). Seife was not in the transfer.
    assert [c.args for c in mock_client.create_category.await_args_list] == [
        (1, "🥬 Obst und Gemüse"),
        (1, "🧂 Gewürze, Öl und Soßen"),
    ]
    assert [c.args[0] for c in mock_client.set_item_category.await_args_list] == [
        201,
        203,
    ]


async def test_transfer_never_overwrites_and_skips_other(
    ws: WS, mock_client: MagicMock, hass: HomeAssistant, rows: list[dict[str, Any]]
) -> None:
    rows[0]["category"] = FREEZER  # Tomaten has one now
    rows[2]["name"] = "Wunderzeug"  # unknown: "other" is not written
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11])
    assert msg["success"], msg
    await hass.async_block_till_done(wait_background_tasks=True)
    mock_client.set_item_category.assert_not_awaited()
    mock_client.create_category.assert_not_awaited()


async def test_transfer_with_option_off_writes_nothing(
    ws: WS, mock_client: MagicMock, hass: HomeAssistant
) -> None:
    set_write(hass, ws, False)
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11])
    assert msg["success"], msg
    await hass.async_block_till_done(wait_background_tasks=True)
    mock_client.set_item_category.assert_not_awaited()
    mock_client.create_category.assert_not_awaited()
    mock_client.list_categories.assert_not_awaited()


async def test_transfer_does_not_wait_or_fail_for_categories(
    ws: WS,
    mock_client: MagicMock,
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    gate = asyncio.Event()

    async def slow(*_args: Any) -> list[dict[str, Any]]:
        await gate.wait()
        raise KitchenOwlError("down")

    mock_client.list_categories.side_effect = slow
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11])
    assert msg["success"], msg
    assert msg["result"] == {"added": 3}
    gate.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    mock_client.set_item_category.assert_not_awaited()
    assert "Writing the category of Tomaten to KitchenOwl failed" in caplog.text


async def test_transfer_writes_at_most_forty(
    ws: WS, mock_client: MagicMock, hass: HomeAssistant, rows: list[dict[str, Any]]
) -> None:
    items = [
        {"id": 1000 + n, "name": "Milch", "description": "1 l", "optional": False}
        for n in range(60)
    ]
    mock_client.get_recipe.return_value = {"id": 11, "name": "Big", "items": items}
    rows[:] = [
        {"id": item["id"], "name": "Milch", "description": "1 l", "category": None}
        for item in items
    ]
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11])
    assert msg["success"], msg
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_client.set_item_category.await_count == MAX_CATEGORY_WRITES == 40
    # Found once in the household (default_key "dairy"), never created.
    mock_client.create_category.assert_not_awaited()


async def test_background_write_ends_on_unload(
    ws: WS, mock_client: MagicMock, hass: HomeAssistant
) -> None:
    gate = asyncio.Event()

    async def hang(*_args: Any) -> list[dict[str, Any]]:
        await gate.wait()
        return []

    mock_client.list_categories.side_effect = hang
    assert (await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11]))["success"]
    data = ws.entry.runtime_data  # type: ignore[attr-defined]
    task = data._category_task
    assert task is not None and not task.done()
    assert await hass.config_entries.async_unload(ws.entry.entry_id)  # type: ignore[attr-defined]
    await hass.async_block_till_done()
    assert task.cancelled() or task.done()


# ----- entries in the Picnic cart leave the list after 3 days --------------------


async def test_cart_entries_leave_after_three_days(
    ws: WS, mock_client: MagicMock, freezer: FrozenDateTimeFactory
) -> None:
    store = store_of(ws)
    store.async_set_picnic_sent(201, "s1", 1, description="2 Dose")
    store.async_set_picnic_sent(203, "s3", 1, uncertain=True, description="")
    freezer.tick(timedelta(days=1))
    store.async_set_picnic_sent(202, "s2", 1, description="250g")
    freezer.tick(timedelta(days=2, minutes=1))
    result = (await ws.call("eatfresh/shopping"))["result"]
    # Only the sure one sent 3 days ago; the unclear one stays (mark gone).
    mock_client.remove_from_shoppinglist.assert_awaited_once_with(2, 201)
    assert [item["item_id"] for item in result["items"]] == [202, 203, 204]
    assert store.picnic_sent(201) is None
    assert store.picnic_sent(203) is None
    assert item_of(result, 203)["sent_at"] is None
    assert item_of(result, 202)["sent_at"] is not None
    # Not in "done" either: it is in the cart, not ticked off.
    assert result["done"] == []


async def test_cart_take_off_error_retries_next_time(
    ws: WS, mock_client: MagicMock, freezer: FrozenDateTimeFactory
) -> None:
    store = store_of(ws)
    store.async_set_picnic_sent(201, "s1", 1, description="2 Dose")
    store.async_set_picnic_sent(202, "s2", 1, description="250g")
    freezer.tick(timedelta(days=4))
    remove = mock_client.remove_from_shoppinglist.side_effect
    mock_client.remove_from_shoppinglist.side_effect = KitchenOwlError("down")
    msg = await ws.call("eatfresh/shopping")
    assert msg["success"], msg
    assert mock_client.remove_from_shoppinglist.await_count == 2  # each due one, once
    assert item_of(msg["result"], 201)["sent_at"] is not None
    assert store.picnic_sent(201) is not None
    mock_client.remove_from_shoppinglist.side_effect = remove
    msg = await ws.call("eatfresh/shopping")
    assert [item["item_id"] for item in msg["result"]["items"]] == [203, 204]


async def test_cart_take_off_before_a_transfer(
    ws: WS, mock_client: MagicMock, freezer: FrozenDateTimeFactory
) -> None:
    store_of(ws).async_set_picnic_sent(204, "s4", 1, description="1")
    freezer.tick(timedelta(days=3, minutes=1))
    mock_client.remove_from_shoppinglist.side_effect = KitchenOwlError("down")
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11])
    assert msg["success"], msg  # the transfer goes on
    mock_client.remove_from_shoppinglist.assert_awaited_once_with(2, 204)
    mock_client.remove_from_shoppinglist.side_effect = None
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11])
    assert msg["success"], msg
    assert mock_client.remove_from_shoppinglist.await_count == 2
    assert store_of(ws).picnic_sent(204) is None


# ----- store --------------------------------------------------------------------


async def test_store_upgrade_and_broken_rows(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory
) -> None:
    now = "2026-11-25T10:00:00+00:00"
    freezer.move_to(now)
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 4,
        "key": STORAGE_KEY,
        "data": {"favorites": {}, "hidden": {}, "picnic_sent": {}},
    }
    store = FavoritesStore(hass)
    await store.async_load()
    assert store.shop_done_entries() == []
    assert store.shop_department("Salz") is None

    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 5,
        "key": STORAGE_KEY,
        "data": {
            "shop_done": {
                "201": {
                    "name": "Tomaten",
                    "description": "2 Dose",
                    "department": "canned",
                    "at": now,
                },
                "202": {"name": "", "at": now},
                "x": {"name": "Salz", "at": now},
                "203": {"name": "Salz", "at": "kaputt"},
                "204": {"name": "Milch", "at": now},
            },
            "shop_departments": {"  Salz ": "spices", "Milch": 5, "": "dairy"},
        },
    }
    store = FavoritesStore(hass)
    await store.async_load()
    assert [item_id for item_id, _row in store.shop_done_entries()] == [201, 204]
    assert store.shop_done(204) == {
        "name": "Milch",
        "description": "",
        "department": OTHER,
        "at": now,
    }
    assert store.shop_department("salz") == "spices"
    assert store.shop_department("Milch") is None


async def test_store_saves_done_and_groups(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    store.async_set_shop_done(201, "Tomaten", "2 Dose", "canned")
    store.async_set_shop_department("Tomaten", "ko:21")
    await store.async_save_now()
    data = hass_storage[STORAGE_KEY]["data"]
    assert data["shop_done"]["201"]["description"] == "2 Dose"
    assert data["shop_departments"] == {"tomaten": "ko:21"}
    again = FavoritesStore(hass)
    await again.async_load()
    assert again.shop_done(201)["name"] == "Tomaten"
    assert again.shop_department("TOMATEN") == "ko:21"
    assert again.async_remove_shop_done(201) is True
    assert again.async_remove_shop_done(201) is False


# ----- after the review (0.5.0) -----------------------------------------------------


async def test_cart_same_text_leaves_after_three_days(
    ws: WS, mock_client: MagicMock, freezer: FrozenDateTimeFactory
) -> None:
    store_of(ws).async_set_picnic_sent(202, "s2", 1, description=" 250g ")
    freezer.tick(timedelta(days=3, minutes=1))
    result = (await ws.call("eatfresh/shopping"))["result"]
    mock_client.remove_from_shoppinglist.assert_awaited_once_with(2, 202)
    assert 202 not in [item["item_id"] for item in result["items"]]


async def test_cart_grown_entry_stays_open_with_a_hint(
    ws: WS,
    mock_client: MagicMock,
    rows: list[dict[str, Any]],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Sent as "250g", then a recipe added 100 g: open again, never taken off."""
    store = store_of(ws)
    store.async_set_picnic_sent(202, "s2", 1, description="250g")
    rows[1]["description"] = "350g"
    butter = item_of((await ws.call("eatfresh/shopping"))["result"], 202)
    assert butter["sent_at"] is None
    assert butter["sent_uncertain"] is False
    assert butter["cart_hint"] == "250g"
    assert butter["amount"] == 1
    assert store.picnic_sent(202) is not None  # the mark stays for now
    freezer.tick(timedelta(days=3, minutes=1))
    result = (await ws.call("eatfresh/shopping"))["result"]
    mock_client.remove_from_shoppinglist.assert_not_awaited()
    butter = item_of(result, 202)
    assert (butter["sent_at"], butter["cart_hint"]) == (None, None)
    assert store.picnic_sent(202) is None  # only the mark went
    # Ticking it off works like for an open entry.
    msg = await ws.call("eatfresh/shopping/check", item_id=202)
    assert msg["success"], msg


async def test_cart_grown_entry_is_not_taken_off_before_a_transfer(
    ws: WS,
    mock_client: MagicMock,
    rows: list[dict[str, Any]],
    freezer: FrozenDateTimeFactory,
) -> None:
    store_of(ws).async_set_picnic_sent(202, "s2", 1, description="250g")
    rows[1]["description"] = "300g"
    freezer.tick(timedelta(days=4))
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11])
    assert msg["success"], msg
    mock_client.remove_from_shoppinglist.assert_not_awaited()


async def test_cart_mark_of_0_4_is_never_taken_off(
    ws: WS, mock_client: MagicMock, freezer: FrozenDateTimeFactory
) -> None:
    """A mark without an amount text only loses its mark after 3 days."""
    store = store_of(ws)
    store.async_set_picnic_sent(201, "s1", 1)
    assert item_of((await ws.call("eatfresh/shopping"))["result"], 201)["sent_at"]
    freezer.tick(timedelta(days=3, minutes=1))
    result = (await ws.call("eatfresh/shopping"))["result"]
    mock_client.remove_from_shoppinglist.assert_not_awaited()
    tomatoes = item_of(result, 201)
    assert (tomatoes["sent_at"], tomatoes["cart_hint"]) == (None, None)
    assert store.picnic_sent(201) is None


async def test_cart_mark_text_survives_a_restart(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    store.async_set_picnic_sent(5, "s5", 1, description="2 Dose")
    await store.async_save_now()
    again = FavoritesStore(hass)
    await again.async_load()
    assert again.picnic_sent(5)["description"] == "2 Dose"


async def test_uncheck_twice_at_once_writes_once(
    ws: WS, mock_client: MagicMock
) -> None:
    await ws.call("eatfresh/shopping/check", item_id=201)
    data = ws.entry.runtime_data  # type: ignore[attr-defined]

    async def get_item(item_id: int) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        return {"id": item_id, "name": "Tomaten", "category": None}

    mock_client.get_item.side_effect = get_item
    results = await asyncio.gather(
        data.async_shopping_uncheck(201),
        data.async_shopping_uncheck(201),
        return_exceptions=True,
    )
    mock_client.add_item_to_shoppinglist.assert_awaited_once_with(
        2, 201, "Tomaten", "2 Dose"
    )
    assert results[0] is None
    assert getattr(results[1], "code", None) == "not_done"
    assert store_of(ws).shop_done(201) is None


async def test_uncheck_failed_write_puts_the_entry_back(
    ws: WS, mock_client: MagicMock
) -> None:
    await ws.call("eatfresh/shopping/check", item_id=201)
    store = store_of(ws)
    before = dict(store.shop_done(201))
    data = ws.entry.runtime_data  # type: ignore[attr-defined]
    mock_client.get_item.side_effect = lambda item_id: {"id": item_id, "name": "T"}
    mock_client.add_item_to_shoppinglist.side_effect = KitchenOwlError("down")
    results = await asyncio.gather(
        data.async_shopping_uncheck(201),
        data.async_shopping_uncheck(201),
        return_exceptions=True,
    )
    # Both tried (one after the other), both failed, the entry is back as it was.
    assert [type(r).__name__ for r in results] == ["KitchenOwlError"] * 2
    assert mock_client.add_item_to_shoppinglist.await_count == 2
    assert store.shop_done(201) == before


async def test_uncheck_cancelled_puts_the_entry_back(
    ws: WS, mock_client: MagicMock
) -> None:
    await ws.call("eatfresh/shopping/check", item_id=201)
    data = ws.entry.runtime_data  # type: ignore[attr-defined]
    started = asyncio.Event()

    async def get_item(item_id: int) -> dict[str, Any]:
        started.set()
        await asyncio.sleep(10)
        return {"id": item_id}

    mock_client.get_item.side_effect = get_item
    task = asyncio.ensure_future(data.async_shopping_uncheck(201))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert store_of(ws).shop_done(201) is not None
    assert not data._shop_lock.locked()


async def test_set_department_takes_the_name_from_the_list(
    ws: WS, mock_client: MagicMock
) -> None:
    msg = await ws.call(
        "eatfresh/shopping/set_department",
        item_id=201,
        name="Something else",
        department="canned",
    )
    assert msg["success"], msg
    assert store_of(ws).shop_department("Tomaten") == "canned"
    assert store_of(ws).shop_department("Something else") is None


async def test_set_department_not_on_list(ws: WS, mock_client: MagicMock) -> None:
    msg = await ws.call(
        "eatfresh/shopping/set_department",
        item_id=999,
        name="Butter",
        department="spices",
    )
    assert msg["error"]["code"] == "not_on_list"
    mock_client.set_item_category.assert_not_awaited()
    mock_client.create_category.assert_not_awaited()
    assert store_of(ws).shop_department("Butter") is None
