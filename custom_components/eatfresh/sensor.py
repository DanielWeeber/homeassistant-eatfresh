"""Sensor "Today": the meals planned for today."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_change

from .entity import EatFreshEntity
from .image_proxy import sign_photo
from .runtime import EatFreshConfigEntry, planner_date, today

PARALLEL_UPDATES = 0

# The state holds names joined by commas; HA allows 255 characters.
MAX_STATE_LENGTH = 255


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EatFreshConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the today sensor."""
    coordinator = entry.runtime_data.coordinator
    assert coordinator is not None
    async_add_entities([EatFreshTodaySensor(coordinator, "today")])


def todays_entries(entries: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Return the meal plan entries of today (time zone of Home Assistant)."""
    now = today()
    return [
        entry
        for entry in entries or []
        if isinstance(entry.get("recipe_id"), int) and planner_date(entry) == now
    ]


class EatFreshTodaySensor(EatFreshEntity, SensorEntity):
    """Names of today's meals, or unknown when nothing is planned."""

    # The signed image paths change with every update; keep them out of history.
    _unrecorded_attributes = frozenset({"recipes"})

    async def async_added_to_hass(self) -> None:
        """Update the state shortly after midnight as well."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(
                self.hass, self._async_new_day, hour=0, minute=0, second=5
            )
        )

    @callback
    def _async_new_day(self, _now: datetime) -> None:
        """Write the state for the new day."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        """Return the names of today's meals joined by commas."""
        entries = todays_entries(self.coordinator.data)
        names = [name for entry in entries if (name := str(entry.get("name") or ""))]
        if not names:
            return None
        value = ", ".join(names)
        if len(value) > MAX_STATE_LENGTH:
            value = value[: MAX_STATE_LENGTH - 1].rstrip(", ") + "…"
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the recipes of today with KitchenOwl id, name and image."""
        return {
            "recipes": [
                {
                    "kitchenowl_id": entry["recipe_id"],
                    "name": entry.get("name"),
                    "image": sign_photo(self.hass, entry.get("photo")),
                }
                for entry in todays_entries(self.coordinator.data)
            ]
        }
