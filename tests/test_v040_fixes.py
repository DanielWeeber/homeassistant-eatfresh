"""Fixes of the 0.4.0 assembly: manifest, message codes, timeouts."""

from __future__ import annotations

import asyncio
import threading
import json
from pathlib import Path
import re
from typing import Any
from unittest.mock import patch

from homeassistant.core import HomeAssistant
import pytest

from custom_components.eatfresh import picnic, runtime
from custom_components.eatfresh.const import DOMAIN, STORAGE_KEY
from custom_components.eatfresh.store import FavoritesStore

from .test_picnic import FakePicnic, PicnicAuthError, wait_idle
from .test_store_picnic import _save
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
COMPONENT = ROOT / "custom_components" / DOMAIN
I18N = ROOT / "frontend" / "src" / "i18n.ts"


def _codes() -> set[str]:
    """Return every code of a Picnic reason or message."""
    found = {
        value
        for name, value in vars(picnic).items()
        if name.startswith("CODE_") and isinstance(value, str)
    }
    found |= {
        value
        for name, value in vars(runtime).items()
        if name.startswith("CODE_PICNIC_") and isinstance(value, str)
    }
    return found


# ----- manifest -------------------------------------------------------------


def test_manifest_has_no_picnic_dependency() -> None:
    """No after_dependencies: Home Assistant would install the Picnic library.

    Home Assistant processes the requirements of every after_dependency when
    EatFresh loads (requirements.py, _async_process_integration). A failed
    install would stop EatFresh, even without a Picnic account. EatFresh finds
    Picnic at run time through its config entry instead.
    """
    manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))
    assert "after_dependencies" not in manifest
    assert "picnic" not in manifest.get("dependencies", [])
    assert manifest["requirements"] == []


async def test_finds_picnic_set_up_later(
    ws: WS, hass: HomeAssistant, fake_picnic: FakePicnic
) -> None:
    """Picnic loaded after EatFresh is found at run time."""
    msg = await ws.call("eatfresh/shopping")
    assert msg["result"]["picnic"]["available"] is True


# ----- codes ----------------------------------------------------------------


def test_every_code_is_translated_in_the_panel() -> None:
    """The panel has a German and an English text for every code."""
    text = I18N.read_text(encoding="utf-8")
    codes = _codes()
    assert {"auth", "timeout", "maybe_sent", "not_set_up", "busy"} <= codes
    for code in codes:
        assert len(re.findall(rf"^  picnic_code_{code}: ", text, re.MULTILINE)) == 2, code


def test_every_code_has_an_exception_text() -> None:
    for name in ("strings.json", "translations/en.json", "translations/de.json"):
        data = json.loads((COMPONENT / name).read_text(encoding="utf-8"))
        for code in _codes() - {"twice", "not_on_list", "already_sent", "maybe_sent", "not_tried"}:
            assert f"picnic_{code}" in data["exceptions"], (name, code)


async def test_failed_entries_carry_codes(ws: WS, fake_picnic: FakePicnic) -> None:
    fake_picnic.client.add_errors = {1: PicnicAuthError("expired")}
    msg = await ws.call(
        "eatfresh/picnic/send", items=send_items((101, "s1", 1), (102, "s2", 1))
    )
    assert [item["code"] for item in msg["result"]["failed"]] == ["auth", "not_tried"]


async def test_errors_carry_a_translation_key(
    hass: HomeAssistant, ws: WS, fake_picnic: FakePicnic
) -> None:
    fake_picnic.client.search_error = PicnicAuthError("expired")
    msg = await ws.call("eatfresh/picnic/search", query="Milch")
    assert msg["error"]["code"] == "picnic_error"
    assert msg["error"]["translation_key"] == "picnic_auth"

    msg = await ws.call("eatfresh/picnic/undo", item_id=101)
    assert msg["error"]["code"] == "not_found"
    assert msg["error"]["translation_key"] == "picnic_nothing_to_undo"

    data = ws.entry.runtime_data  # type: ignore[attr-defined]
    hold = threading.Event()
    fake_picnic.client.hold = hold
    first = hass.async_create_task(data.async_picnic_send(hass, send_items((101, "s1", 1))))
    for _ in range(100):
        if fake_picnic.added:
            break
        await asyncio.sleep(0.01)
    msg = await ws.call("eatfresh/picnic/send", items=send_items((102, "s2", 1)))
    assert msg["error"]["translation_key"] == "picnic_busy"
    hold.set()
    await first


async def test_unavailable_carries_the_reason_code(ws: WS) -> None:
    msg = await ws.call("eatfresh/picnic/search", query="Milch")
    assert msg["error"]["code"] == "picnic_unavailable"
    assert msg["error"]["translation_key"] == "picnic_not_set_up"


# ----- timeouts -------------------------------------------------------------


async def test_timeout_is_never_sent_twice_by_itself(
    ws: WS, fake_picnic: FakePicnic
) -> None:
    """After a timeout the entry is "maybe sent" and not sent again."""
    fake_picnic.client.add_delay = 0.3
    with patch.object(picnic, "CALL_TIMEOUT", 0.05):
        msg = await ws.call("eatfresh/picnic/send", items=send_items((101, "s1", 3)))
    assert msg["result"]["failed"][0]["code"] == "maybe_sent"
    assert len(fake_picnic.times) == 1
    # No refresh while Picnic does not answer.
    fake_picnic.refresh.assert_not_awaited()

    msg = await ws.call("eatfresh/shopping")
    item = msg["result"]["items"][0]
    assert item["sent_at"] is not None
    assert item["sent_uncertain"] is True
    assert item["amount"] == 3

    await wait_idle(fake_picnic.client)
    fake_picnic.client.add_delay = 0
    msg = await ws.call("eatfresh/picnic/send", items=send_items((101, "s1", 3)))
    assert msg["result"]["failed"][0]["code"] == "already_sent"
    assert len(fake_picnic.times) == 1

    # Not in the cart after all: forget only the mark, no call to Picnic.
    msg = await ws.call("eatfresh/picnic/undo", item_id=101, remove=False)
    assert msg["success"], msg
    assert fake_picnic.client.removed == []
    msg = await ws.call("eatfresh/shopping")
    assert msg["result"]["items"][0]["sent_at"] is None

    # The hung call did put it in (the fake finished it): now the cart has 3,
    # and a new try puts 3 more in on purpose, as the user asked. The run
    # reads the cart first, so the 3 there before are counted in.
    msg = await ws.call("eatfresh/picnic/send", items=send_items((101, "s1", 3)))
    assert msg["result"]["sent"] == sent_items((101, "s1", 3))
    assert fake_picnic.client.cart == {"s1": 6}


async def test_sent_amount_is_shown(ws: WS, fake_picnic: FakePicnic) -> None:
    """A sent entry shows the quantity in the cart, not a newer choice."""
    product = {"id": "s1", "name": "Kartoffeln", "unit_quantity": "1kg", "price": 249}
    await ws.call("eatfresh/picnic/map", name="Kartoffeln", product=product, amount=2)
    await ws.call("eatfresh/picnic/send", items=send_items((101, "s1", 2)))
    await ws.call("eatfresh/picnic/map", name="Kartoffeln", product=product, amount=5)
    msg = await ws.call("eatfresh/shopping")
    item = msg["result"]["items"][0]
    assert item["amount"] == 2
    assert item["sent_uncertain"] is False


async def test_store_keeps_the_uncertain_mark(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    store.async_set_picnic_sent(101, "s1", 2, uncertain=True)
    store.async_set_picnic_sent(102, "s2", 1)
    await _save(hass)
    again = FavoritesStore(hass)
    await again.async_load()
    assert again.picnic_sent(101)["uncertain"] is True  # type: ignore[index]
    assert "uncertain" not in again.picnic_sent(102)  # type: ignore[operator]


@pytest.mark.parametrize("value", ["yes", 1, None])
async def test_store_ignores_odd_uncertain(
    hass: HomeAssistant, hass_storage: dict[str, Any], value: Any
) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    store.async_set_picnic_sent(101, "s1", 2)
    await _save(hass)
    stored = hass_storage[STORAGE_KEY]
    stored["data"]["picnic_sent"]["101"]["uncertain"] = value
    again = FavoritesStore(hass)
    await again.async_load()
    assert "uncertain" not in again.picnic_sent(101)  # type: ignore[operator]
