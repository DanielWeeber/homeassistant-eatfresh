"""Tests for the access to the Picnic integration (``picnic.py``).

Picnic is never called: a fake config entry of the domain ``picnic`` with
a fake client and a fake action ``picnic.add_product`` stand in for it.

The fake behaves like the real library python-picnic-api2 2.0.1
(``client.py``, ``session.py``, ``models/cart.py``), not friendlier:

- It never checks the HTTP status. A failed call raises an error while
  reading the answer (``requests.JSONDecodeError`` or a connection error,
  both without ``response``), or nothing at all.
- An error answer of Picnic in JSON is no error: ``add_product`` and
  ``remove_product`` return a ``Cart`` without items whose ``raw`` is the
  error object. Only the codes ``AUTH_ERROR`` and ``AUTH_INVALID_CRED``
  raise ``PicnicAuthError``.
- ``add_product`` for an unknown or refused product returns an empty
  (error) or an unchanged cart, without an error.
- The action ``picnic.add_product`` of the integration throws the answer
  away (``services.py``, ``handle_add_product``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
import threading
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import requests
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockModule,
    mock_integration,
)

from custom_components.eatfresh import picnic

# The pause as written in picnic.py, before a fixture sets it to 0.
DEFAULT_CALL_PAUSE = picnic.CALL_PAUSE


class PicnicAuthError(Exception):
    """Same class name as the error of the Picnic library."""


def read_error() -> Exception:
    """What the library raises when Picnic answers without JSON (an error page).

    ``Response.json()`` raises it without a ``response``, so no status code
    can be read (requests 2.x, ``models.py``).
    """
    return requests.exceptions.JSONDecodeError("Expecting value", "<html>", 0)


def connection_error() -> Exception:
    """A broken connection: also without a ``response``."""
    return requests.exceptions.ConnectionError("Connection aborted")


def error_object(code: str = "PRODUCT_NOT_FOUND") -> dict[str, Any]:
    """A JSON error answer of Picnic (the library returns it, it raises nothing)."""
    return {"error": {"code": code, "message": "Something went wrong"}}


def new_result(*tiles: dict[str, Any]) -> SimpleNamespace:
    """Search result in the form of python-picnic-api2 2.x (objects)."""
    return SimpleNamespace(
        items=[SimpleNamespace(**tile) for tile in tiles], raw={"body": {}}
    )


def old_result(*tiles: dict[str, Any]) -> list[dict[str, Any]]:
    """Search result in the form of python-picnic-api 1.x (list of groups)."""
    return [{"type": "CATEGORY", "id": "group", "items": list(tiles)}]


def cart_model(payload: dict[str, Any]) -> SimpleNamespace:
    """Like ``Cart.from_api``: unknown keys are ignored, ``raw`` keeps all."""
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    return SimpleNamespace(items=items, raw=payload)


def cart_payload(cart: dict[str, int]) -> dict[str, Any]:
    """A cart in the form of Picnic's ``/cart`` answer (order lines)."""
    return {
        "type": "ORDER",
        "id": "shopping_cart",
        "items": [
            {
                "type": "ORDER_LINE",
                "id": f"line-{product_id}",
                "items": [
                    {
                        "type": "ORDER_ARTICLE",
                        "id": product_id,
                        "name": f"Product {product_id}",
                        "unit_quantity": "1 Stück",
                        "decorators": [{"type": "QUANTITY", "quantity": count}],
                    }
                ],
            }
            for product_id, count in cart.items()
        ],
        "total_count": sum(cart.values()),
    }


POTATOES = {
    "id": "s1000001",
    "name": "Kartoffeln festkochend",
    "display_price": 249,
    "unit_quantity": "2kg",
}
MILK = {
    "id": "s1000002",
    "name": "Milch 3,5 %",
    "display_price": 119,
    "unit_quantity": "1L",
}


class FakeClient:
    """Stands in for ``PicnicAPI``: blocking methods, records the calls.

    Every product id is known unless it is in ``unknown``. The cart lives in
    ``cart`` (product id to pieces).
    """

    def __init__(self, result: Any = None) -> None:
        self.result = result if result is not None else new_result(POTATOES, MILK)
        self.cart: dict[str, int] = {}
        self.searches: list[str] = []
        self.added: list[tuple[str, int]] = []
        self.removed: list[tuple[str, int]] = []
        # Every ended call in order: (name, start, end) with time.monotonic().
        self.calls: list[tuple[str, float, float]] = []
        # Every started call: (name, start).
        self.starts: list[tuple[str, float]] = []
        self.search_error: Exception | None = None
        self.remove_error: Exception | None = None
        self.remove_answer: Any = None
        # Errors of the n-th call of add_product (1 = first).
        self.add_errors: dict[int, Exception] = {}
        # Answer of add_product instead of the cart (for odd forms).
        self.add_answer: Any = None
        # Product ids Picnic does not know or refuses.
        self.unknown: set[str] = set()
        # How Picnic answers for those: "error" (error object) or "unchanged".
        self.unknown_answer = "error"
        self.delay = 0.0
        self.add_delay = 0.0
        # If set, add_product waits for it (at most 5 s).
        self.hold: threading.Event | None = None
        # Answer or error of get_cart instead of the cart.
        self.cart_answer: Any = None
        self.cart_error: Exception | None = None
        # Id in the cart for an id of the search (Picnic may use another one).
        self.cart_ids: dict[str, str] = {}
        # Further order lines of the cart as Picnic sends them (deposit, bundle).
        self.extra_lines: list[dict[str, Any]] = []
        self.active = 0
        self.most_active = 0
        self._lock = threading.Lock()

    def _enter(self, name: str) -> float:
        with self._lock:
            self.starts.append((name, time.monotonic()))
            self.active += 1
            self.most_active = max(self.most_active, self.active)
        return time.monotonic()

    def _leave(self, name: str, start: float) -> None:
        with self._lock:
            self.active -= 1
            self.calls.append((name, start, time.monotonic()))

    def _cart(self) -> Any:
        """The cart as the library returns it, with ids as Picnic keeps them."""
        payload = cart_payload(
            {self.cart_ids.get(pid, pid): count for pid, count in self.cart.items()}
        )
        payload["items"].extend(self.extra_lines)
        return cart_model(payload)

    def get_cart(self) -> Any:
        start = self._enter("get_cart")
        try:
            if self.delay:
                time.sleep(self.delay)
            if self.cart_error:
                raise self.cart_error
            if self.cart_answer is not None:
                return self.cart_answer
            return self._cart()
        finally:
            self._leave("get_cart", start)

    def search(self, term: str) -> Any:
        start = self._enter("search")
        try:
            self.searches.append(term)
            if self.delay:
                time.sleep(self.delay)
            if self.search_error:
                raise self.search_error
            return self.result
        finally:
            self._leave("search", start)

    def add_product(self, product_id: str, count: int = 1) -> Any:
        start = self._enter("add_product")
        try:
            self.added.append((product_id, count))
            if self.hold is not None:
                self.hold.wait(5)
            if self.add_delay:
                time.sleep(self.add_delay)
            if (error := self.add_errors.get(len(self.added))) is not None:
                raise error
            if self.add_answer is not None:
                return self.add_answer
            if product_id in self.unknown:
                if self.unknown_answer == "error":
                    return cart_model(error_object())
                return self._cart()
            self.cart[product_id] = self.cart.get(product_id, 0) + int(count)
            return self._cart()
        finally:
            self._leave("add_product", start)

    def remove_product(self, product_id: str, count: int = 1) -> Any:
        start = self._enter("remove_product")
        try:
            self.removed.append((product_id, count))
            if self.delay:
                time.sleep(self.delay)
            if self.remove_error:
                raise self.remove_error
            if self.remove_answer is not None:
                return self.remove_answer
            left = self.cart.get(product_id, 0) - int(count)
            if left > 0:
                self.cart[product_id] = left
            else:
                self.cart.pop(product_id, None)
            return self._cart()
        finally:
            self._leave("remove_product", start)


def mock_picnic_integration(hass: HomeAssistant) -> None:
    """Replace the Picnic integration of Home Assistant by an empty module.

    Its library is not installed in tests, and nothing of it may run.
    """
    mock_integration(
        hass,
        MockModule("picnic", async_unload_entry=AsyncMock(return_value=True)),
    )


class FakePicnic:
    """A loaded Picnic config entry with client and action."""

    def __init__(self, hass: HomeAssistant, client: Any) -> None:
        mock_picnic_integration(hass)
        self.hass = hass
        self.client = client
        self.entry = MockConfigEntry(domain="picnic", state=ConfigEntryState.LOADED)
        self.entry.add_to_hass(hass)
        self.refresh = AsyncMock()
        self.entry.runtime_data = SimpleNamespace(
            picnic_api_client=client, async_request_refresh=self.refresh
        )
        self.action_calls: list[dict[str, Any]] = []

        async def add_product(call: ServiceCall) -> None:
            # Like the real action: the answer of the library is thrown away.
            self.action_calls.append(dict(call.data))
            await hass.async_add_executor_job(
                self.entry.runtime_data.picnic_api_client.add_product,
                call.data["product_id"],
                call.data.get("amount", 1),
            )

        hass.services.async_register("picnic", "add_product", add_product)

    @property
    def added(self) -> list[tuple[str, int]]:
        """Every call of ``add_product`` of the client (product id, pieces)."""
        return self.client.added

    @property
    def times(self) -> list[float]:
        """Start of every call of ``add_product`` of the client."""
        return [start for name, start in self.client.starts if name == "add_product"]


@pytest.fixture(autouse=True)
def no_pause() -> Iterator[None]:
    """No pause between Picnic calls in tests (one test sets it again)."""
    with patch.object(picnic, "CALL_PAUSE", 0):
        yield


@pytest.fixture
def fake_picnic(hass: HomeAssistant) -> FakePicnic:
    return FakePicnic(hass, FakeClient())


async def wait_idle(client: FakeClient) -> None:
    """Wait until no blocking call of the fake client runs any more."""
    for _ in range(200):
        if client.active == 0:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("a call of the fake client still runs")


# ----- status ---------------------------------------------------------------


async def test_status_without_picnic(hass: HomeAssistant) -> None:
    assert picnic.async_status(hass) == {
        "available": False,
        "search": False,
        "reason": picnic.REASON_NOT_SET_UP,
        "reason_code": "not_set_up",
    }
    with pytest.raises(picnic.PicnicUnavailable):
        await picnic.async_search(hass, "Milch")
    with pytest.raises(picnic.PicnicUnavailable):
        await picnic.async_add(hass, "s1", 1, {})
    with pytest.raises(picnic.PicnicUnavailable):
        await picnic.async_remove(hass, "s1", 1)
    await picnic.async_refresh(hass)  # nothing to refresh, no error


async def test_status_entry_not_loaded(hass: HomeAssistant) -> None:
    mock_picnic_integration(hass)
    MockConfigEntry(domain="picnic", state=ConfigEntryState.SETUP_ERROR).add_to_hass(
        hass
    )
    assert picnic.async_status(hass)["reason"] == picnic.REASON_NOT_LOADED
    with pytest.raises(picnic.PicnicUnavailable, match="not loaded"):
        await picnic.async_search(hass, "Milch")


async def test_status_without_add_product(hass: HomeAssistant) -> None:
    """Without ``add_product`` on the client nothing can go into the cart."""
    mock_picnic_integration(hass)
    entry = MockConfigEntry(domain="picnic", state=ConfigEntryState.LOADED)
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(picnic_api_client=SimpleNamespace())
    assert picnic.async_status(hass) == {
        "available": False,
        "search": False,
        "reason": picnic.REASON_NO_CLIENT,
        "reason_code": "unknown_form",
    }


async def test_status_does_not_need_the_action(hass: HomeAssistant) -> None:
    """EatFresh uses the client, not the action (the action answers nothing)."""
    mock_picnic_integration(hass)
    entry = MockConfigEntry(domain="picnic", state=ConfigEntryState.LOADED)
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(picnic_api_client=FakeClient())
    assert picnic.async_status(hass)["available"] is True


async def test_status_ready(hass: HomeAssistant, fake_picnic: FakePicnic) -> None:
    assert picnic.async_status(hass) == {
        "available": True,
        "search": True,
        "reason": None,
        "reason_code": None,
    }


async def test_status_without_client(
    hass: HomeAssistant, fake_picnic: FakePicnic
) -> None:
    """A changed runtime_data turns Picnic off; nothing is called."""
    fake_picnic.entry.runtime_data = object()
    assert picnic.async_status(hass) == {
        "available": False,
        "search": False,
        "reason": picnic.REASON_NO_CLIENT,
        "reason_code": "unknown_form",
    }
    with pytest.raises(picnic.PicnicUnavailable):
        await picnic.async_search(hass, "Milch")
    with pytest.raises(picnic.PicnicUnavailable):
        await picnic.async_add(hass, "s1", 2, {})
    with pytest.raises(picnic.PicnicUnavailable):
        await picnic.async_remove(hass, "s1", 2)
    assert fake_picnic.added == []
    assert fake_picnic.action_calls == []


async def test_status_client_without_search(
    hass: HomeAssistant, fake_picnic: FakePicnic
) -> None:
    client = FakeClient()
    client.search = "no"  # type: ignore[assignment,method-assign]
    fake_picnic.entry.runtime_data.picnic_api_client = client
    assert picnic.async_status(hass)["reason"] == picnic.REASON_NO_SEARCH
    assert picnic.async_status(hass)["available"] is True
    with pytest.raises(picnic.PicnicUnavailable, match="no product search"):
        await picnic.async_search(hass, "Milch")


# ----- search ---------------------------------------------------------------


async def test_search_new_form(hass: HomeAssistant, fake_picnic: FakePicnic) -> None:
    hits = await picnic.async_search(hass, "Kartoffeln")
    assert hits == [
        {
            "id": "s1000001",
            "name": "Kartoffeln festkochend",
            "unit_quantity": "2kg",
            "price": 249,
        },
        {"id": "s1000002", "name": "Milch 3,5 %", "unit_quantity": "1L", "price": 119},
    ]
    assert fake_picnic.client.searches == ["Kartoffeln"]


async def test_search_old_form(hass: HomeAssistant, fake_picnic: FakePicnic) -> None:
    fake_picnic.client.result = old_result(
        {"type": "SINGLE_ARTICLE", **POTATOES}, {"type": "SINGLE_ARTICLE", **MILK}
    )
    hits = await picnic.async_search(hass, "Kartoffeln")
    assert [hit["id"] for hit in hits] == ["s1000001", "s1000002"]
    assert hits[1]["price"] == 119


async def test_search_is_tolerant(hass: HomeAssistant, fake_picnic: FakePicnic) -> None:
    fake_picnic.client.result = new_result(
        {"id": "s1", "name": "  Gut   und günstig  "},  # no price, no pack
        {"id": "s2", "name": None},  # no name
        {"id": None, "name": "No id"},
        {"id": "s1", "name": "Repeated id"},
        {"id": 12345, "name": "Number id", "display_price": 1.5},
        {"id": "s3", "name": "Bool price", "display_price": True, "unit_quantity": 3},
        {"id": "s4", "name": "x" * 500, "display_price": -5},
    )
    hits = await picnic.async_search(hass, "Test")
    assert hits[0] == {
        "id": "s1",
        "name": "Gut und günstig",
        "unit_quantity": None,
        "price": None,
    }
    assert [hit["id"] for hit in hits] == ["s1", "12345", "s3", "s4"]
    assert hits[1]["price"] is None
    assert hits[2]["price"] is None and hits[2]["unit_quantity"] == "3"
    assert len(hits[3]["name"]) == picnic.MAX_NAME_LENGTH
    assert hits[3]["price"] is None


async def test_search_dict_form_and_limit(
    hass: HomeAssistant, fake_picnic: FakePicnic
) -> None:
    fake_picnic.client.result = {
        "items": [{"id": f"s{i}", "name": f"Product {i}"} for i in range(30)]
    }
    assert len(await picnic.async_search(hass, "Test")) == 8
    assert len(await picnic.async_search(hass, "Test", 100)) == picnic.MAX_HITS


async def test_search_unknown_form(hass: HomeAssistant, fake_picnic: FakePicnic) -> None:
    fake_picnic.client.result = "unexpected"
    with pytest.raises(picnic.PicnicError, match="error"):
        await picnic.async_search(hass, "Test")


async def test_search_error_object(hass: HomeAssistant, fake_picnic: FakePicnic) -> None:
    """An error object in the answer is no empty result."""
    fake_picnic.client.result = SimpleNamespace(
        items=[], raw={"error": {"code": "AUTH_ERROR"}}
    )
    with pytest.raises(picnic.PicnicStop, match="login"):
        await picnic.async_search(hass, "Test")
    fake_picnic.client.result = {"error": {"code": "SOMETHING"}}
    with pytest.raises(picnic.PicnicError):
        await picnic.async_search(hass, "Test")


async def test_search_timeout(hass: HomeAssistant, fake_picnic: FakePicnic) -> None:
    fake_picnic.client.delay = 0.3
    with (
        patch.object(picnic, "CALL_TIMEOUT", 0.05),
        pytest.raises(picnic.PicnicTimeout, match="in time"),
    ):
        await picnic.async_search(hass, "Test")


@pytest.mark.parametrize(
    ("error", "kind", "match"),
    [
        (PicnicAuthError("expired"), picnic.PicnicStop, "login"),
        (read_error(), picnic.PicnicError, "error"),
        (connection_error(), picnic.PicnicError, "error"),
        (ValueError("bad json"), picnic.PicnicError, "error"),
    ],
)
async def test_search_errors(
    hass: HomeAssistant,
    fake_picnic: FakePicnic,
    error: Exception,
    kind: type[Exception],
    match: str,
) -> None:
    """Errors come as the library raises them: no status code to read."""
    fake_picnic.client.search_error = error
    with pytest.raises(kind, match=match):
        await picnic.async_search(hass, "Test")
    # No second try by itself.
    assert fake_picnic.client.searches == ["Test"]


async def test_search_error_object_is_no_empty_result(
    hass: HomeAssistant, fake_picnic: FakePicnic
) -> None:
    """An error answer in JSON comes back as a result without items."""
    fake_picnic.client.result = SimpleNamespace(items=[], raw=error_object("BLOCKED"))
    with pytest.raises(picnic.PicnicError):
        await picnic.async_search(hass, "Test")
    assert fake_picnic.client.searches == ["Test"]


async def test_second_search_is_refused(
    hass: HomeAssistant, fake_picnic: FakePicnic
) -> None:
    """A new search is refused while one runs; no queue of searches."""
    fake_picnic.client.delay = 0.2
    first = hass.async_create_task(picnic.async_search(hass, "Milch"))
    await asyncio.sleep(0.05)
    with pytest.raises(picnic.PicnicError) as err:
        await picnic.async_search(hass, "Butter")
    assert err.value.code == "search_running"
    assert len(await first) == 2
    assert fake_picnic.client.searches == ["Milch"]
    # After the first one a new search is fine again.
    fake_picnic.client.delay = 0
    await picnic.async_search(hass, "Butter")
    assert fake_picnic.client.searches == ["Milch", "Butter"]


async def test_auth_error_as_cause(hass: HomeAssistant, fake_picnic: FakePicnic) -> None:
    """An auth error wrapped by Home Assistant is still found."""
    try:
        raise PicnicAuthError("expired")
    except PicnicAuthError as cause:
        wrapped = RuntimeError("wrapped")
        wrapped.__cause__ = cause
    fake_picnic.client.search_error = wrapped
    with pytest.raises(picnic.PicnicStop):
        await picnic.async_search(hass, "Test")


def test_the_pause_is_at_least_one_second() -> None:
    """The pause written in picnic.py (the fixtures set it to 0 in tests)."""
    assert DEFAULT_CALL_PAUSE >= 1.0


async def test_calls_have_a_pause(hass: HomeAssistant, fake_picnic: FakePicnic) -> None:
    """One call at a time, and the pause runs from the end of the last call."""
    fake_picnic.client.add_delay = 0.05
    with patch.object(picnic, "CALL_PAUSE", 0.1):
        await asyncio.gather(
            picnic.async_add(hass, "s1", 1, {}),
            picnic.async_add(hass, "s2", 1, {}),
            picnic.async_search(hass, "Milch"),
        )
    calls = fake_picnic.client.calls
    assert len(calls) == 3
    for before, after in zip(calls, calls[1:], strict=False):
        assert after[1] - before[2] >= 0.09
    assert fake_picnic.client.most_active == 1


async def test_hung_call_blocks_the_next(
    hass: HomeAssistant, fake_picnic: FakePicnic
) -> None:
    """After a timeout the next call waits until the hung call really ended."""
    fake_picnic.client.add_delay = 0.3
    with (
        patch.object(picnic, "CALL_TIMEOUT", 0.05),
        pytest.raises(picnic.PicnicTimeout),
    ):
        await picnic.async_add(hass, "s1", 1, {})
    await picnic.async_search(hass, "Milch")
    (add, add_start, add_end), (search, search_start, _) = fake_picnic.client.calls
    assert (add, search) == ("add_product", "search")
    assert search_start >= add_end
    assert fake_picnic.client.most_active == 1


async def test_hung_call_makes_others_wait_not_forever(
    hass: HomeAssistant, fake_picnic: FakePicnic
) -> None:
    """A call waits for a hung call only a while, then gives up (busy)."""
    fake_picnic.client.add_delay = 0.4
    with (
        patch.object(picnic, "CALL_TIMEOUT", 0.05),
        patch.object(picnic, "GATE_WAIT", 0.1),
    ):
        with pytest.raises(picnic.PicnicTimeout):
            await picnic.async_add(hass, "s1", 1, {})
        with pytest.raises(picnic.PicnicError) as err:
            await picnic.async_add(hass, "s2", 1, {})
    assert err.value.code == "call_running"
    assert err.value.nothing_done is True
    assert fake_picnic.added == [("s1", 1)]
    await wait_idle(fake_picnic.client)


# ----- cart -----------------------------------------------------------------


async def test_add_uses_the_client(hass: HomeAssistant, fake_picnic: FakePicnic) -> None:
    """The client answers with the cart; the action would throw it away."""
    cart = await picnic.async_add(hass, "s1000001", 3, {})
    assert cart == {"s1000001": 3}
    assert fake_picnic.added == [("s1000001", 3)]
    assert fake_picnic.action_calls == []
    # With the cart of the last answer the next one is checked against it.
    cart = await picnic.async_add(hass, "s1000001", 2, cart)
    assert cart == {"s1000001": 5}


@pytest.mark.parametrize("answer", ["error", "unchanged"])
async def test_add_unknown_product_is_not_in_the_cart(
    hass: HomeAssistant, fake_picnic: FakePicnic, answer: str
) -> None:
    """Picnic refuses a product without an error: it is not in the cart."""
    fake_picnic.client.unknown = {"s9"}
    fake_picnic.client.unknown_answer = answer
    with pytest.raises(picnic.PicnicNotAdded) as err:
        await picnic.async_add(hass, "s9", 1, {})
    assert err.value.code == "not_added"
    assert err.value.nothing_done is True


async def test_add_unchanged_cart_is_not_added(
    hass: HomeAssistant, fake_picnic: FakePicnic
) -> None:
    """With the cart of the last answer an unchanged cart means: not added."""
    fake_picnic.client.cart = {"s9": 2}
    fake_picnic.client.unknown = {"s9"}
    fake_picnic.client.unknown_answer = "unchanged"
    with pytest.raises(picnic.PicnicNotAdded):
        await picnic.async_add(hass, "s9", 1, {"s9": 2})


async def test_add_product_in_the_cart_before(
    hass: HomeAssistant, fake_picnic: FakePicnic
) -> None:
    """With the cart before, pieces already there are counted in."""
    fake_picnic.client.cart = {"s1": 1}
    assert await picnic.async_add(hass, "s1", 1, {"s1": 1}) == {"s1": 2}
    # Another number than expected is only "maybe".
    with pytest.raises(picnic.PicnicUncertain) as err:
        await picnic.async_add(hass, "s1", 1, {"s1": 5})
    assert err.value.code == "maybe_sent"
    assert err.value.nothing_done is False
    # Pieces of the product before unclear: nothing is sent.
    calls = len(fake_picnic.added)
    with pytest.raises(picnic.PicnicCartUnreadable) as err:
        await picnic.async_add(hass, "s1", 1, {"s1": None})
    assert err.value.nothing_done is True
    assert len(fake_picnic.added) == calls


@pytest.mark.parametrize(
    "answer",
    [
        None,
        "garbage",
        SimpleNamespace(raw=None),
        cart_model({"type": "ORDER"}),
        cart_model({"items": [{"type": "ORDER_LINE", "items": "x"}]}),
        cart_model(
            {"items": [{"items": [{"id": "s1", "decorators": []}]}]}
        ),
        cart_model(
            {
                "items": [
                    {"items": [{"id": "s1", "decorators": [{"type": "QUANTITY", "quantity": "2"}]}]}
                ]
            }
        ),
    ],
)
async def test_add_unreadable_answer_is_maybe(
    hass: HomeAssistant, fake_picnic: FakePicnic, answer: Any
) -> None:
    """An answer in an unknown form never counts as "in the cart"."""
    fake_picnic.client.add_answer = answer if answer is not None else SimpleNamespace()
    with pytest.raises(picnic.PicnicUncertain):
        await picnic.async_add(hass, "s1", 1, {})


async def test_add_reads_lines_and_quantities(
    hass: HomeAssistant, fake_picnic: FakePicnic
) -> None:
    """Pieces of one product in two lines count together; a dict is fine too."""
    article = {"id": "s1", "decorators": [{"type": "QUANTITY", "quantity": 1}]}
    other = {"id": "s2", "decorators": [{"type": "QUANTITY", "quantity": 4}]}
    fake_picnic.client.add_answer = {
        "items": [{"items": [article, other]}, {"items": [dict(article)]}]
    }
    assert await picnic.async_add(hass, "s1", 2, {}) == {"s1": 2, "s2": 4}


@pytest.mark.parametrize(
    ("error", "kind", "nothing_done"),
    [
        (PicnicAuthError("expired"), picnic.PicnicStop, True),
        (read_error(), picnic.PicnicError, False),
        (connection_error(), picnic.PicnicError, False),
        (RuntimeError("odd"), picnic.PicnicError, False),
    ],
)
async def test_add_errors(
    hass: HomeAssistant,
    fake_picnic: FakePicnic,
    error: Exception,
    kind: type[picnic.PicnicError],
    nothing_done: bool,
) -> None:
    """Only a rejected login says for sure that nothing happened."""
    fake_picnic.client.add_errors = {1: error}
    with pytest.raises(kind) as err:
        await picnic.async_add(hass, "s1", 1, {})
    assert err.value.nothing_done is nothing_done
    assert fake_picnic.added == [("s1", 1)]


async def test_add_error_object(hass: HomeAssistant, fake_picnic: FakePicnic) -> None:
    fake_picnic.client.add_answer = cart_model(error_object("AUTH_ERROR"))
    with pytest.raises(picnic.PicnicStop):
        await picnic.async_add(hass, "s1", 1, {})
    fake_picnic.client.add_answer = cart_model(error_object("TOO_MANY_REQUESTS"))
    with pytest.raises(picnic.PicnicNotAdded):
        await picnic.async_add(hass, "s1", 1, {})


async def test_add_timeout(hass: HomeAssistant, fake_picnic: FakePicnic) -> None:
    fake_picnic.client.add_delay = 0.3
    with (
        patch.object(picnic, "CALL_TIMEOUT", 0.05),
        pytest.raises(picnic.PicnicTimeout) as err,
    ):
        await picnic.async_add(hass, "s1", 1, {})
    assert err.value.nothing_done is False
    await wait_idle(fake_picnic.client)


async def test_remove_uses_the_client(
    hass: HomeAssistant, fake_picnic: FakePicnic
) -> None:
    fake_picnic.client.cart = {"s1000001": 2}
    await picnic.async_remove(hass, "s1000001", 2)
    assert fake_picnic.client.removed == [("s1000001", 2)]
    assert fake_picnic.client.cart == {}

    fake_picnic.client.cart = {"s1000001": 9}
    fake_picnic.client.remove_error = read_error()
    with pytest.raises(picnic.PicnicError) as err:
        await picnic.async_remove(hass, "s1000001", 2)
    assert err.value.nothing_done is False

    fake_picnic.client.remove_error = None
    fake_picnic.client.remove_answer = cart_model(error_object("AUTH_INVALID_CRED"))
    with pytest.raises(picnic.PicnicStop):
        await picnic.async_remove(hass, "s1000001", 2)

    fake_picnic.client.remove_answer = cart_model(error_object())
    with pytest.raises(picnic.PicnicError) as err:
        await picnic.async_remove(hass, "s1000001", 2)
    assert err.value.nothing_done is True


async def test_refresh(hass: HomeAssistant, fake_picnic: FakePicnic) -> None:
    await picnic.async_refresh(hass)
    fake_picnic.refresh.assert_awaited_once()
    fake_picnic.refresh.side_effect = RuntimeError("down")
    await picnic.async_refresh(hass)  # errors are only logged
