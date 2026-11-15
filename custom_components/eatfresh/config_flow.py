"""Config flow and options flow of EatFresh."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol
from yarl import URL

from .const import (
    CHEFKOCH,
    CONF_ACCEPT_CHEFKOCH,
    CONF_HOUSEHOLD_ID,
    CONF_PLANNER_INTERVAL,
    CONF_SHOPPINGLIST_ID,
    CONF_SOURCES,
    CONF_TOKEN,
    CONF_URL,
    DOMAIN,
    MAX_PLANNER_INTERVAL,
    MIN_PLANNER_INTERVAL,
    NAME,
)
from .errors import KitchenOwlAuthError, KitchenOwlError
from .kitchenowl import KitchenOwlClient
from .runtime import enabled_source_ids, planner_interval
from .sources import SOURCE_CLASSES

_LOGGER = logging.getLogger(__name__)

EXAMPLE_URL = "https://kitchenowl.example.com"
URL_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))
TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
INTERVAL_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=MIN_PLANNER_INTERVAL,
        max=MAX_PLANNER_INTERVAL,
        step=1,
        mode=NumberSelectorMode.BOX,
        unit_of_measurement="min",
    )
)


def _normalize_url(value: str) -> str | None:
    """Return the base URL without trailing slash, or None if invalid."""
    value = value.strip().rstrip("/")
    parsed = URL(value)
    if parsed.scheme not in ("http", "https") or not parsed.host:
        return None
    return value


def _minutes(options: Mapping[str, Any]) -> int:
    """Return the meal plan interval of options (or of the form) in minutes."""
    return int(planner_interval(options).total_seconds() // 60)


def _options(items: list[dict[str, Any]]) -> list[SelectOptionDict]:
    """Turn KitchenOwl objects with id and name into select options."""
    return [
        SelectOptionDict(value=str(item["id"]), label=str(item.get("name") or item["id"]))
        for item in items
    ]


class EatFreshConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up EatFresh with a KitchenOwl account."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._url: str = ""
        self._token: str = ""
        self._client: KitchenOwlClient | None = None
        self._households: list[dict[str, Any]] = []
        self._shoppinglists: list[dict[str, Any]] = []
        self._household_id: int | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> EatFreshOptionsFlow:
        """Return the options flow."""
        return EatFreshOptionsFlow()

    async def _async_check(self, url: str, token: str) -> str | None:
        """Check address and token. Return an error key or None."""
        client = KitchenOwlClient(async_get_clientsession(self.hass), url, token)
        try:
            await client.get_user()
            households = await client.list_households()
        except KitchenOwlAuthError:
            return "invalid_auth"
        except KitchenOwlError:
            return "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error while checking KitchenOwl")
            return "unknown"
        if not households:
            return "no_households"
        self._client = client
        self._households = households
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the KitchenOwl address and token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = _normalize_url(user_input[CONF_URL])
            token = user_input[CONF_TOKEN].strip()
            if url is None:
                errors[CONF_URL] = "invalid_url"
            elif (error := await self._async_check(url, token)) is not None:
                errors["base"] = error
            else:
                self._url, self._token = url, token
                return await self.async_step_household()

        schema = vol.Schema(
            {
                vol.Required(CONF_URL): URL_SELECTOR,
                vol.Required(CONF_TOKEN): TOKEN_SELECTOR,
            }
        )
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(
                schema, {CONF_URL: user_input.get(CONF_URL, "")}
            )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={"example_url": EXAMPLE_URL},
        )

    async def async_step_household(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the KitchenOwl household."""
        errors: dict[str, str] = {}
        if user_input is None and len(self._households) == 1:
            user_input = {CONF_HOUSEHOLD_ID: str(self._households[0]["id"])}
        if user_input is not None:
            household_id = int(user_input[CONF_HOUSEHOLD_ID])
            assert self._client is not None
            try:
                self._shoppinglists = await self._client.list_shoppinglists(
                    household_id
                )
            except KitchenOwlAuthError:
                return self.async_abort(reason="invalid_auth")
            except KitchenOwlError:
                errors["base"] = "cannot_connect"
            else:
                if not self._shoppinglists:
                    errors["base"] = "no_shoppinglists"
                else:
                    self._household_id = household_id
                    return await self.async_step_shoppinglist()

        return self.async_show_form(
            step_id="household",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOUSEHOLD_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=_options(self._households),
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_shoppinglist(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the shopping list for the ingredients."""
        if user_input is not None:
            assert self._household_id is not None
            await self.async_set_unique_id(str(self._household_id))
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=NAME,
                data={
                    CONF_URL: self._url,
                    CONF_TOKEN: self._token,
                    CONF_HOUSEHOLD_ID: self._household_id,
                    CONF_SHOPPINGLIST_ID: int(user_input[CONF_SHOPPINGLIST_ID]),
                },
            )

        return self.async_show_form(
            step_id="shoppinglist",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SHOPPINGLIST_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=_options(self._shoppinglists),
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start a reauthentication when KitchenOwl rejects the token."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new token."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            error = await self._async_check(entry.data[CONF_URL], token)
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_TOKEN: token}
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): TOKEN_SELECTOR}),
            errors=errors,
        )


class EatFreshOptionsFlow(OptionsFlowWithReload):
    """Choose the active recipe sources and the meal plan interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the list of sources."""
        errors: dict[str, str] = {}
        searchable = [cls for cls in SOURCE_CLASSES if cls.searchable]
        options = self.config_entry.options

        if user_input is not None:
            selected = list(user_input.get(CONF_SOURCES, []))
            accepted = bool(user_input.get(CONF_ACCEPT_CHEFKOCH, False))
            # Entries of 0.2.0 have no interval: the form shows the default.
            interval = _minutes(
                user_input if CONF_PLANNER_INTERVAL in user_input else options
            )
            if CHEFKOCH in selected and not accepted:
                errors[CONF_ACCEPT_CHEFKOCH] = "chefkoch_terms"
            else:
                return self.async_create_entry(
                    data={
                        CONF_SOURCES: selected,
                        CONF_ACCEPT_CHEFKOCH: accepted,
                        CONF_PLANNER_INTERVAL: interval,
                    }
                )
            current = selected
            current_accepted = accepted
        else:
            current = enabled_source_ids(options, SOURCE_CLASSES)
            current_accepted = bool(options.get(CONF_ACCEPT_CHEFKOCH, False))
            interval = _minutes(options)

        schema = vol.Schema(
            {
                vol.Optional(CONF_SOURCES, default=current): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=cls.id, label=cls.name)
                            for cls in searchable
                        ],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    CONF_ACCEPT_CHEFKOCH, default=current_accepted
                ): BooleanSelector(),
                vol.Optional(
                    CONF_PLANNER_INTERVAL, default=interval
                ): INTERVAL_SELECTOR,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
