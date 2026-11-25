"""WebSocket commands used by the EatFresh panel."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from datetime import date
from functools import wraps
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from . import picnic
from .const import (
    DEFAULT_SEARCH_LIMIT,
    DOMAIN,
    ERR_KITCHENOWL_AUTH,
    ERR_KITCHENOWL_ERROR,
    ERR_NOT_FOUND,
    ERR_NOT_LOADED,
    ERR_PICNIC_ERROR,
    ERR_PICNIC_UNAVAILABLE,
    ERR_SOURCE_BLOCKED,
    ERR_SOURCE_ERROR,
    MAX_PICNIC_AMOUNT,
    MAX_PICNIC_NAME_LENGTH,
    MAX_PICNIC_QUERY_LENGTH,
    MAX_PICNIC_REST_LENGTH,
    MAX_PICNIC_SEND_ITEMS,
    MAX_PICNIC_SMALL_AMOUNT,
    MAX_PLANNER_YEAR,
    MAX_SEARCH_LIMIT,
    MAX_TAG_LENGTH,
    MAX_TAGS,
    MIN_PLANNER_YEAR,
    PICNIC_SEARCH_LIMIT,
)
from .departments import DEPARTMENTS
from .errors import (
    EatFreshError,
    KitchenOwlAuthError,
    KitchenOwlError,
    RecipeNotFound,
    SourceBlocked,
    SourceError,
)
from .image_proxy import sign_image_url, sign_photo
from .kitchenowl import MAX_ITEM_NAME
from .picnic_amount import fits_rest
from .portions import MAX_SERVINGS, MIN_SERVINGS
from .runtime import (
    FOREIGN_PREFIX,
    EatFreshData,
    PlannerWeek,
    ShoppingEntryError,
    ShoppingListPartial,
    async_reauth_on_auth_error,
    entry_servings,
    error_message,
    get_runtime_data,
    today,
)

_LOGGER = logging.getLogger(__name__)

KITCHENOWL_ID = vol.All(vol.Coerce(int), vol.Range(min=1))


def whole_number(value: Any) -> int:
    """Accept only a whole number: no bool, no text, no float (not 3.0)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise vol.Invalid("Expected a whole number")
    return value


SERVINGS = vol.All(whole_number, vol.Range(min=MIN_SERVINGS, max=MAX_SERVINGS))
# Names of remembered ingredients (KitchenOwl allows 128 characters).
INGREDIENT_NAMES = vol.All(
    [vol.All(str, vol.Length(min=1, max=MAX_ITEM_NAME))], vol.Length(max=200)
)


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _iso_date(value: Any) -> date:
    """Validate a day written as YYYY-MM-DD, in the years 2000 to 2100.

    KitchenOwl keeps "no day" as 0001-01-01, and days far away break the
    week arithmetic, so only sensible years are accepted.
    """
    if isinstance(value, str) and _ISO_DATE.fullmatch(value):
        try:
            day = date.fromisoformat(value)
        except ValueError:
            pass
        else:
            if MIN_PLANNER_YEAR <= day.year <= MAX_PLANNER_YEAR:
                return day
            raise vol.Invalid(
                f"Expected a day in the years {MIN_PLANNER_YEAR} to {MAX_PLANNER_YEAR}"
            )
    raise vol.Invalid("Expected a date as YYYY-MM-DD")


type Handler = Callable[
    [HomeAssistant, websocket_api.ActiveConnection, dict[str, Any], EatFreshData],
    Awaitable[None],
]


def error_code(err: EatFreshError) -> str:
    """Map an EatFresh error to a WebSocket error code."""
    # Order matters: subclasses first.
    if isinstance(err, ShoppingEntryError):
        return err.code
    if isinstance(err, SourceBlocked):
        return ERR_SOURCE_BLOCKED
    if isinstance(err, RecipeNotFound):
        return ERR_NOT_FOUND
    if isinstance(err, SourceError):
        return ERR_SOURCE_ERROR
    if isinstance(err, KitchenOwlAuthError):
        return ERR_KITCHENOWL_AUTH
    if isinstance(err, KitchenOwlError):
        return ERR_KITCHENOWL_ERROR
    if isinstance(err, picnic.PicnicNothingToUndo):
        return ERR_NOT_FOUND
    if isinstance(err, picnic.PicnicUnavailable):
        return ERR_PICNIC_UNAVAILABLE
    if isinstance(err, picnic.PicnicError):
        return ERR_PICNIC_ERROR
    return ERR_SOURCE_ERROR


def _with_data(
    func: Handler,
) -> Callable[
    [HomeAssistant, websocket_api.ActiveConnection, dict[str, Any]], Awaitable[None]
]:
    """Pass the runtime data and turn EatFresh errors into WebSocket errors."""

    @wraps(func)
    async def wrapper(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        data = get_runtime_data(hass)
        if data is None:
            connection.send_error(msg["id"], ERR_NOT_LOADED, "EatFresh is not set up")
            return
        try:
            await func(hass, connection, msg, data)
        except ShoppingListPartial as err:
            async_reauth_on_auth_error(hass, err)
            # The panel reads the placeholders to leave out the recipes that
            # are already on the list when the user tries again.
            connection.send_error(
                msg["id"],
                error_code(err.cause),
                error_message(err),
                translation_key="shopping_list_partial",
                translation_domain=DOMAIN,
                translation_placeholders={
                    "added_recipes": str(err.done),
                    "total": str(err.total),
                    "added": str(err.items),
                    "message": error_message(err.cause),
                },
            )
        except ShoppingEntryError as err:
            # The message is in the language of Home Assistant already.
            connection.send_error(
                msg["id"],
                err.code,
                error_message(err),
                translation_key=err.code,
                translation_domain=DOMAIN,
            )
        except picnic.PicnicError as err:
            # The panel translates the code of a Picnic error (translation_key).
            connection.send_error(
                msg["id"],
                error_code(err),
                error_message(err),
                translation_key=f"picnic_{err.code}",
                translation_domain=DOMAIN,
            )
        except EatFreshError as err:
            async_reauth_on_auth_error(hass, err)
            connection.send_error(msg["id"], error_code(err), error_message(err))

    return wrapper


@callback
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register all EatFresh WebSocket commands."""
    for command in (
        ws_sources,
        ws_search,
        ws_recipe,
        ws_favorite,
        ws_unfavorite,
        ws_favorites,
        ws_collection,
        ws_collection_recipe,
        ws_collection_hide,
        ws_collection_unhide,
        ws_collection_set_tags,
        ws_collection_restore,
        ws_collection_forget,
        ws_tags,
        ws_shopping_list_add,
        ws_planner,
        ws_planner_add,
        ws_planner_remove,
        ws_planner_set_servings,
        ws_planner_shopping_list,
        ws_shopping,
        ws_picnic_search,
        ws_picnic_map,
        ws_picnic_map_small,
        ws_picnic_unmap,
        ws_picnic_skip,
        ws_picnic_send,
        ws_picnic_undo,
        ws_shopping_check,
        ws_shopping_uncheck,
        ws_shopping_set_department,
    ):
        websocket_api.async_register_command(hass, command)


@websocket_api.websocket_command({vol.Required("type"): "eatfresh/sources"})
@websocket_api.async_response
@_with_data
async def ws_sources(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Return the enabled sources."""
    from .sources import SOURCE_CLASSES  # noqa: PLC0415

    sources = [
        {
            "id": cls.id,
            "name": cls.name,
            "enabled": cls.id in data.sources,
            "searchable": cls.searchable,
        }
        for cls in SOURCE_CLASSES
    ]
    connection.send_result(msg["id"], {"sources": sources})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/search",
        vol.Required("query"): vol.All(str, vol.Strip, vol.Length(min=1, max=200)),
        vol.Optional("sources"): [str],
        vol.Optional("limit", default=DEFAULT_SEARCH_LIMIT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_SEARCH_LIMIT)
        ),
    }
)
@websocket_api.async_response
@_with_data
async def ws_search(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Search the recipe sources. ``limit`` applies to each source."""
    result = await data.async_search(msg["query"], msg.get("sources"), msg["limit"])
    hits = []
    for hit in result.hits:
        item = hit.as_dict()
        item["image"] = sign_image_url(hass, hit.image)
        item["favorite"] = data.is_favorite(hit.key, hit.url)
        hits.append(item)
    connection.send_result(msg["id"], {"hits": hits, "errors": result.errors})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/recipe",
        vol.Exclusive("key", "recipe"): str,
        vol.Exclusive("url", "recipe"): vol.All(str, vol.Strip, vol.Url()),
    }
)
@websocket_api.async_response
@_with_data
async def ws_recipe(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Return a full recipe by key or by web address."""
    if "key" in msg:
        recipe = await data.async_get_recipe(msg["key"])
    elif "url" in msg:
        recipe = await data.async_get_recipe_by_url(msg["url"])
    else:
        connection.send_error(
            msg["id"], websocket_api.ERR_INVALID_FORMAT, "Need key or url"
        )
        return
    item = recipe.as_dict()
    item["image"] = sign_image_url(hass, recipe.image)
    kitchenowl_id = data.kitchenowl_id_of(recipe.key, recipe.url)
    connection.send_result(
        msg["id"],
        {
            "recipe": item,
            "favorite": kitchenowl_id is not None,
            "kitchenowl_id": kitchenowl_id,
        },
    )


@websocket_api.websocket_command(
    {vol.Required("type"): "eatfresh/favorite", vol.Required("key"): str}
)
@websocket_api.async_response
@_with_data
async def ws_favorite(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Set the heart: save the recipe in KitchenOwl if needed.

    A recipe hidden in the collection is shown again. ``tags`` are the tags
    of the recipe in KitchenOwl.
    """
    kitchenowl_id, created = await data.async_favorite(msg["key"])
    try:
        tags = await data.async_recipe_tags(kitchenowl_id)
    except EatFreshError as err:
        # The heart is set; missing tags must not turn it into an error.
        _LOGGER.debug("Tags of recipe %s not loaded: %s", kitchenowl_id, err)
        tags = []
    connection.send_result(
        msg["id"], {"kitchenowl_id": kitchenowl_id, "created": created, "tags": tags}
    )


@websocket_api.websocket_command(
    {vol.Required("type"): "eatfresh/unfavorite", vol.Required("key"): str}
)
@websocket_api.async_response
@_with_data
async def ws_unfavorite(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Remove the heart. KitchenOwl stays unchanged."""
    data.async_unfavorite(msg["key"])
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command({vol.Required("type"): "eatfresh/favorites"})
@websocket_api.async_response
@_with_data
async def ws_favorites(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Return all favorites."""
    favorites = [
        {
            "key": key,
            "source": favorite["source"],
            "id": favorite["id"],
            "url": favorite["url"],
            "title": favorite["title"],
            "image": sign_image_url(hass, favorite.get("image")),
            "kitchenowl_id": favorite["kitchenowl_id"],
            "added_at": favorite["added_at"],
        }
        for key, favorite in data.favorites()
    ]
    connection.send_result(msg["id"], {"favorites": favorites})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/collection",
        vol.Optional("include_hidden", default=False): bool,
    }
)
@websocket_api.async_response
@_with_data
async def ws_collection(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Return the recipes stored in KitchenOwl (hidden ones only on request).

    ``missing`` is the number of remembered ingredients a recipe no longer
    has in KitchenOwl.
    """
    recipes = [
        {
            "kitchenowl_id": recipe["id"],
            "name": recipe.get("name"),
            "image": sign_photo(hass, recipe.get("photo")),
            "source": recipe.get("source"),
            "time": recipe.get("time"),
            "yields": recipe.get("yields"),
            "tags": list(recipe.get("tags") or []),
            "hidden": recipe["hidden"],
            "missing": recipe.get("missing", 0),
        }
        for recipe in await data.async_collection(msg["include_hidden"])
    ]
    connection.send_result(msg["id"], {"recipes": recipes})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/collection/recipe",
        vol.Required("kitchenowl_id"): KITCHENOWL_ID,
        vol.Optional("servings"): SERVINGS,
    }
)
@websocket_api.async_response
@_with_data
async def ws_collection_recipe(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Return a recipe as stored in KitchenOwl, without loading its web page.

    The ingredients include the remembered ones missing in KitchenOwl;
    ``missing`` lists their names. The amounts are scaled to ``servings``
    (default: the start value of the recipe); ``portions`` says how, and
    each ingredient carries ``portion: {scaled, rounded_from}``.
    """
    kitchenowl_id = msg["kitchenowl_id"]
    recipe, missing, portions, marks = await data.async_collection_recipe_portions(
        kitchenowl_id, msg.get("servings")
    )
    item = recipe.as_dict()
    item["image"] = sign_photo(hass, recipe.image)
    for ingredient, mark in zip(item["ingredients"], marks, strict=False):
        ingredient["portion"] = mark
    connection.send_result(
        msg["id"],
        {
            "recipe": item,
            "kitchenowl_id": kitchenowl_id,
            "tags": data.localize_tags(recipe.tags),
            "hidden": data.store.is_hidden(kitchenowl_id),
            "missing": missing,
            "portions": portions,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/collection/hide",
        vol.Required("kitchenowl_id"): KITCHENOWL_ID,
    }
)
@websocket_api.async_response
@_with_data
async def ws_collection_hide(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Hide a recipe of the own collection. KitchenOwl stays unchanged."""
    await data.async_hide(msg["kitchenowl_id"])
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/collection/unhide",
        vol.Required("kitchenowl_id"): KITCHENOWL_ID,
    }
)
@websocket_api.async_response
@_with_data
async def ws_collection_unhide(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Show a hidden recipe in the collection again."""
    data.async_unhide(msg["kitchenowl_id"])
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/collection/set_tags",
        vol.Required("kitchenowl_id"): KITCHENOWL_ID,
        vol.Required("tags"): vol.All(
            [vol.All(str, vol.Length(max=MAX_TAG_LENGTH))],
            vol.Length(max=MAX_TAGS),
        ),
    }
)
@websocket_api.async_response
@_with_data
async def ws_collection_set_tags(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Replace the tags (categories) of a KitchenOwl recipe."""
    tags = await data.async_set_tags(msg["kitchenowl_id"], msg["tags"])
    connection.send_result(msg["id"], {"tags": tags})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/collection/restore",
        vol.Required("kitchenowl_id"): KITCHENOWL_ID,
    }
)
@websocket_api.async_response
@_with_data
async def ws_collection_restore(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Add the remembered ingredients missing in KitchenOwl back to a recipe.

    Only adds: every ingredient the recipe has stays. ``missing`` lists the
    names still missing after the write (normally none).
    """
    result = await data.async_restore_ingredients(msg["kitchenowl_id"])
    connection.send_result(
        msg["id"], {"restored": result["restored"], "missing": result["missing"]}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/collection/forget",
        vol.Required("kitchenowl_id"): KITCHENOWL_ID,
        vol.Optional("names"): INGREDIENT_NAMES,
    }
)
@websocket_api.async_response
@_with_data
async def ws_collection_forget(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Forget remembered ingredients that are missing in KitchenOwl.

    Without ``names`` all missing ones are forgotten. KitchenOwl stays
    unchanged.
    """
    result = await data.async_forget_ingredients(msg["kitchenowl_id"], msg.get("names"))
    connection.send_result(
        msg["id"], {"removed": result["removed"], "missing": result["missing"]}
    )


@websocket_api.websocket_command({vol.Required("type"): "eatfresh/tags"})
@websocket_api.async_response
@_with_data
async def ws_tags(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Return the canonical categories and all tags of the household."""
    categories, tags = await data.async_tags()
    connection.send_result(msg["id"], {"categories": categories, "tags": tags})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/shopping_list/add",
        vol.Required("kitchenowl_ids"): vol.All(
            [vol.Coerce(int)], vol.Length(min=1, max=50)
        ),
        vol.Optional("servings"): SERVINGS,
    }
)
@websocket_api.async_response
@_with_data
async def ws_shopping_list_add(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Put the ingredients of KitchenOwl recipes on the shopping list.

    The amounts are scaled to ``servings`` (default: the start value of
    each recipe).
    """
    added = await data.async_add_to_shopping_list(
        msg["kitchenowl_ids"], msg.get("servings")
    )
    connection.send_result(msg["id"], {"added": added})


def _planner_item(
    hass: HomeAssistant, entry: dict[str, Any], default: int
) -> dict[str, Any]:
    """Return one meal plan entry as the panel and the cards read it.

    ``servings`` is the number of the entry, else the start value of the
    recipe, else None; ``base`` the ``yields`` of the recipe or None.
    """
    base = entry.get("base")
    return {
        "kitchenowl_id": entry["recipe_id"],
        "name": entry.get("name"),
        "image": sign_photo(hass, entry.get("photo")),
        "servings": entry_servings(entry, default),
        "base": base if isinstance(base, int) else None,
    }


def _week_result(
    hass: HomeAssistant, week: PlannerWeek, data: EatFreshData
) -> dict[str, Any]:
    """Return a week; ``today`` lets the panel and the cards use HA's day.

    ``shopping_list_at`` is when the week went to the shopping list (ISO
    time, UTC) or None. ``default_servings`` is the option of the entry.
    """
    default = data.default_servings
    return {
        "week_start": week.week_start.isoformat(),
        "today": today().isoformat(),
        "shopping_list_at": data.week_list_time(week.week_start),
        "default_servings": default,
        "days": [
            {
                "date": day.isoformat(),
                "entries": [_planner_item(hass, entry, default) for entry in entries],
            }
            for day, entries in week.days
        ],
        "unscheduled": [
            _planner_item(hass, entry, default) for entry in week.unscheduled
        ],
    }


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/planner",
        vol.Optional("week_start"): _iso_date,
    }
)
@websocket_api.async_response
@_with_data
async def ws_planner(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Return the meal plan of a week, Monday to Sunday.

    Without ``week_start`` the current week is used (time zone of Home
    Assistant). A day other than Monday stands for the week it is in.
    ``today`` is the current day in the time zone of Home Assistant, so the
    panel and the cards do not depend on the time zone of the browser.
    """
    week = await data.async_planner_week(msg.get("week_start"))
    connection.send_result(msg["id"], _week_result(hass, week, data))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/planner/add",
        vol.Required("kitchenowl_id"): KITCHENOWL_ID,
        vol.Required("date"): _iso_date,
        vol.Optional("servings"): SERVINGS,
    }
)
@websocket_api.async_response
@_with_data
async def ws_planner_add(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Plan a KitchenOwl recipe on a day (default: its start servings)."""
    await data.async_planner_add(msg["kitchenowl_id"], msg["date"], msg.get("servings"))
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/planner/set_servings",
        vol.Required("kitchenowl_id"): KITCHENOWL_ID,
        vol.Required("date"): _iso_date,
        vol.Required("servings"): SERVINGS,
    }
)
@websocket_api.async_response
@_with_data
async def ws_planner_set_servings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Change the servings of a recipe planned on a day.

    The shopping list stays as it is, even if the week went to it.
    """
    await data.async_planner_set_servings(
        msg["kitchenowl_id"], msg["date"], msg["servings"]
    )
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/planner/remove",
        vol.Required("kitchenowl_id"): KITCHENOWL_ID,
        vol.Optional("date"): vol.Any(None, _iso_date),
    }
)
@websocket_api.async_response
@_with_data
async def ws_planner_remove(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Take a recipe off a day, or off the plan without a day."""
    await data.async_planner_remove(msg["kitchenowl_id"], msg.get("date"))
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/planner/shopping_list",
        vol.Optional("week_start"): _iso_date,
        vol.Optional("confirm", default=False): bool,
    }
)
@websocket_api.async_response
@_with_data
async def ws_planner_shopping_list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Put the ingredients of the recipes planned in a week on the list.

    If the week went to the list before (on any device), nothing is sent
    unless ``confirm`` is set; the answer then carries ``already_added_at``.
    """
    result = await data.async_planner_shopping_list(
        msg.get("week_start"), confirm=msg["confirm"]
    )
    connection.send_result(msg["id"], result)


# ----- shopping list and Picnic ---------------------------------------------

PICNIC_NAME = vol.All(str, vol.Strip, vol.Length(min=1, max=MAX_PICNIC_NAME_LENGTH))


def _picnic_product_id(value: Any) -> str:
    """Validate a Picnic product id: text (or a whole number) of 1 to 64 signs."""
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        raise vol.Invalid("Expected a product id")
    value = value.strip()
    if not 1 <= len(value) <= picnic.MAX_ID_LENGTH or not value.isprintable():
        raise vol.Invalid("Expected a product id of 1 to 64 signs")
    return value


def _price_cents(value: Any) -> int:
    """Validate a price in cents."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise vol.Invalid("Expected a price in cents")
    return value


PICNIC_PRODUCT_ID = _picnic_product_id
PICNIC_AMOUNT = vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_PICNIC_AMOUNT))
# 0.5.0: in a transfer the main product may have 0 pieces (only the smaller
# product goes in), and the smaller product 0 to 20.
PICNIC_SEND_AMOUNT = vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_PICNIC_AMOUNT))
PICNIC_SMALL_AMOUNT = vol.All(
    vol.Coerce(int), vol.Range(min=0, max=MAX_PICNIC_SMALL_AMOUNT)
)
PICNIC_REST_TEXT = vol.All(str, vol.Strip, vol.Length(max=MAX_PICNIC_REST_LENGTH))


def _something_to_send(item: dict[str, Any]) -> dict[str, Any]:
    """Require at least one piece of the main or the smaller product."""
    if item["amount"] < 1 and item["small_amount"] < 1:
        raise vol.Invalid("amount or small_amount must be at least 1")
    return item


PICNIC_PRODUCT = vol.Schema(
    {
        vol.Required("id"): PICNIC_PRODUCT_ID,
        vol.Required("name"): vol.All(
            str, vol.Strip, vol.Length(min=1, max=picnic.MAX_NAME_LENGTH)
        ),
        vol.Optional("unit_quantity", default=None): vol.Any(
            None, vol.All(str, vol.Strip, vol.Length(max=picnic.MAX_UNIT_LENGTH))
        ),
        vol.Optional("price", default=None): vol.Any(None, _price_cents),
    },
    extra=vol.REMOVE_EXTRA,
)


@websocket_api.websocket_command({vol.Required("type"): "eatfresh/shopping"})
@websocket_api.async_response
@_with_data
async def ws_shopping(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Return the shopping list with Picnic products. Never calls Picnic."""
    connection.send_result(msg["id"], await data.async_shopping(hass))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/picnic/search",
        vol.Required("query"): vol.All(
            str, vol.Strip, vol.Length(min=1, max=MAX_PICNIC_QUERY_LENGTH)
        ),
        # 0.5.0: the rest a smaller pack has to cover and the main pack.
        vol.Optional("rest"): vol.Any(None, PICNIC_REST_TEXT),
        vol.Optional("main_unit_quantity"): vol.Any(None, PICNIC_REST_TEXT),
    }
)
@websocket_api.async_response
@_with_data
async def ws_picnic_search(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Search Picnic products (only when the user asks).

    Each hit says whether it is a smaller pack that covers ``rest``
    (``fits_rest``); without ``rest`` it is always False.
    """
    products = await picnic.async_search(hass, msg["query"], PICNIC_SEARCH_LIMIT)
    rest = msg.get("rest") or None
    main = msg.get("main_unit_quantity") or None
    for product in products:
        product["fits_rest"] = fits_rest(rest, product.get("unit_quantity"), main)
    connection.send_result(msg["id"], {"products": products})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/picnic/map",
        vol.Required("name"): PICNIC_NAME,
        vol.Required("product"): PICNIC_PRODUCT,
        vol.Optional("amount"): PICNIC_AMOUNT,
    }
)
@websocket_api.async_response
@_with_data
async def ws_picnic_map(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Remember the Picnic product of an ingredient."""
    product = msg["product"]
    data.store.async_set_picnic_product(
        msg["name"],
        product_id=product["id"],
        product_name=product["name"],
        unit_quantity=product["unit_quantity"] or None,
        price=product["price"],
        amount=msg.get("amount"),
    )
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/picnic/map_small",
        vol.Required("name"): PICNIC_NAME,
        vol.Required("product"): vol.Any(None, PICNIC_PRODUCT),
    }
)
@websocket_api.async_response
@_with_data
async def ws_picnic_map_small(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Remember (or with ``product: null`` forget) the smaller product.

    Only for an ingredient with a remembered main product (else not found).
    """
    product = msg["product"]
    small = (
        None
        if product is None
        else {
            "product_id": product["id"],
            "name": product["name"],
            "unit_quantity": product["unit_quantity"] or None,
            "price": product["price"],
        }
    )
    if not data.store.async_set_picnic_small(msg["name"], small):
        connection.send_error(
            msg["id"],
            ERR_NOT_FOUND,
            "No Picnic product is remembered for this ingredient",
        )
        return
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {vol.Required("type"): "eatfresh/picnic/unmap", vol.Required("name"): PICNIC_NAME}
)
@websocket_api.async_response
@_with_data
async def ws_picnic_unmap(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Forget the Picnic product of an ingredient."""
    data.store.async_remove_picnic_product(msg["name"])
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/picnic/skip",
        vol.Required("name"): PICNIC_NAME,
        vol.Required("skip"): bool,
    }
)
@websocket_api.async_response
@_with_data
async def ws_picnic_skip(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Never buy an ingredient at Picnic, or take it back in."""
    data.store.async_set_picnic_skip(msg["name"], msg["skip"])
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/picnic/send",
        vol.Required("items"): vol.All(
            [
                vol.All(
                    vol.Schema(
                        {
                            vol.Required("item_id"): KITCHENOWL_ID,
                            vol.Required("product_id"): PICNIC_PRODUCT_ID,
                            vol.Required("amount"): PICNIC_SEND_AMOUNT,
                            vol.Optional(
                                "small_amount", default=0
                            ): PICNIC_SMALL_AMOUNT,
                        }
                    ),
                    _something_to_send,
                )
            ],
            vol.Length(min=1, max=MAX_PICNIC_SEND_ITEMS),
        ),
    }
)
@websocket_api.async_response
@_with_data
async def ws_picnic_send(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Put products into the Picnic cart. Nothing is ever ordered."""
    connection.send_result(msg["id"], await data.async_picnic_send(hass, msg["items"]))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/picnic/undo",
        vol.Required("item_id"): KITCHENOWL_ID,
        # False: only forget the mark (the product was not in the cart).
        vol.Optional("remove", default=True): bool,
    }
)
@websocket_api.async_response
@_with_data
async def ws_picnic_undo(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Take what EatFresh put into the cart for an entry out again."""
    await data.async_picnic_undo(hass, msg["item_id"], msg["remove"])
    connection.send_result(msg["id"], {})


# ----- ticking off and groups (0.5.0) ---------------------------------------

_FOREIGN_KEY = re.compile(rf"{re.escape(FOREIGN_PREFIX)}[1-9][0-9]{{0,9}}")


def _department(value: Any) -> str:
    """Validate the key of a group: one of ``DEPARTMENTS`` or ``ko:<id>``."""
    if isinstance(value, str) and (
        value in DEPARTMENTS or _FOREIGN_KEY.fullmatch(value)
    ):
        return value
    raise vol.Invalid("Expected the key of a group of the shopping list")


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/shopping/check",
        vol.Required("item_id"): KITCHENOWL_ID,
    }
)
@websocket_api.async_response
@_with_data
async def ws_shopping_check(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Tick an entry off: it leaves the KitchenOwl list (the item stays)."""
    await data.async_shopping_check(msg["item_id"])
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/shopping/uncheck",
        vol.Required("item_id"): KITCHENOWL_ID,
    }
)
@websocket_api.async_response
@_with_data
async def ws_shopping_uncheck(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Put an entry ticked off back on the list with its remembered amount."""
    await data.async_shopping_uncheck(msg["item_id"])
    connection.send_result(msg["id"], {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/shopping/set_department",
        vol.Required("item_id"): KITCHENOWL_ID,
        vol.Required("name"): vol.All(
            str, vol.Strip, vol.Length(min=1, max=MAX_ITEM_NAME)
        ),
        vol.Required("department"): _department,
    }
)
@websocket_api.async_response
@_with_data
async def ws_shopping_set_department(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Put an ingredient into another group (and its item in KitchenOwl)."""
    await data.async_shopping_set_department(
        msg["item_id"], msg["name"], msg["department"]
    )
    connection.send_result(msg["id"], {})
