"""Persistent favorites and a small in-memory cache for EatFresh."""

from __future__ import annotations

from collections import OrderedDict
from datetime import timedelta
import time
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import CACHE_MAX_ENTRIES, STORAGE_KEY, STORAGE_SAVE_DELAY, STORAGE_VERSION
from .kitchenowl import normalize_source


class Favorite(TypedDict):
    """One favorite as stored on disk."""

    source: str
    id: str
    url: str
    title: str
    image: str | None
    kitchenowl_id: int
    added_at: str


class FavoritesStore:
    """Favorites keyed by "<source>:<id>", saved with the Home Assistant store."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the store."""
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._favorites: dict[str, Favorite] = {}

    async def async_load(self) -> None:
        """Load the favorites from disk."""
        data = await self._store.async_load()
        favorites = (data or {}).get("favorites") or {}
        self._favorites = {
            key: value for key, value in favorites.items() if isinstance(value, dict)
        }

    @callback
    def _data_to_save(self) -> dict[str, Any]:
        """Return the data to write to disk."""
        return {"favorites": dict(self._favorites)}

    @callback
    def _schedule_save(self) -> None:
        """Write the favorites to disk after a short delay."""
        self._store.async_delay_save(self._data_to_save, STORAGE_SAVE_DELAY)

    @callback
    def get(self, key: str) -> Favorite | None:
        """Return the favorite of a key or None."""
        return self._favorites.get(key)

    @callback
    def is_favorite(self, key: str) -> bool:
        """Return True if the key is a favorite."""
        return key in self._favorites

    @callback
    def items(self) -> list[tuple[str, Favorite]]:
        """Return all favorites, newest first."""
        return sorted(
            self._favorites.items(),
            key=lambda item: item[1].get("added_at", ""),
            reverse=True,
        )

    @callback
    def find_by_url(self, url: str) -> tuple[str, Favorite] | None:
        """Return the favorite with this recipe URL or None.

        Addresses are compared like KitchenOwl sources (scheme, host case,
        trailing slash and fragment do not matter).
        """
        if found := self.keys_for_url(url):
            return found[0], self._favorites[found[0]]
        return None

    @callback
    def keys_for_url(self, url: str) -> list[str]:
        """Return the keys of all favorites with this recipe URL."""
        wanted = normalize_source(url) if url else ""
        if not wanted:
            return []
        return [
            key
            for key, favorite in self._favorites.items()
            if favorite.get("url") and normalize_source(favorite["url"]) == wanted
        ]

    @callback
    def async_set(
        self,
        key: str,
        *,
        source: str,
        recipe_id: str,
        url: str,
        title: str,
        image: str | None,
        kitchenowl_id: int,
    ) -> Favorite:
        """Add or replace a favorite and save it."""
        previous = self._favorites.get(key)
        favorite: Favorite = {
            "source": source,
            "id": recipe_id,
            "url": url,
            "title": title,
            "image": image,
            "kitchenowl_id": kitchenowl_id,
            "added_at": previous["added_at"]
            if previous
            else dt_util.utcnow().isoformat(),
        }
        self._favorites[key] = favorite
        self._schedule_save()
        return favorite

    @callback
    def async_remove(self, key: str) -> bool:
        """Remove a favorite. Return True if it existed."""
        if self._favorites.pop(key, None) is None:
            return False
        self._schedule_save()
        return True


class TTLCache[V]:
    """A small least-recently-used cache whose entries expire."""

    def __init__(self, ttl: timedelta, max_entries: int = CACHE_MAX_ENTRIES) -> None:
        """Initialize the cache."""
        self._ttl = ttl.total_seconds()
        self._max_entries = max_entries
        self._data: OrderedDict[Any, tuple[float, V]] = OrderedDict()

    def get(self, key: Any) -> V | None:
        """Return a cached value or None if missing or expired."""
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if expires < time.monotonic():
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: Any, value: V) -> None:
        """Store a value."""
        self._data[key] = (time.monotonic() + self._ttl, value)
        self._data.move_to_end(key)
        while len(self._data) > self._max_entries:
            self._data.popitem(last=False)

    def clear(self) -> None:
        """Drop all values."""
        self._data.clear()

    def __len__(self) -> int:
        """Return the number of entries, including expired ones."""
        return len(self._data)
