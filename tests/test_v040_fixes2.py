"""Second fixes of 0.4.0: what EatFresh knows about the Picnic cart.

A run reads the cart once at its start (``get_cart``), so the pieces before
are known for every product. "Surely not in the cart" needs proof: an error
object or a cart unchanged in every number. "Undo" compares the cart before
and after taking out.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
import pytest

from custom_components.eatfresh import picnic

from .test_picnic import (
    FakePicnic,
    PicnicAuthError,
    cart_model,
    cart_payload,
    error_object,
    read_error,
    wait_idle,
)
from .test_websocket_api import WS
from .test_websocket_picnic import (  # noqa: F401  (fixtures)
    fake_picnic,
    no_pause,
    send_items,
    sent_items,
    shopping_list,
    ws,
)

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "frontend" / "src" / "i18n.ts"

# An order line of the cart without the decorator QUANTITY (deposit, bundle).
DEPOSIT_LINE = {
    "type": "ORDER_LINE",
    "id": "line-deposit",
    "items": [{"type": "ORDER_ARTICLE", "id": "deposit-1", "decorators": []}],
}


def ops(fake: FakePicnic) -> list[str]:
    """Names of the calls to the Picnic client, in order."""
    return [name for name, _start in fake.client.starts]


# ----- 1: the cart is read once at the start of a run -----------------------


async def test_run_reads_the_cart_once_at_the_start(
    ws: WS, fake_picnic: FakePicnic
) -> None:
    msg = await ws.call(
        "eatfresh/picnic/send",
        items=send_items((101, "s1", 1), (102, "s2", 2), (103, "s3", 1)),
    )
    assert len(msg["result"]["sent"]) == 3
    assert ops(fake_picnic) == ["get_cart", "add_product", "add_product", "add_product"]


async def test_nothing_to_send_reads_nothing(ws: WS, fake_picnic: FakePicnic) -> None:
    """Entries off the list are not sent: no call to Picnic at all."""
    msg = await ws.call("eatfresh/picnic/send", items=send_items((999, "s1", 1)))
    assert msg["result"]["failed"][0]["code"] == "not_on_list"
    assert ops(fake_picnic) == []


async def test_product_already_in_the_cart_is_sent(
    ws: WS, fake_picnic: FakePicnic
) -> None:
    """With the cart read first, a product in it already is a plain success."""
    fake_picnic.client.cart = {"s1": 1}
    msg = await ws.call(
        "eatfresh/picnic/send", items=send_items((101, "s1", 2), (102, "s2", 1))
    )
    assert msg["result"]["sent"] == sent_items((101, "s1", 2), (102, "s2", 1))
    assert msg["result"]["failed"] == []
    assert fake_picnic.client.cart == {"s1": 3, "s2": 1}
    # Undo takes out only the pieces EatFresh put in.
    msg = await ws.call("eatfresh/picnic/undo", item_id=101)
    assert msg["success"], msg
    assert fake_picnic.client.removed == [("s1", 2)]
    assert fake_picnic.client.cart == {"s1": 1, "s2": 1}


async def test_silent_refusal_of_a_product_in_the_cart(
    ws: WS, fake_picnic: FakePicnic
) -> None:
    """Already 1 in the cart, Picnic adds nothing: not "in the cart"."""
    fake_picnic.client.cart = {"s1": 1}
    fake_picnic.client.unknown = {"s1"}
    fake_picnic.client.unknown_answer = "unchanged"
    msg = await ws.call(
        "eatfresh/picnic/send", items=send_items((101, "s1", 1), (102, "s2", 1))
    )
    assert msg["result"]["sent"] == []
    assert [(f["item_id"], f["code"]) for f in msg["result"]["failed"]] == [
        (101, "not_added"),
        (102, "not_tried"),
    ]
    assert fake_picnic.client.cart == {"s1": 1}
    data = ws.entry.runtime_data  # type: ignore[attr-defined]
    assert data.store.picnic_sent(101) is None
    # Nothing to undo: the piece put in by hand stays.
    msg = await ws.call("eatfresh/picnic/undo", item_id=101)
    assert msg["error"]["translation_key"] == "picnic_nothing_to_undo"
    assert fake_picnic.client.removed == []


@pytest.mark.parametrize(
    ("setup", "key"),
    [
        ({"cart_error": read_error()}, "picnic_cart_unreadable"),
        ({"cart_error": RuntimeError("odd")}, "picnic_cart_unreadable"),
        ({"cart_answer": cart_model(error_object())}, "picnic_cart_unreadable"),
        ({"cart_answer": cart_model({"type": "ORDER"})}, "picnic_cart_unreadable"),
        ({"cart_answer": "garbage"}, "picnic_cart_unreadable"),
        ({"cart_error": PicnicAuthError("expired")}, "picnic_auth"),
        ({"cart_answer": cart_model(error_object("AUTH_ERROR"))}, "picnic_auth"),
    ],
)
async def test_run_does_not_start_without_the_cart(
    ws: WS, fake_picnic: FakePicnic, setup: dict[str, Any], key: str
) -> None:
    for name, value in setup.items():
        setattr(fake_picnic.client, name, value)
    msg = await ws.call(
        "eatfresh/picnic/send", items=send_items((101, "s1", 1), (102, "s2", 1))
    )
    assert msg["error"]["code"] == "picnic_error"
    assert msg["error"]["translation_key"] == key
    assert ops(fake_picnic) == ["get_cart"]
    data = ws.entry.runtime_data  # type: ignore[attr-defined]
    assert data.store.picnic_sent(101) is None
    assert data.store.picnic_sent(102) is None
    fake_picnic.refresh.assert_not_awaited()


async def test_run_does_not_start_after_a_timeout_of_the_read(
    ws: WS, fake_picnic: FakePicnic
) -> None:
    fake_picnic.client.delay = 0.3
    with patch.object(picnic, "CALL_TIMEOUT", 0.05):
        msg = await ws.call("eatfresh/picnic/send", items=send_items((101, "s1", 1)))
    assert msg["error"]["translation_key"] == "picnic_cart_unreadable"
    assert ops(fake_picnic) == ["get_cart"]
    await wait_idle(fake_picnic.client)


# ----- 2: "surely not in the cart" only with proof --------------------------


async def test_other_id_in_the_cart_is_maybe(ws: WS, fake_picnic: FakePicnic) -> None:
    """The cart changed but shows another id: maybe in the cart, stop."""
    fake_picnic.client.cart_ids = {"s1": "a1"}
    msg = await ws.call(
        "eatfresh/picnic/send", items=send_items((101, "s1", 1), (102, "s2", 1))
    )
    assert msg["result"]["sent"] == []
    assert [(f["item_id"], f["code"]) for f in msg["result"]["failed"]] == [
        (101, "maybe_sent"),
        (102, "not_tried"),
    ]
    data = ws.entry.runtime_data  # type: ignore[attr-defined]
    assert data.store.picnic_sent(101)["uncertain"] is True
    # Sending again does not put it in twice.
    msg = await ws.call("eatfresh/picnic/send", items=send_items((101, "s1", 1)))
    assert msg["result"]["failed"][0]["code"] == "already_sent"
    assert fake_picnic.added == [("s1", 1)]


async def test_add_needs_proof_for_not_added(
    hass: HomeAssistant, fake_picnic: FakePicnic
) -> None:
    client = fake_picnic.client
    # Changed cart without the product: maybe.
    client.cart_ids = {"s1": "a1"}
    with pytest.raises(picnic.PicnicUncertain):
        await picnic.async_add(hass, "s1", 1, {})
    # A cart that became empty without an error object: maybe as well.
    client.add_answer = cart_model(cart_payload({}))
    with pytest.raises(picnic.PicnicUncertain):
        await picnic.async_add(hass, "s2", 1, {"s3": 1})
    # Unchanged in every number: surely not added.
    client.add_answer = cart_model(cart_payload({"s3": 1}))
    with pytest.raises(picnic.PicnicNotAdded) as err:
        await picnic.async_add(hass, "s2", 1, {"s3": 1})
    assert err.value.nothing_done is True
    # An error object: surely not added.
    client.add_answer = cart_model(error_object())
    with pytest.raises(picnic.PicnicNotAdded):
        await picnic.async_add(hass, "s2", 1, {"s3": 1})


async def test_line_without_pieces_does_not_block(
    ws: WS, fake_picnic: FakePicnic
) -> None:
    """A deposit line without QUANTITY leaves the other products readable."""
    fake_picnic.client.extra_lines = [DEPOSIT_LINE]
    msg = await ws.call(
        "eatfresh/picnic/send", items=send_items((101, "s1", 1), (102, "s2", 1))
    )
    assert len(msg["result"]["sent"]) == 2


async def test_product_without_pieces_is_not_sent(
    ws: WS, fake_picnic: FakePicnic
) -> None:
    """The product itself is in a line without pieces: nothing is sent."""
    line = {
        "type": "ORDER_LINE",
        "id": "line-bundle",
        "items": [{"type": "ORDER_ARTICLE", "id": "s1", "decorators": []}],
    }
    fake_picnic.client.extra_lines = [line]
    msg = await ws.call(
        "eatfresh/picnic/send", items=send_items((101, "s1", 1), (102, "s2", 1))
    )
    assert [(f["item_id"], f["code"]) for f in msg["result"]["failed"]] == [
        (101, "cart_unreadable"),
        (102, "not_tried"),
    ]
    assert fake_picnic.added == []
    data = ws.entry.runtime_data  # type: ignore[attr-defined]
    assert data.store.picnic_sent(101) is None


def test_cart_counts_marks_unclear_products() -> None:
    payload = cart_payload({"s1": 2})
    payload["items"].append(DEPOSIT_LINE)
    assert picnic.cart_counts(cart_model(payload)) == {"s1": 2, "deposit-1": None}


# ----- 3: a hung call says what helps ---------------------------------------


def test_call_running_says_what_helps() -> None:
    assert "restart Home Assistant" in picnic.MSG_CALL_RUNNING
    text = I18N.read_text(encoding="utf-8")
    assert "Hilft das nicht, Home Assistant neu starten." in text
    assert "If that does not help, restart Home Assistant." in text


# ----- 4: undo compares the cart before and after ---------------------------


async def test_undo_reads_the_cart_and_checks_the_answer(
    ws: WS, fake_picnic: FakePicnic
) -> None:
    await ws.call("eatfresh/picnic/send", items=send_items((101, "s1", 2)))
    fake_picnic.client.starts.clear()
    msg = await ws.call("eatfresh/picnic/undo", item_id=101)
    assert msg["success"], msg
    assert ops(fake_picnic) == ["get_cart", "remove_product"]


async def test_undo_that_took_nothing_out_is_maybe(
    ws: WS, fake_picnic: FakePicnic
) -> None:
    """Picnic answers without an error, but the pieces did not drop."""
    await ws.call("eatfresh/picnic/send", items=send_items((101, "s1", 2)))
    fake_picnic.client.remove_answer = cart_model(cart_payload({"s1": 2}))
    msg = await ws.call("eatfresh/picnic/undo", item_id=101)
    assert msg["error"]["translation_key"] == "picnic_maybe_sent"
    data = ws.entry.runtime_data  # type: ignore[attr-defined]
    assert data.store.picnic_sent(101)["uncertain"] is True
    # Never taken out a second time.
    fake_picnic.client.remove_answer = None
    msg = await ws.call("eatfresh/picnic/undo", item_id=101)
    assert msg["error"]["translation_key"] == "picnic_maybe_no_undo"
    assert fake_picnic.client.removed == [("s1", 2)]


async def test_undo_with_fewer_pieces_in_the_cart_takes_nothing_out(
    ws: WS, fake_picnic: FakePicnic
) -> None:
    """Someone took pieces out in the app: EatFresh does not guess."""
    await ws.call("eatfresh/picnic/send", items=send_items((101, "s1", 2)))
    fake_picnic.client.cart = {"s1": 1}
    msg = await ws.call("eatfresh/picnic/undo", item_id=101)
    assert msg["error"]["translation_key"] == "picnic_cart_changed"
    assert fake_picnic.client.removed == []
    data = ws.entry.runtime_data  # type: ignore[attr-defined]
    assert data.store.picnic_sent(101)["uncertain"] is True


async def test_undo_without_the_cart_keeps_the_mark(
    ws: WS, fake_picnic: FakePicnic
) -> None:
    await ws.call("eatfresh/picnic/send", items=send_items((101, "s1", 2)))
    fake_picnic.client.cart_error = read_error()
    msg = await ws.call("eatfresh/picnic/undo", item_id=101)
    assert msg["error"]["translation_key"] == "picnic_cart_unreadable"
    assert fake_picnic.client.removed == []
    data = ws.entry.runtime_data  # type: ignore[attr-defined]
    assert "uncertain" not in data.store.picnic_sent(101)
