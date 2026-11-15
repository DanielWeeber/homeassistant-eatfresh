"""Coordinator that keeps the KitchenOwl meal plan for the entities."""

from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .errors import KitchenOwlAuthError, KitchenOwlError

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .kitchenowl import KitchenOwlClient

_LOGGER = logging.getLogger(__name__)

type PlannerEntries = list[dict[str, Any]]


class PlannerCoordinator(DataUpdateCoordinator[PlannerEntries]):
    """Fetch the meal plan regularly and after each change in EatFresh.

    The interval comes from the options (default: every minute). Each update
    is one request to KitchenOwl (``list_planner``). A plan fetched elsewhere
    by EatFresh (``async_set_updated_data``) counts as an update and moves the
    next one back by a whole interval, so the two never add up.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: KitchenOwlClient,
        household_id: int,
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} meal plan",
            update_interval=update_interval,
        )
        self.client = client
        self.household_id = household_id
        # Monotonic time of the last successful fetch (see ``fresh_data``).
        self.fetched_at: float | None = None

    @callback
    def async_set_updated_data(self, data: PlannerEntries) -> None:
        """Take a plan fetched elsewhere (by EatFresh) as fresh data."""
        self.fetched_at = time.monotonic()
        super().async_set_updated_data(data)

    @callback
    def fresh_data(self, max_age: timedelta) -> PlannerEntries | None:
        """Return the plan if the last update worked and is recent, else None."""
        if (
            self.data is None
            or not self.last_update_success
            or self.fetched_at is None
            or time.monotonic() - self.fetched_at > max_age.total_seconds()
        ):
            return None
        return self.data

    async def _async_update_data(self) -> PlannerEntries:
        """Return the meal plan entries of the household.

        A rejected token starts the reauthentication; any other KitchenOwl
        error makes the entities unavailable until the next update.
        """
        try:
            entries = await self.client.list_planner(self.household_id)
        except KitchenOwlAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="kitchenowl_auth_setup"
            ) from err
        except KitchenOwlError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="kitchenowl_unavailable",
            ) from err
        self.fetched_at = time.monotonic()
        return entries
