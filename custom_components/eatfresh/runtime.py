"""Runtime state and the shared logic behind WebSocket commands and actions."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
import logging
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.core import HomeAssistant, callback
from yarl import URL

from .const import (
    CHEFKOCH,
    CONF_ACCEPT_CHEFKOCH,
    CONF_SOURCES,
    DOMAIN,
    JSONLD,
    RECIPE_CACHE_TTL,
    SEARCH_CACHE_TTL,
)
from .errors import EatFreshError, KitchenOwlAuthError, KitchenOwlError, RecipeNotFound
from .http import UnsafeAddress, check_public_url, host_matches, split_url
from .kitchenowl import normalize_source
from .models import Recipe, SearchHit, split_key
from .store import Favorite, FavoritesStore, TTLCache

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .kitchenowl import KitchenOwlClient
    from .sources.base import RecipeSource

_LOGGER = logging.getLogger(__name__)


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
    # One lock per normalized recipe address, so two hearts at the same time
    # create only one recipe in KitchenOwl.
    _save_locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    _save_users: dict[str, int] = field(default_factory=dict)

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
        """Return the KitchenOwl id of a favorite or None."""
        found = self.favorite_for(key, url)
        return found[1]["kitchenowl_id"] if found else None

    @callback
    def is_favorite(self, key: str, url: str | None = None) -> bool:
        """Return True if the recipe has a heart (by key or by address)."""
        return self.favorite_for(key, url) is not None

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
            kitchenowl_id = await self.client.create_recipe(self.household_id, to_create)
            created = True
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
        """Set the heart of a recipe."""
        if (found := self.favorite_for(key)) is not None:
            return found[1]["kitchenowl_id"], False
        recipe = await self.async_get_recipe(key)
        return await self.async_save_recipe(recipe)

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
        """Return all favorites, newest first."""
        return self.store.items()

    # ----- KitchenOwl ---------------------------------------------------

    async def async_collection(self) -> list[dict[str, Any]]:
        """Return the recipes stored in KitchenOwl."""
        return await self.client.list_recipes(self.household_id)

    async def async_add_to_shopping_list(self, recipe_ids: list[int]) -> int:
        """Put the ingredients of KitchenOwl recipes on the shopping list.

        The recipes are sent one after the other, in the given order. If one
        fails after others went through, ``ShoppingListPartial`` says how many
        are already on the list, so a second try can leave them out.
        """
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
