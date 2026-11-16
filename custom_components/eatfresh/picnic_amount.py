"""Suggest how many Picnic packs cover an amount from the shopping list.

Pure Python, no Home Assistant imports. The result is only a suggestion:
the user can always change it in the panel.

Examples (``description`` of the shopping list entry, ``unit_quantity`` of
the Picnic product):

- "500g" and "1kg" give 1, "1500g" and "4 x 250g" give 2.
- "1,5 l" and "500 ml" give 3, "6 Stück" and "4 Stück" give 2.
- Text without a number, an unknown pack size or different kinds of
  quantity (weight against pieces) give 1.
"""

from __future__ import annotations

import math
import re

# The most packs ever suggested (the send command accepts 1 to 20).
MAX_SUGGESTED = 20
# Up to 10 percent of a pack more than whole packs still counts as covered,
# so 510 g with packs of 500 g suggests 1, not 2.
TOLERANCE = 0.1

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
_QUANTITY = re.compile(
    rf"(?P<number>{_NUMBER})\s*(?P<unit>[a-zäöüß]+\.?)?(?![a-zäöüß])",
    re.IGNORECASE,
)
# "4 x 250g", "4x250 g", "2 × 1 l"
_MULTIPACK = re.compile(
    rf"(?P<count>\d+)\s*[x×]\s*(?P<rest>{_NUMBER}\s*[a-zäöüß]+\.?)",
    re.IGNORECASE,
)


def _number(text: str) -> float | None:
    """Read "1,5", "1.5" or "1/2" as a number."""
    text = text.replace(" ", "")
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


def parse_quantity(text: str | None) -> tuple[float, str] | None:
    """Return (amount in g, ml or pieces, kind) of the first quantity in a text.

    A number without a known unit counts as pieces. Returns None for text
    without a number or with a number of 0.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    if multi := _MULTIPACK.search(text):
        inner = parse_quantity(multi["rest"])
        if inner is not None:
            return inner[0] * int(multi["count"]), inner[1]
    for match in _QUANTITY.finditer(text):
        value = _number(match["number"])
        if value is None or value <= 0:
            continue
        unit = (match["unit"] or "").lower().rstrip(".")
        if not unit:
            return value, _COUNT
        if unit in _UNITS:
            kind, factor = _UNITS[unit]
            return value * factor, kind
        # A number followed by an unknown word ("2 Bund", "1 Dose") counts
        # as pieces of that thing.
        return value, _COUNT
    return None


def suggest_amount(description: str | None, unit_quantity: str | None) -> int:
    """Return how many packs of ``unit_quantity`` cover ``description``.

    Always between 1 and ``MAX_SUGGESTED``. Falls back to 1 whenever the
    texts cannot be read or describe different kinds of quantity.
    """
    need = parse_quantity(description)
    pack = parse_quantity(unit_quantity)
    if need is None or pack is None or need[1] != pack[1]:
        return 1
    needed, size = need[0], pack[0]
    if size <= 0:
        return 1
    packs = math.ceil(needed / size - 1e-9)
    if packs > 1 and needed <= (packs - 1 + TOLERANCE) * size:
        packs -= 1
    return max(1, min(MAX_SUGGESTED, packs))
