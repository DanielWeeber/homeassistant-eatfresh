"""Sidebar panel of EatFresh."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.util.hass_dict import HassKey

from .const import (
    CARDS_FILENAME,
    PANEL_ELEMENT,
    PANEL_FILENAME,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL_PATH,
    STATIC_URL_PATH,
    VERSION,
)

_LOGGER = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent / "frontend"
DATA_STATIC_REGISTERED: HassKey[bool] = HassKey("eatfresh_static_registered")
DATA_PANEL_REGISTERED: HassKey[bool] = HassKey("eatfresh_panel_registered")
DATA_CARDS_URL: HassKey[str] = HassKey("eatfresh_cards_url")
CARDS_URL = f"{STATIC_URL_PATH}/{CARDS_FILENAME}?v={VERSION}"


async def _async_register_static(hass: HomeAssistant) -> None:
    """Serve the frontend folder (once per run: it cannot be removed again)."""
    if hass.data.get(DATA_STATIC_REGISTERED):
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL_PATH, str(FRONTEND_DIR), cache_headers=False)]
    )
    hass.data[DATA_STATIC_REGISTERED] = True


async def async_register_panel(hass: HomeAssistant) -> bool:
    """Serve the panel file and add the sidebar entry.

    Return False (and only log a warning) when the built panel file is missing,
    so the integration still works without the sidebar entry.
    """
    panel_file = FRONTEND_DIR / PANEL_FILENAME
    if not await hass.async_add_executor_job(panel_file.is_file):
        _LOGGER.warning(
            "Panel file %s is missing, the sidebar entry is not added", PANEL_FILENAME
        )
        return False

    await _async_register_static(hass)

    if hass.data.get(DATA_PANEL_REGISTERED):
        return True
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        module_url=f"{STATIC_URL_PATH}/{PANEL_FILENAME}?v={VERSION}",
        embed_iframe=False,
        require_admin=False,
    )
    hass.data[DATA_PANEL_REGISTERED] = True
    return True


def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove the sidebar entry if it was added."""
    if hass.data.pop(DATA_PANEL_REGISTERED, False):
        frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)


async def async_register_cards(hass: HomeAssistant) -> bool:
    """Load the dashboard cards on every dashboard.

    Return False (and only log a warning) when the card file is missing.
    """
    cards_file = FRONTEND_DIR / CARDS_FILENAME
    if not await hass.async_add_executor_job(cards_file.is_file):
        _LOGGER.warning(
            "Card file %s is missing, the dashboard cards are not loaded",
            CARDS_FILENAME,
        )
        return False
    await _async_register_static(hass)
    if hass.data.get(DATA_CARDS_URL):
        return True
    try:
        frontend.add_extra_js_url(hass, CARDS_URL)
    except KeyError:
        # The frontend is not set up (for example in safe mode).
        _LOGGER.warning("The frontend is not loaded, the dashboard cards are not added")
        return False
    hass.data[DATA_CARDS_URL] = CARDS_URL
    return True


def async_unregister_cards(hass: HomeAssistant) -> None:
    """Stop loading the dashboard cards if they were added."""
    if url := hass.data.pop(DATA_CARDS_URL, None):
        try:
            frontend.remove_extra_js_url(hass, url)
        except KeyError:
            _LOGGER.debug("Card file %s was not registered", url)
