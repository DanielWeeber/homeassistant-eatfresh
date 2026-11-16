"""The only place where EatFresh touches the Picnic integration of Home Assistant.

EatFresh has no Picnic account and no Picnic library of its own. It uses the
Picnic integration the user set up, and nothing else in EatFresh imports or
reads it. The Picnic integration is not built to be used by others, so every
assumption is checked when it is used, and a missing or changed integration
only turns the Picnic features off (with a reason), never the rest of
EatFresh.

Where EatFresh hangs on the Picnic integration (read in Home Assistant
2026.11.0, ``homeassistant/components/picnic``, and python-picnic-api2
2.0.1; check these places first when Picnic changes):

1. Config entry of the domain ``picnic``, loaded
   (``hass.config_entries.async_loaded_entries("picnic")``).
2. ``entry.runtime_data`` is the ``PicnicUpdateCoordinator``
   (``__init__.py``, ``async_setup_entry``) and its attribute
   ``picnic_api_client`` is the ``PicnicAPI`` client (``coordinator.py``,
   ``__init__``; the integration's own action reads it the same way in
   ``services.py``, ``get_api_client``).
3. ``client.search(term)`` (library ``client.py``), blocking (``requests``,
   no timeout of its own). Since 2.0.0 it returns ``SearchResult`` with
   ``.items`` of ``SearchResultItem`` (``id``, ``name``, ``display_price``
   in cents, ``unit_quantity`` as text; ``models/search.py``). Before 2.0.0
   it returned a list of groups with dicts (``result[0]["items"][i]``).
   Both forms are read here.
4. ``client.get_cart()`` (library ``client.py``), blocking, read once at
   the start of a transfer and of an undo: the pieces before are known for
   every product. Same form as the answer of ``add_product`` (below).
5. ``client.add_product(product_id, count)`` (library ``client.py``),
   blocking. It returns the cart after the call (``Cart.from_api``, with the
   answer verbatim in ``raw``): order lines in ``items``, each with articles
   in ``items`` (``id``) and the pieces in the decorator of type
   ``QUANTITY``. The action ``picnic.add_product`` of the integration calls
   the same method but throws this answer away (``services.py``,
   ``handle_add_product``), so EatFresh calls the client: only the cart in
   the answer shows whether the product went in.
6. ``client.remove_product(product_id, count)`` (library ``client.py``),
   blocking, same answer. There is no action for removing.
7. ``PicnicAuthError``, ``Picnic2FARequired`` and ``Picnic2FAError`` (library
   ``session.py``) are recognised by their class names, so no Picnic code is
   imported.

How the library fails (read in ``client.py``, ``_get`` and ``_post``): it
never checks the HTTP status. An answer that is no JSON (an error page)
raises ``requests.JSONDecodeError`` without ``response``, a broken
connection a ``requests.ConnectionError``. A JSON error object raises
nothing: ``add_product`` and ``remove_product`` then return a cart without
items whose ``raw`` is the error object. Only the codes ``AUTH_ERROR`` and
``AUTH_INVALID_CRED`` raise ``PicnicAuthError``. So EatFresh reads every
answer itself and takes "no error" for nothing.
8. ``entry.runtime_data.async_request_refresh()`` (``DataUpdateCoordinator``
   of Home Assistant) is called once after a transfer, so the cart sensors
   and the to-do list show the change.

Calls to Picnic only happen on a user action, one after the other with a
short pause, each with a time limit. After a timeout the blocking call
goes on in the background; the next call waits until it really ended.
Nothing is ever tried a second time by itself. Nothing here orders or books
a delivery slot.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util.hass_dict import HassKey

from .errors import EatFreshError

_LOGGER = logging.getLogger(__name__)

PICNIC_DOMAIN = "picnic"
# Seconds a single call to Picnic may take.
CALL_TIMEOUT = 15
# Seconds between the end of one call to Picnic and the start of the next.
CALL_PAUSE = 1.0
# Seconds a call waits for the one before (also a hung one) before it gives up.
GATE_WAIT = 30
# Hits returned by a search at most.
MAX_HITS = 20
MAX_NAME_LENGTH = 200
MAX_ID_LENGTH = 64
MAX_UNIT_LENGTH = 64

MSG_NOT_SET_UP = "The Picnic integration is not set up in Home Assistant"
MSG_NOT_LOADED = "The Picnic integration is not loaded"
MSG_NO_CLIENT = "The Picnic integration has an unknown form"
MSG_NO_SEARCH = "The Picnic integration offers no product search"

# Reasons of ``async_status``: short English sentences for logs and tools.
# The panel shows the matching ``reason_code`` in the language of the user.
REASON_NOT_SET_UP = MSG_NOT_SET_UP
REASON_NOT_LOADED = MSG_NOT_LOADED
REASON_NO_CLIENT = MSG_NO_CLIENT
REASON_NO_SEARCH = MSG_NO_SEARCH

# Stable codes of reasons and errors. The panel translates them; the
# English message only stays as a fallback.
CODE_NOT_SET_UP = "not_set_up"
CODE_NOT_LOADED = "not_loaded"
CODE_NO_CLIENT = "unknown_form"
CODE_NO_SEARCH = "no_search"
CODE_NO_REMOVE = "no_remove"
CODE_AUTH = "auth"
CODE_TIMEOUT = "timeout"
CODE_ERROR = "error"
CODE_NOTHING_TO_UNDO = "nothing_to_undo"
CODE_NOT_ADDED = "not_added"
CODE_MAYBE_SENT = "maybe_sent"
CODE_SEARCH_RUNNING = "search_running"
CODE_CALL_RUNNING = "call_running"
CODE_CART_UNREADABLE = "cart_unreadable"
CODE_CART_CHANGED = "cart_changed"

_REASON_CODES = {
    REASON_NOT_SET_UP: CODE_NOT_SET_UP,
    REASON_NOT_LOADED: CODE_NOT_LOADED,
    REASON_NO_CLIENT: CODE_NO_CLIENT,
    REASON_NO_SEARCH: CODE_NO_SEARCH,
}

_AUTH_ERRORS = frozenset(
    {
        "PicnicAuthError",
        "Picnic2FARequired",
        "Picnic2FAError",
        "ConfigEntryAuthFailed",
    }
)
_AUTH_CODES = frozenset({"AUTH_ERROR", "AUTH_INVALID_CRED"})


class PicnicError(EatFreshError):
    """Picnic answered with an error or did not answer.

    ``code`` is a stable word the panel translates (see the ``CODE_*``
    constants); the message is English and only a fallback.

    ``nothing_done`` is True only when it is sure that the cart did not
    change (Picnic said no, or nothing was sent). Otherwise the call may
    have gone through.
    """

    default_code = CODE_ERROR
    nothing_done = False

    def __init__(self, message: str = "", code: str | None = None) -> None:
        super().__init__(message)
        self.code = code or self.default_code


class PicnicUnavailable(PicnicError):
    """The Picnic integration is missing, not loaded or not in the known form."""

    default_code = CODE_NOT_SET_UP
    nothing_done = True


class PicnicStop(PicnicError):
    """Picnic rejected the login. Stop all calls.

    The library raises it only after reading Picnic's answer with an
    authentication error, so the cart did not change.
    """

    default_code = CODE_AUTH
    nothing_done = True


class PicnicNothingToUndo(PicnicError):
    """There is no mark of an entry put into the cart."""

    default_code = CODE_NOTHING_TO_UNDO
    nothing_done = True


class PicnicBusy(PicnicError):
    """Another call to Picnic still runs; this one was not sent."""

    default_code = CODE_CALL_RUNNING
    nothing_done = True


class PicnicRefused(PicnicError):
    """Picnic answered with an error object: the cart did not change."""

    nothing_done = True


class PicnicNotAdded(PicnicRefused):
    """The cart in Picnic's answer does not have the product (more): not added."""

    default_code = CODE_NOT_ADDED


class PicnicUncertain(PicnicError):
    """Picnic's answer does not show clearly whether the product went in."""

    default_code = CODE_MAYBE_SENT


class PicnicCartUnreadable(PicnicError):
    """The cart could not be read (no answer, an error or an unknown form).

    Nothing was put in or taken out: the call that changes the cart was not
    sent.
    """

    default_code = CODE_CART_UNREADABLE
    nothing_done = True


class PicnicCartChanged(PicnicError):
    """The cart has fewer pieces of the product than EatFresh put in.

    Nothing was taken out: EatFresh does not guess whose pieces they are.
    """

    default_code = CODE_CART_CHANGED
    nothing_done = True


class PicnicTimeout(PicnicError):
    """Picnic did not answer in time. The call may still have gone through."""

    default_code = CODE_TIMEOUT


MSG_NO_REMOVE = (
    "Removing from the Picnic cart is not possible here; remove it in the Picnic app"
)
MSG_AUTH = "Picnic rejected the login; sign in again in the Picnic integration"
MSG_TIMEOUT = "Picnic did not answer in time"
MSG_ERROR = "Picnic answered with an error"
MSG_NOT_ADDED = "Picnic did not put the product into the cart"
MSG_UNCLEAR = (
    "Picnic's answer does not show whether the product is in the cart. "
    "Please check the Picnic app"
)
MSG_SEARCH_RUNNING = "A search at Picnic is running already"
MSG_CALL_RUNNING = (
    "Picnic is still busy with the call before; try again later. "
    "If that does not help, restart Home Assistant"
)
MSG_CART_UNREADABLE = (
    "EatFresh could not read the Picnic cart and changed nothing; try again later"
)
MSG_CART_CHANGED = (
    "The Picnic cart has fewer pieces than EatFresh put in; EatFresh took nothing "
    "out. Please check the Picnic app"
)
MSG_NOT_REMOVED = (
    "Picnic's answer does not show that the pieces are out of the cart. "
    "Please check the Picnic app"
)


@dataclass
class _Gate:
    """One call to Picnic at a time, with a pause between two calls.

    The lock stays taken until a blocking call really ended, also after a
    timeout. ``last`` is when the last call ended.
    """

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last: float = 0.0
    searching: bool = False


_GATE: HassKey[_Gate] = HassKey("eatfresh_picnic_gate")


# ----- finding the integration -------------------------------------------


def _loaded_entry(hass: HomeAssistant) -> Any | None:
    """Return the first loaded Picnic config entry or None."""
    entries = hass.config_entries.async_loaded_entries(PICNIC_DOMAIN)
    return entries[0] if entries else None


def _client(entry: Any) -> Any | None:
    """Return the Picnic client of a loaded entry, or None if it is not there."""
    coordinator = getattr(entry, "runtime_data", None)
    return getattr(coordinator, "picnic_api_client", None)


def _method(client: Any, name: str) -> Callable[..., Any] | None:
    method = getattr(client, name, None) if client is not None else None
    return method if callable(method) else None


def async_status(hass: HomeAssistant) -> dict[str, Any]:
    """Return whether Picnic can be used: ``{available, search, reason}``.

    Reads only Home Assistant's own state, never Picnic. ``available``
    means products can be put into the cart, ``search`` that products can
    be searched. ``reason`` says why when one of them is False.
    """
    entry = _loaded_entry(hass)
    if entry is None:
        reason = (
            REASON_NOT_LOADED
            if hass.config_entries.async_entries(PICNIC_DOMAIN)
            else REASON_NOT_SET_UP
        )
        return _status(False, False, reason)
    client = _client(entry)
    if _method(client, "add_product") is None or _method(client, "get_cart") is None:
        return _status(False, False, REASON_NO_CLIENT)
    if _method(client, "search") is None:
        return _status(True, False, REASON_NO_SEARCH)
    return _status(True, True, None)


def _status(available: bool, search: bool, reason: str | None) -> dict[str, Any]:
    """Build a status; ``reason_code`` is what the panel translates."""
    return {
        "available": available,
        "search": search,
        "reason": reason,
        "reason_code": _REASON_CODES.get(reason) if reason else None,
    }


def require_available(hass: HomeAssistant) -> Any:
    """Return the loaded Picnic entry or raise PicnicUnavailable."""
    status = async_status(hass)
    if not status["available"]:
        raise PicnicUnavailable(status["reason"], status["reason_code"])
    entry = _loaded_entry(hass)
    assert entry is not None
    return entry


def _require_client(hass: HomeAssistant) -> Any:
    """Return the client of the loaded Picnic entry or raise PicnicUnavailable."""
    return _client(require_available(hass))


# ----- errors ------------------------------------------------------------


def _causes(err: BaseException) -> Iterable[BaseException]:
    """Yield the error and its causes (at most 10)."""
    seen = 0
    current: BaseException | None = err
    while current is not None and seen < 10:
        yield current
        current = current.__cause__ or current.__context__
        seen += 1


def _translate(err: Exception) -> PicnicError:
    """Turn any error of a call into a PicnicError.

    The library never raises an error with a status code (see the top of
    this file), so only the rejected login is told apart. Every other error
    may come after Picnic did the call: ``nothing_done`` stays False.
    """
    for cause in _causes(err):
        if type(cause).__name__ in _AUTH_ERRORS:
            return PicnicStop(MSG_AUTH, CODE_AUTH)
    if isinstance(err, PicnicError):
        return err
    _LOGGER.debug("Picnic call failed: %r", err)
    return PicnicError(MSG_ERROR)


def _raw(answer: Any) -> Any:
    """Return the answer as Picnic sent it (``.raw`` of a model) if there is one."""
    raw = getattr(answer, "raw", None)
    return raw if raw is not None else answer


def _check_answer(answer: Any) -> None:
    """Raise if an answer (or its ``.raw``) carries a Picnic error object.

    Picnic said no, so the cart did not change (``PicnicRefused``).
    """
    raw = _raw(answer)
    if not isinstance(raw, Mapping):
        return
    error = raw.get("error")
    if not isinstance(error, Mapping):
        return
    code = error.get("code")
    if code in _AUTH_CODES:
        raise PicnicStop(MSG_AUTH, CODE_AUTH)
    _LOGGER.debug("Picnic answered with the error code %r", code)
    raise PicnicRefused(MSG_ERROR)


def _end_of(gate: _Gate) -> None:
    gate.last = time.monotonic()
    gate.lock.release()


async def _release_after(gate: _Gate, future: asyncio.Future[Any]) -> None:
    """Free the gate once a hung call really ended."""
    try:
        await future
    except BaseException:  # noqa: BLE001
        # Its result or error is of no use any more (it timed out).
        pass
    finally:
        _end_of(gate)


async def _call(hass: HomeAssistant, func: Callable[..., Any], *args: Any) -> Any:
    """Run one blocking call of the Picnic client in the executor.

    Alone, after the pause, with a time limit, never twice by itself. After a
    timeout the call goes on in the executor (``requests`` has no time limit
    of its own); the gate stays taken until it ended, so no second call runs
    at the same time. A call that cannot get the gate in ``GATE_WAIT``
    seconds is not sent (``PicnicBusy``).
    """
    gate = hass.data.setdefault(_GATE, _Gate())
    try:
        async with asyncio.timeout(GATE_WAIT):
            await gate.lock.acquire()
    except TimeoutError as err:
        raise PicnicBusy(MSG_CALL_RUNNING, CODE_CALL_RUNNING) from err
    hung = False
    try:
        wait = gate.last + CALL_PAUSE - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        future = hass.async_add_executor_job(func, *args)
        try:
            async with asyncio.timeout(CALL_TIMEOUT):
                return await asyncio.shield(future)
        except TimeoutError as err:
            hung = not future.done()
            if hung:
                hass.async_create_background_task(
                    _release_after(gate, future), "eatfresh_picnic_hung_call"
                )
            raise PicnicTimeout(MSG_TIMEOUT) from err
        except Exception as err:
            raise _translate(err) from err
    finally:
        if not hung:
            _end_of(gate)


# ----- search ------------------------------------------------------------


def _field(item: Any, *names: str) -> Any:
    """Return the first present field of a dict or an object."""
    for name in names:
        if isinstance(item, Mapping):
            value = item.get(name)
        else:
            value = getattr(item, name, None)
        if value is not None:
            return value
    return None


def _text(value: Any, limit: int) -> str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value[:limit] if value else None


def _price(value: Any) -> int | None:
    """Return a price in cents (Picnic DE sends whole cents) or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    return None


def _raw_items(result: Any) -> list[Any]:
    """Return the product tiles of a search result in either known form.

    New form (library 2.x): an object (or dict) with ``items``. Old form
    (library 1.x): a list of groups, each a dict with ``items``. A plain
    list of products is accepted as well.
    """
    items = _field(result, "items")
    if isinstance(items, list):
        return items
    if isinstance(result, list):
        found: list[Any] = []
        for group in result:
            inner = _field(group, "items")
            if isinstance(inner, list):
                found.extend(inner)
            elif _field(group, "id") is not None:
                found.append(group)
        return found
    return []


def normalize_hits(result: Any, limit: int = 8) -> list[dict[str, Any]]:
    """Return search hits as ``[{id, name, unit_quantity, price}]``.

    Tiles without an id or a name and repeated ids are left out. ``price`` is in cents or None.
    """
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _raw_items(result):
        product_id = _text(_field(item, "id"), MAX_ID_LENGTH)
        name = _text(_field(item, "name"), MAX_NAME_LENGTH)
        if not product_id or not name or product_id in seen:
            continue
        seen.add(product_id)
        hits.append(
            {
                "id": product_id,
                "name": name,
                "unit_quantity": _text(_field(item, "unit_quantity"), MAX_UNIT_LENGTH),
                "price": _price(_field(item, "display_price", "price")),
            }
        )
        if len(hits) >= limit:
            break
    return hits


async def async_search(
    hass: HomeAssistant, query: str, limit: int = 8
) -> list[dict[str, Any]]:
    """Search Picnic products through the client of the Picnic integration.

    A new search is refused while one runs (no queue of searches). A failed
    search is not tried again by itself.
    """
    search = _method(_require_client(hass), "search")
    if search is None:
        raise PicnicUnavailable(MSG_NO_SEARCH, CODE_NO_SEARCH)
    gate = hass.data.setdefault(_GATE, _Gate())
    if gate.searching:
        raise PicnicBusy(MSG_SEARCH_RUNNING, CODE_SEARCH_RUNNING)
    gate.searching = True
    try:
        result = await _call(hass, search, query)
    finally:
        gate.searching = False
    _check_answer(result)
    if not isinstance(result, list) and not isinstance(
        _field(result, "items"), list
    ):
        _LOGGER.warning("Unknown form of a Picnic search result: %s", type(result))
        raise PicnicError(MSG_ERROR)
    return normalize_hits(result, max(1, min(limit, MAX_HITS)))


# ----- cart --------------------------------------------------------------


def cart_counts(answer: Any) -> dict[str, int | None] | None:
    """Return the pieces per product id of a cart answer, or None if unreadable.

    Reads the answer as Picnic sent it (``raw``): order lines in ``items``,
    their articles in ``items``, the pieces in the decorator ``QUANTITY``.
    An article without readable pieces (for example a deposit or a bundle)
    gives its product ``None``: that product is unclear, the others stay
    readable. Anything else in another form makes the whole cart unreadable,
    so nothing counts as "in the cart" by mistake.
    """
    raw = _raw(answer)
    if not isinstance(raw, Mapping) or isinstance(raw.get("error"), Mapping):
        return None
    lines = raw.get("items")
    if not isinstance(lines, list):
        return None
    counts: dict[str, int | None] = {}
    for line in lines:
        articles = line.get("items") if isinstance(line, Mapping) else None
        if not isinstance(articles, list):
            return None
        for article in articles:
            if not isinstance(article, Mapping):
                return None
            product_id = _text(article.get("id"), MAX_ID_LENGTH)
            if product_id is None:
                return None
            pieces = _quantity(article.get("decorators"))
            known = counts.get(product_id, 0)
            counts[product_id] = (
                None if pieces is None or known is None else known + pieces
            )
    return counts


def _quantity(decorators: Any) -> int | None:
    """Return the pieces of the decorator ``QUANTITY`` or None."""
    if not isinstance(decorators, list):
        return None
    for decorator in decorators:
        if isinstance(decorator, Mapping) and decorator.get("type") == "QUANTITY":
            pieces = decorator.get("quantity")
            if isinstance(pieces, int) and not isinstance(pieces, bool) and pieces >= 0:
                return pieces
            return None
    return None


def _same_cart(one: Mapping[str, int | None], other: Mapping[str, int | None]) -> bool:
    """True if two carts are equal in every number (no pieces = not there)."""
    return {k: v for k, v in one.items() if v != 0} == {
        k: v for k, v in other.items() if v != 0
    }


async def async_cart(hass: HomeAssistant) -> dict[str, int | None]:
    """Read the Picnic cart once: pieces per product id (None: unclear).

    ``PicnicStop`` (rejected login) and ``PicnicBusy`` stay as they are.
    Every other failure, also a timeout or an answer in an unknown form, is
    ``PicnicCartUnreadable``: then nothing may be put in or taken out.
    """
    get_cart = _method(_require_client(hass), "get_cart")
    if get_cart is None:
        raise PicnicUnavailable(MSG_NO_CLIENT, CODE_NO_CLIENT)
    try:
        answer = await _call(hass, get_cart)
        _check_answer(answer)
    except (PicnicStop, PicnicBusy, PicnicUnavailable):
        raise
    except PicnicError as err:
        raise PicnicCartUnreadable(MSG_CART_UNREADABLE) from err
    counts = cart_counts(answer)
    if counts is None:
        _LOGGER.warning("Unknown form of Picnic's cart: %s", type(answer))
        raise PicnicCartUnreadable(MSG_CART_UNREADABLE)
    return counts


async def async_add(
    hass: HomeAssistant,
    product_id: str,
    amount: int,
    before: Mapping[str, int | None],
) -> dict[str, int | None]:
    """Put a product into the Picnic cart and check Picnic's answer.

    ``before`` is the cart before this call: from ``async_cart`` at the
    start of a run, then the answer of the call before. Returns the cart of
    the answer; pass it as ``before`` to the next call of the same run.

    The product only counts as in the cart if the answer shows it with the
    pieces expected (``before`` plus ``amount``). Otherwise:

    - ``PicnicCartUnreadable``: the pieces of the product before are unclear;
      nothing is sent.
    - ``PicnicNotAdded``: Picnic said no (error object), or the cart in the
      answer is the same as before in every number. Surely not in the cart.
    - ``PicnicUncertain``: the answer is not readable, or the cart changed
      but does not show the product with the pieces expected (for example
      under another id). It may be in the cart.
    - ``PicnicStop``: rejected login (surely not in the cart).
    - ``PicnicTimeout`` and other ``PicnicError``: it may be in the cart.
    """
    add = _method(_require_client(hass), "add_product")
    if add is None:
        raise PicnicUnavailable(MSG_NO_CLIENT, CODE_NO_CLIENT)
    amount = int(amount)
    was = before.get(product_id, 0)
    if was is None:
        raise PicnicCartUnreadable(MSG_CART_UNREADABLE)
    answer = await _call(hass, add, product_id, amount)
    try:
        _check_answer(answer)
    except PicnicRefused as err:
        raise PicnicNotAdded(MSG_NOT_ADDED) from err
    counts = cart_counts(answer)
    if counts is None:
        _LOGGER.warning(
            "Unknown form of Picnic's cart after adding a product: %s", type(answer)
        )
        raise PicnicUncertain(MSG_UNCLEAR)
    if counts.get(product_id, 0) == was + amount:
        return counts
    if _same_cart(counts, before):
        raise PicnicNotAdded(MSG_NOT_ADDED)
    raise PicnicUncertain(MSG_UNCLEAR)


async def async_remove(hass: HomeAssistant, product_id: str, amount: int) -> None:
    """Take pieces of a product out of the Picnic cart and check the answer.

    Reads the cart first (one call), then takes out (one call) and compares
    the pieces before and after. Nothing changed (``nothing_done``):
    ``PicnicCartUnreadable``, ``PicnicCartChanged`` (fewer pieces in the cart
    than to take out), ``PicnicRefused``, ``PicnicStop``, ``PicnicBusy`` and
    an unavailable Picnic. ``PicnicUncertain``: the answer does not show the
    pieces gone; they may be out already. After any other error the pieces
    may be out already as well.
    """
    remove = _method(_require_client(hass), "remove_product")
    if remove is None:
        raise PicnicRefused(MSG_NO_REMOVE, CODE_NO_REMOVE)
    amount = int(amount)
    before = await async_cart(hass)
    was = before.get(product_id, 0)
    if was is None:
        raise PicnicCartUnreadable(MSG_CART_UNREADABLE)
    if was < amount:
        raise PicnicCartChanged(MSG_CART_CHANGED)
    answer = await _call(hass, remove, product_id, amount)
    _check_answer(answer)
    counts = cart_counts(answer)
    if counts is None or counts.get(product_id, 0) != was - amount:
        raise PicnicUncertain(MSG_NOT_REMOVED)


async def async_refresh(hass: HomeAssistant) -> None:
    """Ask the Picnic integration to read its cart again (best effort)."""
    entry = _loaded_entry(hass)
    refresh = _method(getattr(entry, "runtime_data", None), "async_request_refresh")
    if refresh is None:
        return
    try:
        async with asyncio.timeout(CALL_TIMEOUT):
            await refresh()
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Refresh of the Picnic integration failed: %r", err)
