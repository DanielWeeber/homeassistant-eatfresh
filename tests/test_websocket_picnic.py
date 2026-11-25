"""Tests for the shopping list and Picnic commands of EatFresh 0.4.0."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eatfresh import picnic
from custom_components.eatfresh.const import STORAGE_KEY
from custom_components.eatfresh.errors import KitchenOwlError

from .test_picnic import (
    MILK,
    POTATOES,
    FakeClient,
    FakePicnic,
    PicnicAuthError,
    connection_error,
    old_result,
    read_error,
    wait_idle,
)
from .test_websocket_api import WS

LIST = [
    {"id": 101, "name": "Kartoffeln", "description": "1500g"},
    {"id": 102, "name": "Milch", "description": "2 l"},
    {"id": 103, "name": "Salz", "description": ""},
]

POTATO_PRODUCT = {
    "id": "s1000001",
    "name": "Kartoffeln festkochend",
    "unit_quantity": "1kg",
    "price": 249,
}


@pytest.fixture(autouse=True)
def no_pause() -> Iterator[None]:
    with patch.object(picnic, "CALL_PAUSE", 0):
        yield


@pytest.fixture
def shopping_list(mock_client: MagicMock) -> AsyncMock:
    mock_client.list_shoppinglist_items = AsyncMock(
        side_effect=lambda list_id: [dict(row) for row in LIST]
    )
    return mock_client.list_shoppinglist_items


@pytest.fixture
async def ws(
    init_integration: MockConfigEntry, hass_ws_client, shopping_list: AsyncMock
) -> WS:
    helper = WS(await hass_ws_client())
    helper.entry = init_integration  # type: ignore[attr-defined]
    return helper


@pytest.fixture
def fake_picnic(hass: HomeAssistant) -> FakePicnic:
    return FakePicnic(hass, FakeClient())


def send_items(*rows: tuple[int, str, int]) -> list[dict[str, Any]]:
    return [
        {"item_id": item_id, "product_id": product_id, "amount": amount}
        for item_id, product_id, amount in rows
    ]


def sent_items(*rows: tuple[int, str, int]) -> list[dict[str, Any]]:
    """The answer for sent entries: since 0.5.0 with ``small_amount``."""
    return [{**row, "small_amount": 0} for row in send_items(*rows)]


# ----- without Picnic -------------------------------------------------------


async def test_shopping_without_picnic(ws: WS, shopping_list: AsyncMock) -> None:
    """EatFresh runs as before; the list comes without Picnic."""
    msg = await ws.call("eatfresh/shopping")
    assert msg["success"], msg
    result = msg["result"]
    assert result["picnic"] == {
        "available": False,
        "search": False,
        "reason": picnic.REASON_NOT_SET_UP,
        "reason_code": "not_set_up",
    }
    assert result["items"][0] == {
        "item_id": 101,
        "name": "Kartoffeln",
        "description": "1500g",
        "product": None,
        "amount": 1,
        "skip": False,
        "sent_at": None,
        "sent_uncertain": False,
        # 0.5.0: the amount text in the cart when the entry changed since.
        "cart_hint": None,
        # 0.5.0: smaller pack for the rest.
        "rest": None,
        "exact": None,
        "small": None,
        "small_amount": 0,
        # 0.5.0: the group of the entry (no category in KitchenOwl: by name).
        "department": "fruits_vegetables",
    }
    assert [item["item_id"] for item in result["items"]] == [101, 102, 103]
    shopping_list.assert_awaited_once_with(2)

    msg = await ws.call("eatfresh/picnic/search", query="Milch")
    assert msg["error"]["code"] == "picnic_unavailable"
    msg = await ws.call("eatfresh/picnic/send", items=send_items((101, "s1", 1)))
    assert msg["error"]["code"] == "picnic_unavailable"
    # Remembering works without Picnic as well.
    msg = await ws.call("eatfresh/picnic/map", name="Milch", product=POTATO_PRODUCT)
    assert msg["success"]
    # The other commands are not touched.
    assert (await ws.call("eatfresh/sources"))["success"]


async def test_shopping_kitchenowl_error(ws: WS, shopping_list: AsyncMock) -> None:
    shopping_list.side_effect = KitchenOwlError("down")
    msg = await ws.call("eatfresh/shopping")
    assert msg["error"]["code"] == "kitchenowl_error"


async def test_shopping_does_not_call_picnic(
    ws: WS, fake_picnic: FakePicnic
) -> None:
    msg = await ws.call("eatfresh/shopping")
    assert msg["result"]["picnic"] == {
        "available": True,
        "search": True,
        "reason": None,
        "reason_code": None,
    }
    assert fake_picnic.client.searches == []
    assert fake_picnic.added == []
    fake_picnic.refresh.assert_not_awaited()


async def test_entry_not_loaded(ws: WS, hass: HomeAssistant) -> None:
    fake = FakePicnic(hass, FakeClient())
    fake.entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
    msg = await ws.call("eatfresh/shopping")
    assert msg["result"]["picnic"]["reason"] == picnic.REASON_NOT_LOADED
    msg = await ws.call("eatfresh/picnic/search", query="Milch")
    assert msg["error"]["code"] == "picnic_unavailable"


async def test_client_without_search(ws: WS, fake_picnic: FakePicnic) -> None:
    client = FakeClient()
    client.search = None  # type: ignore[assignment,method-assign]
    fake_picnic.entry.runtime_data.picnic_api_client = client
    msg = await ws.call("eatfresh/shopping")
    assert msg["result"]["picnic"] == {
        "available": True,
        "search": False,
        "reason": picnic.REASON_NO_SEARCH,
        "reason_code": "no_search",
    }
    msg = await ws.call("eatfresh/picnic/search", query="Milch")
    assert msg["error"]["code"] == "picnic_unavailable"


# ----- search ---------------------------------------------------------------


async def test_search_both_forms(ws: WS, fake_picnic: FakePicnic) -> None:
    msg = await ws.call("eatfresh/picnic/search", query="  Kartoffeln ")
    assert msg["result"]["products"][0] == {
        "id": "s1000001",
        "name": "Kartoffeln festkochend",
        "unit_quantity": "2kg",
        "price": 249,
        "fits_rest": False,  # 0.5.0
    }
    assert fake_picnic.client.searches == ["Kartoffeln"]

    fake_picnic.client.result = old_result(POTATOES, MILK)
    msg = await ws.call("eatfresh/picnic/search", query="Milch")
    assert [p["id"] for p in msg["result"]["products"]] == ["s1000001", "s1000002"]


async def test_search_limits(ws: WS, fake_picnic: FakePicnic) -> None:
    for query in ("", "   ", "x" * 61):
        msg = await ws.call("eatfresh/picnic/search", query=query)
        assert msg["error"]["code"] == "invalid_format", query
    assert (await ws.call("eatfresh/picnic/search", query="x" * 60))["success"]
    fake_picnic.client.result = {
        "items": [{"id": f"s{i}", "name": f"P {i}"} for i in range(20)]
    }
    msg = await ws.call("eatfresh/picnic/search", query="P")
    assert len(msg["result"]["products"]) == 8


async def test_search_errors(ws: WS, fake_picnic: FakePicnic) -> None:
    fake_picnic.client.search_error = PicnicAuthError("expired")
    msg = await ws.call("eatfresh/picnic/search", query="Milch")
    assert msg["error"]["code"] == "picnic_error"
    assert "login" in msg["error"]["message"]

    fake_picnic.client.search_error = None
    fake_picnic.client.delay = 0.3
    with patch.object(picnic, "CALL_TIMEOUT", 0.05):
        msg = await ws.call("eatfresh/picnic/search", query="Milch")
    assert msg["error"]["code"] == "picnic_error"
    assert "in time" in msg["error"]["message"]


# ----- remembering ----------------------------------------------------------


async def test_map_unmap_skip(ws: WS) -> None:
    msg = await ws.call(
        "eatfresh/picnic/map", name="  KARTOFFELN ", product=POTATO_PRODUCT
    )
    assert msg["result"] == {}
    msg = await ws.call("eatfresh/shopping")
    potatoes = msg["result"]["items"][0]
    assert potatoes["product"] == POTATO_PRODUCT
    # 1500 g with packs of 1 kg: 2 packs suggested.
    assert potatoes["amount"] == 2

    await ws.call(
        "eatfresh/picnic/map", name="Kartoffeln", product=POTATO_PRODUCT, amount=5
    )
    msg = await ws.call("eatfresh/shopping")
    assert msg["result"]["items"][0]["amount"] == 5

    assert (await ws.call("eatfresh/picnic/skip", name="salz", skip=True))["success"]
    msg = await ws.call("eatfresh/shopping")
    assert [item["skip"] for item in msg["result"]["items"]] == [False, False, True]
    await ws.call("eatfresh/picnic/skip", name="Salz", skip=False)
    msg = await ws.call("eatfresh/shopping")
    assert msg["result"]["items"][2]["skip"] is False

    assert (await ws.call("eatfresh/picnic/unmap", name="kartoffeln"))["success"]
    msg = await ws.call("eatfresh/shopping")
    assert msg["result"]["items"][0]["product"] is None
    # Forgetting twice is no error.
    assert (await ws.call("eatfresh/picnic/unmap", name="kartoffeln"))["success"]


async def test_map_minimal_product(ws: WS) -> None:
    msg = await ws.call(
        "eatfresh/picnic/map", name="Milch", product={"id": 12345, "name": "Milch"}
    )
    assert msg["success"]
    msg = await ws.call("eatfresh/shopping")
    assert msg["result"]["items"][1]["product"] == {
        "id": "12345",
        "name": "Milch",
        "unit_quantity": None,
        "price": None,
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "", "product": POTATO_PRODUCT},
        {"name": "x" * 101, "product": POTATO_PRODUCT},
        {"name": "Milch", "product": {"name": "No id"}},
        {"name": "Milch", "product": {"id": "", "name": "Empty id"}},
        {"name": "Milch", "product": {"id": {"a": 1}, "name": "Dict id"}},
        {"name": "Milch", "product": {"id": "x" * 65, "name": "Long id"}},
        {"name": "Milch", "product": {"id": "s1", "name": ""}},
        {"name": "Milch", "product": {"id": "s1", "name": "M", "price": -1}},
        {"name": "Milch", "product": {"id": "s1", "name": "M", "price": True}},
        {"name": "Milch", "product": POTATO_PRODUCT, "amount": 0},
        {"name": "Milch", "product": POTATO_PRODUCT, "amount": 21},
    ],
)
async def test_map_limits(ws: WS, kwargs: dict[str, Any]) -> None:
    msg = await ws.call("eatfresh/picnic/map", **kwargs)
    assert msg["error"]["code"] == "invalid_format"


# ----- send -----------------------------------------------------------------


async def test_send(ws: WS, fake_picnic: FakePicnic) -> None:
    msg = await ws.call(
        "eatfresh/picnic/send",
        items=send_items((101, "s1000001", 2), (102, "s1000002", 2)),
    )
    assert msg["result"] == {
        "sent": sent_items((101, "s1000001", 2), (102, "s1000002", 2)),
        "failed": [],
    }
    assert fake_picnic.added == [("s1000001", 2), ("s1000002", 2)]
    assert fake_picnic.client.cart == {"s1000001": 2, "s1000002": 2}
    # The client answers with the cart; the action would throw it away.
    assert fake_picnic.action_calls == []
    fake_picnic.refresh.assert_awaited_once()

    msg = await ws.call("eatfresh/shopping")
    items = msg["result"]["items"]
    assert items[0]["sent_at"] is not None
    assert items[0]["sent_uncertain"] is False
    assert items[2]["sent_at"] is None

    # A second try sends nothing again.
    msg = await ws.call("eatfresh/picnic/send", items=send_items((101, "s1000001", 2)))
    assert msg["result"]["sent"] == []
    assert msg["result"]["failed"] == [
        {
            "item_id": 101,
            "code": "already_sent",
            "message": "The entry is in the Picnic cart already",
        }
    ]
    assert len(fake_picnic.added) == 2


async def test_send_checks_the_list(ws: WS, fake_picnic: FakePicnic) -> None:
    msg = await ws.call(
        "eatfresh/picnic/send",
        items=send_items((999, "s1", 1), (101, "s1", 1), (101, "s1", 1)),
    )
    result = msg["result"]
    assert result["sent"] == sent_items((101, "s1", 1))
    assert result["failed"] == [
        {
            "item_id": 999,
            "code": "not_on_list",
            "message": "The entry is no longer on the shopping list",
        },
        {
            "item_id": 101,
            "code": "twice",
            "message": "The entry is in the request twice",
        },
    ]
    assert len(fake_picnic.added) == 1


@pytest.mark.parametrize("answer", ["error", "unchanged"])
async def test_send_stops_at_an_unknown_product(
    ws: WS, fake_picnic: FakePicnic, answer: str
) -> None:
    """Picnic refuses the second product without an error: the run stops.

    The second one is not marked (it is not in the cart), the third one is
    never tried.
    """
    fake_picnic.client.unknown = {"s2"}
    fake_picnic.client.unknown_answer = answer
    msg = await ws.call(
        "eatfresh/picnic/send",
        items=send_items((101, "s1", 1), (102, "s2", 1), (103, "s3", 1)),
    )
    result = msg["result"]
    assert result["sent"] == sent_items((101, "s1", 1))
    assert [(f["item_id"], f["code"]) for f in result["failed"]] == [
        (102, "not_added"),
        (103, "not_tried"),
    ]
    assert fake_picnic.added == [("s1", 1), ("s2", 1)]
    assert fake_picnic.client.cart == {"s1": 1}
    fake_picnic.refresh.assert_not_awaited()
    msg = await ws.call("eatfresh/shopping")
    assert [
        (item["sent_at"] is not None, item["sent_uncertain"])
        for item in msg["result"]["items"]
    ] == [(True, False), (False, False), (False, False)]


async def test_send_stops_on_auth_error(ws: WS, fake_picnic: FakePicnic) -> None:
    """A rejected login halfway stops the run; nothing more goes to Picnic."""
    fake_picnic.client.add_errors = {2: PicnicAuthError("expired")}
    msg = await ws.call(
        "eatfresh/picnic/send",
        items=send_items((101, "s1", 1), (102, "s2", 1), (103, "s3", 1)),
    )
    result = msg["result"]
    assert result["sent"] == sent_items((101, "s1", 1))
    assert [(f["item_id"], f["code"]) for f in result["failed"]] == [
        (102, "auth"),
        (103, "not_tried"),
    ]
    assert "login" in result["failed"][0]["message"]
    assert fake_picnic.added == [("s1", 1), ("s2", 1)]
    # No refresh after a rejected login: that would call Picnic again.
    fake_picnic.refresh.assert_not_awaited()
    # Picnic said no to the login: the second one is surely not in the cart.
    data = ws.entry.runtime_data  # type: ignore[attr-defined]
    assert data.store.picnic_sent(102) is None


@pytest.mark.parametrize(
    "error", [read_error(), connection_error(), RuntimeError("odd")]
)
async def test_send_stops_at_any_error(
    ws: WS, fake_picnic: FakePicnic, error: Exception
) -> None:
    """Any error while putting a product in stops the run at once.

    The real library raises a read error (an error page without JSON) or a
    connection error, never one with a status code. Such a product may be
    in the cart, so it is "maybe sent".
    """
    fake_picnic.client.add_errors = {2: error}
    msg = await ws.call(
        "eatfresh/picnic/send",
        items=send_items((101, "s1", 1), (102, "s2", 1), (103, "s3", 1)),
    )
    result = msg["result"]
    assert result["sent"] == sent_items((101, "s1", 1))
    assert [(f["item_id"], f["code"]) for f in result["failed"]] == [
        (102, "maybe_sent"),
        (103, "not_tried"),
    ]
    assert fake_picnic.added == [("s1", 1), ("s2", 1)]
    fake_picnic.refresh.assert_not_awaited()
    msg = await ws.call("eatfresh/shopping")
    assert [
        (item["sent_at"] is not None, item["sent_uncertain"])
        for item in msg["result"]["items"]
    ] == [(True, False), (True, True), (False, False)]


async def test_send_timeouts(ws: WS, fake_picnic: FakePicnic) -> None:
    """A timeout stops the run at once; the rest is not tried."""
    fake_picnic.client.add_delay = 0.3
    with patch.object(picnic, "CALL_TIMEOUT", 0.05):
        msg = await ws.call(
            "eatfresh/picnic/send",
            items=send_items((101, "s1", 1), (102, "s2", 1), (103, "s3", 1)),
        )
    failed = msg["result"]["failed"]
    assert [(f["item_id"], f["code"]) for f in failed] == [
        (101, "maybe_sent"),
        (102, "not_tried"),
        (103, "not_tried"),
    ]
    assert "may be in the cart" in failed[0]["message"]
    assert len(fake_picnic.added) == 1
    await wait_idle(fake_picnic.client)
    assert fake_picnic.client.most_active == 1


async def test_send_twice_at_the_same_time(
    hass: HomeAssistant, ws: WS, fake_picnic: FakePicnic
) -> None:
    hold = threading.Event()
    fake_picnic.client.hold = hold
    data = ws.entry.runtime_data  # type: ignore[attr-defined]
    first = hass.async_create_task(
        data.async_picnic_send(hass, send_items((101, "s1", 1)))
    )
    for _ in range(100):
        if fake_picnic.added:
            break
        await asyncio.sleep(0.01)
    msg = await ws.call("eatfresh/picnic/send", items=send_items((101, "s1", 1)))
    assert msg["error"]["code"] == "picnic_error"
    assert "running already" in msg["error"]["message"]
    msg = await ws.call("eatfresh/picnic/undo", item_id=101)
    assert msg["error"]["code"] == "picnic_error"
    hold.set()
    result = await first
    assert result["sent"] == sent_items((101, "s1", 1))
    assert len(fake_picnic.added) == 1


@pytest.mark.parametrize(
    "items",
    [
        [],
        send_items(*[(100 + i, "s1", 1) for i in range(61)]),
        send_items((101, "s1", 0)),
        send_items((101, "s1", 21)),
        send_items((0, "s1", 1)),
        send_items((101, "", 1)),
        [{"item_id": 101, "amount": 1}],
    ],
)
async def test_send_limits(
    ws: WS, fake_picnic: FakePicnic, items: list[dict[str, Any]]
) -> None:
    msg = await ws.call("eatfresh/picnic/send", items=items)
    assert msg["error"]["code"] == "invalid_format"
    assert fake_picnic.added == []


async def test_send_sixty_items(
    ws: WS, fake_picnic: FakePicnic, shopping_list: AsyncMock
) -> None:
    rows = [{"id": 100 + i, "name": f"Item {i}", "description": ""} for i in range(60)]
    shopping_list.side_effect = None
    shopping_list.return_value = rows
    msg = await ws.call(
        "eatfresh/picnic/send",
        items=send_items(*[(100 + i, f"s{i}", 20) for i in range(60)]),
    )
    assert len(msg["result"]["sent"]) == 60


# ----- undo -----------------------------------------------------------------


async def test_undo(ws: WS, fake_picnic: FakePicnic) -> None:
    await ws.call("eatfresh/picnic/send", items=send_items((101, "s1000001", 3)))
    fake_picnic.refresh.reset_mock()
    msg = await ws.call("eatfresh/picnic/undo", item_id=101)
    assert msg["result"] == {}
    assert fake_picnic.client.removed == [("s1000001", 3)]
    assert fake_picnic.client.cart == {}
    fake_picnic.refresh.assert_awaited_once()
    msg = await ws.call("eatfresh/shopping")
    assert msg["result"]["items"][0]["sent_at"] is None

    msg = await ws.call("eatfresh/picnic/undo", item_id=101)
    assert msg["error"]["code"] == "not_found"
    assert len(fake_picnic.client.removed) == 1


async def test_undo_without_remove(ws: WS, fake_picnic: FakePicnic) -> None:
    await ws.call("eatfresh/picnic/send", items=send_items((101, "s1", 1)))
    client = FakeClient()
    client.remove_product = None  # type: ignore[assignment,method-assign]
    fake_picnic.entry.runtime_data.picnic_api_client = client
    msg = await ws.call("eatfresh/picnic/undo", item_id=101)
    assert msg["error"]["code"] == "picnic_error"
    assert "Picnic app" in msg["error"]["message"]
    # The mark stays, so the panel still shows "in the cart".
    msg = await ws.call("eatfresh/shopping")
    assert msg["result"]["items"][0]["sent_at"] is not None


async def test_undo_auth_error_keeps_the_mark(ws: WS, fake_picnic: FakePicnic) -> None:
    await ws.call("eatfresh/picnic/send", items=send_items((101, "s1", 1)))
    fake_picnic.client.remove_error = PicnicAuthError("expired")
    msg = await ws.call("eatfresh/picnic/undo", item_id=101)
    assert msg["error"]["code"] == "picnic_error"
    msg = await ws.call("eatfresh/shopping")
    assert msg["result"]["items"][0]["sent_at"] is not None
    assert msg["result"]["items"][0]["sent_uncertain"] is False


@pytest.mark.parametrize("error", [read_error(), connection_error()])
async def test_undo_unclear_answer_is_never_repeated(
    ws: WS, fake_picnic: FakePicnic, error: Exception
) -> None:
    """After an unclear answer to "undo" it may be out already: never again.

    The entry becomes "maybe in the cart", which offers no taking out.
    """
    await ws.call("eatfresh/picnic/send", items=send_items((101, "s1", 2)))
    fake_picnic.client.remove_error = error
    msg = await ws.call("eatfresh/picnic/undo", item_id=101)
    assert msg["error"]["code"] == "picnic_error"
    msg = await ws.call("eatfresh/shopping")
    assert msg["result"]["items"][0]["sent_uncertain"] is True
    fake_picnic.client.remove_error = None
    msg = await ws.call("eatfresh/picnic/undo", item_id=101)
    assert msg["error"]["translation_key"] == "picnic_maybe_no_undo"
    assert fake_picnic.client.removed == [("s1", 2)]


async def test_undo_limits(ws: WS) -> None:
    for item_id in (0, -1, "x"):
        msg = await ws.call("eatfresh/picnic/undo", item_id=item_id)
        assert msg["error"]["code"] == "invalid_format"


# ----- marks ----------------------------------------------------------------


async def test_marks_fall_away(
    ws: WS,
    fake_picnic: FakePicnic,
    shopping_list: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Marks of entries off the list and after 14 days are dropped."""
    await ws.call(
        "eatfresh/picnic/send", items=send_items((101, "s1", 1), (102, "s2", 1))
    )
    data = ws.entry.runtime_data  # type: ignore[attr-defined]
    shopping_list.side_effect = lambda list_id: [dict(LIST[0]), dict(LIST[2])]
    await ws.call("eatfresh/shopping")
    assert data.store.picnic_sent(102) is None
    assert data.store.picnic_sent(101) is not None

    freezer.tick(timedelta(days=15))
    msg = await ws.call("eatfresh/shopping")
    assert msg["result"]["items"][0]["sent_at"] is None
    assert data.store.picnic_sent(101) is None


# ----- 0.4.0 after the review: honest Picnic --------------------------------


async def test_send_keeps_the_pause(ws: WS, fake_picnic: FakePicnic) -> None:
    """Between two calls of one run there is the pause, one call at a time.

    The run reads the cart once first, then puts the three products in.
    """
    fake_picnic.client.add_delay = 0.02
    with patch.object(picnic, "CALL_PAUSE", 0.1):
        msg = await ws.call(
            "eatfresh/picnic/send",
            items=send_items((101, "s1", 1), (102, "s2", 1), (103, "s3", 1)),
        )
    assert len(msg["result"]["sent"]) == 3
    calls = fake_picnic.client.calls
    assert [name for name, _start, _end in calls] == [
        "get_cart",
        "add_product",
        "add_product",
        "add_product",
    ]
    for before, after in zip(calls, calls[1:], strict=False):
        assert after[1] - before[2] >= 0.09
    assert fake_picnic.client.most_active == 1


async def test_marks_are_saved_at_once(
    ws: WS, fake_picnic: FakePicnic, hass_storage: dict[str, Any]
) -> None:
    """A mark is on disk before the next call to Picnic, not 2 s later."""
    seen: list[dict[str, Any]] = []
    client = fake_picnic.client
    original = client.add_product

    def add_and_look(product_id: str, count: int = 1) -> Any:
        stored = hass_storage.get(STORAGE_KEY, {}).get("data", {})
        seen.append(dict(stored.get("picnic_sent", {})))
        return original(product_id, count)

    client.add_product = add_and_look  # type: ignore[method-assign]
    await ws.call(
        "eatfresh/picnic/send", items=send_items((101, "s1", 1), (102, "s2", 1))
    )
    # While the first call runs, its entry is on disk as "maybe" already.
    assert seen[0]["101"]["uncertain"] is True
    # Before the second call the first one is on disk as "in the cart".
    assert "uncertain" not in seen[1]["101"]
    assert seen[1]["102"]["uncertain"] is True
    stored = hass_storage[STORAGE_KEY]["data"]["picnic_sent"]
    assert set(stored) == {"101", "102"}
    assert "uncertain" not in stored["102"]


async def test_maybe_sent_is_never_taken_out(ws: WS, fake_picnic: FakePicnic) -> None:
    """For "maybe in the cart" there is only "is not in the cart"."""
    fake_picnic.client.add_errors = {1: read_error()}
    await ws.call("eatfresh/picnic/send", items=send_items((101, "s1", 2)))
    msg = await ws.call("eatfresh/picnic/undo", item_id=101)
    assert msg["error"]["code"] == "picnic_error"
    assert msg["error"]["translation_key"] == "picnic_maybe_no_undo"
    assert fake_picnic.client.removed == []
    msg = await ws.call("eatfresh/picnic/undo", item_id=101, remove=False)
    assert msg["success"], msg
    assert fake_picnic.client.removed == []


async def test_undo_takes_out_only_what_was_put_in(
    ws: WS, fake_picnic: FakePicnic
) -> None:
    """Pieces that were in the cart before stay there."""
    fake_picnic.client.cart = {"s1": 1}
    # The run reads the cart first, so the piece there before is known.
    msg = await ws.call(
        "eatfresh/picnic/send", items=send_items((102, "s2", 1), (101, "s1", 2))
    )
    assert msg["result"]["sent"] == sent_items((102, "s2", 1), (101, "s1", 2))
    assert fake_picnic.client.cart == {"s1": 3, "s2": 1}
    await ws.call("eatfresh/picnic/undo", item_id=101)
    assert fake_picnic.client.cart == {"s1": 1, "s2": 1}
