"""Tests for the favorites store, the cache and the source selection."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import patch

from homeassistant.const import EVENT_HOMEASSISTANT_FINAL_WRITE
from homeassistant.core import HomeAssistant

from custom_components.eatfresh.const import (
    CONF_ACCEPT_CHEFKOCH,
    CONF_SOURCES,
    STORAGE_KEY,
)
from custom_components.eatfresh.runtime import enabled_source_ids
from custom_components.eatfresh.store import FavoritesStore, TTLCache

from .conftest import FAKE_CLASSES


def _add(store: FavoritesStore, key: str, kitchenowl_id: int) -> None:
    source, recipe_id = key.split(":", 1)
    store.async_set(
        key,
        source=source,
        recipe_id=recipe_id,
        url=f"https://recipes.example.com/{recipe_id}",
        title=f"Recipe {recipe_id}",
        image=None,
        kitchenowl_id=kitchenowl_id,
    )


async def test_store_roundtrip(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Favorites are saved with a delay and loaded again."""
    store = FavoritesStore(hass)
    await store.async_load()
    assert store.items() == []

    _add(store, "fakea:1", 10)
    _add(store, "jsonld:https://recipes.example.com/x", 11)
    assert store.is_favorite("fakea:1")
    assert store.get("fakea:1")["kitchenowl_id"] == 10
    assert store.find_by_url("https://recipes.example.com/1")[0] == "fakea:1"
    assert store.find_by_url("https://nowhere.example.com") is None

    assert STORAGE_KEY not in hass_storage  # delayed
    hass.bus.async_fire(EVENT_HOMEASSISTANT_FINAL_WRITE)
    await hass.async_block_till_done()
    saved = hass_storage[STORAGE_KEY]
    assert saved["version"] == 1
    assert set(saved["data"]["favorites"]) == {
        "fakea:1",
        "jsonld:https://recipes.example.com/x",
    }
    assert set(saved["data"]["favorites"]["fakea:1"]) == {
        "source",
        "id",
        "url",
        "title",
        "image",
        "kitchenowl_id",
        "added_at",
    }

    again = FavoritesStore(hass)
    await again.async_load()
    assert again.get("fakea:1") == store.get("fakea:1")

    assert again.async_remove("fakea:1") is True
    assert again.async_remove("fakea:1") is False
    assert not again.is_favorite("fakea:1")


async def test_store_keeps_added_at(hass: HomeAssistant) -> None:
    """Setting a favorite again keeps its first date; newest come first."""
    store = FavoritesStore(hass)
    await store.async_load()
    _add(store, "fakea:1", 10)
    first = store.get("fakea:1")["added_at"]
    _add(store, "fakea:1", 12)
    assert store.get("fakea:1")["added_at"] == first
    assert store.get("fakea:1")["kitchenowl_id"] == 12


async def test_store_ignores_broken_data(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """Broken entries on disk are skipped."""
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "key": STORAGE_KEY,
        "data": {"favorites": {"a:1": "broken", "a:2": {"kitchenowl_id": 1}}},
    }
    store = FavoritesStore(hass)
    await store.async_load()
    assert not store.is_favorite("a:1")
    assert store.is_favorite("a:2")


def test_ttl_cache_expires_and_evicts() -> None:
    """Entries expire after the TTL and the oldest are dropped first."""
    now = 1000.0
    with patch(
        "custom_components.eatfresh.store.time.monotonic", side_effect=lambda: now
    ):
        cache: TTLCache[int] = TTLCache(timedelta(minutes=1), max_entries=2)
        cache.set("a", 1)
        cache.set("b", 2)
        assert cache.get("a") == 1  # a is now the newest
        cache.set("c", 3)
        assert cache.get("b") is None
        assert cache.get("a") == 1
        assert len(cache) == 2

        now += 61
        assert cache.get("a") is None
        assert cache.get("c") is None
        cache.set("d", 4)
        cache.clear()
        assert len(cache) == 0


def test_enabled_source_ids() -> None:
    """Defaults, chefkoch gate and unknown ids."""
    assert enabled_source_ids({}, FAKE_CLASSES) == ["fakea", "fakeb"]
    assert enabled_source_ids({CONF_SOURCES: []}, FAKE_CLASSES) == []
    assert enabled_source_ids({CONF_SOURCES: ["chefkoch"]}, FAKE_CLASSES) == []
    assert enabled_source_ids(
        {CONF_SOURCES: ["chefkoch", "nope"], CONF_ACCEPT_CHEFKOCH: True},
        FAKE_CLASSES,
    ) == ["chefkoch"]


async def test_store_upgrades_file_of_version_0_1_0(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """A file written by EatFresh 0.1.0 keeps all favorites and gains hidden."""
    favorite = {
        "source": "fakea",
        "id": "r1",
        "url": "https://recipes.example.com/fakea/r1",
        "title": "Soup",
        "image": None,
        "kitchenowl_id": 11,
        "added_at": "2026-11-01T10:00:00+00:00",
    }
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 1,
        "key": STORAGE_KEY,
        "data": {"favorites": {"fakea:r1": favorite}},
    }
    store = FavoritesStore(hass)
    await store.async_load()
    assert store.get("fakea:r1") == favorite
    assert store.hidden_ids() == set()

    assert store.async_hide(12)
    assert not store.async_hide(12)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_FINAL_WRITE)
    await hass.async_block_till_done()
    saved = hass_storage[STORAGE_KEY]
    assert saved["version"] == 1
    assert saved["minor_version"] == 2
    assert saved["data"]["favorites"] == {"fakea:r1": favorite}
    assert list(saved["data"]["hidden"]) == ["12"]

    again = FavoritesStore(hass)
    await again.async_load()
    assert again.is_hidden(12)
    assert not again.is_hidden(11)
    assert again.get("fakea:r1") == favorite


async def test_store_hide_and_unhide(hass: HomeAssistant) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    assert not store.is_hidden(None)
    assert store.async_hide(5)
    assert store.is_hidden(5)
    assert store.async_unhide(5)
    assert not store.async_unhide(5)
    assert not store.is_hidden(5)


async def test_store_ignores_broken_hidden(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 2,
        "key": STORAGE_KEY,
        "data": {"favorites": {}, "hidden": {"7": "t", "x": "t", "-1": "t"}},
    }
    store = FavoritesStore(hass)
    await store.async_load()
    assert store.hidden_ids() == {7}

    hass_storage[STORAGE_KEY]["data"]["hidden"] = ["7"]
    store = FavoritesStore(hass)
    await store.async_load()
    assert store.hidden_ids() == set()
