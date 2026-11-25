"""Runtime state and the shared logic behind WebSocket commands and actions."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util
from yarl import URL

from . import kitchenowl as kitchenowl_module
from . import picnic
from .categories import canonical_category, category_names, suggest_categories
from .const import (
    CATEGORY_CACHE_TTL,
    CHEFKOCH,
    CONF_ACCEPT_CHEFKOCH,
    CONF_DEFAULT_SERVINGS,
    CONF_PLANNER_INTERVAL,
    CONF_SOURCES,
    CONF_WRITE_CATEGORIES,
    DEFAULT_COLLECTION_LIMIT,
    DEFAULT_PLANNER_INTERVAL,
    DEFAULT_WRITE_CATEGORIES,
    DOMAIN,
    DONE_DAYS,
    ERR_ITEM_GONE,
    ERR_NOT_DONE,
    ERR_NOT_ON_LIST,
    ERR_PLAN_ENTRY_LOST,
    ERR_UNKNOWN_DEPARTMENT,
    ERR_UNSCHEDULED_ENTRY,
    JSONLD,
    MAX_CATEGORY_WRITES,
    MAX_PLANNER_INTERVAL,
    MAX_TAG_LENGTH,
    MAX_TAGS,
    MIN_PLANNER_INTERVAL,
    PLANNER_MAX_AGE,
    RECIPE_CACHE_TTL,
    SEARCH_CACHE_TTL,
)
from .departments import (
    DEPARTMENTS,
    KITCHENOWL_DEFAULT_KEYS,
    OTHER,
    classify,
    department_name,
    match_category_name,
)
from .errors import EatFreshError, KitchenOwlAuthError, KitchenOwlError, RecipeNotFound
from .http import UnsafeAddress, check_public_url, host_matches, split_url
from .kitchenowl import ingredient_key, item_rows, merge_items, normalize_source
from .models import Ingredient, Recipe, SearchHit, split_key
from .picnic_amount import suggest_split
from .portions import (
    DEFAULT_SERVINGS,
    MAX_DEFAULT_SERVINGS,
    MAX_SERVINGS,
    MIN_SERVINGS,
    scale_description,
    start_servings,
)
from .store import (
    Favorite,
    FavoritesStore,
    RememberedItem,
    TTLCache,
    cart_text_changed,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import PlannerCoordinator
    from .kitchenowl import KitchenOwlClient
    from .sources.base import RecipeSource

_LOGGER = logging.getLogger(__name__)

# Message of ``RecipeNotFound`` for an id outside the own household.
NOT_IN_COLLECTION = "The recipe is not in the collection"


def is_http_url(url: object) -> bool:
    """Return True for an http(s) address with a host (as aiohttp reads it)."""
    if not isinstance(url, str):
        return False
    try:
        scheme, host, _port = split_url(url)
    except UnsafeAddress:
        return False
    return scheme in ("http", "https") and bool(host)


class ShoppingListPartial(KitchenOwlError):
    """Some recipes reached the shopping list before an error stopped the rest."""

    def __init__(self, cause: EatFreshError, done: int, total: int, items: int) -> None:
        """Keep the original error and how far the transfer got."""
        super().__init__(
            f"{error_message(cause)} ({done} of {total} recipes were added before)"
        )
        self.cause = cause
        self.done = done
        self.total = total
        self.items = items


class ShoppingEntryError(EatFreshError):
    """An entry of the shopping list cannot be ticked off or put back.

    ``code`` is the WebSocket error code (the panel shows the message).
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(slots=True)
class PlannerWeek:
    """The meal plan of one week (Monday to Sunday)."""

    week_start: date
    days: list[tuple[date, list[dict[str, Any]]]]
    unscheduled: list[dict[str, Any]]

    @property
    def recipe_ids(self) -> list[int]:
        """Return the KitchenOwl ids planned on the days of the week.

        A recipe planned on two days is in the list twice (it is cooked
        twice); twice on the same day counts once.
        """
        return [recipe_id for _key, recipe_id in self.planned]

    @property
    def planned(self) -> list[tuple[str, int]]:
        """Return ``("YYYY-MM-DD:<id>", id)`` for each recipe on a day.

        Same order and rules as :attr:`recipe_ids`; the key names one
        planned entry, so a partial transfer can remember what went through.
        """
        result: list[tuple[str, int]] = []
        for day, entries in self.days:
            for recipe_id in dict.fromkeys(entry["recipe_id"] for entry in entries):
                result.append((f"{day.isoformat()}:{recipe_id}", recipe_id))
        return result


def week_start_of(day: date) -> date:
    """Return the Monday of the week of a day."""
    return day - timedelta(days=day.weekday())


def today() -> date:
    """Return today in the time zone of Home Assistant."""
    return dt_util.now().date()


def planner_date(entry: Mapping[str, Any]) -> date | None:
    """Return the day of a meal plan entry as a date, or None without a day."""
    value = entry.get("date")
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            _LOGGER.debug("Ignoring meal plan entry with day %r", value)
    return None


def dated_entries(
    entries: Iterable[Mapping[str, Any]] | None, first: date, days: int
) -> list[tuple[date, dict[str, Any]]]:
    """Return ``(day, entry)`` for the entries from ``first`` on ``days`` days.

    Sorted by day; entries of the same day keep the order of KitchenOwl.
    Entries without a recipe id or without a day are left out.
    """
    end = first + timedelta(days=days)
    result: list[tuple[date, dict[str, Any]]] = []
    for entry in entries or []:
        if not isinstance(entry.get("recipe_id"), int):
            continue
        day = planner_date(entry)
        if day is not None and first <= day < end:
            result.append((day, dict(entry)))
    result.sort(key=lambda item: item[0])
    return result


def unscheduled_entries(
    entries: Iterable[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Return the entries planned without a day (not those with a broken day)."""
    return [
        dict(entry)
        for entry in entries or []
        if isinstance(entry.get("recipe_id"), int) and entry.get("date") in (None, "")
    ]


def default_servings(options: Mapping[str, Any]) -> int:
    """Return the servings a recipe of the collection opens with (1 to 12).

    Entries set up with 0.4.1 or earlier have no such option and get the
    default (3). Values outside 1 to 12 are moved into it.
    """
    try:
        servings = int(options.get(CONF_DEFAULT_SERVINGS, DEFAULT_SERVINGS))
    except TypeError, ValueError, OverflowError:
        servings = DEFAULT_SERVINGS
    return min(max(servings, MIN_SERVINGS), MAX_DEFAULT_SERVINGS)


def scalable_start(base: int | None, default: int) -> int | None:
    """Return the start value of a recipe if its servings can be changed.

    None when ``base`` is unknown or the start value is above 99 (then the
    amounts are never scaled and there is no counter).
    """
    start = start_servings(base, default)
    if start is None or start > MAX_SERVINGS:
        return None
    return start


def entry_servings(entry: Mapping[str, Any], default: int) -> int | None:
    """Return the servings of a meal plan entry.

    The number of the entry, else the start value of its recipe (from
    ``base``), else None. None as well when the recipe is not scalable
    (``base`` above 99): its servings are never used.
    """
    base = entry.get("base")
    base = base if isinstance(base, int) and not isinstance(base, bool) else None
    if base is not None and scalable_start(base, default) is None:
        return None
    servings = entry.get("yields")
    if isinstance(servings, int) and not isinstance(servings, bool) and servings >= 1:
        return servings
    return start_servings(base, default)


def plan_item(
    day: date, entry: Mapping[str, Any], default: int = DEFAULT_SERVINGS
) -> dict[str, Any]:
    """Return ``{date, recipe_id, name, servings}`` of a meal plan entry.

    Used by the actions and the sensor; ``servings`` see :func:`entry_servings`.
    """
    return {
        "date": day.isoformat(),
        "recipe_id": entry["recipe_id"],
        "name": str(entry.get("name") or ""),
        "servings": entry_servings(entry, default),
    }


def build_week(entries: Iterable[Mapping[str, Any]], week_start: date) -> PlannerWeek:
    """Sort meal plan entries into the 7 days of a week and the undated ones."""
    start = week_start_of(week_start)
    days: list[tuple[date, list[dict[str, Any]]]] = [
        (start + timedelta(days=offset), []) for offset in range(7)
    ]
    by_day = {day: items for day, items in days}
    entries = list(entries)
    for day, item in dated_entries(entries, start, 7):
        by_day[day].append(item)
    return PlannerWeek(
        week_start=start, days=days, unscheduled=unscheduled_entries(entries)
    )


def planner_interval(options: Mapping[str, Any]) -> timedelta:
    """Return the time between two fetches of the meal plan.

    Entries set up with 0.2.0 or earlier have no such option and get the
    default (one minute). Values outside 1 to 60 minutes are moved into it.
    """
    try:
        minutes = int(options.get(CONF_PLANNER_INTERVAL, DEFAULT_PLANNER_INTERVAL))
    except TypeError, ValueError:
        minutes = DEFAULT_PLANNER_INTERVAL
    minutes = min(max(minutes, MIN_PLANNER_INTERVAL), MAX_PLANNER_INTERVAL)
    return timedelta(minutes=minutes)


def clean_tags(tags: Iterable[str]) -> list[str]:
    """Return tags without blanks and duplicates (case does not matter)."""
    result: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if not isinstance(tag, str):
            continue
        name = " ".join(tag.split())[:MAX_TAG_LENGTH].strip()
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        result.append(name)
    return result[:MAX_TAGS]


@dataclass(slots=True)
class SearchResult:
    """Hits of all sources plus the sources that failed."""

    hits: list[SearchHit]
    errors: list[dict[str, str]]


@dataclass
class EatFreshData:
    """Everything a loaded config entry needs at runtime."""

    client: KitchenOwlClient
    sources: dict[str, RecipeSource]
    store: FavoritesStore
    household_id: int
    shoppinglist_id: int
    search_cache: TTLCache[list[SearchHit]] = field(
        default_factory=lambda: TTLCache(SEARCH_CACHE_TTL)
    )
    recipe_cache: TTLCache[Recipe] = field(
        default_factory=lambda: TTLCache(RECIPE_CACHE_TTL)
    )
    url_cache: TTLCache[str] = field(default_factory=lambda: TTLCache(RECIPE_CACHE_TTL))
    # Recipe address per key of search hits, to find a heart set by link.
    hit_urls: TTLCache[str] = field(default_factory=lambda: TTLCache(RECIPE_CACHE_TTL))
    extra_image_hosts: set[str] = field(default_factory=set)
    # Session for recipe pages and images: connects to public addresses only.
    public_session: aiohttp.ClientSession | None = None
    # Domains of switched-off opt-in sources (Chefkoch): never fetched.
    blocked_hosts: frozenset[str] = frozenset()
    # Meal plan of KitchenOwl for the calendar and the sensor.
    coordinator: PlannerCoordinator | None = None
    # Language of Home Assistant for category names ("de", "en", ...).
    hass: HomeAssistant | None = None
    # One lock per normalized recipe address, so two hearts at the same time
    # create only one recipe in KitchenOwl.
    _save_locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    _save_users: dict[str, int] = field(default_factory=dict)
    # One lock per week (Monday), so two transfers of the ingredients of a
    # week at the same time send them only once; the second one is asked.
    _week_locks: dict[date, asyncio.Lock] = field(default_factory=dict)
    _week_users: dict[date, int] = field(default_factory=dict)
    # The fetch of the meal plan that callers of
    # ``async_current_planner_entries`` share while it runs.
    _planner_fetch: asyncio.Task[list[dict[str, Any]]] | None = None
    # One transfer to (or undo in) the Picnic cart at a time.
    _picnic_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # One restore of remembered ingredients at a time (button or transfer),
    # so each one reads what the one before it wrote.
    _restore_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # One change of the servings of a meal plan entry at a time (it removes
    # the entry and plans it again).
    _servings_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Categories of the household as last read: (monotonic time, rows).
    # Dropped after a category was created.
    _categories: tuple[float, list[dict[str, Any]]] | None = None
    # One look-up or creation of a category at a time, so a missing one is
    # created only once.
    _category_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Items (id -> name) whose category is written after a transfer, and
    # the background task that writes them.
    _category_queue: dict[int, str] = field(default_factory=dict)
    _category_task: asyncio.Task[None] | None = None
    # One run of taking old cart entries off the list at a time.
    _takeoff_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # One ticking off or putting back at a time, so two calls never write
    # the same entry twice.
    _shop_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Running changes of servings (they finish even if the caller goes).
    _servings_tasks: set[asyncio.Task[None]] = field(default_factory=set)

    def __post_init__(self) -> None:
        """Let the memory of ingredients learn from KitchenOwl's answers.

        Every recipe list and every full recipe the client gets anyway is
        passed on; no extra request is sent for the memory.
        """
        self.client.on_recipe_list = self._learn_recipe_list
        self.client.on_recipe = self._learn_recipe

    # ----- images -------------------------------------------------------

    @callback
    def allowed_image_hosts(self) -> set[str]:
        """Return the hosts the image proxy may fetch from."""
        hosts = {
            host.lower() for source in self.sources.values() for host in source.hosts
        }
        return {
            host
            for host in hosts | self.extra_image_hosts
            if not host_matches(host, self.blocked_hosts)
        }

    @callback
    def allow_image_of(self, source_id: str, image: str | None) -> None:
        """Allow the image host of a recipe from the generic link source."""
        if source_id != JSONLD or not image:
            return
        parsed = URL(image)
        # Both spellings: the proxy compares the decoded host of the link and
        # the ASCII (IDNA) host of every redirect target.
        for host in (parsed.host, parsed.raw_host):
            if host:
                self.extra_image_hosts.add(host.lower().rstrip("."))

    @callback
    def allow_favorite_images(self) -> None:
        """Allow image hosts of stored favorites (after a restart)."""
        for _key, favorite in self.store.items():
            self.allow_image_of(favorite["source"], favorite.get("image"))

    # ----- sources ------------------------------------------------------

    @callback
    def searchable_ids(self, requested: list[str] | None) -> list[str]:
        """Return the enabled searchable sources, optionally filtered."""
        ids = [sid for sid, src in self.sources.items() if src.searchable]
        if requested is None:
            return ids
        wanted = set(requested)
        return [sid for sid in ids if sid in wanted]

    async def async_search(
        self, query: str, requested: list[str] | None, limit: int
    ) -> SearchResult:
        """Search all requested sources. A failing source never stops the others."""
        source_ids = self.searchable_ids(requested)
        normalized = " ".join(query.split()).casefold()

        async def search_one(source_id: str) -> list[SearchHit]:
            cache_key = (source_id, normalized, limit)
            if (cached := self.search_cache.get(cache_key)) is not None:
                return cached
            found = await self.sources[source_id].search(query.strip(), limit)
            # A link in the panel must be a web address, never javascript: etc.
            hits = [hit for hit in found if is_http_url(hit.url)]
            self.search_cache.set(cache_key, hits)
            return hits

        results = await asyncio.gather(
            *(search_one(sid) for sid in source_ids), return_exceptions=True
        )
        per_source: list[list[SearchHit]] = []
        errors: list[dict[str, str]] = []
        for source_id, result in zip(source_ids, results, strict=True):
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result
                if not isinstance(result, EatFreshError):
                    _LOGGER.exception(
                        "Unexpected error in source %s", source_id, exc_info=result
                    )
                errors.append({"source": source_id, "message": error_message(result)})
                continue
            per_source.append(result)

        # Interleave the sources so the first page shows a mix.
        for items in per_source:
            for hit in items:
                self.hit_urls.set(hit.key, hit.url)
        hits: list[SearchHit] = []
        longest = max((len(items) for items in per_source), default=0)
        for index in range(longest):
            hits.extend(items[index] for items in per_source if index < len(items))
        return SearchResult(hits=hits, errors=errors)

    def _remember(self, recipe: Recipe, url: str | None = None) -> None:
        """Check the address of a recipe and put it into the cache."""
        if not is_http_url(recipe.url):
            raise RecipeNotFound("The source gave no valid recipe address")
        self.recipe_cache.set(recipe.key, recipe)
        self.url_cache.set(recipe.url, recipe.key)
        if url:
            self.url_cache.set(url, recipe.key)
        self.allow_image_of(recipe.source, recipe.image)

    async def async_get_recipe(self, key: str) -> Recipe:
        """Return a recipe by key, from the cache if possible."""
        try:
            source_id, recipe_id = split_key(key)
        except ValueError as err:
            raise RecipeNotFound(str(err)) from err
        if (cached := self.recipe_cache.get(key)) is not None:
            return cached
        source = self.sources.get(source_id)
        if source is None:
            raise RecipeNotFound(f"Source {source_id} is not enabled")
        recipe = await source.get(recipe_id)
        self._remember(recipe)
        if recipe.key != key:
            self.recipe_cache.set(key, recipe)
        return recipe

    async def async_get_recipe_by_url(self, url: str) -> Recipe:
        """Return a recipe by its web address."""
        from .sources import source_for_url  # noqa: PLC0415

        if (key := self.url_cache.get(url)) is not None and (
            cached := self.recipe_cache.get(key)
        ) is not None:
            return cached
        source = source_for_url(self.sources, url)
        recipe = await source.get_by_url(url)
        self._remember(recipe, url)
        return recipe

    # ----- favorites ----------------------------------------------------

    @callback
    def url_of(self, key: str) -> str | None:
        """Return the recipe address behind a key, if it is known."""
        if (favorite := self.store.get(key)) is not None:
            return favorite["url"]
        if (cached := self.recipe_cache.get(key)) is not None:
            return cached.url
        if (hit_url := self.hit_urls.get(key)) is not None:
            return hit_url
        try:
            _source_id, recipe_id = split_key(key)
        except ValueError:
            return None
        if recipe_id.lower().startswith(("http://", "https://")):
            return recipe_id
        return None

    @callback
    def favorite_for(
        self, key: str, url: str | None = None
    ) -> tuple[str, Favorite] | None:
        """Return the stored favorite of a recipe.

        The same recipe can have two keys (search id and pasted link), so the
        recipe address is compared as well.
        """
        if (favorite := self.store.get(key)) is not None:
            return key, favorite
        if url is None:
            url = self.url_of(key)
        return self.store.find_by_url(url) if url else None

    @callback
    def kitchenowl_id_of(self, key: str, url: str | None = None) -> int | None:
        """Return the KitchenOwl id of a favorite or None.

        A favorite whose recipe is hidden in the collection does not count.
        """
        found = self.favorite_for(key, url)
        if found is None or self.store.is_hidden(found[1]["kitchenowl_id"]):
            return None
        return found[1]["kitchenowl_id"]

    @callback
    def is_favorite(self, key: str, url: str | None = None) -> bool:
        """Return True if the recipe has a heart (by key or by address)."""
        return self.kitchenowl_id_of(key, url) is not None

    @property
    def default_servings(self) -> int:
        """Return the option "default servings" of the config entry (1 to 12)."""
        options = getattr(self.config_entry, "options", None)
        return default_servings(options if isinstance(options, Mapping) else {})

    @property
    def language(self) -> str:
        """Return the language of Home Assistant."""
        return self.hass.config.language if self.hass is not None else "en"

    @property
    def config_entry(self) -> ConfigEntry | None:
        """Return the config entry (through the coordinator), or None."""
        return getattr(self.coordinator, "config_entry", None)

    @property
    def write_categories(self) -> bool:
        """Return the option "write categories to KitchenOwl" (default on)."""
        options = getattr(self.config_entry, "options", None)
        if not isinstance(options, Mapping):
            return DEFAULT_WRITE_CATEGORIES
        return bool(options.get(CONF_WRITE_CATEGORIES, DEFAULT_WRITE_CATEGORIES))

    async def async_save_recipe(self, recipe: Recipe) -> tuple[int, bool]:
        """Make sure a recipe is in KitchenOwl and marked as favorite.

        Look in the store first (by key and by address), then in KitchenOwl by
        source URL, and only then create the recipe. Return the KitchenOwl id
        and whether it was created. Saves of the same address run one after
        the other, so a second heart finds the recipe of the first.
        """
        lock_key = normalize_source(recipe.url) or recipe.key
        lock = self._save_locks.setdefault(lock_key, asyncio.Lock())
        self._save_users[lock_key] = self._save_users.get(lock_key, 0) + 1
        try:
            async with lock:
                return await self._async_save_recipe_locked(recipe)
        finally:
            self._save_users[lock_key] -= 1
            if not self._save_users[lock_key]:
                del self._save_users[lock_key]
                del self._save_locks[lock_key]

    async def _async_save_recipe_locked(self, recipe: Recipe) -> tuple[int, bool]:
        if (found := self.favorite_for(recipe.key, recipe.url)) is not None:
            # A new heart shows a hidden recipe again.
            self.store.async_unhide(found[1]["kitchenowl_id"])
            return found[1]["kitchenowl_id"], False
        created = False
        kitchenowl_id = await self.client.find_by_source(self.household_id, recipe.url)
        if kitchenowl_id is None:
            # The cached list may be up to two minutes old: look once more with
            # a fresh list, so a recipe added in KitchenOwl meanwhile is reused.
            kitchenowl_id = await self.client.find_by_source(
                self.household_id, recipe.url, fresh=True
            )
        if kitchenowl_id is None:
            to_create = await self._without_unsafe_photo(recipe)
            # Only the canonical categories become tags, not every keyword.
            to_create = replace(
                to_create, tags=suggest_categories(recipe, self.language)
            )
            kitchenowl_id = await self.client.create_recipe(
                self.household_id, to_create
            )
            created = True
            # Remember the sent ingredients at once (ids follow on the next
            # read). They replace any memory of a deleted recipe with this id.
            self.store.async_start_ingredients(
                kitchenowl_id,
                kitchenowl_module.created_item_rows(to_create.ingredients),
                created_at=self.client.created_at_of(kitchenowl_id),
            )
        self.store.async_unhide(kitchenowl_id)
        self.store.async_set(
            recipe.key,
            source=recipe.source,
            recipe_id=recipe.id,
            url=recipe.url,
            title=recipe.title,
            image=recipe.image,
            kitchenowl_id=kitchenowl_id,
        )
        return kitchenowl_id, created

    async def _without_unsafe_photo(self, recipe: Recipe) -> Recipe:
        """Drop the photo link unless KitchenOwl may download it.

        KitchenOwl fetches the photo itself, outside the protection of
        ``http.py``. A link into a private network (or to a switched-off
        source) must not reach it; the recipe is created without a photo.
        """
        if not recipe.image:
            return recipe
        try:
            if host_matches(split_url(recipe.image)[1], self.blocked_hosts):
                raise UnsafeAddress("The photo is on a switched-off source")
            await check_public_url(recipe.image)
        except EatFreshError as err:
            _LOGGER.info("Recipe photo left out: %s", err)
            return replace(recipe, image=None)
        return recipe

    async def async_favorite(self, key: str) -> tuple[int, bool]:
        """Set the heart of a recipe (and show it again if it was hidden)."""
        if (found := self.favorite_for(key)) is not None:
            self.store.async_unhide(found[1]["kitchenowl_id"])
            return found[1]["kitchenowl_id"], False
        recipe = await self.async_get_recipe(key)
        return await self.async_save_recipe(recipe)

    async def async_recipe_tags(self, kitchenowl_id: int) -> list[str]:
        """Return the tags of a KitchenOwl recipe (empty if it is not listed)."""
        for item in await self.client.list_recipes(self.household_id):
            if item.get("id") == kitchenowl_id:
                return self.localize_tags(item.get("tags") or [])
        return []

    def localize_tags(self, tags: Iterable[Any]) -> list[str]:
        """Return tags with canonical categories named in HA's language.

        "Soup" and "Suppe" are the same category, so both become one tag
        (and one filter chip in the panel).
        """
        named = []
        for tag in tags:
            if not isinstance(tag, str):
                continue
            category = canonical_category(tag)
            named.append(category.name(self.language) if category else tag)
        return clean_tags(named)

    async def async_require_own(self, kitchenowl_ids: Iterable[int]) -> None:
        """Raise ``RecipeNotFound`` unless all recipes are in the own household.

        Checked before anything is sent for a single recipe, so an id from
        another household changes nothing and never looks like a rejected
        token. The recipe list is reused for a short time; a missing id is
        looked up once more in a fresh list.
        """
        wanted = set(kitchenowl_ids)
        if not wanted:
            return
        missing = wanted - await self.client.recipe_ids(self.household_id)
        if missing:
            missing -= await self.client.recipe_ids(self.household_id, fresh=True)
        if missing:
            raise RecipeNotFound(NOT_IN_COLLECTION)

    @callback
    def async_unfavorite(self, key: str) -> None:
        """Remove the heart (under every key of the recipe). KitchenOwl stays."""
        url = self.url_of(key)
        self.store.async_remove(key)
        if url:
            for other in self.store.keys_for_url(url):
                self.store.async_remove(other)

    @callback
    def favorites(self) -> list[tuple[str, Favorite]]:
        """Return all favorites whose recipe is not hidden, newest first."""
        return [
            (key, favorite)
            for key, favorite in self.store.items()
            if not self.store.is_hidden(favorite["kitchenowl_id"])
        ]

    # ----- remembered ingredients ---------------------------------------

    @callback
    def _learn_recipe_list(self, household_id: int, recipes: list[dict]) -> None:
        """Learn the items of a fresh recipe list; forget long gone recipes.

        Only lists of the own household count. A recipe without
        ``item_rows`` is kept as it is. A recipe missing from the list is
        forgotten only after 30 days, never because of an empty list (see
        :meth:`FavoritesStore.async_prune_ingredients`).
        """
        if household_id != self.household_id:
            return
        keep: set[int] = set()
        for recipe in recipes:
            try:
                kitchenowl_id = int(recipe["id"])
            except KeyError, TypeError, ValueError:
                continue
            keep.add(kitchenowl_id)
            rows = recipe.get("item_rows")
            if isinstance(rows, list):
                self.store.async_learn_ingredients(
                    kitchenowl_id, rows, recipe.get("created_at")
                )
        self.store.async_prune_ingredients(keep)

    @callback
    def _learn_recipe(self, data: Mapping[str, Any]) -> list[RememberedItem]:
        """Learn the items of a full recipe; return the missing ones.

        A recipe of another household or without an item list is ignored.
        """
        household = data.get("household_id")
        if household is not None and household != self.household_id:
            return []
        items = data.get("items")
        if not isinstance(items, list):
            return []
        try:
            kitchenowl_id = int(data["id"])
        except KeyError, TypeError, ValueError:
            return []
        return self.store.async_learn_ingredients(
            kitchenowl_id, item_rows(items), data.get("created_at")
        )

    @callback
    def _missing_of(self, recipe: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Return the remembered items missing in a recipe of the list."""
        rows = recipe.get("item_rows")
        try:
            memory = self.store.recipe_ingredients(int(recipe["id"]))
        except KeyError, TypeError, ValueError:
            return []
        if not memory or not isinstance(rows, list):
            return []
        return merge_items(memory, rows)[1]

    async def async_restore_ingredients(
        self, kitchenowl_id: int
    ) -> dict[str, list[str]]:
        """Add the remembered ingredients missing in KitchenOwl back to it.

        Return ``{restored, missing}``: the names added and the names still
        missing after the write (normally none). Nothing is removed.
        """
        await self.async_require_own([kitchenowl_id])
        async with self._restore_lock:
            memory = self.store.recipe_ingredients(kitchenowl_id)
            if not memory:
                return {"restored": [], "missing": []}
            result = await self.client.restore_recipe_items(kitchenowl_id, memory)
        return {
            "restored": list(result.get("restored") or []),
            "missing": list(result.get("missing") or []),
        }

    async def async_forget_ingredients(
        self, kitchenowl_id: int, names: Iterable[str] | None = None
    ) -> dict[str, list[str]]:
        """Forget remembered ingredients that are missing in KitchenOwl.

        Only missing ones are forgotten: those named in ``names`` (any case),
        or all without ``names``. The recipe is read once to know what is
        missing now. KitchenOwl is not changed. Return ``{removed, missing}``
        (the names forgotten and the ones still missing).
        """
        await self.async_require_own([kitchenowl_id])
        data = await self.client.get_recipe(kitchenowl_id)
        household = data.get("household_id")
        if household is not None and household != self.household_id:
            raise RecipeNotFound("The recipe belongs to another household")
        missing = self._learn_recipe(data)
        wanted = None if names is None else {ingredient_key(name) for name in names}
        gone = {
            ingredient_key(row["name"])
            for row in missing
            if wanted is None or ingredient_key(row["name"]) in wanted
        }
        removed = [
            row["name"] for row in missing if ingredient_key(row["name"]) in gone
        ]
        if removed:
            memory = self.store.recipe_ingredients(kitchenowl_id) or []
            self.store.async_set_ingredients(
                kitchenowl_id,
                [
                    row
                    for row in memory
                    if row["id"] is not None or ingredient_key(row["name"]) not in gone
                ],
            )
        return {
            "removed": removed,
            "missing": [
                row["name"]
                for row in missing
                if ingredient_key(row["name"]) not in gone
            ],
        }

    # ----- KitchenOwl ---------------------------------------------------

    async def async_collection(
        self, include_hidden: bool = False
    ) -> list[dict[str, Any]]:
        """Return the recipes stored in KitchenOwl.

        Each recipe gets ``hidden`` and ``missing`` (the number of remembered
        ingredients that are no longer in KitchenOwl); their names are added
        to ``items``, so the search finds them. Hidden recipes are left out
        unless ``include_hidden`` is set.
        """
        recipes = []
        listed = await self.client.list_recipes(self.household_id)
        # Also learned by the client's listener; repeated here so the result
        # never depends on it. Learning the same list twice changes nothing.
        self._learn_recipe_list(self.household_id, listed)
        for recipe in listed:
            hidden = self.store.is_hidden(recipe.get("id"))
            if hidden and not include_hidden:
                continue
            tags = self.localize_tags(recipe.get("tags") or [])
            missing = self._missing_of(recipe)
            items = list(recipe.get("items") or [])
            items.extend(row["name"] for row in missing)
            recipes.append(
                {
                    **recipe,
                    "items": items,
                    "tags": tags,
                    "hidden": hidden,
                    "missing": len(missing),
                }
            )
        return recipes

    async def async_search_collection(
        self,
        query: str | None,
        limit: int = DEFAULT_COLLECTION_LIMIT,
        name_only: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return the visible recipes of the collection whose name or an
        ingredient contains ``query`` (any case), each with its planned days,
        and the number of all matches.

        With ``name_only`` only the name is compared, not the ingredients.
        Without ``query`` the whole visible collection matches. At most
        ``limit`` recipes come back. The days come from the plan of the last
        ``PLANNER_MAX_AGE`` if there is one. If only the plan cannot be
        loaded, the recipes come back without days.
        """
        needle = (query or "").strip().casefold()
        recipes = await self.async_collection()
        if needle:
            recipes = [
                recipe
                for recipe in recipes
                if needle in str(recipe.get("name") or "").casefold()
                or (
                    not name_only
                    and any(
                        needle in str(item).casefold()
                        for item in recipe.get("items") or []
                    )
                )
            ]
        total = len(recipes)
        recipes = recipes[: max(limit, 0)]
        if not recipes:
            return [], total
        try:
            entries = await self.async_current_planner_entries()
        except KitchenOwlAuthError:
            raise
        except EatFreshError as err:
            _LOGGER.debug("Meal plan not available for the search: %s", err)
            entries = []
        planned: dict[int, set[str]] = {}
        for entry in entries:
            day = planner_date(entry)
            if day is not None and isinstance(entry.get("recipe_id"), int):
                planned.setdefault(entry["recipe_id"], set()).add(day.isoformat())
        return [
            {
                "recipe_id": recipe["id"],
                "name": recipe.get("name"),
                "time": recipe.get("time"),
                "yields": recipe.get("yields"),
                "tags": list(recipe.get("tags") or []),
                "planned_dates": sorted(planned.get(recipe["id"], ())),
            }
            for recipe in recipes
        ], total

    async def async_collection_recipe(self, kitchenowl_id: int) -> Recipe:
        """Return a recipe as stored in KitchenOwl. No recipe page is fetched.

        The ingredients include the remembered ones missing in KitchenOwl.
        """
        return (await self.async_collection_recipe_missing(kitchenowl_id))[0]

    async def async_collection_recipe_missing(
        self, kitchenowl_id: int
    ) -> tuple[Recipe, list[str]]:
        """Return a recipe of the collection and the names missing in KitchenOwl.

        The ingredients are complete, in the remembered order: an ingredient
        missing in KitchenOwl is built from its remembered name and amount
        text. Nothing is scaled (see :meth:`async_collection_recipe_portions`).
        """
        recipe, names, _rows = await self._async_collection_rows(kitchenowl_id)
        return recipe, names

    async def _async_collection_rows(
        self, kitchenowl_id: int
    ) -> tuple[Recipe, list[str], list[tuple[str, str]]]:
        """Return the recipe, the names missing in KitchenOwl and the rows.

        The rows are ``(name, amount text)`` in the order of the ingredients
        of the recipe, the remembered ones included.
        """
        await self.async_require_own([kitchenowl_id])
        data = await self.client.get_recipe(kitchenowl_id)
        household = data.get("household_id")
        if household is not None and household != self.household_id:
            raise RecipeNotFound("The recipe belongs to another household")
        missing = self._learn_recipe(data)
        recipe = kitchenowl_module.recipe_to_model(data)
        if not missing:
            rows: list[tuple[str, str]] = []
            for item in data.get("items") or []:
                if not isinstance(item, dict):
                    continue
                name = " ".join(str(item.get("name") or "").split())
                if name:
                    rows.append((name, str(item.get("description") or "")))
            return recipe, [], rows
        memory = self.store.recipe_ingredients(kitchenowl_id) or []
        ingredients = []
        for row in memory:
            note = " ".join(row["description"].split())
            raw = f"{note} {row['name']}" if note else row["name"]
            ingredients.append(Ingredient(name=row["name"], raw=raw))
        names = [row["name"] for row in missing]
        rows = [(row["name"], row["description"]) for row in memory]
        return replace(recipe, ingredients=ingredients), names, rows

    async def async_collection_recipe_portions(
        self, kitchenowl_id: int, servings: int | None = None
    ) -> tuple[Recipe, list[str], dict[str, Any], list[dict[str, Any]]]:
        """Return a recipe of the collection scaled to ``servings``.

        Without ``servings`` the start value of the recipe is used. Return
        the recipe (its ``servings`` is the shown number when the recipe is
        scalable), the names missing in KitchenOwl, ``portions`` (``servings``,
        ``base``, ``default``, ``start``, ``scalable``) and one
        ``{scaled, rounded_from}`` per ingredient, in the same order. The
        remembered ingredients missing in KitchenOwl are scaled as well.
        KitchenOwl is not changed.
        """
        recipe, names, rows = await self._async_collection_rows(kitchenowl_id)
        default = self.default_servings
        base = recipe.servings
        start = start_servings(base, default)
        scalable = scalable_start(base, default) is not None
        shown = servings if scalable and servings is not None else start
        ingredients: list[Ingredient] = []
        marks: list[dict[str, Any]] = []
        for name, description in rows:
            scaled = scale_description(description, base, shown if scalable else None)
            note = " ".join(scaled.description.split())
            ingredients.append(
                Ingredient(name=name, raw=f"{note} {name}" if note else name)
            )
            marks.append({"scaled": scaled.scaled, "rounded_from": scaled.rounded_from})
        if scalable:
            recipe = replace(recipe, ingredients=ingredients, servings=shown)
        portions = {
            "servings": shown,
            "base": base,
            "default": default,
            "start": start,
            "scalable": scalable,
        }
        return recipe, names, portions, marks

    async def async_hide(self, kitchenowl_id: int) -> None:
        """Hide a recipe of the collection. KitchenOwl stays unchanged.

        Only recipes of the own collection are accepted, so the store cannot
        fill up with ids that do not exist.
        """
        if not self.store.is_hidden(kitchenowl_id):
            await self.async_require_own([kitchenowl_id])
        self.store.async_hide(kitchenowl_id)

    @callback
    def async_unhide(self, kitchenowl_id: int) -> None:
        """Show a hidden recipe in the collection again."""
        self.store.async_unhide(kitchenowl_id)

    async def async_set_tags(self, kitchenowl_id: int, tags: list[str]) -> list[str]:
        """Replace the tags of a KitchenOwl recipe.

        A tag that names a canonical category in another language is written
        with the name in the language of Home Assistant.
        """
        await self.async_require_own([kitchenowl_id])
        stored = await self.client.set_recipe_tags(
            kitchenowl_id, self.localize_tags(tags)
        )
        return self.localize_tags(stored)

    async def async_tags(self) -> tuple[list[str], list[str]]:
        """Return the canonical categories and all tags of the household.

        Tags naming a canonical category in another language ("Soup" in a
        German Home Assistant) come back under the name in HA's language.
        """
        tags = await self.client.list_tags(self.household_id)
        return category_names(self.language), self.localize_tags(tags)

    # ----- meal plan ----------------------------------------------------

    async def async_planner_entries(self) -> list[dict[str, Any]]:
        """Fetch the meal plan and share it with the calendar and the sensor."""
        entries = await self.client.list_planner(self.household_id)
        if self.coordinator is not None:
            self.coordinator.async_set_updated_data(entries)
        return entries

    async def async_current_planner_entries(self) -> list[dict[str, Any]]:
        """Return the plan of the coordinator while it is younger than
        ``PLANNER_MAX_AGE``, else fetch it (and share it with the entities).
        """
        if self.coordinator is not None:
            cached = self.coordinator.fresh_data(PLANNER_MAX_AGE)
            if cached is not None:
                return cached
        # Many callers at once (cards, scripts) share one running fetch.
        if (task := self._planner_fetch) is None or task.done():
            task = self._planner_fetch = asyncio.ensure_future(
                self.async_planner_entries()
            )
            task.add_done_callback(self._planner_fetch_done)
        return await asyncio.shield(task)

    def _planner_fetch_done(self, task: asyncio.Task[Any]) -> None:
        """Forget the finished shared fetch (its error is read by a caller)."""
        if self._planner_fetch is task:
            self._planner_fetch = None
        if not task.cancelled():
            task.exception()

    async def async_planner_week(
        self, week_start: date | None, *, use_cache: bool = True
    ) -> PlannerWeek:
        """Return the meal plan of a week (default: the current week).

        For the current week the plan of the coordinator is used while it is
        younger than ``PLANNER_MAX_AGE`` (many cards on many screens), unless
        ``use_cache`` is off. A change through EatFresh refreshes it at once.
        """
        day = week_start or today()
        current = week_start_of(day) == week_start_of(today())
        if use_cache and current:
            entries = await self.async_current_planner_entries()
        else:
            entries = await self.async_planner_entries()
        return build_week(entries, day)

    async def async_planner_add(
        self, kitchenowl_id: int, day: date, servings: int | None = None
    ) -> None:
        """Plan a recipe of the own collection on a day.

        Without ``servings`` the start value of the recipe is planned when
        its ``yields`` is known (from the recipe list the check of the
        collection just used, so normally no extra request). For a recipe
        that is not scalable ``servings`` is dropped and no number is
        planned. The plan is written before this returns.
        """
        await self.async_require_own([kitchenowl_id])
        summary = await self.client.recipe_summary(self.household_id, kitchenowl_id)
        base = kitchenowl_module.yields_of((summary or {}).get("yields"))
        start = scalable_start(base, self.default_servings)
        # Not scalable (base unknown or above 99): a number given is dropped,
        # the recipe is planned without one.
        servings = None if start is None else servings or start
        try:
            if servings is None:
                await self.client.add_planner_entry(
                    self.household_id, kitchenowl_id, day
                )
            else:
                await self.client.add_planner_entry(
                    self.household_id, kitchenowl_id, day, yields=servings
                )
        finally:
            await self._async_refresh_planner()

    async def async_planner_set_servings(
        self, kitchenowl_id: int, day: date, servings: int
    ) -> None:
        """Change the servings of the entry of a recipe on a day.

        KitchenOwl keeps the old number when the same recipe is planned on
        the same day again (measured 25.11.2026), so the entry is removed and
        planned again with the new number. If planning fails, the entry is
        planned again with the old number and the error is raised; if that
        fails as well, ``plan_entry_lost`` says the entry is gone. The
        calendar and the sensor are refreshed once, at the end. A shopping
        list the week went to stays as it is.

        Refused (``unscheduled_entry``, nothing written) while the same
        recipe is in the plan without a day as well: KitchenOwl would drop
        that entry when planning again. The check uses the meal plan read
        for the change anyway.

        The change runs in a task of its own: should the caller be
        cancelled (the panel closes), removing and planning again still
        finish, and the lock is released by that task.
        """
        await self.async_require_own([kitchenowl_id])
        task = asyncio.ensure_future(
            self._async_set_servings_locked(kitchenowl_id, day, servings)
        )
        self._servings_tasks.add(task)
        task.add_done_callback(self._servings_task_done)
        await asyncio.shield(task)

    def _servings_task_done(self, task: asyncio.Task[None]) -> None:
        """Forget a finished change of servings (its error went to the caller)."""
        self._servings_tasks.discard(task)
        if not task.cancelled() and (err := task.exception()) is not None:
            _LOGGER.debug("Changing servings ended with %r", err)

    async def _async_set_servings_locked(
        self, kitchenowl_id: int, day: date, servings: int
    ) -> None:
        async with self._servings_lock:
            try:
                entries = await self.client.list_planner(self.household_id)
                entry = next(
                    (
                        item
                        for item in entries
                        if item.get("recipe_id") == kitchenowl_id
                        and planner_date(item) == day
                    ),
                    None,
                )
                if entry is None:
                    raise RecipeNotFound("The recipe is not planned on this day")
                old = entry.get("yields")
                if old == servings:
                    return
                if any(
                    item["recipe_id"] == kitchenowl_id
                    for item in unscheduled_entries(entries)
                ):
                    raise PlannerEntryError(
                        ERR_UNSCHEDULED_ENTRY, self._text("unscheduled_entry")
                    )
                await self.client.remove_planner_entry(
                    self.household_id, kitchenowl_id, day
                )
                try:
                    await self.client.add_planner_entry(
                        self.household_id, kitchenowl_id, day, yields=servings
                    )
                except Exception:
                    await self._async_plan_again(kitchenowl_id, day, old)
                    raise
            finally:
                await self._async_refresh_planner()

    async def _async_plan_again(self, kitchenowl_id: int, day: date, old: Any) -> None:
        """Plan an entry removed by a change of servings again, with ``old``.

        Raises ``plan_entry_lost`` if that fails too: the entry is gone.
        """
        try:
            if isinstance(old, int) and not isinstance(old, bool):
                await self.client.add_planner_entry(
                    self.household_id, kitchenowl_id, day, yields=old
                )
            else:
                await self.client.add_planner_entry(
                    self.household_id, kitchenowl_id, day
                )
        except Exception as err:
            _LOGGER.warning(
                "Could not plan recipe %s on %s again: %s", kitchenowl_id, day, err
            )
            raise PlannerEntryError(
                ERR_PLAN_ENTRY_LOST, self._text("plan_entry_lost")
            ) from err

    async def async_planner_remove(self, kitchenowl_id: int, day: date | None) -> None:
        """Take a recipe off a day (or off the plan without a day)."""
        try:
            await self.client.remove_planner_entry(
                self.household_id, kitchenowl_id, day
            )
        finally:
            await self._async_refresh_planner()

    async def async_planner_shopping_list(
        self, week_start: date | None, *, confirm: bool = False
    ) -> dict[str, Any]:
        """Put the ingredients of the planned recipes of a week on the list.

        Return ``{added, recipes, at}``: the number of items and of recipes
        and the time of this transfer. A recipe planned on two days counts
        twice; recipes without a day are left out. If the week went to the
        list before and ``confirm`` is not set, nothing is sent and the
        answer is ``{added: 0, recipes: 0, already_added_at}`` (the time of
        the earlier transfer, from the store: the same for every device and
        person). A partial transfer raises ``ShoppingListPartial`` and still
        counts as a transfer; the planned entries that went through are
        remembered, and a confirmed second try sends only the rest.

        Two calls for the same week at the same time run one after the
        other (a lock per week around checking and sending), so the second
        one is asked instead of sending everything again.
        """
        monday = week_start_of(week_start or today())
        lock = self._week_locks.setdefault(monday, asyncio.Lock())
        self._week_users[monday] = self._week_users.get(monday, 0) + 1
        try:
            async with lock:
                return await self._async_planner_shopping_list_locked(
                    week_start, confirm=confirm
                )
        finally:
            # Also after an error or a cancel: the lock never stays behind.
            self._week_users[monday] -= 1
            if not self._week_users[monday]:
                del self._week_users[monday]
                del self._week_locks[monday]

    async def _async_planner_shopping_list_locked(
        self, week_start: date | None, *, confirm: bool
    ) -> dict[str, Any]:
        week = await self.async_planner_week(week_start, use_cache=False)
        before = self.store.week_list_time(week.week_start)
        if before is not None and not confirm:
            return {"added": 0, "recipes": 0, "already_added_at": before}
        done = self.store.week_list_done(week.week_start)
        planned = [item for item in week.planned if item[0] not in done]
        if not planned:
            if done:
                # The rest of a partial transfer is empty: the week is complete.
                at = self.store.async_set_week_list_time(week.week_start)
                return {"added": 0, "recipes": 0, "at": at}
            return {"added": 0, "recipes": 0, "at": before}
        recipe_ids = [recipe_id for _key, recipe_id in planned]
        # Each planned entry goes with its own servings (first entry of the
        # recipe on that day, like ``planned``).
        default = self.default_servings
        entry_of: dict[str, dict[str, Any]] = {}
        for day, entries in week.days:
            for entry in entries:
                entry_of.setdefault(f"{day.isoformat()}:{entry['recipe_id']}", entry)
        servings = [
            entry_servings(entry_of[key], default) if key in entry_of else None
            for key, _id in planned
        ]
        try:
            added = await self.async_add_to_shopping_list(recipe_ids, servings)
        except ShoppingListPartial as err:
            self.store.async_set_week_list_time(
                week.week_start,
                done=[*done, *(key for key, _id in planned[: err.done])],
            )
            raise
        at = self.store.async_set_week_list_time(week.week_start)
        return {"added": added, "recipes": len(recipe_ids), "at": at}

    @callback
    def week_list_time(self, week_start: date) -> str | None:
        """Return when the week of a day went to the shopping list, or None."""
        return self.store.week_list_time(week_start_of(week_start))

    async def _async_refresh_planner(self) -> None:
        """Refresh the calendar and the sensor after a change."""
        if self.coordinator is not None:
            await self.coordinator.async_refresh()

    async def async_add_to_shopping_list(
        self,
        recipe_ids: list[int],
        servings: int | Sequence[int | None] | None = None,
    ) -> int:
        """Put the ingredients of KitchenOwl recipes on the shopping list.

        The recipes are sent one after the other, in the given order. Before
        a recipe goes, remembered ingredients missing in KitchenOwl are added
        back to it; if that fails, the recipe fails. If one fails after
        others went through, ``ShoppingListPartial`` says how many are
        already on the list, so a second try can leave them out.

        The amounts are scaled to ``servings``: one number for all recipes,
        or one per recipe (same order). Where it is None, the start value of
        the recipe counts.
        """
        await self.async_require_own(recipe_ids)
        if recipe_ids:
            await self.async_before_list_transfer()
        if servings is None or isinstance(servings, int):
            each: list[int | None] = [servings] * len(recipe_ids)
        else:
            each = list(servings) + [None] * (len(recipe_ids) - len(servings))
        added = 0
        try:
            for done, recipe_id in enumerate(recipe_ids):
                try:
                    added += await self._async_add_recipe_to_list(recipe_id, each[done])
                except EatFreshError as err:
                    if done == 0:
                        raise
                    raise ShoppingListPartial(
                        err, done, len(recipe_ids), added
                    ) from err
        finally:
            # In the background: the transfer never waits for it.
            self._start_category_writes()
        return added

    async def _async_add_recipe_to_list(
        self, recipe_id: int, servings: int | None = None
    ) -> int:
        """Restore missing ingredients of a recipe, then put it on the list.

        The recipe is read once (by the restore, else here); its ``yields``
        is the base for scaling the amounts to ``servings`` (None: the start
        value of the recipe).
        """
        recipe: Any = None
        if self.store.recipe_ingredients(recipe_id):
            async with self._restore_lock:
                memory = self.store.recipe_ingredients(recipe_id) or []
                result = await self.client.restore_recipe_items(recipe_id, memory)
            if result.get("missing"):
                raise KitchenOwlError(
                    "KitchenOwl did not take back the ingredients: "
                    + ", ".join(result["missing"])
                )
            recipe = result.get("recipe")
        if not isinstance(recipe, dict):
            recipe = await self.client.get_recipe(recipe_id)
        if servings is None:
            servings = start_servings(
                kitchenowl_module.yields_of(recipe.get("yields")),
                self.default_servings,
            )
        return await self._async_send_recipe_to_list(recipe_id, recipe, servings)

    async def _async_send_recipe_to_list(
        self, recipe_id: int, recipe: dict[str, Any], servings: int | None
    ) -> int:
        """Put one recipe, as just read, on the list, scaled to ``servings``.

        The amount texts are scaled by :func:`.kitchenowl.shopping_items`
        (``shopping_items(recipe, servings)`` gives each item with its
        ``Scaled`` result, exactly as sent).
        """
        added = await self.client.add_recipe_to_shoppinglist(
            self.shoppinglist_id, recipe_id, recipe=recipe, servings=servings
        )
        self._remember_list_exact(recipe, servings)
        self._queue_category_writes(recipe)
        return added

    async def async_before_list_transfer(self) -> list[dict[str, Any]] | None:
        """Read the shopping list once before a transfer and tidy the store.

        Rows of the exact pack counts (``list_exact``) whose item left the
        list, that are older than 14 days or whose count no longer fits the
        list are dropped. If reading fails, all of them are forgotten.

        Entries surely in the Picnic cart for 3 days are taken off the list
        first (see :meth:`_async_take_off_cart`).

        Returns the rows as read (without the entries just taken off), or
        None when reading failed. Never raises (only a cancel goes through):
        the transfer always goes on. More tidying before a transfer belongs
        here as well.
        """
        try:
            rows = await self.client.list_shoppinglist_items(self.shoppinglist_id)
            if not isinstance(rows, list):
                raise TypeError(f"unexpected list: {type(rows).__name__}")
            rows = await self._async_take_off_cart(rows)
            self.store.async_prune_list_exact(rows)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Reading the list before a transfer failed: %r", err)
            self.store.async_clear_list_exact()
            return None
        return rows

    def _remember_list_exact(
        self, recipe: Mapping[str, Any], servings: int | None
    ) -> None:
        """Remember the exact pack counts of a recipe that just went on the list.

        Uses the same scaling as the transfer (``shopping_items``). Never
        raises: the transfer is done already.
        """
        try:
            for item, scaled in kitchenowl_module.shopping_items(recipe, servings):
                if scaled.packages:
                    self.store.async_add_list_exact(item["id"], scaled.packages)
        except Exception:
            _LOGGER.exception("Remembering the exact pack counts failed")

    # ----- Picnic -------------------------------------------------------

    async def async_shopping(self, hass: HomeAssistant) -> dict[str, Any]:
        """Return the shopping list with the remembered Picnic products.

        Reads only KitchenOwl and the store, never Picnic. Entries surely in
        the Picnic cart for 3 days are taken off the list first. Marks of
        entries that left the list are dropped, unclear ones after 3 days.

        An entry surely in the cart whose amount text changed since it was
        sent (a later transfer added to it) is open again: no ``sent_at``,
        and ``cart_hint`` is the amount text that went into the cart.

        0.5.0: each entry carries its group (``department``); the answer
        has all groups in order (``departments``), the entries ticked off in
        the last 3 days (``done``, newest first, none that is on the list)
        and ``done_days``. The categories of the household are read at most
        every few minutes, at the same time as the list; if that fails, the
        list still comes, with the names of :func:`department_name`.
        """
        categories_task = asyncio.ensure_future(self._async_categories())
        try:
            rows = await self.client.list_shoppinglist_items(self.shoppinglist_id)
        except BaseException:
            categories_task.cancel()
            raise
        categories = await categories_task
        rows = await self._async_take_off_cart(rows)
        self.store.async_prune_picnic_sent(
            (row["id"] for row in rows), _list_texts(rows)
        )
        groups = ShopGroups(categories, rows, self.language)
        items: list[dict[str, Any]] = []
        for row in rows:
            name = row["name"]
            description = row.get("description") or ""
            product: dict[str, Any] | None = None
            small: dict[str, Any] | None = None
            amount = 1
            small_amount = 0
            rest: str | None = None
            exact = self.store.valid_list_exact(row["id"], description)
            if (stored := self.store.picnic_product(name)) is not None:
                product = _product_view(stored)
                stored_small = stored.get("small")
                small = _product_view(stored_small) if stored_small else None
                split = suggest_split(
                    description,
                    stored["unit_quantity"],
                    exact_count=exact["exact"] if exact else None,
                    small_unit_quantity=stored_small["unit_quantity"]
                    if stored_small
                    else None,
                )
                if stored["amount"]:
                    # A remembered fixed count wins: no split, no proposal.
                    amount = stored["amount"]
                else:
                    amount, small_amount = split.amount, split.small_amount
                    rest = split.rest
            sent = self.store.picnic_sent(row["id"])
            cart_hint: str | None = None
            if sent is not None and _changed_since_sent(sent, description):
                # The entry grew or changed after it went into the cart: it
                # is open again, with a hint of what is in the cart.
                cart_hint = sent["description"]
                sent = None
            if sent is not None:
                # Show what went into the cart (and what "undo" takes out).
                amount = sent["amount"]
                sent_small = sent.get("small")
                small = _sent_small_view(sent_small, small) if sent_small else None
                small_amount = sent_small["amount"] if sent_small else 0
            items.append(
                {
                    "item_id": row["id"],
                    "name": name,
                    "description": description,
                    "product": product,
                    "amount": amount,
                    "skip": self.store.is_picnic_skipped(name),
                    "sent_at": sent["at"] if sent else None,
                    "sent_uncertain": bool(sent and sent.get("uncertain")),
                    "cart_hint": cart_hint,
                    "rest": rest,
                    "exact": _exact_text(exact, description),
                    "small": small,
                    "small_amount": small_amount,
                    "department": groups.department_of(
                        row, self.store.shop_department(name)
                    ),
                }
            )
        on_list = {row["id"] for row in rows}
        done = [
            {
                "item_id": item_id,
                "name": entry["name"],
                "description": entry["description"],
                "department": entry["department"],
                "at": entry["at"],
            }
            for item_id, entry in self.store.shop_done_entries()
            if item_id not in on_list
        ]
        return {
            "picnic": picnic.async_status(hass),
            "items": items,
            "departments": groups.departments(),
            "done": done,
            "done_days": DONE_DAYS,
        }

    # ----- ticking off, groups and categories (0.5.0) --------------------

    async def async_shopping_check(self, item_id: int) -> None:
        """Tick an entry off: take it off the KitchenOwl list now.

        The list is read first; only an entry on it is taken off, and its
        name and amount text are remembered as read (for "back on the
        list"). The item itself stays in KitchenOwl, and so does every
        recipe that uses it. A mark of the Picnic cart (sure or unclear) is
        dropped without any call to Picnic, and so is the exact pack count
        of the entry. Returns when KitchenOwl has written.
        """
        async with self._shop_lock:
            rows = await self.client.list_shoppinglist_items(self.shoppinglist_id)
            row = next((row for row in rows if row["id"] == item_id), None)
            if row is None:
                raise ShoppingEntryError(ERR_NOT_ON_LIST, self._text("not_on_list"))
            groups = ShopGroups(self._cached_categories(), rows, self.language)
            department = groups.department_of(
                row, self.store.shop_department(row["name"])
            )
            await self.client.remove_from_shoppinglist(self.shoppinglist_id, item_id)
            self.store.async_set_shop_done(
                item_id, row["name"], row.get("description") or "", department
            )
            self.store.async_remove_picnic_sent(item_id)
            self.store.async_remove_list_exact(item_id)
            await self.store.async_save_now()

    async def async_shopping_uncheck(self, item_id: int) -> None:
        """Put an entry ticked off back on the list, with its remembered amount.

        Uses ``recipeitems``, which sums with an entry already on the list
        (the item may be back through a new recipe). The remembered entry is
        forgotten then. If the item is gone from KitchenOwl, the remembered
        entry stays and the error says so. Returns when KitchenOwl has
        written.

        One at a time (a lock), and the remembered entry leaves the store
        before anything is written: a second call at the same time finds
        nothing to put back (``not_done``), so the amount is written once.
        If writing fails (or is cancelled), the entry comes back.
        """
        async with self._shop_lock:
            done = self.store.async_pop_shop_done(item_id)
            if done is None:
                raise ShoppingEntryError(ERR_NOT_DONE, self._text("not_done"))
            try:
                item = await self.client.get_item(item_id)
                if item is None:
                    raise ShoppingEntryError(ERR_ITEM_GONE, self._text("item_gone"))
                await self.client.add_item_to_shoppinglist(
                    self.shoppinglist_id,
                    item_id,
                    item.get("name") or done["name"],
                    done["description"],
                )
            except BaseException:
                self.store.async_put_back_shop_done(item_id, done)
                raise
            await self.store.async_save_now()

    async def async_shopping_set_department(
        self, item_id: int, name: str, department: str
    ) -> None:
        """Put an ingredient into another group, now and for later.

        The choice is remembered per ingredient (by name) and wins over the
        category in KitchenOwl. With ``write_categories`` on, the category
        of the item in KitchenOwl is set as well (the user moved it, so an
        existing category is replaced): a missing category is created,
        "other" means no category. With the option off nothing is written
        to KitchenOwl.

        The list is read first: only an entry on it is moved, and its name
        is the one on the list (``name`` of the caller is not trusted).
        """
        rows = await self.client.list_shoppinglist_items(self.shoppinglist_id)
        row = next((row for row in rows if row["id"] == item_id), None)
        if row is None:
            raise ShoppingEntryError(ERR_NOT_ON_LIST, self._text("not_on_list"))
        name = str(row.get("name") or name)
        if department.startswith(FOREIGN_PREFIX):
            categories = await self._async_categories()
            if categories is None:
                raise KitchenOwlError("The categories of KitchenOwl could not be read")
            if int(department[len(FOREIGN_PREFIX) :]) not in {
                row["id"] for row in categories
            }:
                raise ShoppingEntryError(
                    ERR_UNKNOWN_DEPARTMENT, self._text("unknown_department")
                )
        elif department not in DEPARTMENTS:
            raise ShoppingEntryError(
                ERR_UNKNOWN_DEPARTMENT, self._text("unknown_department")
            )
        if self.write_categories:
            category_id = await self._async_category_id(department)
            await self.client.set_item_category(item_id, category_id)
        self.store.async_set_shop_department(name, department)

    def _text(self, key: str) -> str:
        """Return a message for the panel in the language of Home Assistant."""
        german, english = _SHOP_TEXTS[key]
        return german if self.language[:2] == "de" else english

    def _cached_categories(self) -> list[dict[str, Any]] | None:
        """Return the categories of the household as last read, if fresh."""
        if self._categories is None:
            return None
        when, rows = self._categories
        if time.monotonic() - when > CATEGORY_CACHE_TTL.total_seconds():
            return None
        return rows

    async def _async_categories(
        self, *, fresh: bool = False
    ) -> list[dict[str, Any]] | None:
        """Return the categories of the household, None if reading failed.

        Read again after a few minutes (or with ``fresh``). Never raises,
        only a cancel goes through.
        """
        if not fresh and (cached := self._cached_categories()) is not None:
            return cached
        try:
            rows = await self.client.list_categories(self.household_id)
            if not isinstance(rows, list):
                raise TypeError(f"unexpected categories: {type(rows).__name__}")
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Reading the categories of KitchenOwl failed: %r", err)
            return None
        self._categories = (time.monotonic(), rows)
        return rows

    async def _async_category_id(self, department: str) -> int | None:
        """Return the KitchenOwl category of a group, created when missing.

        "other" has none (None). A foreign group is its own category. For
        the others the categories of the household are searched (by
        ``default_key``, then by name), read again when the last read has
        none, and only then one is created, with the name of
        :func:`department_name` in the language of Home Assistant. One at a
        time, so the same category is never created twice.
        """
        if department == OTHER:
            return None
        if department.startswith(FOREIGN_PREFIX):
            return int(department[len(FOREIGN_PREFIX) :])
        async with self._category_lock:
            cached = self._cached_categories()
            if cached is not None and (found := find_category(cached, department)):
                return found["id"]
            rows = await self.client.list_categories(self.household_id)
            if not isinstance(rows, list):
                raise KitchenOwlError("Unexpected categories from KitchenOwl")
            self._categories = (time.monotonic(), rows)
            if found := find_category(rows, department):
                return found["id"]
            created = await self.client.create_category(
                self.household_id, department_name(department, self.language)
            )
            # The household has one more category: read it again next time.
            self._categories = None
            _LOGGER.info("Created the category %s in KitchenOwl", created.get("name"))
            return int(created["id"])

    def _queue_category_writes(self, recipe: Mapping[str, Any]) -> None:
        """Remember the items of a recipe that just went on the list.

        Their category is written in the background after the transfer (at
        most ``MAX_CATEGORY_WRITES`` items). Nothing with the option off.
        """
        if not self.write_categories:
            return
        try:
            for item, _scaled in kitchenowl_module.shopping_items(recipe, None):
                if len(self._category_queue) >= MAX_CATEGORY_WRITES:
                    break
                self._category_queue.setdefault(int(item["id"]), item["name"])
        except Exception:
            _LOGGER.exception("Remembering the items for their categories failed")

    @callback
    def _start_category_writes(self) -> None:
        """Start writing the categories of the queued items, in the background.

        A task of the config entry: it ends when the entry is unloaded. One
        at a time; a running one takes new items as well.
        """
        if not self._category_queue or not self.write_categories:
            self._category_queue.clear()
            return
        if self._category_task is not None and not self._category_task.done():
            return
        entry = self.config_entry
        if entry is None or self.hass is None:
            self._category_queue.clear()
            return
        self._category_task = entry.async_create_background_task(
            self.hass, self._async_write_categories(), "eatfresh_write_categories"
        )

    async def _async_write_categories(self) -> None:
        """Write the category of each queued item that has none in KitchenOwl.

        The list is read once per batch; an item that already has a
        category (or left the list) is never touched. The group is the own
        choice of the user, else :func:`classify`; "other" is not written.
        One item after the other; an error goes to the log only.
        """
        while self._category_queue:
            batch = dict(self._category_queue)
            self._category_queue.clear()
            try:
                rows = await self.client.list_shoppinglist_items(self.shoppinglist_id)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Writing categories to KitchenOwl failed: %s", err)
                continue
            by_id = {row["id"]: row for row in rows}
            for item_id in batch:
                row = by_id.get(item_id)
                if row is None or row.get("category") is not None:
                    continue
                department = self.store.shop_department(row["name"]) or classify(
                    row["name"]
                )
                if department == OTHER or not self.write_categories:
                    continue
                try:
                    category_id = await self._async_category_id(department)
                    if category_id is not None:
                        await self.client.set_item_category(item_id, category_id)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "Writing the category of %s to KitchenOwl failed: %s",
                        row["name"],
                        err,
                    )

    async def _async_take_off_cart(
        self, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Take entries surely in the Picnic cart for 3 days off the list.

        Only those due (see :meth:`FavoritesStore.due_cart_marks`), one
        after the other, never an unclear one, and only while the amount
        text on the list is still the one sent. An error goes to the log
        only: the entry and its mark stay, and the next time tries again.
        Skipped while a transfer to Picnic or another run is going on.
        Returns the rows without the entries taken off. Never raises, only
        a cancel goes through.
        """
        if self._picnic_lock.locked() or self._takeoff_lock.locked():
            return rows
        try:
            due = self.store.due_cart_marks(_list_texts(rows))
        except Exception:
            _LOGGER.exception("Finding old entries of the Picnic cart failed")
            return rows
        if not due:
            return rows
        gone: set[int] = set()
        async with self._takeoff_lock:
            for item_id in due:
                try:
                    await self.client.remove_from_shoppinglist(
                        self.shoppinglist_id, item_id
                    )
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning(
                        "Taking an entry of the Picnic cart off the list failed: %s",
                        err,
                    )
                    continue
                gone.add(item_id)
                self.store.async_remove_picnic_sent(item_id)
                self.store.async_remove_list_exact(item_id)
        if gone:
            await self.store.async_save_now()
        return [row for row in rows if row["id"] not in gone]

    async def async_picnic_send(
        self, hass: HomeAssistant, wanted: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """Put products into the Picnic cart, one entry after the other.

        Only entries that are on the shopping list and not marked as sent
        yet are sent. An entry only counts as sent when the cart in Picnic's
        answer shows the product with the pieces expected.

        Before the first product goes in, the cart is read once
        (``get_cart``), so the pieces before are known for every product.
        If that read fails or its answer is unreadable, the run does not
        start (``PicnicError``, nothing marked, nothing sent). After it only
        the answers of the single calls count.

        The run stops at the first error of any kind: no further call to
        Picnic. The entries after it are reported as ``not_tried``.

        Before each call the entry is marked as "maybe sent" and saved at
        once; the answer turns the mark into "sent", removes it (surely not
        in the cart) or leaves it (maybe in the cart: never sent again by
        itself; the user checks the Picnic app and clears the mark).

        Each failed entry carries a ``code`` (translated by the panel) and an
        English ``message`` as a fallback.

        0.5.0: an entry may carry ``small_amount`` pieces of the smaller
        product remembered for its ingredient (never one from the request;
        without one ``small_amount`` is ignored). It goes in after the main
        product, with the same marks and checks, and is not tried after an
        error of the main product. Main product in, smaller one not: the
        entry is in ``sent`` (``small_amount`` 0) and in ``failed``. With
        ``amount`` 0 only the smaller product goes in.
        """
        if self._picnic_lock.locked():
            raise picnic.PicnicError(MSG_PICNIC_BUSY, CODE_PICNIC_BUSY)
        async with self._picnic_lock:
            picnic.require_available(hass)
            rows = await self.client.list_shoppinglist_items(self.shoppinglist_id)
            names = {row["id"]: row["name"] for row in rows}
            texts = _list_texts(rows)
            on_list = set(names)
            self.store.async_prune_picnic_sent(on_list)
            sent: list[dict[str, Any]] = []
            failed: list[dict[str, Any]] = []
            seen: set[int] = set()
            stopped = False
            # The cart as read at the start, then of Picnic's last answer.
            cart: dict[str, int | None] | None = None

            def fail(item_id: int, code: str, message: str) -> None:
                failed.append({"item_id": item_id, "code": code, "message": message})

            for item in wanted:
                item_id = item["item_id"]
                product_id = item["product_id"]
                amount = int(item["amount"])
                small_amount = int(item.get("small_amount") or 0)
                if stopped:
                    fail(item_id, CODE_PICNIC_NOT_TRIED, MSG_PICNIC_NOT_TRIED)
                    continue
                if item_id in seen:
                    fail(item_id, CODE_PICNIC_TWICE, MSG_PICNIC_TWICE)
                    continue
                seen.add(item_id)
                if item_id not in on_list:
                    fail(item_id, CODE_PICNIC_NOT_ON_LIST, MSG_PICNIC_NOT_ON_LIST)
                    continue
                # A mark whose amount text changed since it was sent counts
                # as open (the entry grew): it may go again, and the old
                # mark comes back if nothing goes in.
                before = self.store.picnic_sent(item_id)
                if before is not None and not _changed_since_sent(
                    before, texts[item_id]
                ):
                    fail(item_id, CODE_PICNIC_SENT, MSG_PICNIC_SENT)
                    continue
                text = texts[item_id]
                # The smaller product always comes from the store, never
                # from the request. Without one, ``small_amount`` is ignored.
                stored_small = self.store.picnic_small(names[item_id])
                small_mark: dict[str, Any] | None = (
                    {**stored_small, "amount": small_amount}
                    if stored_small is not None and small_amount >= 1
                    else None
                )
                if amount < 1 and small_mark is None:
                    # Only a smaller product was asked for, and none is
                    # remembered (any more): nothing to put in.
                    fail(item_id, picnic.CODE_ERROR, MSG_PICNIC_NO_SMALL)
                    continue
                if cart is None:
                    # Once per run, only when something goes in: without the
                    # cart before, the run does not start (the error goes
                    # to the caller, nothing is marked).
                    cart = await picnic.async_cart(hass)
                main_in = False
                if amount >= 1:
                    # Marked as "maybe" on disk before the call: should Home
                    # Assistant stop during the call, it is never sent twice.
                    self.store.async_set_picnic_sent(
                        item_id, product_id, amount, uncertain=True, description=text
                    )
                    await self.store.async_save_now()
                    outcome, code, message, cart = await self._picnic_put(
                        hass, product_id, amount, cart
                    )
                    if outcome == _PUT_IN:
                        self.store.async_set_picnic_sent(
                            item_id, product_id, amount, description=text
                        )
                        main_in = True
                    else:
                        stopped = True
                        if outcome == _PUT_NOT:
                            # Surely not in the cart: it can go again on purpose.
                            self._picnic_restore_mark(item_id, before)
                        fail(item_id, code, message)
                        await self.store.async_save_now()
                        # The smaller product is not tried after an error.
                        continue
                if small_mark is not None:
                    self.store.async_set_picnic_sent(
                        item_id,
                        product_id,
                        amount,
                        uncertain=True,
                        small=small_mark,
                        description=text,
                    )
                    await self.store.async_save_now()
                    outcome, code, message, cart = await self._picnic_put(
                        hass, small_mark["product_id"], small_amount, cart
                    )
                    if outcome == _PUT_IN:
                        self.store.async_set_picnic_sent(
                            item_id,
                            product_id,
                            amount,
                            small=small_mark,
                            description=text,
                        )
                    else:
                        stopped = True
                        if outcome == _PUT_NOT:
                            if main_in:
                                # Only the main product is in the cart.
                                self.store.async_set_picnic_sent(
                                    item_id, product_id, amount, description=text
                                )
                            else:
                                self._picnic_restore_mark(item_id, before)
                        # "Maybe": the mark stays uncertain with both products.
                        fail(item_id, code, message)
                        small_amount = 0
                        if not main_in:
                            await self.store.async_save_now()
                            continue
                sent.append(
                    {
                        "item_id": item_id,
                        "product_id": product_id,
                        "amount": amount,
                        "small_amount": small_amount if small_mark else 0,
                    }
                )
                await self.store.async_save_now()
            # Let the Picnic integration read its cart once, but never after a
            # stop: that would be one more call to a Picnic that just failed.
            if sent and not stopped:
                await picnic.async_refresh(hass)
        return {"sent": sent, "failed": failed}

    async def async_picnic_undo(
        self, hass: HomeAssistant, item_id: int, remove: bool = True
    ) -> None:
        """Take what EatFresh put into the cart for an entry out again.

        Only for an entry surely in the cart, and only the pieces EatFresh
        put in. With ``remove`` False only the mark goes (no call to
        Picnic): for an entry that is "maybe sent" and turned out not to be
        in the cart. A "maybe sent" entry is never taken out.

        Taking out reads the cart first and compares it with the answer.
        If the answer is unclear or the pieces did not drop as expected, the
        pieces may be out already: the entry becomes "maybe sent", so it is
        never taken out a second time. The same if the cart has fewer
        pieces than EatFresh put in (nothing is taken out then).
        """
        if self._picnic_lock.locked():
            raise picnic.PicnicError(MSG_PICNIC_BUSY, CODE_PICNIC_BUSY)
        async with self._picnic_lock:
            mark = self.store.picnic_sent(item_id)
            if mark is None:
                raise picnic.PicnicNothingToUndo(MSG_PICNIC_NOTHING_TO_UNDO)
            if not remove:
                self.store.async_remove_picnic_sent(item_id)
                await self.store.async_save_now()
                return
            if mark.get("uncertain"):
                raise picnic.PicnicError(
                    MSG_PICNIC_MAYBE_NO_UNDO, CODE_PICNIC_MAYBE_NO_UNDO
                )
            small = mark.get("small")
            if mark["amount"] >= 1:
                await self._picnic_take_out(
                    hass, item_id, mark, mark["product_id"], mark["amount"]
                )
                if small is not None:
                    # The main product is out: the mark keeps only the
                    # smaller one, so a second "undo" never takes the main
                    # product out again.
                    self.store.async_set_picnic_sent(
                        item_id,
                        mark["product_id"],
                        0,
                        small=small,
                        at=mark["at"],
                        description=mark.get("description"),
                    )
                    await self.store.async_save_now()
                    mark = self.store.picnic_sent(item_id) or mark
            if small is not None:
                await self._picnic_take_out(
                    hass, item_id, mark, small["product_id"], small["amount"]
                )
            self.store.async_remove_picnic_sent(item_id)
            await self.store.async_save_now()
            await picnic.async_refresh(hass)

    async def _picnic_take_out(
        self,
        hass: HomeAssistant,
        item_id: int,
        mark: Mapping[str, Any],
        product_id: str,
        amount: int,
    ) -> None:
        """Take one product of a mark out of the cart (see ``async_picnic_undo``).

        If the pieces may be out already, the mark becomes "maybe sent" (it
        is never taken out a second time), and the error goes on.
        """
        try:
            await picnic.async_remove(hass, product_id, amount)
        except picnic.PicnicError as err:
            if not err.nothing_done or isinstance(err, picnic.PicnicCartChanged):
                self._picnic_mark_unclear(item_id, mark)
                await self.store.async_save_now()
            raise
        except Exception:
            self._picnic_mark_unclear(item_id, mark)
            await self.store.async_save_now()
            raise

    async def _picnic_put(
        self,
        hass: HomeAssistant,
        product_id: str,
        amount: int,
        cart: dict[str, int | None],
    ) -> tuple[str, str, str, dict[str, int | None]]:
        """Put one product into the cart: ``(outcome, code, message, cart)``.

        ``outcome`` is ``_PUT_IN`` (in the cart, ``cart`` is Picnic's answer),
        ``_PUT_NOT`` (surely not in the cart) or ``_PUT_MAYBE`` (it may be in
        the cart). ``code`` and ``message`` describe the failure.
        """
        try:
            answer = await picnic.async_add(hass, product_id, amount, cart)
        except picnic.PicnicError as err:
            if err.nothing_done:
                return _PUT_NOT, err.code, str(err), cart
            if isinstance(err, picnic.PicnicTimeout):
                return _PUT_MAYBE, CODE_PICNIC_MAYBE_SENT, MSG_PICNIC_MAYBE_SENT, cart
            return _PUT_MAYBE, CODE_PICNIC_MAYBE_SENT, MSG_PICNIC_UNCLEAR, cart
        except Exception:
            # Unexpected: it may have gone through. Keep "maybe", stop.
            _LOGGER.exception("Putting a product into the Picnic cart failed")
            return _PUT_MAYBE, CODE_PICNIC_MAYBE_SENT, MSG_PICNIC_UNCLEAR, cart
        return _PUT_IN, "", "", answer

    def _picnic_mark_unclear(self, item_id: int, mark: Mapping[str, Any]) -> None:
        """Turn a mark into "maybe sent" (it may be out of the cart already)."""
        self.store.async_set_picnic_sent(
            item_id,
            mark["product_id"],
            mark["amount"],
            uncertain=True,
            small=mark.get("small"),
            description=mark.get("description"),
        )

    def _picnic_restore_mark(
        self, item_id: int, before: Mapping[str, Any] | None
    ) -> None:
        """Nothing went in: put the mark from before the run back, else none.

        ``before`` is a mark whose amount text had changed (the entry was
        open again); it keeps telling what is in the cart from earlier.
        """
        if before is None:
            self.store.async_remove_picnic_sent(item_id)
            return
        self.store.async_set_picnic_sent(
            item_id,
            before["product_id"],
            before["amount"],
            uncertain=bool(before.get("uncertain")),
            small=before.get("small"),
            at=before["at"],
            description=before.get("description"),
        )


FOREIGN_PREFIX = "ko:"


class PlannerEntryError(ShoppingEntryError):
    """A meal plan entry cannot be changed, or got lost while changing it.

    ``code`` is the WebSocket error code (the panel shows the message).
    """


def _list_texts(rows: Iterable[Mapping[str, Any]]) -> dict[int, str]:
    """Return the amount text of each row of the list, by item id."""
    return {int(row["id"]): str(row.get("description") or "") for row in rows}


def _changed_since_sent(mark: Mapping[str, Any], description: str) -> bool:
    """True for a mark surely in the cart whose amount text changed since.

    An unclear mark keeps its state (it is never sent again by itself).
    """
    return not mark.get("uncertain") and cart_text_changed(mark, description)


# Messages of ShoppingEntryError: (German, English).
_SHOP_TEXTS: dict[str, tuple[str, str]] = {
    "not_on_list": (
        "Der Eintrag steht nicht mehr auf der Einkaufsliste.",
        "The entry is no longer on the shopping list.",
    ),
    "not_done": (
        "Dieser Eintrag ist nicht unter „Erledigt“.",
        "This entry is not under “Done”.",
    ),
    "item_gone": (
        "Den Artikel gibt es in KitchenOwl nicht mehr. "
        "Er bleibt unter „Erledigt“, bis die Zeit um ist.",
        "The item no longer exists in KitchenOwl. "
        "It stays under “Done” until its time is up.",
    ),
    "unknown_department": (
        "Diese Kategorie gibt es nicht.",
        "This category does not exist.",
    ),
    "unscheduled_entry": (
        "Dieses Rezept steht zusätzlich ohne Tag im Wochenplan. KitchenOwl "
        "würde diesen Eintrag beim Ändern der Portionen entfernen. Plane das "
        "Rezept ohne Tag zuerst an einem Tag ein oder nimm es heraus.",
        "This recipe is in the meal plan without a day as well. KitchenOwl "
        "would remove that entry when the servings change. Plan the recipe "
        "without a day on a day first, or take it out.",
    ),
    "plan_entry_lost": (
        "Die Portionen ließen sich nicht ändern, und der Eintrag fehlt jetzt "
        "im Wochenplan. Plane das Rezept an diesem Tag bitte neu ein.",
        "The servings could not be changed, and the entry is now missing "
        "from the meal plan. Please plan the recipe on this day again.",
    ),
}


def category_department(category: Mapping[str, Any] | None) -> str | None:
    """Return the group of a KitchenOwl category, None without one.

    By ``default_key``, else by name (:func:`match_category_name`), else
    the category is a group of its own (``ko:<id>``).
    """
    if not category:
        return None
    key = category.get("default_key")
    if isinstance(key, str) and key in KITCHENOWL_DEFAULT_KEYS:
        return KITCHENOWL_DEFAULT_KEYS[key]
    if by_name := match_category_name(category.get("name") or ""):
        return by_name
    return f"{FOREIGN_PREFIX}{int(category['id'])}"


def find_category(
    categories: Iterable[Mapping[str, Any]], department: str
) -> Mapping[str, Any] | None:
    """Return the category of the household for a group, or None.

    First one with the matching ``default_key``, then one whose name
    matches (in the order of KitchenOwl).
    """
    rows = list(categories)
    for row in rows:
        key = row.get("default_key")
        if isinstance(key, str) and KITCHENOWL_DEFAULT_KEYS.get(key) == department:
            return row
    for row in rows:
        if match_category_name(row.get("name") or "") == department:
            return row
    return None


class ShopGroups:
    """The groups of the shopping list for one answer.

    Built from the categories of the household (None when they could not
    be read) and the categories the rows of the list carry.
    """

    def __init__(
        self,
        categories: list[dict[str, Any]] | None,
        rows: Iterable[Mapping[str, Any]],
        language: str,
    ) -> None:
        self._language = language
        known: dict[int, Mapping[str, Any]] = {}
        for row in categories or ():
            known.setdefault(int(row["id"]), row)
        for row in rows:
            category = row.get("category")
            if isinstance(category, Mapping) and "id" in category:
                current = known.get(int(category["id"]))
                if current is None or (
                    not current.get("name") and category.get("name")
                ):
                    known[int(category["id"])] = category
        self._known = known

    def department_of(self, row: Mapping[str, Any], own: str | None) -> str:
        """Return the group of a list row.

        The own choice of the user (if it is still a group), else the
        category in KitchenOwl, else :func:`classify` of the name.
        """
        if own in DEPARTMENTS:
            return own
        if own and own.startswith(FOREIGN_PREFIX):
            try:
                if int(own[len(FOREIGN_PREFIX) :]) in self._known:
                    return own
            except ValueError:
                pass
        category = row.get("category")
        if isinstance(category, Mapping) and "id" in category:
            department = category_department(
                self._known.get(int(category["id"]), category)
            )
            if department:
                return department
        return classify(str(row.get("name") or ""))

    def departments(self) -> list[dict[str, str]]:
        """Return all groups in shop order, foreign ones before "other".

        The name is that of the matching KitchenOwl category when there is
        one, else :func:`department_name` in the language of Home Assistant.
        """
        categories = list(self._known.values())
        result: list[dict[str, str]] = []
        for key in DEPARTMENTS:
            if key == OTHER:
                continue
            found = find_category(categories, key)
            name = (found.get("name") if found else None) or department_name(
                key, self._language
            )
            result.append({"key": key, "name": name})
        for category in categories:
            department = category_department(category)
            if department and department.startswith(FOREIGN_PREFIX):
                result.append(
                    {
                        "key": department,
                        "name": category.get("name")
                        or department_name(OTHER, self._language),
                    }
                )
        result.append({"key": OTHER, "name": department_name(OTHER, self._language)})
        return result


def _product_view(stored: Mapping[str, Any]) -> dict[str, Any]:
    """Return a remembered Picnic product as the panel gets it."""
    return {
        "id": stored["product_id"],
        "name": stored["name"],
        "unit_quantity": stored.get("unit_quantity"),
        "price": stored.get("price"),
    }


def _sent_small_view(
    sent_small: Mapping[str, Any], remembered: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Return the smaller product in the cart as the panel gets it.

    Name, pack and price are those sent; an old mark without them takes them
    from the remembered smaller product of the same id, else the id.
    """
    same = (
        remembered
        if remembered and remembered["id"] == sent_small["product_id"]
        else {}
    )
    return {
        "id": sent_small["product_id"],
        "name": sent_small.get("name") or same.get("name") or sent_small["product_id"],
        "unit_quantity": sent_small.get("unit_quantity", same.get("unit_quantity")),
        "price": sent_small.get("price", same.get("price")),
    }


def _exact_text(row: Mapping[str, Any] | None, description: str) -> str | None:
    """Return the exact pack count of a list entry ("1.5"), None if whole.

    None as well without a valid row, or when the number on the list (parts
    of the unit of the row, as read by :func:`scale_description`) is the
    exact number: "1.5 Dose" on the list needs no "calculated 1.5". Numbers
    are compared, not texts.
    """
    if row is None or abs(row["exact"] - row["count"]) <= 0.01:
        return None
    try:
        written = sum(
            exact
            for unit, _count, exact in scale_description(
                description or "", None, None
            ).packages
            if unit == row["unit"]
        )
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Reading the amount %r failed", description)
        return None
    if abs(written - row["exact"]) <= 0.01:
        return None
    return f"{row['exact']:.2f}".rstrip("0").rstrip(".")


_PUT_IN = "in"
_PUT_NOT = "not"
_PUT_MAYBE = "maybe"


MSG_PICNIC_BUSY = "A transfer to Picnic is running already"
MSG_PICNIC_TWICE = "The entry is in the request twice"
MSG_PICNIC_NOT_ON_LIST = "The entry is no longer on the shopping list"
MSG_PICNIC_SENT = "The entry is in the Picnic cart already"
MSG_PICNIC_MAYBE_SENT = (
    "Picnic did not answer in time; the product may be in the cart anyway. "
    "Please check the Picnic app"
)
MSG_PICNIC_UNCLEAR = (
    "Picnic's answer does not show whether the product is in the cart; "
    "it may be in the cart. Please check the Picnic app"
)
MSG_PICNIC_NOT_TRIED = "Not sent: the transfer stopped at an error before"
MSG_PICNIC_NOTHING_TO_UNDO = "Nothing to undo for this entry"
MSG_PICNIC_NO_SMALL = "No smaller product is remembered for this ingredient"
MSG_PICNIC_MAYBE_NO_UNDO = (
    "EatFresh takes nothing out for an entry that is maybe in the cart; "
    "please check the Picnic app"
)
# Codes of these messages (the panel translates them).
CODE_PICNIC_BUSY = "busy"
CODE_PICNIC_TWICE = "twice"
CODE_PICNIC_NOT_ON_LIST = "not_on_list"
CODE_PICNIC_SENT = "already_sent"
CODE_PICNIC_MAYBE_SENT = "maybe_sent"
CODE_PICNIC_NOT_TRIED = "not_tried"
CODE_PICNIC_MAYBE_NO_UNDO = "maybe_no_undo"


def error_message(err: Exception) -> str:
    """Return a short message for an error."""
    if isinstance(err, EatFreshError):
        return str(err) or type(err).__name__
    return "Unexpected error"


type EatFreshConfigEntry = ConfigEntry[EatFreshData]


@callback
def async_reauth_on_auth_error(hass: HomeAssistant, err: Exception) -> None:
    """Start the reauthentication flow when KitchenOwl rejected the token."""
    cause = err.cause if isinstance(err, ShoppingListPartial) else err
    if not isinstance(cause, KitchenOwlAuthError):
        return
    entry: EatFreshConfigEntry
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        entry.async_start_reauth(hass)


@callback
def get_runtime_data(hass: HomeAssistant) -> EatFreshData | None:
    """Return the runtime data of the loaded entry or None."""
    entries: list[EatFreshConfigEntry] = hass.config_entries.async_loaded_entries(
        DOMAIN
    )
    return entries[0].runtime_data if entries else None


def enabled_source_ids(
    options: Mapping[str, Any], classes: Iterable[type[RecipeSource]]
) -> list[str]:
    """Return the ids of the enabled searchable sources.

    Without options the sources with default_enabled are used. Chefkoch is only
    returned when its terms were accepted in the options.
    """
    searchable = [cls for cls in classes if cls.searchable]
    known = {cls.id for cls in searchable}
    if CONF_SOURCES in options:
        ids = [sid for sid in options[CONF_SOURCES] if sid in known]
    else:
        ids = [cls.id for cls in searchable if cls.default_enabled]
    if not options.get(CONF_ACCEPT_CHEFKOCH):
        ids = [sid for sid in ids if sid != CHEFKOCH]
    return ids
