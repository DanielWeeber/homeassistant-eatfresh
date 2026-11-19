"""Tests for the Picnic parts of the EatFresh store (version 1.3)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import EVENT_HOMEASSISTANT_FINAL_WRITE
from homeassistant.core import HomeAssistant

from custom_components.eatfresh.const import STORAGE_KEY
from custom_components.eatfresh.store import FavoritesStore, picnic_key

FAVORITE = {
    "source": "fakea",
    "id": "r1",
    "url": "https://recipes.example.com/fakea/r1",
    "title": "Soup",
    "image": None,
    "kitchenowl_id": 11,
    "added_at": "2026-11-01T10:00:00+00:00",
}


async def _save(hass: HomeAssistant) -> None:
    hass.bus.async_fire(EVENT_HOMEASSISTANT_FINAL_WRITE)
    await hass.async_block_till_done()


def _product(store: FavoritesStore, name: str, product_id: str) -> None:
    store.async_set_picnic_product(
        name,
        product_id=product_id,
        product_name=f"Product {product_id}",
        unit_quantity="500g",
        price=199,
        amount=None,
    )


async def test_upgrade_from_0_3_0_keeps_everything(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """A file of EatFresh 0.3.0 (1.2) keeps all data and gains the Picnic parts."""
    old = {
        "favorites": {"fakea:r1": FAVORITE},
        "hidden": {"12": "2026-11-02T10:00:00+00:00"},
        "week_lists": {"2026-11-09": "2026-11-10T08:00:00+00:00"},
        "week_list_done": {"2026-11-09": ["2026-11-10:11"]},
    }
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 2,
        "key": STORAGE_KEY,
        "data": old,
    }
    store = FavoritesStore(hass)
    await store.async_load()
    assert store.get("fakea:r1") == FAVORITE
    assert store.is_hidden(12)
    assert store.picnic_product("Milch") is None
    assert not store.is_picnic_skipped("Milch")

    _product(store, "Milch", "s1")
    await _save(hass)
    saved = hass_storage[STORAGE_KEY]
    assert saved["minor_version"] == 4
    for key, value in old.items():
        assert saved["data"][key] == value
    assert saved["data"]["picnic_map"]["milch"]["product_id"] == "s1"
    assert saved["data"]["picnic_skip"] == []
    assert saved["data"]["picnic_sent"] == {}


async def test_upgrade_from_0_1_0(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {"favorites": {"fakea:r1": FAVORITE}},
    }
    store = FavoritesStore(hass)
    await store.async_load()
    store.async_set_picnic_skip("Salz", True)
    await _save(hass)
    data = hass_storage[STORAGE_KEY]["data"]
    assert data["favorites"] == {"fakea:r1": FAVORITE}
    assert data["hidden"] == {}
    assert data["picnic_skip"] == ["salz"]


async def test_roundtrip(hass: HomeAssistant, hass_storage: dict[str, Any]) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    store.async_set_picnic_product(
        "  Rote   Linsen ",
        product_id="s7",
        product_name="Linsen rot",
        unit_quantity="500g",
        price=None,
        amount=2,
    )
    store.async_set_picnic_skip("Pfeffer", True)
    when = store.async_set_picnic_sent(101, "s7", 2)
    await _save(hass)

    again = FavoritesStore(hass)
    await again.async_load()
    assert again.picnic_product("rote linsen") == {
        "product_id": "s7",
        "name": "Linsen rot",
        "unit_quantity": "500g",
        "price": None,
        "amount": 2,
    }
    assert again.is_picnic_skipped("PFEFFER")
    assert again.picnic_sent(101) == {"product_id": "s7", "amount": 2, "at": when}
    assert again.async_remove_picnic_sent(101)
    assert not again.async_remove_picnic_sent(101)
    assert again.async_remove_picnic_product("Rote Linsen")
    assert not again.async_remove_picnic_product("Rote Linsen")


async def test_broken_picnic_parts_are_ignored(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 3,
        "key": STORAGE_KEY,
        "data": {
            "favorites": {"fakea:r1": FAVORITE},
            "picnic_map": {
                "milch": {"product_id": "s1", "name": "Milch", "amount": True},
                "bad": {"product_id": "", "name": "No id"},
                "worse": "text",
                "": {"product_id": "s2", "name": "No key"},
                "brot": {"product_id": "s3", "name": "Brot", "price": -1},
            },
            "picnic_skip": ["Salz", 5, "salz", ""],
            "picnic_sent": {
                "101": {"product_id": "s1", "amount": 2, "at": "2026-11-15T10:00:00+00:00"},
                "abc": {"product_id": "s1", "amount": 2, "at": "2026-11-15T10:00:00+00:00"},
                "102": {"product_id": "s1", "amount": 0, "at": "2026-11-15T10:00:00+00:00"},
                "103": {"product_id": "s1", "amount": 1, "at": "yesterday"},
            },
        },
    }
    store = FavoritesStore(hass)
    await store.async_load()
    assert store.get("fakea:r1") == FAVORITE
    assert store.picnic_product("milch")["amount"] is None  # type: ignore[index]
    assert store.picnic_product("brot")["price"] is None  # type: ignore[index]
    assert store.picnic_product("bad") is None
    assert store.picnic_product("worse") is None
    assert store.is_picnic_skipped("salz")
    assert store.picnic_sent(101) is not None
    assert store.picnic_sent(102) is None
    assert store.picnic_sent(103) is None


async def test_wrong_types_of_picnic_parts(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 3,
        "key": STORAGE_KEY,
        "data": {"picnic_map": ["x"], "picnic_skip": {"a": 1}, "picnic_sent": 3},
    }
    store = FavoritesStore(hass)
    await store.async_load()
    assert store.picnic_product("x") is None
    assert not store.is_picnic_skipped("a")


async def test_sizes_are_limited(hass: HomeAssistant) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    with (
        patch("custom_components.eatfresh.store.MAX_PICNIC_MAP", 3),
        patch("custom_components.eatfresh.store.MAX_PICNIC_SKIP", 2),
        patch("custom_components.eatfresh.store.MAX_PICNIC_SENT", 2),
    ):
        for i in range(5):
            _product(store, f"Item {i}", f"s{i}")
            store.async_set_picnic_skip(f"Skip {i}", True)
            store.async_set_picnic_sent(i + 1, f"s{i}", 1)
        # Choosing an old one again keeps it as the newest.
        _product(store, "Item 2", "s2b")
        _product(store, "Item 5", "s5")
    assert [store.picnic_product(f"Item {i}") is not None for i in range(6)] == [
        False,
        False,
        True,
        False,
        True,
        True,
    ]
    assert [store.is_picnic_skipped(f"Skip {i}") for i in range(5)] == [
        False,
        False,
        False,
        True,
        True,
    ]
    assert [store.picnic_sent(i + 1) is not None for i in range(5)] == [
        False,
        False,
        False,
        True,
        True,
    ]


async def test_prune_sent(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    store.async_set_picnic_sent(1, "s1", 1)
    freezer.tick(timedelta(days=10))
    store.async_set_picnic_sent(2, "s2", 1)
    store.async_set_picnic_sent(3, "s3", 1)
    store.async_prune_picnic_sent([1, 2])
    assert store.picnic_sent(3) is None  # off the list
    assert store.picnic_sent(1) is not None
    freezer.tick(timedelta(days=5))
    store.async_prune_picnic_sent([1, 2])
    assert store.picnic_sent(1) is None  # older than 14 days
    assert store.picnic_sent(2) is not None


def test_picnic_key() -> None:
    assert picnic_key("  Rote   LINSEN ") == "rote linsen"
