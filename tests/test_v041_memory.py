"""Tests for EatFresh 0.4.1: the memory of the ingredients of a recipe.

An item deleted in KitchenOwl must not disappear from EatFresh: the store
remembers the ingredients of each recipe, the collection shows the missing
ones, and they can be added back to KitchenOwl (only ever added).
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiohttp
from aioresponses import CallbackResult, aioresponses
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import EVENT_HOMEASSISTANT_FINAL_WRITE
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eatfresh.const import STORAGE_KEY
from custom_components.eatfresh.errors import KitchenOwlError, RecipeNotFound
from custom_components.eatfresh.kitchenowl import (
    KitchenOwlClient,
    created_item_rows,
    item_rows,
    merge_items,
)
from custom_components.eatfresh.models import Ingredient
from custom_components.eatfresh.runtime import EatFreshData, ShoppingListPartial
from custom_components.eatfresh.store import FavoritesStore

from .conftest import make_recipe

BASE = "https://kitchenowl.example.com"
TOKEN = "secret-token"


def row(item_id: int | None, name: str, description: str = "", optional: bool = False) -> dict:
    return {"id": item_id, "name": name, "description": description, "optional": optional}


def requests_of(mock: aioresponses, method: str, path: str) -> list[Any]:
    """Return the calls of one method and path."""
    return [
        call
        for (req_method, url), calls in mock.requests.items()
        if req_method == method and url.path == path
        for call in calls
    ]


# ----------------------------------------------------------------- merge_items


def test_merge_first_sight_remembers_current() -> None:
    current = [row(1, "Mehl", "500 g"), row(2, "Salz")]
    memory, missing = merge_items(None, current)
    assert memory == current
    assert missing == []
    assert memory[0] is not current[0]


def test_merge_empty_recipe() -> None:
    assert merge_items(None, []) == ([], [])
    assert merge_items([], []) == ([], [])
    # Every remembered entry is missing when KitchenOwl has none any more.
    memory, missing = merge_items([row(1, "Mehl", "500 g")], [])
    assert memory == [row(None, "Mehl", "500 g")]
    assert missing == [row(None, "Mehl", "500 g")]


def test_merge_match_by_id_takes_kitchenowl_values() -> None:
    """A renamed item keeps its place and takes name and amount from KitchenOwl."""
    memory = [row(1, "Mehl", "500 g"), row(2, "Zucker", "1 EL")]
    current = [row(2, "Rohrzucker", "2 EL", True), row(1, "Weizenmehl", "400 g")]
    merged, missing = merge_items(memory, current)
    assert merged == [row(1, "Weizenmehl", "400 g"), row(2, "Rohrzucker", "2 EL", True)]
    assert missing == []


def test_merge_match_by_name_any_case_and_spaces() -> None:
    memory = [row(None, "rote  Linsen", "175 g"), row(None, "SALZ")]
    current = [row(7, "Salz", "1 Prise"), row(8, " Rote Linsen ", "200 g")]
    merged, missing = merge_items(memory, current)
    assert merged == [row(8, " Rote Linsen ", "200 g"), row(7, "Salz", "1 Prise")]
    assert missing == []


def test_merge_id_goes_before_name() -> None:
    """A name never takes the item another entry matches by id."""
    memory = [row(None, "Salz"), row(5, "Meersalz")]
    current = [row(5, "Salz")]
    merged, missing = merge_items(memory, current)
    # The entry "Salz" without a match has the name of a current item: it is
    # not missing (restoring could never resolve it) and goes.
    assert merged == [row(5, "Salz")]
    assert missing == []


def test_merge_new_item_in_kitchenowl_comes_last() -> None:
    memory = [row(1, "Mehl")]
    merged, missing = merge_items(memory, [row(3, "Eier", "2"), row(1, "Mehl")])
    assert merged == [row(1, "Mehl"), row(3, "Eier", "2")]
    assert missing == []


def test_merge_deleted_item_stays_and_is_missing() -> None:
    """The entry keeps its place; its id is dropped (KitchenOwl may reuse it)."""
    memory = [row(1, "Mehl", "500 g"), row(2, "Butter", "1 g", True), row(3, "Salz")]
    merged, missing = merge_items(memory, [row(1, "Mehl", "500 g"), row(3, "Salz")])
    assert merged == [row(1, "Mehl", "500 g"), row(None, "Butter", "1 g", True), row(3, "Salz")]
    assert missing == [row(None, "Butter", "1 g", True)]
    # Seen again: still missing, nothing changes.
    assert merge_items(merged, [row(1, "Mehl", "500 g"), row(3, "Salz")]) == (
        merged,
        missing,
    )


def test_merge_deleted_and_created_again_with_new_id() -> None:
    memory = [row(1, "Mehl"), row(2, "Butter", "100 g")]
    merged, missing = merge_items(memory, [row(1, "Mehl"), row(9, "Butter", "100 g")])
    assert merged == [row(1, "Mehl"), row(9, "Butter", "100 g")]
    assert missing == []


def test_merge_does_not_change_its_input() -> None:
    memory = [row(1, "Mehl")]
    current = [row(1, "Weizenmehl")]
    merge_items(memory, current)
    assert memory == [row(1, "Mehl")]
    assert current == [row(1, "Weizenmehl")]


def test_item_rows_and_created_rows() -> None:
    assert item_rows("x") == []
    assert item_rows(
        [
            {"id": 1, "name": " Mehl ", "description": "500 g", "optional": False},
            {"id": True, "name": "Salz", "description": None, "optional": 1},
            {"id": 3, "name": ""},
            "broken",
        ]
    ) == [row(1, "Mehl", "500 g"), row(None, "Salz")]
    long_name = "x" * 140
    rows = created_item_rows(
        [
            Ingredient(name="flour", amount=250, unit="g"),
            Ingredient(name="Flour", amount=50, unit="g"),
            Ingredient(name=long_name),
        ]
    )
    assert rows == [row(None, "flour", "250g, 50g"), row(None, "x" * 128)]


# ----------------------------------------------------------------------- store


async def test_store_migrates_13_to_14(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    old = {
        "favorites": {},
        "hidden": {"12": "2026-11-02T10:00:00+00:00"},
        "picnic_map": {},
        "picnic_skip": ["salz"],
        "picnic_sent": {},
    }
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 3,
        "key": STORAGE_KEY,
        "data": old,
    }
    store = FavoritesStore(hass)
    await store.async_load()
    assert store.recipe_ingredients(11) is None
    store.async_learn_ingredients(11, [row(1, "Mehl", "500 g")])
    hass.bus.async_fire(EVENT_HOMEASSISTANT_FINAL_WRITE)
    await hass.async_block_till_done()
    saved = hass_storage[STORAGE_KEY]
    assert saved["minor_version"] == 5  # 0.5.0
    for key, value in old.items():
        assert saved["data"][key] == value
    assert saved["data"]["ingredients"] == {"11": [row(1, "Mehl", "500 g")]}

    again = FavoritesStore(hass)
    await again.async_load()
    assert again.recipe_ingredients(11) == [row(1, "Mehl", "500 g")]


async def test_store_ignores_broken_ingredients(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 4,
        "key": STORAGE_KEY,
        "data": {
            "ingredients": {
                "11": [
                    {"id": 1, "name": "Mehl", "description": "500 g", "optional": False},
                    {"id": "2", "name": "Salz", "description": 3, "optional": "yes"},
                    {"id": 3, "name": "   "},
                    {"name": None},
                    "broken",
                ],
                "x": [{"id": 1, "name": "Mehl"}],
                "12": {"name": "Mehl"},
            }
        },
    }
    store = FavoritesStore(hass)
    await store.async_load()
    assert store.recipe_ingredients(11) == [row(1, "Mehl", "500 g"), row(None, "Salz")]
    assert store.recipe_ingredients(12) is None

    hass_storage[STORAGE_KEY]["data"]["ingredients"] = ["11"]
    store = FavoritesStore(hass)
    await store.async_load()
    assert store.recipe_ingredients(11) is None


async def test_store_learn_set_and_prune(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    assert store.async_learn_ingredients(11, [row(1, "Mehl"), row(2, "Salz")]) == []
    assert store.async_learn_ingredients(11, [row(1, "Mehl")]) == [row(None, "Salz")]
    store.async_set_ingredients(12, [row(None, "Eier", "2")])
    store.async_prune_ingredients([12, 99])
    # Not in the list, but seen today: kept.
    assert store.recipe_ingredients(11) is not None
    freezer.tick(timedelta(days=31))
    store.async_prune_ingredients([12, 99])
    assert store.recipe_ingredients(11) is None
    assert store.recipe_ingredients(12) == [row(None, "Eier", "2")]
    # A copy: changing it does not change the store.
    store.recipe_ingredients(12)[0]["name"] = "Milch"
    assert store.recipe_ingredients(12)[0]["name"] == "Eier"


# ---------------------------------------------------------------------- client


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as sess:
        yield sess


@pytest.fixture
def client(session) -> KitchenOwlClient:
    return KitchenOwlClient(session, BASE, TOKEN)


RECIPE_7 = {
    "id": 7,
    "household_id": 1,
    "name": "Cake",
    "items": [
        {"id": 11, "name": "Mehl", "description": "250 g", "optional": False, "icon": "x"},
        {"id": 12, "name": "Salz", "description": None, "optional": True},
        {"id": 13, "name": "Milch", "description": "", "optional": False},
    ],
}


async def test_listeners_get_lists_and_recipes(client, mock) -> None:
    lists: list[tuple[int, list[dict]]] = []
    recipes: list[dict] = []
    client.on_recipe_list = lambda household, found: lists.append((household, found))
    client.on_recipe = recipes.append
    mock.get(
        f"{BASE}/api/household/1/recipe",
        payload=[{"id": 7, "name": "Cake", "items": RECIPE_7["items"]}],
    )
    mock.get(f"{BASE}/api/recipe/7", payload=RECIPE_7)
    listed = await client.list_recipes(1)
    assert listed[0]["item_rows"] == [
        row(11, "Mehl", "250 g"),
        row(12, "Salz", "", True),
        row(13, "Milch"),
    ]
    assert lists == [(1, listed)]
    # The cached copy is not the one handed out.
    lists[0][1][0]["item_rows"].clear()
    assert (await client._cached_recipes(1))[0]["item_rows"]
    assert await client.get_recipe(7) == RECIPE_7
    assert recipes == [RECIPE_7]


async def test_failing_listener_does_not_break_the_request(client, mock) -> None:
    client.on_recipe = MagicMock(side_effect=ValueError("bug"))
    mock.get(f"{BASE}/api/recipe/7", payload=RECIPE_7)
    assert await client.get_recipe(7) == RECIPE_7


async def test_restore_keeps_every_item_and_adds_missing(client, mock) -> None:
    """The body has each item of the recipe unchanged, then the missing ones."""
    mock.get(f"{BASE}/api/recipe/7", payload=RECIPE_7)
    answer = {
        **RECIPE_7,
        "items": [
            *RECIPE_7["items"],
            {"id": 20, "name": "Butter", "description": "100 g", "optional": False},
            {"id": 21, "name": "Eier", "description": "2", "optional": True},
        ],
    }
    mock.post(f"{BASE}/api/recipe/7", payload=answer)
    memory = [
        row(11, "Mehl", "250 g"),
        row(None, "Butter", "100 g"),
        row(12, "Salz", "", True),
        row(None, "eier", "2", True),
        row(None, "MILCH", "1 l"),  # present by name: not sent again
    ]
    result = await client.restore_recipe_items(7, memory)
    assert result == {"restored": ["Butter", "eier"], "missing": [], "recipe": answer}
    posts = requests_of(mock, "POST", "/api/recipe/7")
    assert len(posts) == 1
    body = posts[0].kwargs["json"]
    assert body == {
        "items": [
            {"name": "Mehl", "description": "250 g", "optional": False},
            {"name": "Salz", "optional": True},
            {"name": "Milch", "description": "", "optional": False},
            {"name": "Butter", "description": "100 g", "optional": False},
            {"name": "eier", "description": "2", "optional": True},
        ]
    }
    # Every item the recipe had is in the body with name, amount and optional.
    for item in RECIPE_7["items"]:
        sent = next(entry for entry in body["items"] if entry["name"] == item["name"])
        assert sent.get("description", item["description"]) == item["description"]
        assert sent["optional"] == item["optional"]
    # KitchenOwl refuses entries with an id.
    assert all("id" not in entry for entry in body["items"])
    # The GET came directly before the POST.
    assert len(requests_of(mock, "GET", "/api/recipe/7")) == 1


async def test_restore_without_missing_writes_nothing(client, mock) -> None:
    mock.get(f"{BASE}/api/recipe/7", payload=RECIPE_7)
    result = await client.restore_recipe_items(
        7, [row(11, "Weizenmehl"), row(None, "salz"), row(99, "Milch")]
    )
    assert result == {"restored": [], "missing": [], "recipe": RECIPE_7}
    assert not requests_of(mock, "POST", "/api/recipe/7")


async def test_restore_writes_nothing_when_the_read_fails(client, mock) -> None:
    mock.get(f"{BASE}/api/recipe/7", status=500, body="down")
    with pytest.raises(KitchenOwlError):
        await client.restore_recipe_items(7, [row(None, "Butter")])
    mock.get(f"{BASE}/api/recipe/7", payload={"id": 7})
    with pytest.raises(KitchenOwlError):
        await client.restore_recipe_items(7, [row(None, "Butter")])
    mock.get(
        f"{BASE}/api/recipe/7",
        payload={"id": 7, "items": [{"id": 1, "name": "Mehl"}, {"id": 2}]},
    )
    with pytest.raises(KitchenOwlError):
        await client.restore_recipe_items(7, [row(None, "Butter")])
    assert not requests_of(mock, "POST", "/api/recipe/7")


async def test_restore_reports_names_missing_in_the_answer(client, mock) -> None:
    mock.get(f"{BASE}/api/recipe/7", payload=RECIPE_7)
    mock.post(
        f"{BASE}/api/recipe/7", payload={**RECIPE_7, "items": RECIPE_7["items"][:2]}
    )
    result = await client.restore_recipe_items(7, [row(None, "Butter", "100 g")])
    assert result["restored"] == []
    assert result["missing"] == ["Milch", "Butter"]


async def test_add_recipe_with_a_given_recipe_reads_nothing(client, mock) -> None:
    mock.post(f"{BASE}/api/shoppinglist/5/recipeitems", payload={"msg": "DONE"})
    assert await client.add_recipe_to_shoppinglist(5, 7, recipe=RECIPE_7) == 3
    assert not requests_of(mock, "GET", "/api/recipe/7")


# --------------------------------------------------------------------- runtime


@pytest.fixture
async def runtime(hass: HomeAssistant, client: KitchenOwlClient) -> EatFreshData:
    store = FavoritesStore(hass)
    await store.async_load()
    return EatFreshData(
        client=client, sources={}, store=store, household_id=1, shoppinglist_id=5
    )


def recipe_list(*recipes: dict) -> list[dict]:
    return [{"id": r["id"], "name": r["name"], "items": r["items"]} for r in recipes]


BREAD = {
    "id": 8,
    "household_id": 1,
    "name": "Bread",
    "items": [{"id": 30, "name": "Hefe", "description": "1 Würfel", "optional": False}],
}


async def test_runtime_learns_from_lists_and_prunes(runtime, client, mock) -> None:
    mock.get(f"{BASE}/api/household/1/recipe", payload=recipe_list(RECIPE_7, BREAD))
    await client.recipe_ids(1)  # any list teaches, not only the collection
    assert [r["name"] for r in runtime.store.recipe_ingredients(7)] == [
        "Mehl",
        "Salz",
        "Milch",
    ]
    assert runtime.store.recipe_ingredients(8) == [row(30, "Hefe", "1 Würfel")]
    # A list of another household teaches nothing and prunes nothing.
    mock.get(f"{BASE}/api/household/2/recipe", payload=[])
    await client.list_recipes(2)
    assert runtime.store.recipe_ingredients(8) is not None
    # A failed list prunes nothing.
    mock.get(f"{BASE}/api/household/1/recipe", status=500, body="down")
    with pytest.raises(KitchenOwlError):
        await client.list_recipes(1)
    assert runtime.store.recipe_ingredients(8) is not None
    # A fresh list without the recipe keeps it (it may be a cut answer).
    mock.get(f"{BASE}/api/household/1/recipe", payload=recipe_list(RECIPE_7))
    await client.list_recipes(1)
    assert runtime.store.recipe_ingredients(8) is not None
    assert runtime.store.recipe_ingredients(7) is not None


async def test_runtime_ignores_recipes_of_other_households(runtime, client, mock) -> None:
    mock.get(f"{BASE}/api/recipe/9", payload={**BREAD, "id": 9, "household_id": 4})
    await client.get_recipe(9)
    assert runtime.store.recipe_ingredients(9) is None


async def test_runtime_remembers_a_created_recipe(runtime, mock) -> None:
    mock.get(f"{BASE}/api/household/1/recipe", payload=[], repeat=True)
    mock.post(f"{BASE}/api/household/1/recipe", payload={"id": 42})
    recipe = replace(
        make_recipe(),
        image=None,
        ingredients=[
            Ingredient(name="flour", amount=250, unit="g"),
            Ingredient(name="salt"),
        ],
    )
    assert await runtime.async_save_recipe(recipe) == (42, True)
    assert runtime.store.recipe_ingredients(42) == [
        row(None, "flour", "250g"),
        row(None, "salt"),
    ]


async def test_collection_shows_and_finds_missing(runtime, mock) -> None:
    mock.get(f"{BASE}/api/household/1/recipe", payload=recipe_list(RECIPE_7, BREAD))
    await runtime.async_collection()
    without_milk = {**RECIPE_7, "items": RECIPE_7["items"][:2]}
    mock.get(
        f"{BASE}/api/household/1/recipe",
        payload=recipe_list(without_milk, BREAD),
        repeat=True,
    )
    mock.get(f"{BASE}/api/household/1/planner", payload=[], repeat=True)
    recipes = {r["id"]: r for r in await runtime.async_collection()}
    assert recipes[7]["items"] == ["Mehl", "Salz", "Milch"]
    assert recipes[7]["missing"] == 1
    assert recipes[8]["missing"] == 0
    found, total = await runtime.async_search_collection("milch")
    assert total == 1
    assert found[0]["recipe_id"] == 7
    found, total = await runtime.async_search_collection("milch", name_only=True)
    assert total == 0


async def test_collection_recipe_is_complete(runtime, mock) -> None:
    mock.get(f"{BASE}/api/household/1/recipe", payload=recipe_list(RECIPE_7), repeat=True)
    mock.get(f"{BASE}/api/recipe/7", payload=RECIPE_7)
    recipe, missing = await runtime.async_collection_recipe_missing(7)
    assert missing == []
    assert [i.name for i in recipe.ingredients] == ["Mehl", "Salz", "Milch"]
    mock.get(
        f"{BASE}/api/recipe/7",
        payload={**RECIPE_7, "items": [RECIPE_7["items"][1]]},
        repeat=True,
    )
    recipe, missing = await runtime.async_collection_recipe_missing(7)
    assert missing == ["Mehl", "Milch"]
    assert [(i.name, i.raw) for i in recipe.ingredients] == [
        ("Mehl", "250 g Mehl"),
        ("Salz", "Salz"),
        ("Milch", "Milch"),
    ]
    assert (await runtime.async_collection_recipe(7)).ingredients == recipe.ingredients


async def test_transfer_restores_before_sending(runtime, mock) -> None:
    mock.get(f"{BASE}/api/household/1/recipe", payload=recipe_list(RECIPE_7), repeat=True)
    await runtime.async_collection()
    short = {**RECIPE_7, "items": RECIPE_7["items"][:2]}
    mock.get(f"{BASE}/api/recipe/7", payload=short)
    mock.post(f"{BASE}/api/recipe/7", payload=RECIPE_7)
    mock.post(f"{BASE}/api/shoppinglist/5/recipeitems", payload={"msg": "DONE"})
    assert await runtime.async_add_to_shopping_list([7]) == 3
    restore = requests_of(mock, "POST", "/api/recipe/7")[0].kwargs["json"]
    assert [entry["name"] for entry in restore["items"]] == ["Mehl", "Salz", "Milch"]
    sent = requests_of(mock, "POST", "/api/shoppinglist/5/recipeitems")[0]
    assert [entry["id"] for entry in sent.kwargs["json"]["items"]] == [11, 12, 13]
    # One read of the recipe only: the answer of the write is reused.
    assert len(requests_of(mock, "GET", "/api/recipe/7")) == 1


async def test_transfer_without_missing_reads_once(runtime, mock) -> None:
    mock.get(f"{BASE}/api/household/1/recipe", payload=recipe_list(RECIPE_7), repeat=True)
    await runtime.async_collection()
    mock.get(f"{BASE}/api/recipe/7", payload=RECIPE_7)
    mock.post(f"{BASE}/api/shoppinglist/5/recipeitems", payload={"msg": "DONE"})
    assert await runtime.async_add_to_shopping_list([7]) == 3
    assert not requests_of(mock, "POST", "/api/recipe/7")
    assert len(requests_of(mock, "GET", "/api/recipe/7")) == 1


async def test_transfer_stops_when_restore_fails(runtime, mock) -> None:
    mock.get(
        f"{BASE}/api/household/1/recipe", payload=recipe_list(BREAD, RECIPE_7), repeat=True
    )
    await runtime.async_collection()
    mock.get(f"{BASE}/api/recipe/8", payload=BREAD)
    short = {**RECIPE_7, "items": RECIPE_7["items"][:2]}
    mock.get(f"{BASE}/api/recipe/7", payload=short)
    mock.post(f"{BASE}/api/recipe/7", payload=short)  # Milch did not come back
    mock.post(f"{BASE}/api/shoppinglist/5/recipeitems", payload={"msg": "DONE"})
    with pytest.raises(ShoppingListPartial) as err:
        await runtime.async_add_to_shopping_list([8, 7])
    assert err.value.done == 1
    assert "Milch" in str(err.value.cause)
    # Only the first recipe went to the list.
    assert len(requests_of(mock, "POST", "/api/shoppinglist/5/recipeitems")) == 1


async def test_restore_and_forget(runtime, mock) -> None:
    mock.get(f"{BASE}/api/household/1/recipe", payload=recipe_list(RECIPE_7))
    await runtime.async_collection()
    short = {**RECIPE_7, "items": RECIPE_7["items"][1:2]}
    mock.get(f"{BASE}/api/household/1/recipe", payload=recipe_list(short), repeat=True)
    mock.get(f"{BASE}/api/recipe/7", payload=short, repeat=True)
    assert await runtime.async_forget_ingredients(7, ["MILCH", "Salz"]) == {
        "removed": ["Milch"],
        "missing": ["Mehl"],
    }
    assert [r["name"] for r in runtime.store.recipe_ingredients(7)] == ["Mehl", "Salz"]
    mock.post(
        f"{BASE}/api/recipe/7",
        payload={**RECIPE_7, "items": RECIPE_7["items"][:2]},
    )
    assert await runtime.async_restore_ingredients(7) == {
        "restored": ["Mehl"],
        "missing": [],
    }
    # KitchenOwl still answers with the short recipe, so Mehl is missing again.
    assert await runtime.async_forget_ingredients(7) == {"removed": ["Mehl"], "missing": []}
    assert await runtime.async_forget_ingredients(7) == {"removed": [], "missing": []}
    assert runtime.store.recipe_ingredients(7) == [row(12, "Salz", "", True)]


async def test_restore_of_unknown_recipe(runtime, mock) -> None:
    mock.get(f"{BASE}/api/household/1/recipe", payload=[], repeat=True)
    with pytest.raises(RecipeNotFound):
        await runtime.async_restore_ingredients(7)
    with pytest.raises(RecipeNotFound):
        await runtime.async_forget_ingredients(7)


# ------------------------------------------------------------------- WebSocket


class WS:
    def __init__(self, client: Any) -> None:
        self.client = client

    async def call(self, msg_type: str, **kwargs: Any) -> dict[str, Any]:
        await self.client.send_json_auto_id({"type": msg_type, **kwargs})
        return await self.client.receive_json()


@pytest.fixture
async def ws(init_integration: MockConfigEntry, hass_ws_client) -> WS:
    return WS(await hass_ws_client())


async def test_ws_collection_and_recipe_report_missing(
    ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    store = init_integration.runtime_data.store
    store.async_set_ingredients(11, [row(1, "Carrots", "2"), row(2, "Leek", "1")])
    mock_client.list_recipes.return_value[0]["item_rows"] = [row(1, "Carrots", "2")]
    mock_client.list_recipes.return_value[0]["items"] = ["Carrots"]
    msg = await ws.call("eatfresh/collection")
    assert msg["success"], msg
    assert [(r["kitchenowl_id"], r["missing"]) for r in msg["result"]["recipes"]] == [
        (11, 1),
        (12, 0),
    ]
    mock_client.get_recipe.return_value = {
        "id": 11,
        "name": "Soup",
        "items": [{"id": 1, "name": "Carrots", "description": "2"}],
    }
    msg = await ws.call("eatfresh/collection/recipe", kitchenowl_id=11)
    assert msg["success"], msg
    assert msg["result"]["missing"] == ["Leek"]
    assert [i["name"] for i in msg["result"]["recipe"]["ingredients"]] == [
        "Carrots",
        "Leek",
    ]


async def test_ws_restore(
    ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    store = init_integration.runtime_data.store
    store.async_set_ingredients(11, [row(None, "Leek", "1")])
    mock_client.restore_recipe_items = AsyncMock(
        return_value={"restored": ["Leek"], "missing": [], "recipe": {}}
    )
    msg = await ws.call("eatfresh/collection/restore", kitchenowl_id=11)
    assert msg["success"], msg
    assert msg["result"] == {"restored": ["Leek"], "missing": []}
    mock_client.restore_recipe_items.assert_awaited_once_with(11, [row(None, "Leek", "1")])

    # Nothing remembered: nothing is written.
    msg = await ws.call("eatfresh/collection/restore", kitchenowl_id=12)
    assert msg["result"] == {"restored": [], "missing": []}
    assert mock_client.restore_recipe_items.await_count == 1

    msg = await ws.call("eatfresh/collection/restore", kitchenowl_id=99)
    assert msg["error"]["code"] == "not_found"
    mock_client.restore_recipe_items.side_effect = KitchenOwlError("500")
    msg = await ws.call("eatfresh/collection/restore", kitchenowl_id=11)
    assert msg["error"]["code"] == "kitchenowl_error"
    msg = await ws.call("eatfresh/collection/restore")
    assert msg["error"]["code"] == "invalid_format"


async def test_ws_forget(
    ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    store = init_integration.runtime_data.store
    store.async_set_ingredients(
        11, [row(1, "Carrots", "2"), row(None, "Leek"), row(None, "Salt")]
    )
    mock_client.get_recipe.return_value = {
        "id": 11,
        "items": [{"id": 1, "name": "Carrots", "description": "2"}],
    }
    msg = await ws.call("eatfresh/collection/forget", kitchenowl_id=11, names=["leek", "Carrots"])
    assert msg["success"], msg
    assert msg["result"] == {"removed": ["Leek"], "missing": ["Salt"]}
    msg = await ws.call("eatfresh/collection/forget", kitchenowl_id=11)
    assert msg["result"] == {"removed": ["Salt"], "missing": []}
    assert store.recipe_ingredients(11) == [row(1, "Carrots", "2")]
    mock_client.set_recipe_tags.assert_not_awaited()

    mock_client.get_recipe.return_value = {"id": 11, "household_id": 9, "items": []}
    msg = await ws.call("eatfresh/collection/forget", kitchenowl_id=11)
    assert msg["error"]["code"] == "not_found"
    msg = await ws.call("eatfresh/collection/forget", kitchenowl_id=11, names=[""])
    assert msg["error"]["code"] == "invalid_format"
    msg = await ws.call("eatfresh/collection/forget", kitchenowl_id=11, names="Leek")
    assert msg["error"]["code"] == "invalid_format"


# ------------------------------------------------- fixes after the review (0.4.1)


def test_merge_drops_missing_entry_with_a_present_name() -> None:
    """The reviewer's case: a renamed duplicate would stay missing for ever."""
    memory = [row(1, "Pfeffer"), row(None, "Pfeffer")]
    merged, missing = merge_items(memory, [row(1, "Pfeffer")])
    assert merged == [row(1, "Pfeffer")]
    assert missing == []
    # Renamed in KitchenOwl to a name the memory has as a missing entry.
    memory = [row(1, "Pfeffer", "1 TL"), row(None, "Salz", "1 Prise")]
    merged, missing = merge_items(memory, [row(1, "Salz", "2 Prisen")])
    assert merged == [row(1, "Salz", "2 Prisen")]
    assert missing == []


def test_merge_keeps_remembered_values_when_unknown() -> None:
    """An answer without amount text or optional does not erase them."""
    memory = [row(1, "Mehl", "500 g", True)]
    current = [{"id": 1, "name": "Mehl", "description": None, "optional": None}]
    merged, _ = merge_items(memory, current)
    assert merged == [row(1, "Mehl", "500 g", True)]
    # An empty text from KitchenOwl is a change and wins.
    merged, _ = merge_items(memory, [row(1, "Mehl", "", False)])
    assert merged == [row(1, "Mehl", "", False)]


def test_item_rows_unknown_fields() -> None:
    assert item_rows([{"id": 1, "name": "Mehl"}]) == [
        {"id": 1, "name": "Mehl", "description": None, "optional": None}
    ]
    assert item_rows([{"id": 1, "name": "Mehl", "description": None, "optional": None}]) == [
        row(1, "Mehl")
    ]


async def test_store_learns_without_erasing_amounts(hass: HomeAssistant) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    store.async_learn_ingredients(11, [row(1, "Mehl", "500 g", True)])
    store.async_learn_ingredients(11, item_rows([{"id": 1, "name": "Mehl"}]))
    assert store.recipe_ingredients(11) == [row(1, "Mehl", "500 g", True)]
    # First sight with unknown fields: stored as empty text and not optional.
    store.async_learn_ingredients(12, item_rows([{"id": 2, "name": "Salz"}]))
    assert store.recipe_ingredients(12) == [row(2, "Salz")]


async def test_store_migrated_memory_counts_as_seen_today(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to("2026-11-19 12:00:00+01:00")
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 4,
        "key": STORAGE_KEY,
        "data": {
            "hidden": {"5": "2026-11-02T10:00:00+00:00"},
            "ingredients": {"11": [row(1, "Mehl")], "12": [row(2, "Salz")], "13": []},
            "ingredient_meta": {
                "12": {"seen": "2026-10-01", "created_at": 1700000000000},
                "13": {"seen": "not a date", "created_at": True},
                "99": {"seen": "2026-11-01"},
                "x": "broken",
            },
        },
    }
    store = FavoritesStore(hass)
    await store.async_load()
    assert store.recipe_seen(11) == "2026-11-19"
    assert store.recipe_seen(12) == "2026-10-01"
    assert store.recipe_seen(13) == "2026-11-19"
    assert store.recipe_seen(99) is None
    hass.bus.async_fire(EVENT_HOMEASSISTANT_FINAL_WRITE)
    await hass.async_block_till_done()
    saved = hass_storage[STORAGE_KEY]["data"]
    assert saved["hidden"] == {"5": "2026-11-02T10:00:00+00:00"}
    assert saved["ingredient_meta"] == {
        "11": {"seen": "2026-11-19"},
        "12": {"seen": "2026-10-01", "created_at": 1700000000000},
        "13": {"seen": "2026-11-19"},
    }
    # A broken section is ignored; the memory still counts as seen today.
    hass_storage[STORAGE_KEY]["data"]["ingredient_meta"] = ["broken"]
    store = FavoritesStore(hass)
    await store.async_load()
    assert store.recipe_seen(12) == "2026-11-19"
    assert store.recipe_ingredients(12) == [row(2, "Salz")]


async def test_store_forgets_only_after_30_days(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to("2026-11-19 12:00:00+01:00")
    store = FavoritesStore(hass)
    await store.async_load()
    store.async_learn_ingredients(11, [row(1, "Mehl")])
    store.async_learn_ingredients(12, [row(2, "Salz")])
    # An empty list never forgets, not even much later.
    freezer.tick(timedelta(days=90))
    store.async_prune_ingredients([])
    assert store.recipe_ingredients(11) is not None
    assert store.recipe_ingredients(12) is not None
    freezer.move_to("2026-11-20 12:00:00+01:00")
    # A cut list: recipe 11 is not in it, but was seen yesterday.
    store.async_prune_ingredients([12])
    assert store.recipe_ingredients(11) is not None
    assert store.recipe_seen(12) == "2026-11-20"
    freezer.move_to("2026-12-19 12:00:00+01:00")  # 30 days after the last sight
    store.async_prune_ingredients([12])
    assert store.recipe_ingredients(11) is not None
    freezer.move_to("2026-12-20 12:00:00+01:00")
    store.async_prune_ingredients([12])
    assert store.recipe_ingredients(11) is None
    assert store.recipe_seen(11) is None
    assert store.recipe_ingredients(12) is not None


async def test_store_seen_is_saved_at_most_once_a_day(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    store.async_learn_ingredients(11, [row(1, "Mehl")])
    saves = MagicMock()
    store._schedule_save = saves  # type: ignore[method-assign]
    for _ in range(3):
        store.async_learn_ingredients(11, [row(1, "Mehl")])
        store.async_prune_ingredients([11])
    assert saves.call_count == 0
    freezer.tick(timedelta(days=1))
    for _ in range(3):
        store.async_learn_ingredients(11, [row(1, "Mehl")])
        store.async_prune_ingredients([11])
    assert saves.call_count == 1


async def test_store_reused_recipe_id_starts_over(hass: HomeAssistant) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    store.async_learn_ingredients(11, [row(1, "Mehl"), row(2, "Salz")], 1000)
    assert store.async_learn_ingredients(11, [row(1, "Mehl")], 1000) == [row(None, "Salz")]
    # No creation time in the answer: nothing is checked or thrown away.
    assert store.async_learn_ingredients(11, [row(5, "Reis")]) == [
        row(None, "Mehl"),
        row(None, "Salz"),
    ]
    # Another creation time: a new recipe got the id; old items are gone.
    assert store.async_learn_ingredients(11, [row(7, "Reis")], 2000) == []
    assert store.recipe_ingredients(11) == [row(7, "Reis")]
    assert store.async_learn_ingredients(11, [row(7, "Reis")], 2000) == []
    # A recipe EatFresh creates replaces the memory and its creation time.
    store.async_start_ingredients(11, [row(None, "Eier", "2")])
    assert store.recipe_ingredients(11) == [row(None, "Eier", "2")]
    assert store.async_learn_ingredients(11, [row(8, "Eier", "2")], 3000) == []
    assert store.recipe_ingredients(11) == [row(8, "Eier", "2")]
    assert store.async_learn_ingredients(11, [], 3000) == [row(None, "Eier", "2")]


async def test_store_limits(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    many = [row(index, f"Zutat {index}") for index in range(1, 302)]
    assert store.async_learn_ingredients(11, many) == []
    assert len(store.recipe_ingredients(11)) == 300
    # The memory is full: a new item is not remembered, the old ones stay.
    store.async_learn_ingredients(11, [*many[:300], row(999, "Neu")])
    remembered = store.recipe_ingredients(11)
    assert len(remembered) == 300
    assert "Neu" not in {r["name"] for r in remembered}
    monkeypatch.setattr("custom_components.eatfresh.store.MAX_REMEMBERED_RECIPES", 2)
    store.async_learn_ingredients(12, [row(1, "Mehl")])
    caplog.set_level("DEBUG", logger="custom_components.eatfresh.store")
    assert store.async_learn_ingredients(13, [row(1, "Mehl")]) == []
    store.async_set_ingredients(13, [row(1, "Mehl")])
    store.async_start_ingredients(13, [row(1, "Mehl")])
    assert store.recipe_ingredients(13) is None
    assert "Not remembering the ingredients of recipe 13" in caplog.text
    # Known recipes still learn.
    assert store.async_learn_ingredients(12, []) == [row(None, "Mehl")]


async def test_restore_refuses_odd_reads(client, mock) -> None:
    """Nothing is written when the read gives no usable item list."""
    for payload in (
        {"id": 7, "items": None},
        {"id": 7, "items": {"id": 1, "name": "Mehl"}},
        {"id": 7, "items": "Mehl"},
        {"id": 7, "items": [{"id": 1, "name": "", "optional": False}]},
        {"id": 7, "items": [{"id": 1, "name": None, "optional": False}]},
        {"id": 7, "items": [{"id": 1, "name": "Mehl", "description": "1 kg"}]},
        {"id": 7, "items": [{"id": 1, "name": "Mehl", "optional": None}]},
        {"id": 7, "items": [{"id": 1, "name": "Mehl", "optional": "false"}]},
    ):
        mock.get(f"{BASE}/api/recipe/7", payload=payload)
        with pytest.raises(KitchenOwlError):
            await client.restore_recipe_items(7, [row(None, "Butter")])
    assert not requests_of(mock, "POST", "/api/recipe/7")


async def test_restore_never_sends_null_and_keeps_optional(client, mock) -> None:
    """Measured: no description keeps the text, no optional makes it optional."""
    recipe = {
        "id": 7,
        "items": [
            {"id": 1, "name": "Mehl", "description": None, "optional": False},
            {"id": 2, "name": "Salz", "optional": True},
            {"id": 3, "name": "Milch", "description": 5, "optional": False},
        ],
    }
    mock.get(f"{BASE}/api/recipe/7", payload=recipe)
    mock.post(f"{BASE}/api/recipe/7", payload=recipe)
    await client.restore_recipe_items(7, [row(None, "Butter")])
    body = requests_of(mock, "POST", "/api/recipe/7")[0].kwargs["json"]
    assert body["items"][:3] == [
        {"name": "Mehl", "optional": False},
        {"name": "Salz", "optional": True},
        {"name": "Milch", "optional": False},
    ]
    assert all(value is not None for item in body["items"] for value in item.values())


def kitchenowl_recipe(mock: aioresponses, recipe: dict) -> dict:
    """Serve one recipe like KitchenOwl: a write replaces its item links."""
    state = {"items": [dict(item) for item in recipe["items"]], "next": 100}

    def answer() -> CallbackResult:
        return CallbackResult(
            payload={**recipe, "items": [dict(item) for item in state["items"]]}
        )

    def on_post(url: Any, **kwargs: Any) -> CallbackResult:
        old = {item["name"].lower(): item for item in state["items"]}
        items = []
        for entry in kwargs["json"]["items"]:
            before = old.get(entry["name"].lower())
            if before is None:
                state["next"] += 1
            items.append(
                {
                    "id": before["id"] if before else state["next"],
                    "name": entry["name"],
                    "description": entry.get(
                        "description", before["description"] if before else ""
                    ),
                    "optional": entry.get("optional", True),
                }
            )
        state["items"] = items
        return answer()

    async def on_get(url: Any, **kwargs: Any) -> CallbackResult:
        # Let other tasks run between the read and the write, like a network.
        result = answer()
        for _ in range(3):
            await asyncio.sleep(0)
        return result

    mock.get(f"{BASE}/api/recipe/{recipe['id']}", callback=on_get, repeat=True)
    mock.post(f"{BASE}/api/recipe/{recipe['id']}", callback=on_post, repeat=True)
    return state


async def test_two_restores_at_once_write_once(runtime, mock) -> None:
    mock.get(f"{BASE}/api/household/1/recipe", payload=recipe_list(RECIPE_7), repeat=True)
    await runtime.async_collection()
    state = kitchenowl_recipe(mock, {**RECIPE_7, "items": RECIPE_7["items"][:1]})
    first, second = await asyncio.gather(
        runtime.async_restore_ingredients(7), runtime.async_restore_ingredients(7)
    )
    assert first == {"restored": ["Salz", "Milch"], "missing": []}
    assert second == {"restored": [], "missing": []}
    assert len(requests_of(mock, "POST", "/api/recipe/7")) == 1
    assert [(i["name"], i["optional"]) for i in state["items"]] == [
        ("Mehl", False),
        ("Salz", True),
        ("Milch", False),
    ]


async def test_restore_during_a_transfer(runtime, mock) -> None:
    mock.get(f"{BASE}/api/household/1/recipe", payload=recipe_list(RECIPE_7), repeat=True)
    await runtime.async_collection()
    state = kitchenowl_recipe(mock, {**RECIPE_7, "items": RECIPE_7["items"][1:]})
    mock.post(f"{BASE}/api/shoppinglist/5/recipeitems", payload={"msg": "DONE"})
    added, restored = await asyncio.gather(
        runtime.async_add_to_shopping_list([7]), runtime.async_restore_ingredients(7)
    )
    assert added == 3
    assert restored == {"restored": [], "missing": []}
    assert len(requests_of(mock, "POST", "/api/recipe/7")) == 1
    assert [i["name"] for i in state["items"]] == ["Salz", "Milch", "Mehl"]
    assert [i["description"] for i in state["items"]] == [None, "", "250 g"]
    sent = requests_of(mock, "POST", "/api/shoppinglist/5/recipeitems")[0]
    assert len(sent.kwargs["json"]["items"]) == 3


def listed(recipe: dict, created: int | None = None) -> dict:
    entry = {"id": recipe["id"], "name": recipe["name"], "items": recipe["items"]}
    if created is not None:
        entry["created_at"] = created
    return entry


async def test_runtime_keeps_memory_through_empty_and_cut_lists(
    runtime, client, mock, freezer: FrozenDateTimeFactory
) -> None:
    mock.get(f"{BASE}/api/household/1/recipe", payload=[listed(RECIPE_7), listed(BREAD)])
    await client.list_recipes(1)
    mock.get(f"{BASE}/api/household/1/recipe", payload=[])
    await client.list_recipes(1)
    assert runtime.store.recipe_ingredients(7) is not None
    assert runtime.store.recipe_ingredients(8) is not None
    freezer.tick(timedelta(days=29))
    mock.get(f"{BASE}/api/household/1/recipe", payload=[listed(BREAD)])
    await client.list_recipes(1)
    assert runtime.store.recipe_ingredients(7) is not None
    freezer.tick(timedelta(days=2))
    mock.get(f"{BASE}/api/household/1/recipe", payload=[listed(BREAD)])
    await client.list_recipes(1)
    assert runtime.store.recipe_ingredients(7) is None
    assert runtime.store.recipe_ingredients(8) is not None


async def test_runtime_reused_recipe_id(runtime, client, mock) -> None:
    """A deleted recipe's id given to a new one: old items are not missing."""
    mock.get(f"{BASE}/api/household/1/recipe", payload=[listed(RECIPE_7, 1000)])
    await client.list_recipes(1)
    other = {**BREAD, "id": 7, "name": "Brot"}
    mock.get(f"{BASE}/api/household/1/recipe", payload=[listed(other, 2000)], repeat=True)
    recipes = await runtime.async_collection()
    assert recipes[0]["missing"] == 0
    assert recipes[0]["items"] == ["Hefe"]
    assert runtime.store.recipe_ingredients(7) == [row(30, "Hefe", "1 Würfel")]
    # The full recipe with the same creation time keeps it as it is.
    mock.get(f"{BASE}/api/recipe/7", payload={**other, "created_at": 2000})
    mock.post(f"{BASE}/api/shoppinglist/5/recipeitems", payload={"msg": "DONE"})
    assert await runtime.async_add_to_shopping_list([7]) == 1
    assert not requests_of(mock, "POST", "/api/recipe/7")


async def test_restore_with_nothing_missing_accepts_odd_items(client, mock) -> None:
    """A recipe that misses nothing is not checked: the transfer must not fail."""
    odd = {
        "id": 7,
        "items": [
            {"id": 1, "name": "Mehl", "description": "500g", "optional": None},
            {"id": 2, "description": "1"},
        ],
    }
    mock.get(f"{BASE}/api/recipe/7", payload=odd)
    result = await client.restore_recipe_items(7, [row(1, "Mehl")])
    assert result == {"restored": [], "missing": [], "recipe": odd}
    assert not requests_of(mock, "POST", "/api/recipe/7")
    # With something to add the same recipe is refused, and nothing is sent.
    mock.get(f"{BASE}/api/recipe/7", payload=odd)
    with pytest.raises(KitchenOwlError):
        await client.restore_recipe_items(7, [row(1, "Mehl"), row(None, "Butter")])
    assert not requests_of(mock, "POST", "/api/recipe/7")


def test_created_at_of_only_knows_the_last_created_recipe(client) -> None:
    assert client.created_at_of(7) is None
    client._created_at = {7: 1795000000000}
    assert client.created_at_of(7) == 1795000000000
    assert client.created_at_of(8) is None


async def test_store_created_recipe_keeps_its_creation_time(hass: HomeAssistant) -> None:
    """The creation time of a created recipe guards it before the first list."""
    store = FavoritesStore(hass)
    await store.async_load()
    store.async_start_ingredients(21, [row(None, "Eier", "2")], created_at=5000)
    # Same recipe: its items are learned, a missing one stays remembered.
    assert store.async_learn_ingredients(21, [], 5000) == [row(None, "Eier", "2")]
    # Another recipe got the id before any list was read: start over.
    assert store.async_learn_ingredients(21, [row(9, "Reis")], 6000) == []
    assert store.recipe_ingredients(21) == [row(9, "Reis")]
    # An unusable value is ignored, nothing breaks.
    store.async_start_ingredients(22, [row(None, "Mehl")], created_at="soon")
    assert store.async_learn_ingredients(22, [row(3, "Mehl")], 7000) == []
