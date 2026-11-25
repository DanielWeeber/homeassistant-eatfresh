"""Tests for EatFresh 0.3.0: actions for scripts, meal plan interval, ``week``."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)
import voluptuous as vol

from custom_components.eatfresh.const import (
    CONF_ACCEPT_CHEFKOCH,
    CONF_PLANNER_INTERVAL,
    CONF_SOURCES,
    DOMAIN,
)
from custom_components.eatfresh.errors import KitchenOwlAuthError, KitchenOwlError
from custom_components.eatfresh.runtime import (
    build_week,
    dated_entries,
    planner_interval,
    unscheduled_entries,
)

from .conftest import RECIPE_HOST
from .test_websocket_api import WS

SENSOR = "sensor.eatfresh_today"
CALENDAR = "calendar.eatfresh_week_plan"
TODAY = date(2026, 11, 18)


def plan(*entries: tuple[int, str, date | None]) -> list[dict[str, Any]]:
    """Return meal plan entries like KitchenOwlClient.list_planner."""
    return [
        {"recipe_id": rid, "name": name, "photo": f"p{rid}.jpg", "date": day}
        for rid, name, day in entries
    ]


RECIPES = [
    {
        "id": 11,
        "name": "Tomato Soup",
        "source": f"https://{RECIPE_HOST}/fakea/soup",
        "photo": "abc123.jpg",
        "time": 25,
        "yields": 4,
        "tags": ["Suppe"],
        "items": ["Tomaten", "Zwiebel"],
    },
    {
        "id": 12,
        "name": "Bread",
        "source": None,
        "photo": None,
        "time": None,
        "yields": None,
        "tags": [],
        "items": ["Mehl", "Hefe"],
    },
    {
        "id": 13,
        "name": "Pasta",
        "source": None,
        "photo": None,
        "time": 15,
        "yields": 2,
        "tags": ["Schnell"],
        "items": ["Nudeln", "TOMATEN"],
    },
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


@pytest.fixture
def recipes(mock_client: MagicMock) -> MagicMock:
    """Give the fake client three recipes with ingredients."""
    mock_client.list_recipes.return_value = [dict(r) for r in RECIPES]
    return mock_client


async def call(hass: HomeAssistant, action: str, **data: Any) -> dict[str, Any]:
    return await hass.services.async_call(
        DOMAIN, action, data, blocking=True, return_response=True
    )


async def refresh(entry: MockConfigEntry) -> None:
    await entry.runtime_data.coordinator.async_refresh()
    await entry.runtime_data.coordinator.hass.async_block_till_done()


def reauth_flows(hass: HomeAssistant) -> int:
    return len(hass.config_entries.flow.async_progress_by_handler(DOMAIN))


# ------------------------------------------------------------- search_collection


async def test_search_collection_all(
    hass: HomeAssistant, init_integration: MockConfigEntry, recipes: MagicMock
) -> None:
    """Without a query the whole visible collection comes back with its days."""
    recipes.list_planner.return_value = plan(
        (11, "Tomato Soup", TODAY + timedelta(days=2)),
        (11, "Tomato Soup", TODAY),
        (12, "Bread", None),
    )
    await refresh(init_integration)
    fetches = recipes.list_planner.await_count
    init_integration.runtime_data.store.async_hide(13)

    response = await call(hass, "search_collection")
    assert response == {
        "recipes": [
            {
                "recipe_id": 11,
                "name": "Tomato Soup",
                "time": 25,
                "yields": 4,
                # Canonical category in the language of Home Assistant.
                "tags": ["Soup"],
                "planned_dates": ["2026-11-18", "2026-11-20"],
            },
            {
                "recipe_id": 12,
                "name": "Bread",
                "time": None,
                "yields": None,
                "tags": [],
                "planned_dates": [],
            },
        ],
        "total": 2,
    }
    # The fresh plan of the coordinator is reused.
    assert recipes.list_planner.await_count == fetches


@pytest.mark.parametrize(
    ("query", "ids"),
    [
        ("soup", [11]),
        ("  BREAD ", [12]),
        ("tomaten", [11, 13]),
        ("hefe", [12]),
        ("", [11, 12, 13]),
        ("nothing", []),
    ],
)
async def test_search_collection_query(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    recipes: MagicMock,
    query: str,
    ids: list[int],
) -> None:
    """The query matches the name or an ingredient, in any case."""
    response = await call(hass, "search_collection", query=query)
    assert [r["recipe_id"] for r in response["recipes"]] == ids


async def test_search_collection_fetches_stale_plan(
    hass: HomeAssistant, init_integration: MockConfigEntry, recipes: MagicMock
) -> None:
    """An old plan is fetched again (once) and shared with the entities."""
    init_integration.runtime_data.coordinator.fetched_at = None
    recipes.list_planner.return_value = plan((13, "Pasta", TODAY))
    fetches = recipes.list_planner.await_count
    response = await call(hass, "search_collection", query="pasta")
    assert response["recipes"][0]["planned_dates"] == ["2026-11-18"]
    assert recipes.list_planner.await_count == fetches + 1
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR).state == "Pasta"


async def test_search_collection_needs_response(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The reading actions are useless without a response."""
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "search_collection", {}, blocking=True, return_response=False
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "get_planner", {}, blocking=True, return_response=False
        )


async def test_search_collection_query_too_long(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    with pytest.raises(vol.Invalid):
        await call(hass, "search_collection", query="x" * 101)


@pytest.mark.parametrize(
    ("error", "key", "flows"),
    [
        (KitchenOwlAuthError("401"), "kitchenowl_auth", 1),
        (KitchenOwlError("500"), "kitchenowl_error", 0),
    ],
)
async def test_search_collection_errors(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    error: Exception,
    key: str,
    flows: int,
) -> None:
    mock_client.list_recipes.side_effect = error
    with pytest.raises(HomeAssistantError) as exc:
        await call(hass, "search_collection")
    assert exc.value.translation_key == key
    await hass.async_block_till_done()
    assert reauth_flows(hass) == flows


# ------------------------------------------------------------------ get_planner


async def test_get_planner_default(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Default: today and the next six days, by day, and the undated ones."""
    mock_client.list_planner.return_value = plan(
        (13, "Pasta", TODAY + timedelta(days=6)),
        (11, "Soup", TODAY),
        (12, "Bread", TODAY - timedelta(days=1)),
        (14, "Cake", TODAY + timedelta(days=7)),
        (15, "Someday", None),
        (16, "Salad", TODAY),
    )
    await refresh(init_integration)
    assert await call(hass, "get_planner") == {
        "start_date": "2026-11-18",
        "days": 7,
        "entries": [
            # 0.5.0: plan entries without yields and base have no servings.
            {"date": "2026-11-18", "recipe_id": 11, "name": "Soup", "servings": None},
            {"date": "2026-11-18", "recipe_id": 16, "name": "Salad", "servings": None},
            {"date": "2026-11-24", "recipe_id": 13, "name": "Pasta", "servings": None},
        ],
        "unscheduled": [{"recipe_id": 15, "name": "Someday", "servings": None}],
    }


async def test_get_planner_range(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A start day (text or date) and a number of days pick the range."""
    mock_client.list_planner.return_value = plan(
        (11, "Soup", date(2026, 12, 1)),
        (12, "Bread", date(2026, 12, 31)),
        (13, "Pasta", date(2027, 1, 1)),
    )
    await refresh(init_integration)
    response = await call(hass, "get_planner", start_date="2026-12-01", days=31)
    assert [e["recipe_id"] for e in response["entries"]] == [11, 12]
    response = await call(hass, "get_planner", start_date=date(2026, 12, 31), days=1)
    assert response["start_date"] == "2026-12-31" and response["days"] == 1
    assert [e["recipe_id"] for e in response["entries"]] == [12]


@pytest.mark.parametrize(
    "data",
    [
        {"days": 0},
        {"days": 32},
        {"days": "many"},
        {"start_date": "18.11.2026"},
        {"start_date": "1999-12-31"},
        {"start_date": "2101-01-01"},
        {"other": 1},
    ],
)
async def test_get_planner_invalid(
    hass: HomeAssistant, init_integration: MockConfigEntry, data: dict[str, Any]
) -> None:
    with pytest.raises(vol.Invalid):
        await call(hass, "get_planner", **data)


async def test_get_planner_error(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A stale plan is fetched; KitchenOwl errors become translated errors."""
    init_integration.runtime_data.coordinator.fetched_at = None
    mock_client.list_planner.side_effect = KitchenOwlAuthError("401")
    with pytest.raises(HomeAssistantError) as exc:
        await call(hass, "get_planner")
    assert exc.value.translation_key == "kitchenowl_auth"
    await hass.async_block_till_done()
    assert reauth_flows(hass) == 1


# -------------------------------------------------------- plan / unplan recipe


async def test_plan_recipe_updates_entities_at_once(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    fetches = mock_client.list_planner.await_count

    async def add(
        household_id: int, recipe_id: int, day: date, yields: int | None = None
    ) -> None:
        mock_client.list_planner.return_value = plan((recipe_id, "Soup", day))

    mock_client.add_planner_entry.side_effect = add
    response = await call(hass, "plan_recipe", recipe_id="11", date="2026-11-18")
    assert response == {"recipe_id": 11, "date": "2026-11-18"}
    # 0.5.0: recipe 11 has yields 4, so the start value 3 is planned.
    mock_client.add_planner_entry.assert_awaited_once_with(1, 11, TODAY, yields=3)
    assert mock_client.list_planner.await_count == fetches + 1
    await hass.async_block_till_done()
    state = hass.states.get(SENSOR)
    assert state.state == "Soup"
    assert state.attributes["week"] == [
        # 0.5.0: the plan entry of the fake has no yields: no servings.
        {"date": "2026-11-18", "recipe_id": 11, "name": "Soup", "servings": None}
    ]
    assert hass.states.get(CALENDAR).attributes["message"] == "Soup"


async def test_unplan_recipe(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    fetches = mock_client.list_planner.await_count
    response = await call(hass, "unplan_recipe", recipe_id=11, date="2026-11-19")
    assert response == {"recipe_id": 11, "date": "2026-11-19"}
    mock_client.remove_planner_entry.assert_awaited_once_with(
        1, 11, TODAY + timedelta(days=1)
    )
    response = await call(hass, "unplan_recipe", recipe_id=12)
    assert response == {"recipe_id": 12, "date": None}
    mock_client.remove_planner_entry.assert_awaited_with(1, 12, None)
    assert mock_client.list_planner.await_count == fetches + 2


@pytest.mark.parametrize("action", ["plan_recipe", "unplan_recipe"])
async def test_plan_not_in_collection(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    action: str,
) -> None:
    """A recipe of another household is refused before anything is sent."""
    with pytest.raises(ServiceValidationError) as exc:
        await call(hass, action, recipe_id=99, date="2026-11-18")
    assert exc.value.translation_key == "not_in_collection"
    mock_client.add_planner_entry.assert_not_awaited()
    mock_client.remove_planner_entry.assert_not_awaited()
    await hass.async_block_till_done()
    assert reauth_flows(hass) == 0


@pytest.mark.parametrize(
    "data",
    [
        {"recipe_id": 11},
        {"date": "2026-11-18"},
        {"recipe_id": 0, "date": "2026-11-18"},
        {"recipe_id": "abc", "date": "2026-11-18"},
        {"recipe_id": 11, "date": "0001-01-01"},
        {"recipe_id": 11, "date": "tomorrow"},
    ],
)
async def test_plan_recipe_invalid(
    hass: HomeAssistant, init_integration: MockConfigEntry, data: dict[str, Any]
) -> None:
    with pytest.raises(vol.Invalid):
        await call(hass, "plan_recipe", **data)


@pytest.mark.parametrize(
    "data", [{}, {"recipe_id": -1}, {"recipe_id": 11, "date": "2026-13-01"}]
)
async def test_unplan_recipe_invalid(
    hass: HomeAssistant, init_integration: MockConfigEntry, data: dict[str, Any]
) -> None:
    with pytest.raises(vol.Invalid):
        await call(hass, "unplan_recipe", **data)


@pytest.mark.parametrize(
    ("action", "method"),
    [("plan_recipe", "add_planner_entry"), ("unplan_recipe", "remove_planner_entry")],
)
@pytest.mark.parametrize(
    ("error", "key", "flows"),
    [
        (KitchenOwlAuthError("401"), "kitchenowl_auth", 1),
        (KitchenOwlError("500"), "kitchenowl_error", 0),
    ],
)
async def test_plan_errors(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    action: str,
    method: str,
    error: Exception,
    key: str,
    flows: int,
) -> None:
    """KitchenOwl errors are translated; the plan is refreshed anyway."""
    getattr(mock_client, method).side_effect = error
    fetches = mock_client.list_planner.await_count
    with pytest.raises(HomeAssistantError) as exc:
        await call(hass, action, recipe_id=11, date="2026-11-18")
    assert exc.value.translation_key == key
    assert mock_client.list_planner.await_count == fetches + 1
    await hass.async_block_till_done()
    assert reauth_flows(hass) == flows


@pytest.mark.parametrize(
    ("action", "data"),
    [
        ("search_collection", {}),
        ("get_planner", {}),
        ("plan_recipe", {"recipe_id": 11, "date": "2026-11-18"}),
        ("unplan_recipe", {"recipe_id": 11}),
    ],
)
async def test_new_actions_not_loaded(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    action: str,
    data: dict[str, Any],
) -> None:
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    with pytest.raises(ServiceValidationError) as exc:
        await call(hass, action, **data)
    assert exc.value.translation_key == "not_loaded"


# -------------------------------------------------------------- interval


@pytest.mark.parametrize(
    ("options", "minutes"),
    [
        ({}, 1),
        ({CONF_SOURCES: ["fakea"], CONF_ACCEPT_CHEFKOCH: False}, 1),
        ({CONF_PLANNER_INTERVAL: 5}, 5),
        ({CONF_PLANNER_INTERVAL: 5.0}, 5),
        ({CONF_PLANNER_INTERVAL: "15"}, 15),
        ({CONF_PLANNER_INTERVAL: 0}, 1),
        ({CONF_PLANNER_INTERVAL: 120}, 60),
        ({CONF_PLANNER_INTERVAL: "x"}, 1),
        ({CONF_PLANNER_INTERVAL: None}, 1),
    ],
)
def test_planner_interval(options: dict[str, Any], minutes: int) -> None:
    """Entries without the option (0.2.0) get one minute."""
    assert planner_interval(options) == timedelta(minutes=minutes)


async def test_entry_of_020_fetches_every_minute(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """One request per minute, and a fresh plan for the cards in between."""
    coordinator = init_integration.runtime_data.coordinator
    assert CONF_PLANNER_INTERVAL not in init_integration.options
    assert coordinator.update_interval == timedelta(minutes=1)
    before = mock_client.list_planner.await_count
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert mock_client.list_planner.await_count == before + 1
    # Cards, the sensor's week and the actions use that plan.
    data = init_integration.runtime_data
    await data.async_planner_week(None)
    await call(hass, "get_planner")
    await call(hass, "search_collection")
    assert mock_client.list_planner.await_count == before + 1


async def test_fetch_elsewhere_moves_the_next_update(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A plan fetched for a card counts as the update of that minute.

    The coordinator drops its planned update and plans a new one a whole
    interval later (``async_set_updated_data``), so both never add up.
    """
    data = init_integration.runtime_data
    planned = data.coordinator._unsub_refresh
    assert planned is not None
    data.coordinator.fetched_at = None
    before = mock_client.list_planner.await_count
    await data.async_planner_week(None)
    assert mock_client.list_planner.await_count == before + 1
    assert data.coordinator._unsub_refresh not in (None, planned)
    assert data.coordinator.fresh_data(timedelta(seconds=60)) is not None


async def test_interval_from_options(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    patch_client: MagicMock,
    mock_sources: MagicMock,
    panel_dir: Path,
    aioclient_mock: AiohttpClientMocker,
    mock_client: MagicMock,
) -> None:
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title=config_entry.title,
        unique_id=config_entry.unique_id,
        data=dict(config_entry.data),
        options={CONF_PLANNER_INTERVAL: 10},
    )
    config_entry.add_to_hass(hass)
    with patch(
        "custom_components.eatfresh.async_create_public_session",
        side_effect=lambda hass: aioclient_mock.create_session(hass.loop),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data.coordinator
    assert coordinator.update_interval == timedelta(minutes=10)
    before = mock_client.list_planner.await_count
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=5))
    await hass.async_block_till_done()
    assert mock_client.list_planner.await_count == before
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=11))
    await hass.async_block_till_done()
    assert mock_client.list_planner.await_count == before + 1


async def test_options_flow_interval(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The form shows one minute for an entry without the option and saves."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    schema = result["data_schema"].schema
    key = next(k for k in schema if k == CONF_PLANNER_INTERVAL)
    assert key.default() == 1
    assert schema[key].config["min"] == 1 and schema[key].config["max"] == 60
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SOURCES: ["fakea"], CONF_PLANNER_INTERVAL: 15}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options[CONF_PLANNER_INTERVAL] == 15
    await hass.async_block_till_done()
    coordinator = init_integration.runtime_data.coordinator
    assert coordinator.update_interval == timedelta(minutes=15)

    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    key = next(k for k in result["data_schema"].schema if k == CONF_PLANNER_INTERVAL)
    assert key.default() == 15


@pytest.mark.parametrize("value", [0, 61])
async def test_options_flow_interval_out_of_range(
    hass: HomeAssistant, init_integration: MockConfigEntry, value: int
) -> None:
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    with pytest.raises(vol.Invalid):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SOURCES: ["fakea"], CONF_PLANNER_INTERVAL: value}
        )


# ---------------------------------------------------------------- sensor week


async def test_sensor_week(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    assert hass.states.get(SENSOR).attributes["week"] == []
    mock_client.list_planner.return_value = plan(
        (14, "Cake", TODAY + timedelta(days=7)),
        (13, "Pasta", TODAY + timedelta(days=6)),
        (12, "Bread", TODAY - timedelta(days=1)),
        (11, "Soup", TODAY),
        (15, "Someday", None),
        (16, "Salad", TODAY + timedelta(days=2)),
    )
    await refresh(init_integration)
    assert hass.states.get(SENSOR).attributes["week"] == [
        # 0.5.0: plan entries without yields and base have no servings.
        {"date": "2026-11-18", "recipe_id": 11, "name": "Soup", "servings": None},
        {"date": "2026-11-20", "recipe_id": 16, "name": "Salad", "servings": None},
        {"date": "2026-11-24", "recipe_id": 13, "name": "Pasta", "servings": None},
    ]


async def test_sensor_week_moves_at_midnight(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """After midnight yesterday drops out and the seventh day comes in.

    Like the midnight test of the state: real next midnight, no new plan.
    """
    first = dt_util.as_local(dt_util.utcnow()).date()
    tomorrow = first + timedelta(days=1)
    midnight = dt_util.start_of_local_day(tomorrow)
    mock_client.list_planner.return_value = plan(
        (11, "Soup", first),
        (12, "Bread", tomorrow),
        (13, "Pasta", first + timedelta(days=7)),
    )
    with patch(
        "custom_components.eatfresh.runtime.dt_util.now",
        side_effect=lambda: dt_util.as_local(midnight - timedelta(hours=1)),
    ):
        await refresh(init_integration)
        assert [e["recipe_id"] for e in hass.states.get(SENSOR).attributes["week"]] == [
            11,
            12,
        ]
    coordinator = init_integration.runtime_data.coordinator
    coordinator.update_interval = None
    coordinator._unschedule_refresh()
    fetches = mock_client.list_planner.await_count
    with patch(
        "custom_components.eatfresh.runtime.dt_util.now",
        side_effect=lambda: dt_util.as_local(midnight + timedelta(seconds=5)),
    ):
        async_fire_time_changed(hass, dt_util.as_utc(midnight + timedelta(seconds=5)))
        await hass.async_block_till_done()
        state = hass.states.get(SENSOR)
    assert [e["recipe_id"] for e in state.attributes["week"]] == [12, 13]
    assert state.state == "Bread"
    assert mock_client.list_planner.await_count == fetches


# ---------------------------------------------------------------- helpers


def test_dated_and_unscheduled_entries() -> None:
    entries = [
        *plan((1, "A", TODAY), (2, "B", None)),
        {"recipe_id": 3, "name": "C", "date": "2026-11-19"},
        {"recipe_id": 4, "name": "D", "date": "broken"},
        {"recipe_id": "5", "name": "E", "date": "2026-11-18"},
        {"recipe_id": 6, "name": "F", "date": ""},
    ]
    assert [(d, e["recipe_id"]) for d, e in dated_entries(entries, TODAY, 2)] == [
        (TODAY, 1),
        (TODAY + timedelta(days=1), 3),
    ]
    assert dated_entries(None, TODAY, 7) == []
    assert [e["recipe_id"] for e in unscheduled_entries(entries)] == [2, 6]
    week = build_week(entries, TODAY)
    assert [e["recipe_id"] for e in week.unscheduled] == [2, 6]
    assert week.recipe_ids == [1, 3]


async def test_ws_planner_still_uses_cache(
    hass: HomeAssistant, init_integration: MockConfigEntry, hass_ws_client, mock_client
) -> None:
    """The 60-second path of ``eatfresh/planner`` is unchanged."""
    ws = WS(await hass_ws_client())
    before = mock_client.list_planner.await_count
    msg = await ws.call("eatfresh/planner")
    assert msg["success"]
    assert mock_client.list_planner.await_count == before


@pytest.mark.parametrize(
    ("query", "name_only", "ids"),
    [
        ("tomaten", True, []),
        ("tomaten", False, [11, 13]),
        ("soup", True, [11]),
        ("", True, [11, 12, 13]),
    ],
)
async def test_search_collection_name_only(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    recipes: MagicMock,
    query: str,
    name_only: bool,
    ids: list[int],
) -> None:
    """With name_only the query only matches the name (wish of 0.4.0)."""
    response = await call(
        hass, "search_collection", query=query, name_only=name_only
    )
    assert [r["recipe_id"] for r in response["recipes"]] == ids
    assert response["total"] == len(ids)


async def test_search_collection_name_only_default_off(
    hass: HomeAssistant, init_integration: MockConfigEntry, recipes: MagicMock
) -> None:
    response = await call(hass, "search_collection", query="hefe")
    assert [r["recipe_id"] for r in response["recipes"]] == [12]
    with pytest.raises(vol.Invalid):
        await call(hass, "search_collection", query="hefe", name_only="maybe")
