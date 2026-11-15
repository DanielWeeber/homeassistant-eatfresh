"""EatFresh: find recipes and save them in KitchenOwl."""

from __future__ import annotations

import logging

import aiohttp
from homeassistant.const import EVENT_HOMEASSISTANT_CLOSE, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.ssl import client_context

from . import panel
from .const import (
    CONF_HOUSEHOLD_ID,
    CONF_SHOPPINGLIST_ID,
    CONF_TOKEN,
    CONF_URL,
    DOMAIN,
    USER_AGENT,
)
from .coordinator import PlannerCoordinator
from .errors import KitchenOwlAuthError, KitchenOwlError
from .http import HttpClient, create_public_session
from .image_proxy import EatFreshImageView
from .kitchenowl import KitchenOwlClient
from .runtime import (
    EatFreshConfigEntry,
    EatFreshData,
    enabled_source_ids,
    planner_interval,
)
from .services import async_register_services
from .sources import SOURCE_CLASSES, blocked_hosts, build_sources
from .store import FavoritesStore
from .websocket_api import async_register_websocket_commands

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.SENSOR]

__all__ = ["EatFreshConfigEntry", "EatFreshData"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register actions, WebSocket commands and the image proxy once.

    They stay registered while Home Assistant runs and answer with a
    "not loaded" error when no config entry is loaded.
    """
    async_register_services(hass)
    async_register_websocket_commands(hass)
    hass.http.register_view(EatFreshImageView())
    return True


def async_create_public_session(hass: HomeAssistant) -> aiohttp.ClientSession:
    """Return the session for recipe pages and images.

    Its resolver refuses non-public addresses, so the address check and the
    connection use the same answer (no DNS rebinding). KitchenOwl is reached
    with the shared session of Home Assistant, because it may be local.
    """
    return create_public_session(ssl=client_context())


async def async_setup_entry(hass: HomeAssistant, entry: EatFreshConfigEntry) -> bool:
    """Connect to KitchenOwl, build the sources and add the panel."""
    session = async_get_clientsession(hass)
    client = KitchenOwlClient(session, entry.data[CONF_URL], entry.data[CONF_TOKEN])
    try:
        await client.get_user()
    except KitchenOwlAuthError as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="kitchenowl_auth_setup"
        ) from err
    except KitchenOwlError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="kitchenowl_unavailable"
        ) from err

    enabled = enabled_source_ids(entry.options, SOURCE_CLASSES)
    blocked = blocked_hosts(enabled, SOURCE_CLASSES)
    public_session = async_create_public_session(hass)

    async def _async_close_session(_event: Event | None = None) -> None:
        await public_session.close()

    entry.async_on_unload(_async_close_session)
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_CLOSE, _async_close_session)
    )
    sources = build_sources(
        HttpClient(public_session, USER_AGENT, blocked_hosts=blocked), enabled
    )
    store = FavoritesStore(hass)
    await store.async_load()

    household_id = int(entry.data[CONF_HOUSEHOLD_ID])
    coordinator = PlannerCoordinator(
        hass, entry, client, household_id, planner_interval(entry.options)
    )
    # Not the first-refresh helper: an unreachable meal plan only makes the
    # entities unavailable, the panel keeps working. A rejected token still
    # starts the reauthentication.
    await coordinator.async_refresh()

    data = EatFreshData(
        client=client,
        sources=sources,
        store=store,
        household_id=household_id,
        shoppinglist_id=int(entry.data[CONF_SHOPPINGLIST_ID]),
        public_session=public_session,
        blocked_hosts=blocked,
        coordinator=coordinator,
        hass=hass,
    )
    data.allow_favorite_images()
    entry.runtime_data = data

    await panel.async_register_panel(hass)
    await panel.async_register_cards(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EatFreshConfigEntry) -> bool:
    """Remove the entities, the panel and the cards, and drop the caches."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    panel.async_unregister_panel(hass)
    panel.async_unregister_cards(hass)
    entry.runtime_data.search_cache.clear()
    entry.runtime_data.recipe_cache.clear()
    entry.runtime_data.url_cache.clear()
    return True
