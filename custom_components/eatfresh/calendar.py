"""Calendar "Week plan": the KitchenOwl meal plan as all-day events."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .entity import EatFreshEntity
from .runtime import EatFreshConfigEntry, planner_date, today

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EatFreshConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the week plan calendar."""
    coordinator = entry.runtime_data.coordinator
    assert coordinator is not None
    async_add_entities([EatFreshWeekPlanCalendar(coordinator, "week_plan")])


def planner_events(entries: list[dict[str, Any]] | None) -> list[CalendarEvent]:
    """Return one all-day event per planned recipe with a day, sorted by day."""
    events: list[CalendarEvent] = []
    for entry in entries or []:
        day = planner_date(entry)
        if day is None or not isinstance(entry.get("recipe_id"), int):
            continue
        events.append(
            CalendarEvent(
                start=day,
                end=day + timedelta(days=1),
                summary=str(entry.get("name") or ""),
                uid=f"{entry['recipe_id']}-{day.isoformat()}",
            )
        )
    events.sort(key=lambda event: (event.start, event.summary))
    return events


def _as_date(value: date | datetime) -> date:
    """Return the local day of a date or a time."""
    if isinstance(value, datetime):
        return dt_util.as_local(value).date()
    return value


class EatFreshWeekPlanCalendar(EatFreshEntity, CalendarEntity):
    """The meal plan of KitchenOwl."""

    @property
    def event(self) -> CalendarEvent | None:
        """Return the meal of today or the next planned one."""
        now = today()
        for event in planner_events(self.coordinator.data):
            if _as_date(event.end) > now:
                return event
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return the planned meals between two times."""
        first = _as_date(start_date)
        last = _as_date(end_date)
        return [
            event
            for event in planner_events(self.coordinator.data)
            if _as_date(event.start) <= last and _as_date(event.end) > first
        ]
