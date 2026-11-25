"""Suggest how many Picnic packs cover an amount from the shopping list.

Pure Python, no Home Assistant imports. The result is only a suggestion:
the user can always change it in the panel.

Examples (``description`` of the shopping list entry, ``unit_quantity`` of
the Picnic product):

- "500g" and "1kg" give 1, "1500g" and "4 x 250g" give 2.
- "1,5 l" and "500 ml" give 3, "6 Stück" and "4 Stück" give 2.
- "1.000 g" is 1000 g (a dot for thousands, as in :mod:`.portions`),
  "1.500 kg" is 1.5 kg.
- Text without a number, an unknown pack size or different kinds of
  quantity (weight against pieces) give 1.
- A count with a package unit is a count of packs: "2 Dose" and "400 g"
  give 2, "4 Dose" and "3 x 200 g" give 2, "2 Dose" and "4 Stück" give 2
  (a product counted in pieces is one pack). "6 Stück" or "6" and
  "4 Stück" still give 2. Here an unknown pack size is a
  single pack: "2 Dose" and "" give 2.

:func:`suggest_split` also says what the last pack has to cover. "600g" and
"500 g" give 2 packs and a rest of "100 g": a smaller pack would do for it.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace

from .portions import PACKAGE_UNITS, round_metric

# The most packs ever suggested (the send command accepts 1 to 20).
MAX_SUGGESTED = 20
# Up to 10 percent of a pack more than whole packs still counts as covered,
# so 510 g with packs of 500 g suggests 1, not 2.
TOLERANCE = 0.1
# The last pack is worth replacing by a smaller one when the list needs at
# most this share of it.
REST_LIMIT = 0.6
# Slack for comparing floats.
_EPSILON = 1e-9

_MASS = "mass"
_VOLUME = "volume"
_COUNT = "count"

# Unit word (lower case, without a trailing dot) to kind and factor.
_UNITS: dict[str, tuple[str, float]] = {
    "mg": (_MASS, 0.001),
    "g": (_MASS, 1.0),
    "gr": (_MASS, 1.0),
    "gram": (_MASS, 1.0),
    "gramm": (_MASS, 1.0),
    "grams": (_MASS, 1.0),
    "kg": (_MASS, 1000.0),
    "kilo": (_MASS, 1000.0),
    "kilogramm": (_MASS, 1000.0),
    "kilogram": (_MASS, 1000.0),
    "ml": (_VOLUME, 1.0),
    "cl": (_VOLUME, 10.0),
    "dl": (_VOLUME, 100.0),
    "l": (_VOLUME, 1000.0),
    "liter": (_VOLUME, 1000.0),
    "litre": (_VOLUME, 1000.0),
    "stück": (_COUNT, 1.0),
    "stk": (_COUNT, 1.0),
    "st": (_COUNT, 1.0),
    "x": (_COUNT, 1.0),
    "pcs": (_COUNT, 1.0),
    "pc": (_COUNT, 1.0),
    "piece": (_COUNT, 1.0),
    "pieces": (_COUNT, 1.0),
}

_NUMBER = r"\d+(?:[.,]\d+)?(?:\s*/\s*\d+)?"
# "1.000", "1.250": a dot for thousands, the last digit is 0.
_THOUSANDS = re.compile(r"[1-9]\d{0,2}\.\d\d0")
# Nobody needs 1000 kg: before these units "1.500" stays 1.5.
_NO_THOUSANDS = frozenset(
    {"kg", "kilo", "kilogramm", "kilogram", "l", "liter", "litre"}
)
_QUANTITY = re.compile(
    rf"(?P<number>{_NUMBER})\s*(?P<unit>[a-zäöüß]+\.?)?(?![a-zäöüß])",
    re.IGNORECASE,
)
# "4 x 250g", "4x250 g", "2 × 1 l"
_MULTIPACK = re.compile(
    rf"(?P<count>\d+)\s*[x×]\s*(?P<rest>{_NUMBER}\s*[a-zäöüß]+\.?)",
    re.IGNORECASE,
)


def _number(text: str, *, thousands: bool = False) -> float | None:
    """Read "1,5", "1.5" or "1/2" as a number, with ``thousands`` "1.000"."""
    text = text.replace(" ", "")
    if thousands and _THOUSANDS.fullmatch(text):
        return float(text.replace(".", ""))
    if "/" in text:
        top, _, bottom = text.partition("/")
        try:
            divisor = float(bottom)
            return float(top.replace(",", ".")) / divisor if divisor else None
        except ValueError:
            return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class Split:
    """Packs of the main product and of a smaller one that cover an amount.

    ``amount`` is 0 only when ``small_amount`` is at least 1. ``rest`` is
    what the last pack only has to cover ("200 ml"), None when the last pack
    is needed for more than ``REST_LIMIT`` of it or nothing can be said.
    """

    amount: int
    small_amount: int
    rest: str | None


@dataclass(frozen=True, slots=True)
class _Quantity:
    """The first quantity of a text."""

    amount: float  # g, ml or pieces; a multipack counts all its packs
    kind: str
    unit: str  # unit word as written, "" for a bare number
    factor: float  # of the unit: 1000 for kg and l
    packs: int  # packs in a multipack ("4 x 250g" gives 4), else 1


def _read(text: str | None) -> _Quantity | None:
    """Read the first quantity of a text, None without a number above 0."""
    if not isinstance(text, str) or not text.strip():
        return None
    if multi := _MULTIPACK.search(text):
        inner = _read(multi["rest"])
        if inner is not None:
            count = int(multi["count"])
            return replace(inner, amount=inner.amount * count, packs=count)
    for match in _QUANTITY.finditer(text):
        unit = match["unit"] or ""
        thousands = unit.lower().rstrip(".") not in _NO_THOUSANDS
        value = _number(match["number"], thousands=thousands)
        if value is None or value <= 0:
            continue
        # A number without a unit, or followed by an unknown word ("2 Bund",
        # "1 Dose"), counts pieces of that thing.
        kind, factor = _UNITS.get(unit.lower().rstrip("."), (_COUNT, 1.0))
        return _Quantity(value * factor, kind, unit, factor, 1)
    return None


def parse_quantity(text: str | None) -> tuple[float, str] | None:
    """Return (amount in g, ml or pieces, kind) of the first quantity in a text.

    A number without a known unit counts as pieces. Returns None for text
    without a number or with a number of 0.
    """
    quantity = _read(text)
    return None if quantity is None else (quantity.amount, quantity.kind)


def _is_package_count(need: _Quantity) -> bool:
    """Return True for a count of packs such as "2 Dose" or "1 Pck."."""
    return (
        need.kind == _COUNT
        and need.packs == 1
        and need.unit.lower().rstrip(".") in PACKAGE_UNITS
    )


def _packs_per_product(pack: _Quantity | None) -> float:
    """Return how many packs one product holds for a count of packs.

    A product counted in pieces ("6 Stück") is one pack: only a multipack
    ("3 x 200 g") holds more.
    """
    return 1.0 if pack is None else float(pack.packs)


def _positive(value: object) -> float | None:
    """Return a number above 0 as float, None for everything else."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value > 0 else None


def _needed(
    description: str | None, unit_quantity: str | None, exact_count: float | None
) -> tuple[float, _Quantity | None] | None:
    """Return how many products are needed, not rounded, and the pack read.

    None when the texts cannot be read or describe different kinds of
    quantity. A count of packs (``exact_count``, or a description such as
    "2 Dose") needs no readable pack size: an unknown one is a single pack.
    Such a count is divided only by the packs of a multipack, never by the
    pieces of a product counted in pieces.
    """
    need = _read(description)
    pack = _read(unit_quantity)
    count = exact_count
    if count is None and need is not None and _is_package_count(need):
        count = need.amount
    if count is not None:
        per_product = _packs_per_product(pack)
        needed = count / per_product if per_product > 0 else math.nan
    elif need is None or pack is None or need.kind != pack.kind or pack.amount <= 0:
        return None
    else:
        needed = need.amount / pack.amount
    if not math.isfinite(needed) or needed <= 0:
        return None
    return needed, pack


def _cover(needed: float) -> int:
    """Return the whole packs that cover ``needed`` packs, at least 1."""
    packs = math.ceil(needed - _EPSILON)
    if packs > 1 and needed <= packs - 1 + TOLERANCE + _EPSILON:
        packs -= 1
    return max(1, packs)


def suggest_amount(description: str | None, unit_quantity: str | None) -> int:
    """Return how many packs of ``unit_quantity`` cover ``description``.

    Always between 1 and ``MAX_SUGGESTED``. Falls back to 1 whenever the
    texts cannot be read or describe different kinds of quantity. A count
    with a package unit ("2 Dose") is the count itself for a single pack or
    a product counted in pieces ("4 Stück") and is divided by the packs of
    a multipack ("3 x 200 g"), rounded up.
    """
    found = _needed(description, unit_quantity, None)
    return 1 if found is None else min(MAX_SUGGESTED, _cover(found[0]))


def _plain(value: float) -> str:
    """Write a number with a dot and at most 3 decimals."""
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _rest_text(amount: float, pack: _Quantity) -> str | None:
    """Write a rest in the unit of the pack, None when it is no real rest."""
    if pack.kind == _COUNT:
        pieces = _cover(amount)
        if pieces >= pack.amount:
            return None
        word = pack.unit.rstrip(".").lower()
        # "6er" is no unit worth showing.
        unit = pack.unit if len(word) >= 3 or word in ("st", "pc") else ""
        return f"{pieces} {unit}".strip()
    value = round_metric(amount)
    if not 0 < value < pack.amount or not float(_plain(value)):
        return None
    big, small = ("kg", "g") if pack.kind == _MASS else ("l", "ml")
    if pack.factor >= 1000 and value % 1000 == 0:
        return f"{_plain(value / 1000)} {big}"
    return f"{_plain(value)} {small}"


def _small_packs(rest: float, pack: _Quantity, small_unit_quantity: str | None) -> int:
    """Return how many smaller packs replace the last pack, 0 for none."""
    small = _read(small_unit_quantity)
    if small is None or small.kind != pack.kind:
        return 0
    if not 0 < small.amount < pack.amount:
        return 0
    count = _cover(rest / small.amount)
    if count > MAX_SUGGESTED or count * small.amount >= pack.amount - _EPSILON:
        return 0
    return count


def suggest_split(
    description: str | None,
    unit_quantity: str | None,
    *,
    exact_count: float | None = None,
    small_unit_quantity: str | None = None,
) -> Split:
    """Return the packs to buy and what the last pack only has to cover.

    The need is read from ``description`` as in :func:`suggest_amount`. With
    ``exact_count`` it is that exact number of packs instead ("1.5" for a
    list that says "2 Dose"). It is divided by the packs of a multipack
    ("3 x 200 g"), but a product counted in pieces ("6 Stück") is one
    pack. ``amount`` is what :func:`suggest_amount` gives. When the last
    pack is needed for at most ``REST_LIMIT`` of it, ``rest`` says how much
    that is. If then ``small_unit_quantity`` is a
    smaller pack of the same kind and some of them cover the rest with less
    content than one main pack, they replace the last main pack.
    """
    found = _needed(description, unit_quantity, _positive(exact_count))
    if found is None:
        return Split(1, 0, None)
    needed, pack = found
    amount = min(MAX_SUGGESTED, _cover(needed))
    last = needed - (amount - 1)  # share of the last product that is needed
    if pack is None or not 0 < last <= REST_LIMIT + _EPSILON:
        return Split(amount, 0, None)
    rest_amount = last * pack.amount
    rest = _rest_text(rest_amount, pack)
    if rest is None:
        return Split(amount, 0, None)
    small = _small_packs(rest_amount, pack, small_unit_quantity)
    return Split(amount - 1 if small else amount, small, rest)


def fits_rest(
    rest: str | None, unit_quantity: str | None, main_unit_quantity: str | None
) -> bool:
    """Return True if a product is a smaller pack that covers the rest.

    It has to be of the same kind as the rest and as the main pack, cover
    the rest (up to 10 percent short still counts) and be smaller than the
    main pack.
    """
    need = _read(rest)
    pack = _read(unit_quantity)
    main = _read(main_unit_quantity)
    if need is None or pack is None or main is None:
        return False
    if not need.kind == pack.kind == main.kind:
        return False
    covers = need.amount <= pack.amount * (1 + TOLERANCE) + _EPSILON
    return covers and 0 < pack.amount < main.amount
