"""Persistent favorites and a small in-memory cache for EatFresh."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable
from datetime import date, timedelta
import logging
import time
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CACHE_MAX_ENTRIES,
    MAX_WEEK_LISTS,
    STORAGE_KEY,
    STORAGE_MINOR_VERSION,
    STORAGE_SAVE_DELAY,
    STORAGE_VERSION,
)
from .kitchenowl import normalize_source

_LOGGER = logging.getLogger(__name__)


class Favorite(TypedDict):
    """One favorite as stored on disk."""

    source: str
    id: str
    url: str
    title: str
    image: str | None
    kitchenowl_id: int
    added_at: str


class _EatFreshStore(Store[dict[str, Any]]):
    """Home Assistant store that upgrades files of older EatFresh versions."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Keep everything and add what newer versions expect.

        1.1 (EatFresh 0.1.0) had only favorites; 1.2 adds hidden recipes.
        """
        data = dict(old_data or {})
        if old_major_version == 1 and old_minor_version < 2:
            data.setdefault("hidden", {})
        return data


class FavoritesStore:
    """Favorites keyed by "<source>:<id>" and hidden collection recipes.

    Saved with the Home Assistant store. Hidden recipes are keyed by the
    KitchenOwl id (as text) and hold the time they were hidden. ``week_lists``
    holds, per Monday (``YYYY-MM-DD``), when the ingredients of that week
    were put on the shopping list, so a second transfer asks first.
    ``week_list_done`` holds, per Monday, the planned entries
    (``YYYY-MM-DD:<id>``) that went through before a transfer stopped
    halfway, so a second try sends only the rest.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the store."""
        self._store: Store[dict[str, Any]] = _EatFreshStore(
            hass, STORAGE_VERSION, STORAGE_KEY, minor_version=STORAGE_MINOR_VERSION
        )
        self._favorites: dict[str, Favorite] = {}
        self._hidden: dict[str, str] = {}
        self._week_lists: dict[str, str] = {}
        self._week_list_done: dict[str, list[str]] = {}

    async def async_load(self) -> None:
        """Load the favorites and hidden recipes from disk.

        A part with the wrong shape (for example a list instead of an
        object) is ignored with a warning, so the integration still starts.
        """
        data = await self._store.async_load() or {}
        if not isinstance(data, dict):
            _LOGGER.warning("Ignoring the EatFresh store: it is not an object")
            data = {}
        favorites = _section(data, "favorites")
        self._favorites = {
            str(key): value
            for key, value in favorites.items()
            if isinstance(value, dict)
        }
        hidden = _section(data, "hidden")
        self._hidden = {
            str(key): str(value) for key, value in hidden.items() if str(key).isdigit()
        }
        week_lists = _section(data, "week_lists")
        self._week_lists = {
            str(key): value
            for key, value in week_lists.items()
            if _is_iso_date(key) and isinstance(value, str)
        }
        week_list_done = _section(data, "week_list_done")
        self._week_list_done = {
            str(key): [str(item) for item in value if isinstance(item, str)]
            for key, value in week_list_done.items()
            if key in self._week_lists and isinstance(value, list)
        }

    @callback
    def _data_to_save(self) -> dict[str, Any]:
        """Return the data to write to disk."""
        return {
            "favorites": dict(self._favorites),
            "hidden": dict(self._hidden),
            "week_lists": dict(self._week_lists),
            "week_list_done": {
                key: list(value) for key, value in self._week_list_done.items()
            },
        }

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

    # ----- hidden recipes -----------------------------------------------

    @callback
    def is_hidden(self, kitchenowl_id: int | None) -> bool:
        """Return True if a KitchenOwl recipe is hidden in EatFresh."""
        return kitchenowl_id is not None and str(kitchenowl_id) in self._hidden

    @callback
    def hidden_ids(self) -> set[int]:
        """Return the KitchenOwl ids of all hidden recipes."""
        return {int(key) for key in self._hidden}

    @callback
    def async_hide(self, kitchenowl_id: int) -> bool:
        """Hide a recipe in the collection. Return False if it was hidden."""
        key = str(int(kitchenowl_id))
        if key in self._hidden:
            return False
        self._hidden[key] = dt_util.utcnow().isoformat()
        self._schedule_save()
        return True

    @callback
    def async_unhide(self, kitchenowl_id: int) -> bool:
        """Show a hidden recipe again. Return True if it was hidden."""
        if self._hidden.pop(str(int(kitchenowl_id)), None) is None:
            return False
        self._schedule_save()
        return True


    # ----- shopping list of a week --------------------------------------

    @callback
    def week_list_time(self, week_start: date) -> str | None:
        """Return when a week went to the shopping list (ISO time) or None."""
        return self._week_lists.get(week_start.isoformat())

    @callback
    def week_list_done(self, week_start: date) -> set[str]:
        """Return the planned entries of a week already sent after a partial try."""
        return set(self._week_list_done.get(week_start.isoformat(), ()))

    @callback
    def async_set_week_list_time(
        self, week_start: date, *, done: Iterable[str] | None = None
    ) -> str:
        """Remember that a week went to the shopping list now; return the time.

        ``done`` lists the planned entries that went through when the
        transfer stopped halfway; without it the week is complete.
        """
        when = dt_util.utcnow().isoformat()
        key = week_start.isoformat()
        # Set again at the end, so among equal times the newest comes last.
        self._week_lists.pop(key, None)
        self._week_lists[key] = when
        if done:
            self._week_list_done[key] = sorted(set(done))
        else:
            self._week_list_done.pop(key, None)
        # Keep only the last transfers (by time, not by the day of the week):
        # a week sent just now stays, however old it is.
        newest = sorted(self._week_lists, key=self._week_lists.__getitem__)
        for old in newest[:-MAX_WEEK_LISTS]:
            del self._week_lists[old]
            self._week_list_done.pop(old, None)
        self._schedule_save()
        return when


def _section(data: dict[str, Any], name: str) -> dict[Any, Any]:
    """Return one part of the stored data, or {} (with a warning) if broken."""
    value = data.get(name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        _LOGGER.warning(
            "Ignoring %s in the EatFresh store: expected an object, got %s",
            name,
            type(value).__name__,
        )
        return {}
    return value


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return len(value) == 10


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
