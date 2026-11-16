"""Runtime state and the shared logic behind WebSocket commands and actions."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
import logging
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util
from yarl import URL

from . import kitchenowl as kitchenowl_module, picnic
from .categories import canonical_category, category_names, suggest_categories
from .const import (
    CHEFKOCH,
    CONF_ACCEPT_CHEFKOCH,
    CONF_PLANNER_INTERVAL,
    CONF_SOURCES,
    DEFAULT_PLANNER_INTERVAL,
    DEFAULT_COLLECTION_LIMIT,
    DOMAIN,
    JSONLD,
    MAX_PLANNER_INTERVAL,
    MAX_TAG_LENGTH,
    MAX_TAGS,
    MIN_PLANNER_INTERVAL,
    PLANNER_MAX_AGE,
    RECIPE_CACHE_TTL,
    SEARCH_CACHE_TTL,
)
from .errors import EatFreshError, KitchenOwlAuthError, KitchenOwlError, RecipeNotFound
from .http import UnsafeAddress, check_public_url, host_matches, split_url
from .kitchenowl import normalize_source
from .models import Recipe, SearchHit, split_key
from .picnic_amount import suggest_amount
from .store import Favorite, FavoritesStore, TTLCache

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


def plan_item(day: date, entry: Mapping[str, Any]) -> dict[str, Any]:
    """Return ``{date, recipe_id, name}`` of a meal plan entry (actions, sensor)."""
    return {
        "date": day.isoformat(),
        "recipe_id": entry["recipe_id"],
        "name": str(entry.get("name") or ""),
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
    except (TypeError, ValueError):
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
                errors.append(
                    {"source": source_id, "message": error_message(result)}
                )
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
    def language(self) -> str:
        """Return the language of Home Assistant."""
        return self.hass.config.language if self.hass is not None else "en"

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
            kitchenowl_id = await self.client.create_recipe(self.household_id, to_create)
            created = True
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

    # ----- KitchenOwl ---------------------------------------------------

    async def async_collection(self, include_hidden: bool = False) -> list[dict[str, Any]]:
        """Return the recipes stored in KitchenOwl.

        Each recipe gets ``hidden``. Hidden recipes are left out unless
        ``include_hidden`` is set.
        """
        recipes = []
        for recipe in await self.client.list_recipes(self.household_id):
            hidden = self.store.is_hidden(recipe.get("id"))
            if hidden and not include_hidden:
                continue
            tags = self.localize_tags(recipe.get("tags") or [])
            recipes.append({**recipe, "tags": tags, "hidden": hidden})
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
        """Return a recipe as stored in KitchenOwl. No recipe page is fetched."""
        await self.async_require_own([kitchenowl_id])
        data = await self.client.get_recipe(kitchenowl_id)
        household = data.get("household_id")
        if household is not None and household != self.household_id:
            raise RecipeNotFound("The recipe belongs to another household")
        return kitchenowl_module.recipe_to_model(data)

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

    async def async_planner_add(self, kitchenowl_id: int, day: date) -> None:
        """Plan a recipe of the own collection on a day."""
        await self.async_require_own([kitchenowl_id])
        try:
            await self.client.add_planner_entry(self.household_id, kitchenowl_id, day)
        finally:
            await self._async_refresh_planner()

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
        try:
            added = await self.async_add_to_shopping_list(recipe_ids)
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

    async def async_add_to_shopping_list(self, recipe_ids: list[int]) -> int:
        """Put the ingredients of KitchenOwl recipes on the shopping list.

        The recipes are sent one after the other, in the given order. If one
        fails after others went through, ``ShoppingListPartial`` says how many
        are already on the list, so a second try can leave them out.
        """
        await self.async_require_own(recipe_ids)
        added = 0
        for done, recipe_id in enumerate(recipe_ids):
            try:
                added += await self.client.add_recipe_to_shoppinglist(
                    self.shoppinglist_id, recipe_id
                )
            except EatFreshError as err:
                if done == 0:
                    raise
                raise ShoppingListPartial(err, done, len(recipe_ids), added) from err
        return added

    # ----- Picnic -------------------------------------------------------

    async def async_shopping(self, hass: HomeAssistant) -> dict[str, Any]:
        """Return the shopping list with the remembered Picnic products.

        Reads only KitchenOwl and the store, never Picnic. Marks of entries
        that left the list or are older than 14 days are dropped.
        """
        rows = await self.client.list_shoppinglist_items(self.shoppinglist_id)
        self.store.async_prune_picnic_sent(row["id"] for row in rows)
        items: list[dict[str, Any]] = []
        for row in rows:
            name = row["name"]
            description = row.get("description") or ""
            product: dict[str, Any] | None = None
            amount = 1
            if (stored := self.store.picnic_product(name)) is not None:
                product = {
                    "id": stored["product_id"],
                    "name": stored["name"],
                    "unit_quantity": stored["unit_quantity"],
                    "price": stored["price"],
                }
                amount = stored["amount"] or suggest_amount(
                    description, stored["unit_quantity"]
                )
            sent = self.store.picnic_sent(row["id"])
            if sent is not None:
                # Show what went into the cart (and what "undo" takes out).
                amount = sent["amount"]
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
                }
            )
        return {"picnic": picnic.async_status(hass), "items": items}

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
        """
        if self._picnic_lock.locked():
            raise picnic.PicnicError(MSG_PICNIC_BUSY, CODE_PICNIC_BUSY)
        async with self._picnic_lock:
            picnic.require_available(hass)
            rows = await self.client.list_shoppinglist_items(self.shoppinglist_id)
            on_list = {row["id"] for row in rows}
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
                amount = item["amount"]
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
                if self.store.picnic_sent(item_id) is not None:
                    fail(item_id, CODE_PICNIC_SENT, MSG_PICNIC_SENT)
                    continue
                if cart is None:
                    # Once per run, only when something goes in: without the
                    # cart before, the run does not start (the error goes
                    # to the caller, nothing is marked).
                    cart = await picnic.async_cart(hass)
                # Marked as "maybe" on disk before the call: should Home
                # Assistant stop during the call, it is never sent twice.
                self.store.async_set_picnic_sent(
                    item_id, product_id, amount, uncertain=True
                )
                await self.store.async_save_now()
                try:
                    cart = await picnic.async_add(hass, product_id, amount, cart)
                except picnic.PicnicError as err:
                    stopped = True
                    if err.nothing_done:
                        # Surely not in the cart: it can go again on purpose.
                        self.store.async_remove_picnic_sent(item_id)
                        fail(item_id, err.code, str(err))
                    elif isinstance(err, picnic.PicnicTimeout):
                        fail(item_id, CODE_PICNIC_MAYBE_SENT, MSG_PICNIC_MAYBE_SENT)
                    else:
                        fail(item_id, CODE_PICNIC_MAYBE_SENT, MSG_PICNIC_UNCLEAR)
                except Exception:
                    # Unexpected: it may have gone through. Keep "maybe", stop.
                    _LOGGER.exception("Putting a product into the Picnic cart failed")
                    stopped = True
                    fail(item_id, CODE_PICNIC_MAYBE_SENT, MSG_PICNIC_UNCLEAR)
                else:
                    self.store.async_set_picnic_sent(item_id, product_id, amount)
                    sent.append(
                        {"item_id": item_id, "product_id": product_id, "amount": amount}
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
                raise picnic.PicnicError(MSG_PICNIC_MAYBE_NO_UNDO, CODE_PICNIC_MAYBE_NO_UNDO)
            try:
                await picnic.async_remove(hass, mark["product_id"], mark["amount"])
            except picnic.PicnicError as err:
                if not err.nothing_done or isinstance(err, picnic.PicnicCartChanged):
                    self._picnic_mark_unclear(item_id, mark)
                    await self.store.async_save_now()
                raise
            except Exception:
                self._picnic_mark_unclear(item_id, mark)
                await self.store.async_save_now()
                raise
            self.store.async_remove_picnic_sent(item_id)
            await self.store.async_save_now()
            await picnic.async_refresh(hass)

    def _picnic_mark_unclear(self, item_id: int, mark: Mapping[str, Any]) -> None:
        """Turn a mark into "maybe sent" (it may be out of the cart already)."""
        self.store.async_set_picnic_sent(
            item_id, mark["product_id"], mark["amount"], uncertain=True
        )


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
