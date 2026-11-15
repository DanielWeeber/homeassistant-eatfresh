"""Sidebar panel of EatFresh."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.util.hass_dict import HassKey

from .const import (
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

    # Static paths cannot be removed again, so register them once per run.
    if not hass.data.get(DATA_STATIC_REGISTERED):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL_PATH, str(FRONTEND_DIR), cache_headers=False)]
        )
        hass.data[DATA_STATIC_REGISTERED] = True

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
