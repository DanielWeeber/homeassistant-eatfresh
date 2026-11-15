"""Actions of EatFresh (with response data)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
import functools
from typing import Any

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import (
    ATTR_DATE,
    ATTR_DAYS,
    ATTR_LIMIT,
    ATTR_QUERY,
    ATTR_RECIPE_ID,
    ATTR_START_DATE,
    ATTR_URL,
    DEFAULT_PLANNER_DAYS,
    DEFAULT_COLLECTION_LIMIT,
    DOMAIN,
    MAX_PLANNER_DAYS,
    MAX_PLANNER_YEAR,
    MAX_QUERY_LENGTH,
    MAX_COLLECTION_LIMIT,
    MIN_PLANNER_YEAR,
    SERVICE_ADD_TO_SHOPPING_LIST,
    SERVICE_GET_PLANNER,
    SERVICE_IMPORT_RECIPE,
    SERVICE_PLAN_RECIPE,
    SERVICE_SEARCH_COLLECTION,
    SERVICE_UNPLAN_RECIPE,
)
from .errors import (
    EatFreshError,
    KitchenOwlAuthError,
    KitchenOwlError,
    RecipeNotFound,
    SourceBlocked,
)
from .runtime import (
    NOT_IN_COLLECTION,
    EatFreshData,
    async_reauth_on_auth_error,
    dated_entries,
    error_message,
    get_runtime_data,
    plan_item,
    today,
    unscheduled_entries,
)


def _planner_day(value: Any) -> date:
    """Validate a day (date or YYYY-MM-DD) in the years 2000 to 2100.

    KitchenOwl keeps "no day" as 0001-01-01, so only sensible years pass.
    """
    day = cv.date(value)
    if not MIN_PLANNER_YEAR <= day.year <= MAX_PLANNER_YEAR:
        raise vol.Invalid(
            f"Expected a day in the years {MIN_PLANNER_YEAR} to {MAX_PLANNER_YEAR}"
        )
    return day


RECIPE_ID = vol.All(vol.Coerce(int), vol.Range(min=1))

IMPORT_RECIPE_SCHEMA = vol.Schema({vol.Required(ATTR_URL): cv.url})
ADD_TO_SHOPPING_LIST_SCHEMA = vol.Schema({vol.Required(ATTR_RECIPE_ID): RECIPE_ID})
SEARCH_COLLECTION_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_QUERY): vol.All(cv.string, vol.Length(max=MAX_QUERY_LENGTH)),
        vol.Optional(ATTR_LIMIT, default=DEFAULT_COLLECTION_LIMIT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_COLLECTION_LIMIT)
        ),
    }
)
GET_PLANNER_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_START_DATE): _planner_day,
        vol.Optional(ATTR_DAYS, default=DEFAULT_PLANNER_DAYS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_PLANNER_DAYS)
        ),
    }
)
PLAN_RECIPE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_RECIPE_ID): RECIPE_ID, vol.Required(ATTR_DATE): _planner_day}
)
UNPLAN_RECIPE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_RECIPE_ID): RECIPE_ID, vol.Optional(ATTR_DATE): _planner_day}
)


def _require_data(hass: HomeAssistant) -> EatFreshData:
    """Return the runtime data or raise if the entry is not loaded."""
    if (data := get_runtime_data(hass)) is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_loaded"
        )
    return data


def _ha_error(err: EatFreshError) -> HomeAssistantError:
    """Turn an EatFresh error into a Home Assistant error."""
    if isinstance(err, RecipeNotFound) and str(err) == NOT_IN_COLLECTION:
        return ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_in_collection"
        )
    if isinstance(err, KitchenOwlAuthError):
        key = "kitchenowl_auth"
    elif isinstance(err, KitchenOwlError):
        key = "kitchenowl_error"
    elif isinstance(err, SourceBlocked):
        key = "source_blocked"
    else:
        key = "source_error"
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders={"message": error_message(err)},
    )


type Action = Callable[[ServiceCall, EatFreshData], Awaitable[ServiceResponse]]


def _action(func: Action) -> Callable[[ServiceCall], Awaitable[ServiceResponse]]:
    """Give an action the runtime data and turn EatFresh errors into HA errors.

    A rejected token also starts the reauthentication.
    """

    @functools.wraps(func)
    async def wrapper(call: ServiceCall) -> ServiceResponse:
        data = _require_data(call.hass)
        try:
            return await func(call, data)
        except EatFreshError as err:
            async_reauth_on_auth_error(call.hass, err)
            raise _ha_error(err) from err

    return wrapper


@_action
async def _async_import_recipe(
    call: ServiceCall, data: EatFreshData
) -> ServiceResponse:
    """Import a recipe from a web address into KitchenOwl."""
    recipe = await data.async_get_recipe_by_url(call.data[ATTR_URL])
    kitchenowl_id, created = await data.async_save_recipe(recipe)
    return {"kitchenowl_id": kitchenowl_id, "title": recipe.title, "created": created}


@_action
async def _async_add_to_shopping_list(
    call: ServiceCall, data: EatFreshData
) -> ServiceResponse:
    """Put the ingredients of a KitchenOwl recipe on the shopping list."""
    added = await data.async_add_to_shopping_list([call.data[ATTR_RECIPE_ID]])
    return {"added": added}


@_action
async def _async_search_collection(
    call: ServiceCall, data: EatFreshData
) -> ServiceResponse:
    """Return the recipes of the collection (name or ingredient matching).

    ``total`` counts all matches, ``recipes`` holds at most ``limit`` of them.
    """
    recipes, total = await data.async_search_collection(
        call.data.get(ATTR_QUERY), call.data[ATTR_LIMIT]
    )
    return {"recipes": recipes, "total": total}


@_action
async def _async_get_planner(call: ServiceCall, data: EatFreshData) -> ServiceResponse:
    """Return the meal plan from a day (default today) on a number of days."""
    start: date = call.data.get(ATTR_START_DATE) or today()
    days: int = call.data[ATTR_DAYS]
    entries = await data.async_current_planner_entries()
    return {
        "start_date": start.isoformat(),
        "days": days,
        "entries": [
            plan_item(day, entry) for day, entry in dated_entries(entries, start, days)
        ],
        "unscheduled": [
            {"recipe_id": entry["recipe_id"], "name": str(entry.get("name") or "")}
            for entry in unscheduled_entries(entries)
        ],
    }


@_action
async def _async_plan_recipe(call: ServiceCall, data: EatFreshData) -> ServiceResponse:
    """Plan a recipe of the collection on a day."""
    recipe_id: int = call.data[ATTR_RECIPE_ID]
    day: date = call.data[ATTR_DATE]
    await data.async_planner_add(recipe_id, day)
    return {"recipe_id": recipe_id, "date": day.isoformat()}


@_action
async def _async_unplan_recipe(
    call: ServiceCall, data: EatFreshData
) -> ServiceResponse:
    """Take a recipe of the collection off a day (or off the plan without one)."""
    recipe_id: int = call.data[ATTR_RECIPE_ID]
    day: date | None = call.data.get(ATTR_DATE)
    await data.async_require_own([recipe_id])
    await data.async_planner_remove(recipe_id, day)
    return {"recipe_id": recipe_id, "date": day.isoformat() if day else None}


# Name, handler, schema and whether a response is optional or required (the
# two reading actions are useless without one).
ACTIONS: tuple[tuple[str, Callable[..., Any], vol.Schema, SupportsResponse], ...] = (
    (
        SERVICE_IMPORT_RECIPE,
        _async_import_recipe,
        IMPORT_RECIPE_SCHEMA,
        SupportsResponse.OPTIONAL,
    ),
    (
        SERVICE_ADD_TO_SHOPPING_LIST,
        _async_add_to_shopping_list,
        ADD_TO_SHOPPING_LIST_SCHEMA,
        SupportsResponse.OPTIONAL,
    ),
    (
        SERVICE_SEARCH_COLLECTION,
        _async_search_collection,
        SEARCH_COLLECTION_SCHEMA,
        SupportsResponse.ONLY,
    ),
    (
        SERVICE_GET_PLANNER,
        _async_get_planner,
        GET_PLANNER_SCHEMA,
        SupportsResponse.ONLY,
    ),
    (
        SERVICE_PLAN_RECIPE,
        _async_plan_recipe,
        PLAN_RECIPE_SCHEMA,
        SupportsResponse.OPTIONAL,
    ),
    (
        SERVICE_UNPLAN_RECIPE,
        _async_unplan_recipe,
        UNPLAN_RECIPE_SCHEMA,
        SupportsResponse.OPTIONAL,
    ),
)


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register the EatFresh actions."""
    for name, handler, schema, supports_response in ACTIONS:
        hass.services.async_register(
            DOMAIN, name, handler, schema=schema, supports_response=supports_response
        )
