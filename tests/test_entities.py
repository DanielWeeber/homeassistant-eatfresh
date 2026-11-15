"""Tests for the week plan calendar, the today sensor and the dashboard cards."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.eatfresh.calendar import planner_events
from custom_components.eatfresh.const import DOMAIN, VERSION
from custom_components.eatfresh.errors import KitchenOwlAuthError, KitchenOwlError

CALENDAR = "calendar.eatfresh_week_plan"
SENSOR = "sensor.eatfresh_today"
TODAY = date(2026, 11, 18)
CARDS_URL = f"/eatfresh_static/eatfresh-cards.js?v={VERSION}"


def plan(*entries: tuple[int, str, date | None]) -> list[dict[str, Any]]:
    return [
        {"recipe_id": rid, "name": name, "photo": f"p{rid}.jpg", "date": day}
        for rid, name, day in entries
    ]


@pytest.fixture(autouse=True)
def fixed_today() -> Any:
    """Make today 2026-11-18, 12:00 in the time zone of Home Assistant."""

    def now() -> Any:
        return dt_util.as_local(
            dt_util.start_of_local_day(TODAY) + timedelta(hours=12)
        )

    with patch("custom_components.eatfresh.runtime.dt_util.now", side_effect=now):
        yield


async def refresh(entry: MockConfigEntry) -> None:
    await entry.runtime_data.coordinator.async_refresh()
    await entry.runtime_data.coordinator.hass.async_block_till_done()


async def test_entities_and_device(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    entity_registry = er.async_get(hass)
    calendar = entity_registry.async_get(CALENDAR)
    sensor = entity_registry.async_get(SENSOR)
    assert calendar is not None
    assert sensor is not None
    assert calendar.unique_id == f"{init_integration.entry_id}_week_plan"
    assert sensor.translation_key == "today"
    device = dr.async_get(hass).async_get(calendar.device_id)
    assert device.name == "EatFresh"
    assert device.entry_type is dr.DeviceEntryType.SERVICE
    assert (DOMAIN, init_integration.entry_id) in device.identifiers
    assert hass.states.get(SENSOR).attributes["friendly_name"] == "EatFresh Today"
    assert hass.states.get(CALENDAR).attributes["friendly_name"] == "EatFresh Week plan"


async def test_sensor_today(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    assert hass.states.get(SENSOR).state == STATE_UNKNOWN
    assert hass.states.get(SENSOR).attributes["recipes"] == []

    mock_client.list_planner.return_value = plan(
        (11, "Soup", TODAY),
        (12, "Bread", TODAY),
        (13, "Cake", TODAY + timedelta(days=1)),
        (14, "Someday", None),
    )
    await refresh(init_integration)
    state = hass.states.get(SENSOR)
    assert state.state == "Soup, Bread"
    recipes = state.attributes["recipes"]
    assert [(r["kitchenowl_id"], r["name"]) for r in recipes] == [
        (11, "Soup"),
        (12, "Bread"),
    ]
    assert "photo=p11.jpg" in recipes[0]["image"]


async def test_sensor_long_state_is_cut(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_client.list_planner.return_value = plan(
        *((i, "x" * 40, TODAY) for i in range(1, 10))
    )
    await refresh(init_integration)
    state = hass.states.get(SENSOR).state
    assert len(state) <= 255
    assert state.endswith("…")


async def test_sensor_changes_at_midnight(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The sensor's own timer writes the new day shortly after midnight.

    Time trackers of Home Assistant count from the real clock, so the test
    uses the real next midnight and fires exactly 5 s after it.
    """
    tomorrow = dt_util.as_local(dt_util.utcnow()).date() + timedelta(days=1)
    midnight = dt_util.start_of_local_day(tomorrow)
    mock_client.list_planner.return_value = plan((13, "Cake", tomorrow))
    await refresh(init_integration)
    assert hass.states.get(SENSOR).state == STATE_UNKNOWN
    # No new plan from KitchenOwl: only the sensor's own timer may change the
    # state (the plan of the coordinator is still the same).
    coordinator = init_integration.runtime_data.coordinator
    coordinator.update_interval = None
    coordinator._unschedule_refresh()
    fetches = mock_client.list_planner.await_count

    with patch(
        "custom_components.eatfresh.runtime.dt_util.now",
        side_effect=lambda: dt_util.as_local(midnight + timedelta(seconds=5)),
    ):
        async_fire_time_changed(hass, dt_util.as_utc(midnight - timedelta(seconds=1)))
        await hass.async_block_till_done()
        assert hass.states.get(SENSOR).state == STATE_UNKNOWN
        async_fire_time_changed(hass, dt_util.as_utc(midnight + timedelta(seconds=5)))
        await hass.async_block_till_done()
        assert hass.states.get(SENSOR).state == "Cake"
    assert mock_client.list_planner.await_count == fetches


async def test_calendar_event_and_list(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_client.list_planner.return_value = plan(
        (10, "Old", TODAY - timedelta(days=2)),
        (12, "Bread", TODAY + timedelta(days=2)),
        (11, "Soup", TODAY),
        (14, "Someday", None),
    )
    await refresh(init_integration)
    state = hass.states.get(CALENDAR)
    assert state.state == "on"
    assert state.attributes["message"] == "Soup"
    assert state.attributes["all_day"] is True
    assert state.attributes["start_time"].startswith(TODAY.isoformat())

    start = dt_util.start_of_local_day(TODAY - timedelta(days=3))
    result = await hass.services.async_call(
        "calendar",
        "get_events",
        {"start_date_time": start, "end_date_time": start + timedelta(days=7)},
        target={"entity_id": CALENDAR},
        blocking=True,
        return_response=True,
    )
    events = result[CALENDAR]["events"]
    assert [(e["start"], e["summary"]) for e in events] == [
        ((TODAY - timedelta(days=2)).isoformat(), "Old"),
        (TODAY.isoformat(), "Soup"),
        ((TODAY + timedelta(days=2)).isoformat(), "Bread"),
    ]
    assert events[0]["end"] == (TODAY - timedelta(days=1)).isoformat()

    # Only the next days: the old meal is left out.
    result = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "start_date_time": dt_util.start_of_local_day(TODAY + timedelta(days=1)),
            "end_date_time": dt_util.start_of_local_day(TODAY + timedelta(days=5)),
        },
        target={"entity_id": CALENDAR},
        blocking=True,
        return_response=True,
    )
    assert [e["summary"] for e in result[CALENDAR]["events"]] == ["Bread"]


async def test_calendar_next_event_and_empty(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    assert hass.states.get(CALENDAR).state == "off"
    mock_client.list_planner.return_value = plan((12, "Bread", TODAY + timedelta(days=3)))
    await refresh(init_integration)
    state = hass.states.get(CALENDAR)
    assert state.state == "off"
    assert state.attributes["message"] == "Bread"


def test_planner_events_skip_bad_entries() -> None:
    events = planner_events(
        [
            {"recipe_id": 1, "name": "A", "date": "2026-11-18"},
            {"recipe_id": 2, "name": "B", "date": "not a date"},
            {"recipe_id": "x", "name": "C", "date": "2026-11-18"},
            {"recipe_id": 3, "name": None, "date": TODAY},
        ]
    )
    assert [(e.uid, e.summary) for e in events] == [
        ("3-2026-11-18", ""),
        ("1-2026-11-18", "A"),
    ]
    assert planner_events(None) == []


async def test_unreachable_kitchenowl_makes_entities_unavailable(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_client.list_planner.side_effect = KitchenOwlError("down")
    await refresh(init_integration)
    assert hass.states.get(SENSOR).state == STATE_UNAVAILABLE
    assert hass.states.get(CALENDAR).state == STATE_UNAVAILABLE
    assert init_integration.state is ConfigEntryState.LOADED

    mock_client.list_planner.side_effect = None
    mock_client.list_planner.return_value = plan((11, "Soup", TODAY))
    await refresh(init_integration)
    assert hass.states.get(SENSOR).state == "Soup"


async def test_plan_is_fetched_every_15_minutes(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    before = mock_client.list_planner.await_count
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=16))
    await hass.async_block_till_done()
    assert mock_client.list_planner.await_count == before + 1


async def test_rejected_token_starts_reauth(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_client.list_planner.side_effect = KitchenOwlAuthError("401")
    await refresh(init_integration)
    flows = hass.config_entries.flow.async_progress()
    assert any(flow["context"]["source"] == "reauth" for flow in flows)
    assert hass.states.get(SENSOR).state == STATE_UNAVAILABLE


async def test_setup_works_while_plan_is_unreachable(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    patch_client: MagicMock,
    mock_sources: MagicMock,
    panel_dir: Path,
    mock_client: MagicMock,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """The panel still loads; only the entities are unavailable."""
    mock_client.list_planner.side_effect = KitchenOwlError("down")
    config_entry.add_to_hass(hass)
    with patch(
        "custom_components.eatfresh.async_create_public_session",
        side_effect=lambda hass: aioclient_mock.create_session(hass.loop),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(SENSOR).state == STATE_UNAVAILABLE


async def test_unload_removes_entities(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR).state == STATE_UNAVAILABLE


# ----- dashboard cards --------------------------------------------------


async def _setup(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    entry.add_to_hass(hass)
    with patch(
        "custom_components.eatfresh.async_create_public_session",
        side_effect=lambda hass: aioclient_mock.create_session(hass.loop),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_cards_are_added_and_removed(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    patch_client: MagicMock,
    mock_sources: MagicMock,
    panel_dir: Path,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    (panel_dir / "eatfresh-cards.js").write_text("export {};\n", encoding="utf-8")
    hass.data[DATA_EXTRA_MODULE_URL] = set()
    await _setup(hass, config_entry, aioclient_mock)
    assert CARDS_URL in hass.data[DATA_EXTRA_MODULE_URL]

    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.data[DATA_EXTRA_MODULE_URL] == {CARDS_URL}

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert CARDS_URL not in hass.data[DATA_EXTRA_MODULE_URL]


async def test_missing_cards_file_only_warns(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    patch_client: MagicMock,
    mock_sources: MagicMock,
    panel_dir: Path,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    hass.data[DATA_EXTRA_MODULE_URL] = set()
    await _setup(hass, config_entry, aioclient_mock)
    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.data[DATA_EXTRA_MODULE_URL] == set()
    assert "Card file eatfresh-cards.js is missing" in caplog.text
    assert await hass.config_entries.async_unload(config_entry.entry_id)


async def test_cards_without_frontend_only_warn(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    patch_client: MagicMock,
    mock_sources: MagicMock,
    panel_dir: Path,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    (panel_dir / "eatfresh-cards.js").write_text("export {};\n", encoding="utf-8")
    hass.data.pop(DATA_EXTRA_MODULE_URL, None)
    await _setup(hass, config_entry, aioclient_mock)
    assert config_entry.state is ConfigEntryState.LOADED
    assert "the dashboard cards are not added" in caplog.text
    assert await hass.config_entries.async_unload(config_entry.entry_id)
