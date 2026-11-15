"""WebSocket commands used by the EatFresh panel."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
import logging
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
import voluptuous as vol

from .const import (
    DEFAULT_SEARCH_LIMIT,
    DOMAIN,
    ERR_KITCHENOWL_AUTH,
    ERR_KITCHENOWL_ERROR,
    ERR_NOT_FOUND,
    ERR_NOT_LOADED,
    ERR_SOURCE_BLOCKED,
    ERR_SOURCE_ERROR,
    MAX_SEARCH_LIMIT,
)
from .errors import (
    EatFreshError,
    KitchenOwlAuthError,
    KitchenOwlError,
    RecipeNotFound,
    SourceBlocked,
    SourceError,
)
from .image_proxy import sign_image_url, sign_photo
from .runtime import (
    EatFreshData,
    ShoppingListPartial,
    async_reauth_on_auth_error,
    error_message,
    get_runtime_data,
)

_LOGGER = logging.getLogger(__name__)

type Handler = Callable[
    [HomeAssistant, websocket_api.ActiveConnection, dict[str, Any], EatFreshData],
    Awaitable[None],
]


def error_code(err: EatFreshError) -> str:
    """Map an EatFresh error to a WebSocket error code."""
    # Order matters: subclasses first.
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
        ws_shopping_list_add,
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
    """Search the recipe sources."""
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
    """Set the heart: save the recipe in KitchenOwl if needed."""
    kitchenowl_id, created = await data.async_favorite(msg["key"])
    connection.send_result(
        msg["id"], {"kitchenowl_id": kitchenowl_id, "created": created}
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


@websocket_api.websocket_command({vol.Required("type"): "eatfresh/collection"})
@websocket_api.async_response
@_with_data
async def ws_collection(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    data: EatFreshData,
) -> None:
    """Return the recipes stored in KitchenOwl."""
    recipes = [
        {
            "kitchenowl_id": recipe["id"],
            "name": recipe.get("name"),
            "image": sign_photo(hass, recipe.get("photo")),
            "source": recipe.get("source"),
            "time": recipe.get("time"),
            "yields": recipe.get("yields"),
        }
        for recipe in await data.async_collection()
    ]
    connection.send_result(msg["id"], {"recipes": recipes})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eatfresh/shopping_list/add",
        vol.Required("kitchenowl_ids"): vol.All(
            [vol.Coerce(int)], vol.Length(min=1, max=50)
        ),
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
    """Put the ingredients of KitchenOwl recipes on the shopping list."""
    added = await data.async_add_to_shopping_list(msg["kitchenowl_ids"])
    connection.send_result(msg["id"], {"added": added})
