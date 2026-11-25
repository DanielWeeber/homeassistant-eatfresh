"""Persistent favorites and a small in-memory cache for EatFresh."""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta
from typing import Any, NotRequired, TypedDict

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CACHE_MAX_ENTRIES,
    DONE_DAYS,
    LIST_EXACT_MAX_AGE,
    MAX_LIST_EXACT,
    MAX_PICNIC_AMOUNT,
    MAX_PICNIC_MAP,
    MAX_PICNIC_SENT,
    MAX_PICNIC_SKIP,
    MAX_SHOP_DEPARTMENTS,
    MAX_SHOP_DONE,
    MAX_WEEK_LISTS,
    PICNIC_SENT_MAX_AGE,
    STORAGE_KEY,
    STORAGE_MINOR_VERSION,
    STORAGE_SAVE_DELAY,
    STORAGE_VERSION,
)
from .departments import OTHER
from .kitchenowl import (
    MAX_ITEM_NAME,
    merge_items,
    normalize_source,
    recipe_created_at,
)
from .portions import scale_description

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
        the remembered ingredients of the recipes; 1.5 (EatFresh 0.5.0) adds
        the exact pack counts of the list (``list_exact``), the entries
        ticked off (``shop_done``) and the own groups of ingredients
        (``shop_departments``). The optional smaller product (``small``) in
        ``picnic_map`` and ``picnic_sent`` needs no change of older data.
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
        if old_major_version == 1 and old_minor_version < 5:
            data.setdefault("list_exact", {})
            data.setdefault("shop_done", {})
            data.setdefault("shop_departments", {})
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


class PicnicSmall(TypedDict):
    """A smaller Picnic product for the rest of an ingredient (0.5.0)."""

    product_id: str
    name: str
    unit_quantity: str | None
    price: int | None


class PicnicProduct(TypedDict):
    """The Picnic product remembered for an ingredient.

    ``small`` is an optional smaller product for the rest of the last pack.
    """

    product_id: str
    name: str
    unit_quantity: str | None
    price: int | None
    amount: int | None
    small: NotRequired[PicnicSmall]


class PicnicSentSmall(TypedDict):
    """The smaller product put into the cart for an entry (0.5.0).

    ``name``, ``unit_quantity`` and ``price`` are what was sent, so the
    panel can show it even after the remembered product changed.
    """

    product_id: str
    amount: int
    name: NotRequired[str]
    unit_quantity: NotRequired[str | None]
    price: NotRequired[int | None]


class PicnicSent(TypedDict):
    """What EatFresh put into the Picnic cart for a shopping list entry.

    ``uncertain`` is True when Picnic did not answer in time: the product
    may or may not be in the cart, and it is not sent again by itself.
    ``small`` is the smaller product that went in as well. ``amount`` is 0
    only when ``small`` is there (only the smaller product went in, or the
    main product was already taken out again by "undo").
    ``description`` is the amount text of the entry when it was sent
    (0.5.0); marks of 0.4.x have none.
    """

    product_id: str
    amount: int
    at: str
    uncertain: NotRequired[bool]
    small: NotRequired[PicnicSentSmall]
    description: NotRequired[str]


class ListExact(TypedDict):
    """The exact pack count behind a list entry (0.5.0).

    ``count`` is the whole packs EatFresh put on the list in ``unit``,
    ``exact`` the number before rounding up (summed over all transfers),
    ``at`` the time of the last transfer.
    """

    unit: str
    count: int
    exact: float
    at: str


class ShopDone(TypedDict):
    """An entry ticked off the shopping list (0.5.0).

    ``name`` and ``description`` are as read from the list just before it
    was taken off, so "back on the list" puts the same amount back.
    ``department`` is the group it was in, ``at`` when it was ticked off.
    """

    name: str
    description: str
    department: str
    at: str


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
        self._list_exact: dict[str, ListExact] = {}
        self._shop_done: dict[str, ShopDone] = {}
        self._shop_departments: dict[str, str] = {}

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
        self._list_exact = {
            str(int(key)): row
            for key, value in _section(data, "list_exact").items()
            if str(key).isdigit() and (row := _list_exact(value)) is not None
        }
        self._list_exact = dict(list(self._list_exact.items())[-MAX_LIST_EXACT:])
        self._shop_done = {
            str(int(key)): row
            for key, value in _section(data, "shop_done").items()
            if str(key).isdigit() and (row := _shop_done(value)) is not None
        }
        self._shop_done = dict(list(self._shop_done.items())[-MAX_SHOP_DONE:])
        self._shop_departments = {}
        for key, value in _section(data, "shop_departments").items():
            if isinstance(value, str) and value and picnic_key(key):
                self._shop_departments[picnic_key(key)] = value
        self._shop_departments = dict(
            list(self._shop_departments.items())[-MAX_SHOP_DEPARTMENTS:]
        )
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
            "picnic_map": {
                key: _plain_copy(value) for key, value in self._picnic_map.items()
            },
            "picnic_skip": list(self._picnic_skip),
            "picnic_sent": {
                key: _plain_copy(value) for key, value in self._picnic_sent.items()
            },
            "list_exact": {key: dict(value) for key, value in self._list_exact.items()},
            "shop_done": {key: dict(value) for key, value in self._shop_done.items()},
            "shop_departments": dict(self._shop_departments),
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
        if (
            self._ingredients.get(key) == rows
            and self._ingredient_meta.get(key) == meta
        ):
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
        """Remember the Picnic product of an ingredient (the newest last).

        A remembered smaller product of the ingredient stays.
        """
        key = picnic_key(name)
        old = self._picnic_map.pop(key, None)
        product: PicnicProduct = {
            "product_id": product_id,
            "name": product_name,
            "unit_quantity": unit_quantity,
            "price": price,
            "amount": amount,
        }
        if old is not None and "small" in old:
            product["small"] = old["small"]
        self._picnic_map[key] = product
        while len(self._picnic_map) > MAX_PICNIC_MAP:
            del self._picnic_map[next(iter(self._picnic_map))]
        self._schedule_save()

    @callback
    def picnic_small(self, name: str) -> PicnicSmall | None:
        """Return the smaller product remembered for an ingredient or None."""
        product = self._picnic_map.get(picnic_key(name))
        return None if product is None else product.get("small")

    @callback
    def async_set_picnic_small(
        self, name: str, small: Mapping[str, Any] | None
    ) -> bool:
        """Remember (or with None forget) the smaller product of an ingredient.

        Only for an ingredient with a remembered main product: returns False
        (and changes nothing) without one.
        """
        product = self._picnic_map.get(picnic_key(name))
        if product is None:
            return False
        if small is None:
            if product.pop("small", None) is not None:
                self._schedule_save()
            return True
        product["small"] = {
            "product_id": str(small["product_id"]),
            "name": str(small["name"]),
            "unit_quantity": small.get("unit_quantity") or None,
            "price": small.get("price"),
        }
        self._schedule_save()
        return True

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
        self,
        item_id: int,
        product_id: str,
        amount: int,
        uncertain: bool = False,
        *,
        small: Mapping[str, Any] | None = None,
        at: str | None = None,
        description: str | None = None,
    ) -> str:
        """Mark a list entry as put into the cart now; return the time.

        ``uncertain``: Picnic did not answer in time, so it may be there.
        ``small``: the smaller product that went in as well
        (``{product_id, amount, name, unit_quantity, price}``). ``at`` keeps
        the time of an earlier mark instead of now. ``description``: the
        amount text of the entry on the list when it was sent.
        """
        when = at or dt_util.utcnow().isoformat()
        key = str(int(item_id))
        self._picnic_sent.pop(key, None)
        mark: PicnicSent = {
            "product_id": product_id,
            "amount": int(amount),
            "at": when,
        }
        if uncertain:
            mark["uncertain"] = True
        if small is not None:
            mark["small"] = _sent_small_copy(small)
        if isinstance(description, str):
            mark["description"] = description
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
    def async_prune_picnic_sent(
        self,
        on_list: Iterable[int],
        descriptions: Mapping[int, str] | None = None,
    ) -> None:
        """Drop marks of entries no longer on the list, and old unclear ones.

        A mark lives 3 days (0.5.0). A mark surely in the cart stays while
        its entry is on the list, even when older: the entry is taken off
        the list first (see :meth:`due_cart_marks`), and the mark goes with
        it. An unclear mark ("maybe in the cart") goes after 3 days, its
        entry stays on the list. So does a sure mark that is never taken
        off: one without a remembered amount text (0.4.x), or one whose
        amount text differs from ``descriptions`` (the amount texts of the
        list as just read, by item id).
        """
        keep = {str(int(item_id)) for item_id in on_list}
        texts = {str(int(k)): v for k, v in (descriptions or {}).items()}
        oldest = dt_util.utcnow() - PICNIC_SENT_MAX_AGE
        gone = [
            key
            for key, sent in self._picnic_sent.items()
            if key not in keep
            or (
                _older_than(sent["at"], oldest)
                and (
                    sent.get("uncertain")
                    or "description" not in sent
                    or (key in texts and cart_text_changed(sent, texts[key]))
                )
            )
        ]
        for key in gone:
            del self._picnic_sent[key]
        if gone:
            self._schedule_save()

    @callback
    def due_cart_marks(self, descriptions: Mapping[int, str]) -> list[int]:
        """Return the entries on the list surely in the cart for 3 days or more.

        ``descriptions`` are the amount texts of the list as just read, by
        item id. Oldest first. Due is only a mark whose remembered amount
        text is still the one on the list: never an unclear mark, never one
        of 0.4.x (no amount text), never one whose entry grew or changed.
        """
        texts = {int(k): v for k, v in descriptions.items()}
        oldest = dt_util.utcnow() - PICNIC_SENT_MAX_AGE
        due = [
            (sent["at"], int(key))
            for key, sent in self._picnic_sent.items()
            if int(key) in texts
            and not sent.get("uncertain")
            and "description" in sent
            and not cart_text_changed(sent, texts[int(key)])
            and _older_than(sent["at"], oldest)
        ]
        return [item_id for _at, item_id in sorted(due)]

    # ----- entries ticked off and own groups (0.5.0) ----------------------

    @callback
    def shop_done(self, item_id: int) -> ShopDone | None:
        """Return the entry ticked off with this item id, if not too old."""
        row = self._shop_done.get(str(int(item_id)))
        if row is None or _older_than(row["at"], _done_limit()):
            return None
        return row

    @callback
    def shop_done_entries(self) -> list[tuple[int, ShopDone]]:
        """Return the entries ticked off, newest first.

        Entries older than 3 days are dropped here.
        """
        limit = _done_limit()
        gone = [
            k for k, row in self._shop_done.items() if _older_than(row["at"], limit)
        ]
        for key in gone:
            del self._shop_done[key]
        if gone:
            self._schedule_save()
        rows = [(int(key), row) for key, row in self._shop_done.items()]
        return sorted(rows, key=lambda item: item[1]["at"], reverse=True)

    @callback
    def async_set_shop_done(
        self, item_id: int, name: str, description: str, department: str
    ) -> str:
        """Remember an entry just ticked off; return the time."""
        when = dt_util.utcnow().isoformat()
        key = str(int(item_id))
        self._shop_done.pop(key, None)
        self._shop_done[key] = {
            "name": name,
            "description": description,
            "department": department,
            "at": when,
        }
        while len(self._shop_done) > MAX_SHOP_DONE:
            del self._shop_done[next(iter(self._shop_done))]
        self._schedule_save()
        return when

    @callback
    def async_pop_shop_done(self, item_id: int) -> ShopDone | None:
        """Take an entry ticked off out of the store and return it, or None.

        Too old entries count as gone (and are dropped as well).
        """
        row = self._shop_done.pop(str(int(item_id)), None)
        if row is None:
            return None
        self._schedule_save()
        if _older_than(row["at"], _done_limit()):
            return None
        return row

    @callback
    def async_put_back_shop_done(self, item_id: int, row: Mapping[str, Any]) -> None:
        """Put an entry taken out by :meth:`async_pop_shop_done` back, as it was."""
        if (entry := _shop_done(dict(row))) is None:
            return
        self._shop_done[str(int(item_id))] = entry
        while len(self._shop_done) > MAX_SHOP_DONE:
            del self._shop_done[next(iter(self._shop_done))]
        self._schedule_save()

    @callback
    def async_remove_shop_done(self, item_id: int) -> bool:
        """Forget an entry ticked off. True if there was one."""
        if self._shop_done.pop(str(int(item_id)), None) is None:
            return False
        self._schedule_save()
        return True

    @callback
    def shop_department(self, name: str) -> str | None:
        """Return the group the user chose for an ingredient, or None."""
        return self._shop_departments.get(picnic_key(name))

    @callback
    def async_set_shop_department(self, name: str, department: str) -> None:
        """Remember the group the user chose for an ingredient (newest last)."""
        key = picnic_key(name)
        if not key:
            return
        self._shop_departments.pop(key, None)
        self._shop_departments[key] = department
        while len(self._shop_departments) > MAX_SHOP_DEPARTMENTS:
            del self._shop_departments[next(iter(self._shop_departments))]
        self._schedule_save()

    # ----- exact pack counts of the list (0.5.0) -------------------------

    @callback
    def list_exact(self, item_id: int) -> ListExact | None:
        """Return the remembered exact pack count of a list entry or None."""
        return self._list_exact.get(str(int(item_id)))

    @callback
    def async_add_list_exact(
        self, item_id: int, packages: Iterable[tuple[str, int, float]]
    ) -> None:
        """Add the packs of one transfer of an item to its remembered row.

        ``packages`` is ``Scaled.packages`` of the amount text that went on
        the list: (unit, whole packs, exact number). Parts of the same unit
        are summed, also with a row of an earlier transfer (KitchenOwl sums
        the amounts on the list as well). Another unit for the same item
        (within the text or against the row) drops the row: no proposal.
        """
        parts = list(packages)
        if not parts:
            return
        key = str(int(item_id))
        units = {unit for unit, _count, _exact in parts}
        old = self._list_exact.pop(key, None)
        if len(units) != 1 or (old is not None and old["unit"] not in units):
            self._schedule_save()
            return
        count = sum(int(count) for _unit, count, _exact in parts)
        exact = sum(float(exact) for _unit, _count, exact in parts)
        if old is not None:
            count += old["count"]
            exact += old["exact"]
        self._list_exact[key] = {
            "unit": next(iter(units)),
            "count": count,
            "exact": round(exact, 4),
            "at": dt_util.utcnow().isoformat(),
        }
        while len(self._list_exact) > MAX_LIST_EXACT:
            del self._list_exact[next(iter(self._list_exact))]
        self._schedule_save()

    @callback
    def async_remove_list_exact(self, item_id: int) -> None:
        """Forget the exact pack count of one entry (it left the list)."""
        if self._list_exact.pop(str(int(item_id)), None) is not None:
            self._schedule_save()

    @callback
    def async_clear_list_exact(self) -> None:
        """Forget every remembered exact pack count."""
        if self._list_exact:
            self._list_exact.clear()
            self._schedule_save()

    @callback
    def async_prune_list_exact(self, rows: Iterable[Mapping[str, Any]]) -> None:
        """Keep only rows valid for the shopping list as just read.

        A row goes when its item is no longer on the list, when it is older
        than 14 days, or when the list no longer says ``count`` packs of its
        unit (someone changed the list by hand).
        """
        on_list = {str(int(row["id"])): row.get("description") or "" for row in rows}
        oldest = dt_util.utcnow() - LIST_EXACT_MAX_AGE
        gone = [
            key
            for key, row in self._list_exact.items()
            if key not in on_list
            or _older_than(row["at"], oldest)
            or list_count(on_list[key], row["unit"]) != row["count"]
        ]
        for key in gone:
            del self._list_exact[key]
        if gone:
            self._schedule_save()

    @callback
    def valid_list_exact(self, item_id: int, description: str) -> ListExact | None:
        """Return the row of a list entry if it still fits the list, else None.

        A row that does not fit (other count of its unit, or too old) is
        dropped.
        """
        key = str(int(item_id))
        row = self._list_exact.get(key)
        if row is None:
            return None
        oldest = dt_util.utcnow() - LIST_EXACT_MAX_AGE
        if _older_than(row["at"], oldest) or (
            list_count(description, row["unit"]) != row["count"]
        ):
            del self._list_exact[key]
            self._schedule_save()
            return None
        return row


def list_count(description: str, unit: str) -> int:
    """Return the whole packs of ``unit`` an amount text on the list says.

    Parts of the same (canonical) unit are summed; 0 without such a part.
    """
    return sum(
        count
        for part_unit, count, _exact in scale_description(
            description or "", None, None
        ).packages
        if part_unit == unit
    )


def cart_text_changed(mark: Mapping[str, Any], description: str | None) -> bool:
    """True if the amount text of a cart mark is not the one on the list now.

    Exact, character for character, after removing blanks at both ends. A
    mark without a remembered text (0.4.x) never counts as changed.
    """
    sent = mark.get("description")
    if not isinstance(sent, str):
        return False
    return sent.strip() != (description or "").strip()


def _plain_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a stored mark or product, with its nested ``small`` copied too."""
    copy = dict(value)
    if isinstance(copy.get("small"), Mapping):
        copy["small"] = dict(copy["small"])
    return copy


def _sent_small_copy(small: Mapping[str, Any]) -> PicnicSentSmall:
    """Return the stored form of the smaller product put into the cart."""
    copy: PicnicSentSmall = {
        "product_id": str(small["product_id"]),
        "amount": int(small["amount"]),
    }
    if isinstance(small.get("name"), str) and small["name"]:
        copy["name"] = small["name"]
    if "unit_quantity" in small:
        unit = small.get("unit_quantity")
        copy["unit_quantity"] = unit if isinstance(unit, str) and unit else None
    if "price" in small:
        price = small.get("price")
        copy["price"] = price if _is_count(price, 0) else None
    return copy


def _is_count(value: Any, minimum: int) -> bool:
    """True for a whole number (not a bool) of at least ``minimum``."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _list_exact(value: Any) -> ListExact | None:
    """Return a stored exact pack count if it has the right shape."""
    if not isinstance(value, dict):
        return None
    unit = value.get("unit")
    count = value.get("count")
    exact = value.get("exact")
    at = value.get("at")
    if not isinstance(unit, str) or not unit or not _is_count(count, 1):
        return None
    if isinstance(exact, bool) or not isinstance(exact, (int, float)) or exact <= 0:
        return None
    if not isinstance(at, str) or dt_util.parse_datetime(at) is None:
        return None
    return {"unit": unit, "count": count, "exact": float(exact), "at": at}


def _done_limit() -> datetime:
    """Return the time before which an entry ticked off is forgotten."""
    return dt_util.utcnow() - timedelta(days=DONE_DAYS)


def _shop_done(value: Any) -> ShopDone | None:
    """Return a stored entry ticked off if it has the right shape."""
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    description = value.get("description")
    department = value.get("department")
    at = value.get("at")
    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(at, str) or dt_util.parse_datetime(at) is None:
        return None
    return {
        "name": name,
        "description": description if isinstance(description, str) else "",
        "department": department
        if isinstance(department, str) and department
        else OTHER,
        "at": at,
    }


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
    product: PicnicProduct = {
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
    if (small := _picnic_small(value.get("small"))) is not None:
        product["small"] = small
    return product


def _picnic_small(value: Any) -> PicnicSmall | None:
    """Return a stored smaller product if it has the right shape."""
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
    return {
        "product_id": product_id,
        "name": name,
        "unit_quantity": unit if isinstance(unit, str) and unit else None,
        "price": price if _is_count(price, 0) else None,
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
    small = value.get("small")
    if isinstance(small, dict) and (
        isinstance(small.get("product_id"), str)
        and small["product_id"]
        and _is_count(small.get("amount"), 1)
        and small["amount"] <= MAX_PICNIC_AMOUNT
    ):
        small_copy: PicnicSentSmall | None = _sent_small_copy(small)
    else:
        small_copy = None
    # Without a smaller product the main product has at least one piece.
    if not _is_count(amount, 0 if small_copy is not None else 1):
        return None
    if not isinstance(at, str) or dt_util.parse_datetime(at) is None:
        return None
    mark: PicnicSent = {"product_id": product_id, "amount": amount, "at": at}
    if value.get("uncertain") is True:
        mark["uncertain"] = True
    if small_copy is not None:
        mark["small"] = small_copy
    if isinstance(value.get("description"), str):
        mark["description"] = value["description"]
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
