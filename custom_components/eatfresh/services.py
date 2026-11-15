"""Actions of EatFresh (with response data)."""

from __future__ import annotations

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
    ATTR_RECIPE_ID,
    ATTR_URL,
    DOMAIN,
    SERVICE_ADD_TO_SHOPPING_LIST,
    SERVICE_IMPORT_RECIPE,
)
from .errors import EatFreshError, KitchenOwlAuthError, KitchenOwlError, SourceBlocked
from .runtime import (
    EatFreshData,
    async_reauth_on_auth_error,
    error_message,
    get_runtime_data,
)

IMPORT_RECIPE_SCHEMA = vol.Schema({vol.Required(ATTR_URL): cv.url})
ADD_TO_SHOPPING_LIST_SCHEMA = vol.Schema(
    {vol.Required(ATTR_RECIPE_ID): vol.All(vol.Coerce(int), vol.Range(min=1))}
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


async def _async_import_recipe(call: ServiceCall) -> ServiceResponse:
    """Import a recipe from a web address into KitchenOwl."""
    data = _require_data(call.hass)
    try:
        recipe = await data.async_get_recipe_by_url(call.data[ATTR_URL])
        kitchenowl_id, created = await data.async_save_recipe(recipe)
    except EatFreshError as err:
        async_reauth_on_auth_error(call.hass, err)
        raise _ha_error(err) from err
    return {"kitchenowl_id": kitchenowl_id, "title": recipe.title, "created": created}


async def _async_add_to_shopping_list(call: ServiceCall) -> ServiceResponse:
    """Put the ingredients of a KitchenOwl recipe on the shopping list."""
    data = _require_data(call.hass)
    try:
        added = await data.async_add_to_shopping_list([call.data[ATTR_RECIPE_ID]])
    except EatFreshError as err:
        async_reauth_on_auth_error(call.hass, err)
        raise _ha_error(err) from err
    return {"added": added}


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register the EatFresh actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_RECIPE,
        _async_import_recipe,
        schema=IMPORT_RECIPE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_TO_SHOPPING_LIST,
        _async_add_to_shopping_list,
        schema=ADD_TO_SHOPPING_LIST_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
