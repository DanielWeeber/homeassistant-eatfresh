"""Persistent favorites and a small in-memory cache for EatFresh."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable
from datetime import date, datetime, timedelta
import logging
import time
from typing import Any, NotRequired, TypedDict

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CACHE_MAX_ENTRIES,
    MAX_PICNIC_MAP,
    MAX_PICNIC_SENT,
    MAX_PICNIC_SKIP,
    MAX_WEEK_LISTS,
    PICNIC_SENT_MAX_AGE,
    STORAGE_KEY,
    STORAGE_MINOR_VERSION,
    STORAGE_SAVE_DELAY,
    STORAGE_VERSION,
)
from .kitchenowl import (
    MAX_ITEM_NAME,
    merge_items,
    normalize_source,
    recipe_created_at,
)

_LOGGER = logging.getLogger(__name__)

# Limits of the memory of ingredients: beyond them nothing new is remembered.
MAX_REMEMBERED_ITEMS = 300
MAX_REMEMBERED_RECIPES = 3000
# A recipe is forgotten once it has been in no recipe list for this long.
FORGET_RECIPE_AFTER = timedelta(days=30)


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

        1.1 (EatFresh 0.1.0) had only favorites; 1.2 adds hidden recipes;
        1.3 (EatFresh 0.4.0) adds the Picnic parts; 1.4 (EatFresh 0.4.1) adds
        the remembered ingredients of the recipes.
        """
        data = dict(old_data or {})
        if old_major_version == 1 and old_minor_version < 2:
            data.setdefault("hidden", {})
        if old_major_version == 1 and old_minor_version < 3:
            data.setdefault("picnic_map", {})
            data.setdefault("picnic_skip", [])
            data.setdefault("picnic_sent", {})
        if old_major_version == 1 and old_minor_version < 4:
            data.setdefault("ingredients", {})
        return data


class RememberedItem(TypedDict):
    """One remembered ingredient of a KitchenOwl recipe.

    ``id`` is the KitchenOwl item id, or None when it is not known (created
    by EatFresh and not read back yet, or missing in KitchenOwl).
    """

    id: int | None
    name: str
    description: str
    optional: bool


class IngredientMeta(TypedDict, total=False):
    """What EatFresh knows about a remembered recipe besides its items.

    ``seen`` is the day (``YYYY-MM-DD``) it was last in a recipe list or
    read; ``created_at`` KitchenOwl's creation time in milliseconds.
    """

    seen: str
    created_at: int


class PicnicProduct(TypedDict):
    """The Picnic product remembered for an ingredient."""

    product_id: str
    name: str
    unit_quantity: str | None
    price: int | None
    amount: int | None


class PicnicSent(TypedDict):
    """What EatFresh put into the Picnic cart for a shopping list entry.

    ``uncertain`` is True when Picnic did not answer in time: the product
    may or may not be in the cart, and it is not sent again by itself.
    """

    product_id: str
    amount: int
    at: str
    uncertain: NotRequired[bool]


def picnic_key(name: str) -> str:
    """Return the key of an ingredient: lower case, single spaces."""
    return " ".join(str(name).split()).lower()


class FavoritesStore:
    """Favorites keyed by "<source>:<id>" and hidden collection recipes.

    Saved with the Home Assistant store. Hidden recipes are keyed by the
    KitchenOwl id (as text) and hold the time they were hidden. ``week_lists``
    holds, per Monday (``YYYY-MM-DD``), when the ingredients of that week
    were put on the shopping list, so a second transfer asks first.
    ``week_list_done`` holds, per Monday, the planned entries
    (``YYYY-MM-DD:<id>``) that went through before a transfer stopped
    halfway, so a second try sends only the rest.
    ``ingredients`` holds, per KitchenOwl recipe id (as text), the
    ingredients EatFresh has seen in it, so an item deleted in KitchenOwl is
    not lost (see :func:`merge_items`). ``ingredient_meta`` holds, per
    recipe id, ``seen`` (the day, ``YYYY-MM-DD``, the recipe was last in a
    recipe list or read) and ``created_at`` (KitchenOwl's creation time in
    milliseconds, when known), so a reused id is noticed.
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
        self._picnic_map: dict[str, PicnicProduct] = {}
        self._picnic_skip: list[str] = []
        self._picnic_sent: dict[str, PicnicSent] = {}
        self._ingredients: dict[str, list[RememberedItem]] = {}
        self._ingredient_meta: dict[str, IngredientMeta] = {}

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
        self._picnic_map = {}
        for key, value in _section(data, "picnic_map").items():
            if (product := _picnic_product(value)) is not None and picnic_key(key):
                self._picnic_map[picnic_key(key)] = product
        self._picnic_map = dict(list(self._picnic_map.items())[-MAX_PICNIC_MAP:])
        skip = data.get("picnic_skip")
        if skip is not None and not isinstance(skip, list):
            _LOGGER.warning("Ignoring picnic_skip in the EatFresh store: not a list")
            skip = []
        self._picnic_skip = list(
            dict.fromkeys(
                picnic_key(name)
                for name in skip or ()
                if isinstance(name, str) and picnic_key(name)
            )
        )[-MAX_PICNIC_SKIP:]
        self._picnic_sent = {
            str(key): sent
            for key, value in _section(data, "picnic_sent").items()
            if str(key).isdigit() and (sent := _picnic_sent(value)) is not None
        }
        self._ingredients = {}
        for key, value in _section(data, "ingredients").items():
            if not str(key).isdigit() or not isinstance(value, list):
                continue
            if len(self._ingredients) >= MAX_REMEMBERED_RECIPES:
                _LOGGER.debug("Ignoring remembered ingredients beyond the limit")
                break
            self._ingredients[str(int(key))] = [
                row for item in value if (row := _remembered_item(item)) is not None
            ][:MAX_REMEMBERED_ITEMS]
        stored_meta = {
            str(int(key)): value
            for key, value in _section(data, "ingredient_meta").items()
            if str(key).isdigit()
        }
        self._ingredient_meta = {}
        today = _today()
        filled = False
        for key in self._ingredients:
            meta = _ingredient_meta(stored_meta.get(key))
            if "seen" not in meta:
                # Not known yet (memory of an older file): seen today.
                meta["seen"] = today
                filled = True
            self._ingredient_meta[key] = meta
        if filled:
            self._schedule_save()

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
            "picnic_map": {key: dict(value) for key, value in self._picnic_map.items()},
            "picnic_skip": list(self._picnic_skip),
            "picnic_sent": {
                key: dict(value) for key, value in self._picnic_sent.items()
            },
            "ingredients": {
                key: [dict(row) for row in rows]
                for key, rows in self._ingredients.items()
            },
            "ingredient_meta": {
                key: dict(value) for key, value in self._ingredient_meta.items()
            },
        }

    async def async_save_now(self) -> None:
        """Write everything to disk now (marks of the Picnic cart).

        A pending delayed write is replaced by this one.
        """
        await self._store.async_save(self._data_to_save())

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


    # ----- remembered ingredients ---------------------------------------

    @callback
    def recipe_ingredients(self, kitchenowl_id: int) -> list[RememberedItem] | None:
        """Return the remembered ingredients of a recipe, or None if unknown."""
        rows = self._ingredients.get(str(int(kitchenowl_id)))
        if rows is None:
            return None
        return [RememberedItem(**row) for row in rows]

    @callback
    def recipe_seen(self, kitchenowl_id: int) -> str | None:
        """Return the day a remembered recipe was last seen, or None."""
        return self._ingredient_meta.get(str(int(kitchenowl_id)), {}).get("seen")

    @callback
    def _room_for(self, key: str) -> bool:
        """Return whether a recipe may be remembered (limit of recipes)."""
        if key in self._ingredients or len(self._ingredients) < MAX_REMEMBERED_RECIPES:
            return True
        _LOGGER.debug(
            "Not remembering the ingredients of recipe %s: %s recipes remembered",
            key,
            MAX_REMEMBERED_RECIPES,
        )
        return False

    @callback
    def _put_ingredients(
        self, key: str, rows: list[RememberedItem], meta: IngredientMeta
    ) -> None:
        """Store rows (cut to the limit) and meta; save only on a change."""
        if len(rows) > MAX_REMEMBERED_ITEMS:
            _LOGGER.debug(
                "Remembering only %s ingredients of recipe %s",
                MAX_REMEMBERED_ITEMS,
                key,
            )
            rows = rows[:MAX_REMEMBERED_ITEMS]
        if self._ingredients.get(key) == rows and self._ingredient_meta.get(key) == meta:
            return
        self._ingredients[key] = rows
        self._ingredient_meta[key] = meta
        self._schedule_save()

    @callback
    def async_learn_ingredients(
        self, kitchenowl_id: int, current: Iterable[Any], created_at: Any = None
    ) -> list[RememberedItem]:
        """Merge the current items of a recipe into the memory.

        Return the remembered ingredients that are missing in KitchenOwl.
        ``created_at`` is KitchenOwl's creation time of the recipe: if it
        differs from the remembered one, the id was given to a new recipe and
        the memory starts over with the current items. Without it nothing is
        checked. The recipe counts as seen today. Saved only when something
        changed (so the date costs at most one write a day).
        """
        key = str(int(kitchenowl_id))
        if not self._room_for(key):
            return []
        rows = [
            row
            for item in current
            if (row := _remembered_item(item, keep_unknown=True)) is not None
        ]
        memory = self._ingredients.get(key)
        meta = dict(self._ingredient_meta.get(key, {}))
        created = _created_at(created_at)
        if (
            memory is not None
            and created is not None
            and meta.get("created_at") is not None
            and meta["created_at"] != created
        ):
            _LOGGER.debug(
                "Recipe %s is a new recipe in KitchenOwl; its memory starts over", key
            )
            memory = None
        merged, missing = merge_items(memory, rows)
        if created is not None:
            meta["created_at"] = created
        meta["seen"] = _today()
        self._put_ingredients(
            key,
            [row for item in merged if (row := _remembered_item(item)) is not None],
            IngredientMeta(**meta),
        )
        remembered = self._ingredients.get(key, [])
        return [
            RememberedItem(**row)
            for item in missing
            if (row := _remembered_item(item)) is not None and row in remembered
        ]

    @callback
    def async_set_ingredients(self, kitchenowl_id: int, items: Iterable[Any]) -> None:
        """Replace the remembered ingredients of a recipe (keeps its meta)."""
        key = str(int(kitchenowl_id))
        if not self._room_for(key):
            return
        rows = [row for item in items if (row := _remembered_item(item)) is not None]
        meta = IngredientMeta(**self._ingredient_meta.get(key, {}))
        meta.setdefault("seen", _today())
        self._put_ingredients(key, rows, meta)

    @callback
    def async_start_ingredients(
        self, kitchenowl_id: int, items: Iterable[Any], created_at: Any = None
    ) -> None:
        """Remember the items of a recipe EatFresh just created.

        Replaces whatever was remembered for this id before (KitchenOwl may
        give the id of a deleted recipe to a new one), without mixing.
        ``created_at`` is KitchenOwl's creation time if the answer had one.
        """
        key = str(int(kitchenowl_id))
        if not self._room_for(key):
            return
        rows = [row for item in items if (row := _remembered_item(item)) is not None]
        meta = IngredientMeta(seen=_today())
        if (created := recipe_created_at(created_at)) is not None:
            meta["created_at"] = created
        self._put_ingredients(key, rows, meta)

    @callback
    def async_prune_ingredients(self, keep: Iterable[int]) -> None:
        """Note the recipes of a fresh list; forget long gone ones.

        Every recipe in ``keep`` counts as seen today. A remembered recipe is
        forgotten only when it has been in no list for more than 30 days
        (:data:`FORGET_RECIPE_AFTER`). An empty list forgets nothing: it may
        be a broken answer.
        """
        wanted = {str(int(kitchenowl_id)) for kitchenowl_id in keep}
        if not wanted:
            _LOGGER.debug("Empty recipe list: no remembered recipe is forgotten")
            return
        today = _today()
        limit = (dt_util.now().date() - FORGET_RECIPE_AFTER).isoformat()
        changed = False
        for key in list(self._ingredients):
            if key not in self._ingredient_meta:
                self._ingredient_meta[key] = IngredientMeta(seen=today)
                changed = True
            meta = self._ingredient_meta[key]
            if key in wanted:
                if meta.get("seen") != today:
                    meta["seen"] = today
                    changed = True
            elif meta.get("seen", today) < limit:
                del self._ingredients[key]
                self._ingredient_meta.pop(key, None)
                changed = True
        if changed:
            self._schedule_save()

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

    # ----- Picnic -------------------------------------------------------

    @callback
    def picnic_product(self, name: str) -> PicnicProduct | None:
        """Return the Picnic product remembered for an ingredient or None."""
        return self._picnic_map.get(picnic_key(name))

    @callback
    def async_set_picnic_product(
        self,
        name: str,
        *,
        product_id: str,
        product_name: str,
        unit_quantity: str | None,
        price: int | None,
        amount: int | None,
    ) -> None:
        """Remember the Picnic product of an ingredient (the newest last)."""
        key = picnic_key(name)
        self._picnic_map.pop(key, None)
        self._picnic_map[key] = {
            "product_id": product_id,
            "name": product_name,
            "unit_quantity": unit_quantity,
            "price": price,
            "amount": amount,
        }
        while len(self._picnic_map) > MAX_PICNIC_MAP:
            del self._picnic_map[next(iter(self._picnic_map))]
        self._schedule_save()

    @callback
    def async_remove_picnic_product(self, name: str) -> bool:
        """Forget the Picnic product of an ingredient. True if there was one."""
        if self._picnic_map.pop(picnic_key(name), None) is None:
            return False
        self._schedule_save()
        return True

    @callback
    def is_picnic_skipped(self, name: str) -> bool:
        """Return True if an ingredient is never bought at Picnic."""
        return picnic_key(name) in self._picnic_skip

    @callback
    def async_set_picnic_skip(self, name: str, skip: bool) -> None:
        """Exclude an ingredient from Picnic, or take it back in."""
        key = picnic_key(name)
        if (key in self._picnic_skip) == skip:
            return
        if skip:
            self._picnic_skip.append(key)
            del self._picnic_skip[:-MAX_PICNIC_SKIP]
        else:
            self._picnic_skip.remove(key)
        self._schedule_save()

    @callback
    def picnic_sent(self, item_id: int) -> PicnicSent | None:
        """Return what was put into the cart for a list entry, or None."""
        return self._picnic_sent.get(str(int(item_id)))

    @callback
    def async_set_picnic_sent(
        self, item_id: int, product_id: str, amount: int, uncertain: bool = False
    ) -> str:
        """Mark a list entry as put into the cart now; return the time.

        ``uncertain``: Picnic did not answer in time, so it may be there.
        """
        when = dt_util.utcnow().isoformat()
        key = str(int(item_id))
        self._picnic_sent.pop(key, None)
        mark: PicnicSent = {
            "product_id": product_id,
            "amount": int(amount),
            "at": when,
        }
        if uncertain:
            mark["uncertain"] = True
        self._picnic_sent[key] = mark
        while len(self._picnic_sent) > MAX_PICNIC_SENT:
            del self._picnic_sent[next(iter(self._picnic_sent))]
        self._schedule_save()
        return when

    @callback
    def async_remove_picnic_sent(self, item_id: int) -> bool:
        """Remove the mark of a list entry. True if there was one."""
        if self._picnic_sent.pop(str(int(item_id)), None) is None:
            return False
        self._schedule_save()
        return True

    @callback
    def async_prune_picnic_sent(self, on_list: Iterable[int]) -> None:
        """Drop marks older than 14 days or of entries no longer on the list."""
        keep = {str(int(item_id)) for item_id in on_list}
        oldest = dt_util.utcnow() - PICNIC_SENT_MAX_AGE
        gone = [
            key
            for key, sent in self._picnic_sent.items()
            if key not in keep or _older_than(sent["at"], oldest)
        ]
        for key in gone:
            del self._picnic_sent[key]
        if gone:
            self._schedule_save()


def _older_than(value: str, limit: datetime) -> bool:
    """Return True if an ISO time is before ``limit`` (or unreadable)."""
    when = dt_util.parse_datetime(value)
    if when is None:
        return True
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt_util.UTC)
    return when < limit


def _remembered_item(value: Any, keep_unknown: bool = False) -> RememberedItem | None:
    """Return a remembered ingredient if it has the right shape.

    With ``keep_unknown`` a ``description`` or ``optional`` of None stays
    None (unknown, see :func:`merge_items`); otherwise it becomes ``""`` or
    False.
    """
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    if not isinstance(name, str) or not " ".join(name.split()):
        return None
    item_id = value.get("id")
    description = value.get("description")
    optional = value.get("optional")
    return {
        "id": item_id
        if isinstance(item_id, int) and not isinstance(item_id, bool)
        else None,
        "name": " ".join(name.split())[:MAX_ITEM_NAME],
        "description": None  # type: ignore[typeddict-item]
        if keep_unknown and description is None
        else description
        if isinstance(description, str)
        else "",
        "optional": None  # type: ignore[typeddict-item]
        if keep_unknown and optional is None
        else optional is True,
    }


def _today() -> str:
    """Return today's local date as ``YYYY-MM-DD``."""
    return dt_util.now().date().isoformat()


def _created_at(value: Any) -> int | None:
    """Return a KitchenOwl creation time (milliseconds) or None."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _ingredient_meta(value: Any) -> IngredientMeta:
    """Return the stored meta of a remembered recipe; broken parts dropped."""
    meta = IngredientMeta()
    if not isinstance(value, dict):
        return meta
    seen = value.get("seen")
    if _is_iso_date(seen):
        meta["seen"] = seen
    if (created := _created_at(value.get("created_at"))) is not None:
        meta["created_at"] = created
    return meta


def _picnic_product(value: Any) -> PicnicProduct | None:
    """Return a stored Picnic product if it has the right shape."""
    if not isinstance(value, dict):
        return None
    product_id = value.get("product_id")
    name = value.get("name")
    if not isinstance(product_id, str) or not product_id:
        return None
    if not isinstance(name, str) or not name:
        return None
    unit = value.get("unit_quantity")
    price = value.get("price")
    amount = value.get("amount")
    return {
        "product_id": product_id,
        "name": name,
        "unit_quantity": unit if isinstance(unit, str) else None,
        "price": price
        if isinstance(price, int) and not isinstance(price, bool) and price >= 0
        else None,
        "amount": amount
        if isinstance(amount, int) and not isinstance(amount, bool) and amount >= 1
        else None,
    }


def _picnic_sent(value: Any) -> PicnicSent | None:
    """Return a stored cart mark if it has the right shape."""
    if not isinstance(value, dict):
        return None
    product_id = value.get("product_id")
    amount = value.get("amount")
    at = value.get("at")
    if not isinstance(product_id, str) or not product_id:
        return None
    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 1:
        return None
    if not isinstance(at, str) or dt_util.parse_datetime(at) is None:
        return None
    mark: PicnicSent = {"product_id": product_id, "amount": amount, "at": at}
    if value.get("uncertain") is True:
        mark["uncertain"] = True
    return mark


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
