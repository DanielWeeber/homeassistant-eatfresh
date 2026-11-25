"""Scale the amounts of a recipe to another number of servings.

Pure Python, no Home Assistant imports. This is the only place where
amounts are recalculated for servings: everything else shows or stores what
:func:`scale_description` returns.

The text is a description as KitchenOwl keeps it for an ingredient or an
entry of the shopping list: parts separated by commas, each part a number,
a number with a unit, a unit alone or a note in brackets ("250g, (Type
405)", "1 Dose, (400 g)", "2 EL", "3"). Commas inside brackets do not
separate. A comma between two digits ("1,5 kg") is a decimal sign: EatFresh
and KitchenOwl always write the separator as a comma and a space. A number
like "1.000" or "1.250" (one to three digits, a dot, three digits ending
in 0) is read with a dot for thousands, except before kg and l. EatFresh
never writes such a number itself, so "1.125kg" and "0.5" stay decimals.

A unit alone ("Dose", "Bund", "EL") counts as 1. A known unit may be
followed by more words ("2 EL gehäuft", "1 Prise Salz"): they stay as they
are. A single unknown word after the number ("1 Große", "3 Eier") counts
pieces.

Examples (from 4 to 3 servings unless stated):

- "500g" gives "375g", "1kg" gives "750g", "1 EL" gives "0.75 EL".
- "3" gives "3" with ``rounded_from`` "2.25": whole pieces are rounded up.
- "1 Dose" from 2 to 3 servings gives "2 Dose", ``rounded_from`` "1.5".
- "1,5 kg" from 4 to 8 servings gives "3kg", "Bund" gives "2 Bund".
- Unknown servings, or as many servings as the recipe has, return the text
  exactly as it is.

How a calculated number ``x`` is rounded, by the class of its unit:

- mass, volume in g or ml: step 1 below 20, step 5 below 250, step 10
  below 1000, step 50 from 1000. Between 250 and 1000 an exact multiple of
  5 stays ("375g"). Never 0: then two significant digits.
- mass, volume in kg or l: below 1 written in g or ml (rule above), from 1
  step 0.05.
- spoon (EL, TL, Tasse) and other known units (mg, cl, dl, cm, mm,
  Tropfen, Portion): step 0.5 from 1, below 1 step 0.25 and at least 0.25.
- pinch (Prise, Msp., Schuss, Spritzer, Handvoll): whole number, at least 1.
- package (Dose, Pck., Bund, ...) and piece (no unit, Stück, Zehe, ...):
  rounded up to whole pieces, never below 1. Up to 0.1 above a whole
  number is rounded down (2.08 gives 2). A single unknown word after the
  number ("1 große", "1 Große", "3 Eier") counts pieces as well.

The result keeps the unit as it was written, so KitchenOwl can still add
entries up. Only kg and l below 1 change to g and ml. A unit alone of the
classes package, piece and spoon is written with its number ("3 Bund"),
one of the class pinch stays alone ("Prise").
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction

from .ingredients import _UNIT_SPELLINGS

MIN_SERVINGS = 1
MAX_SERVINGS = 99
DEFAULT_SERVINGS = 3
MAX_DEFAULT_SERVINGS = 12

# A recipe that claims more servings than this is not scaled.
_MAX_BASE = 1000
# A larger number in a text is not touched.
_MAX_NUMBER = 1_000_000

_MASS = "mass"
_VOLUME = "volume"
_SPOON = "spoon"
_PINCH = "pinch"
_PACKAGE = "package"
_PIECE = "piece"
_OTHER = "other"

# Class -> canonical units. Every other unit is "other".
_CLASSES: dict[str, tuple[str, ...]] = {
    _MASS: ("g", "kg"),
    _VOLUME: ("ml", "l"),
    _SPOON: ("EL", "TL", "Tasse"),
    _PINCH: ("Prise", "Msp.", "Schuss", "Spritzer", "Handvoll"),
    _PACKAGE: (
        "Dose",
        "Pck.",
        "Becher",
        "Glas",
        "Flasche",
        "Tüte",
        "Beutel",
        "Würfel",
        "Rolle",
        "Kästchen",
        "Bund",
        "Kopf",
        "Knolle",
        "Kugel",
        "Stange",
        "Tube",
        "Tafel",
        "Netz",
        "Schale",
        "can",
        "tin",
        "pack",
        "package",
        "jar",
        "bottle",
        "bunch",
        "bag",
    ),
    _PIECE: ("Stück", "Zehe", "Scheibe", "Blatt", "Zweig", "Stiel"),
}
_CLASS_OF: dict[str, str] = {
    unit: kind for kind, units in _CLASSES.items() for unit in units
}

# Spellings beyond the table of the ingredient parser: canonical unit ->
# spellings (lower case, without a trailing dot).
_MORE_SPELLINGS: dict[str, tuple[str, ...]] = {
    "g": ("gram", "grams"),
    "kg": ("kilogram", "kilograms"),
    "l": ("litre", "litres", "liters"),
    "Stück": ("stücke", "x", "piece", "pieces", "pc", "pcs"),
    "Spritzer": ("spritzer",),
    "Beutel": ("beutel",),
    "Tube": ("tube", "tuben"),
    "Tafel": ("tafel", "tafeln"),
    "Netz": ("netz", "netze"),
    "Schale": ("schale", "schalen"),
    "can": ("can", "cans"),
    "tin": ("tin", "tins"),
    "pack": ("pack", "packs"),
    "package": ("package", "packages"),
    "jar": ("jar", "jars"),
    "bottle": ("bottle", "bottles"),
    "bunch": ("bunch", "bunches"),
    "bag": ("bag", "bags"),
    "cm": ("cm", "zentimeter"),
    "mm": ("mm", "millimeter"),
    "Tropfen": ("tropfen",),
}


def _build_lookup() -> dict[str, str]:
    """Return spelling (lower case, no trailing dot) -> canonical unit."""
    lookup: dict[str, str] = {}
    for table in (_UNIT_SPELLINGS, _MORE_SPELLINGS):
        for canonical, spellings in table.items():
            lookup[canonical.rstrip(".").lower()] = canonical
            for spelling in spellings:
                lookup[spelling] = canonical
    return lookup


_LOOKUP = _build_lookup()

# Every spelling of a unit that is bought as a whole pack, in lower case.
# Abbreviations are listed with and without their dot ("pck", "pck.").
PACKAGE_UNITS: frozenset[str] = frozenset(
    spelling
    for spelling, canonical in _LOOKUP.items()
    if _CLASS_OF.get(canonical) == _PACKAGE
) | frozenset(unit.lower() for unit in _CLASSES[_PACKAGE])

# Written without a space after the number, as KitchenOwl adds them up.
_SI_UNITS = frozenset({"mg", "g", "kg", "ml", "l"})
# Below 1 these are written in the smaller unit.
_SMALLER_UNIT = {"kg": "g", "l": "ml"}
# A unit alone gives a number of 1 for these classes, pinch stays alone.
_BARE_CLASSES = frozenset({"package", "piece", "spoon"})

_VULGAR: dict[str, Fraction] = {
    "½": Fraction(1, 2),
    "⅓": Fraction(1, 3),
    "⅔": Fraction(2, 3),
    "¼": Fraction(1, 4),
    "¾": Fraction(3, 4),
    "⅕": Fraction(1, 5),
    "⅖": Fraction(2, 5),
    "⅗": Fraction(3, 5),
    "⅘": Fraction(4, 5),
    "⅙": Fraction(1, 6),
    "⅚": Fraction(5, 6),
    "⅛": Fraction(1, 8),
    "⅜": Fraction(3, 8),
    "⅝": Fraction(5, 8),
    "⅞": Fraction(7, 8),
}
_VULGAR_CLASS = f"[{''.join(_VULGAR)}]"
# "1.000", "1.250", "12.500": a dot for thousands, the last digit is 0.
_THOUSANDS = r"[1-9]\d{0,2}(?:\.\d{3})*\.\d\d0(?!\d)"
_THOUSANDS_RE = re.compile(_THOUSANDS)
# One number: "1½", "1 1/2", "1/2", "½", "1.000", "1.5", "1,5". Order
# matters (longest first).
_NUM = (
    rf"(?:\d{{1,9}}\s*{_VULGAR_CLASS}"
    r"|\d{1,9}\s+\d{1,9}/\d{1,9}"
    r"|\d{1,9}/\d{1,9}"
    rf"|{_VULGAR_CLASS}"
    rf"|{_THOUSANDS}"
    r"|\d{1,9}(?:[.,]\d{1,9})?)"
)
_UNIT = r"[^\W\d_]+\.?"
_WORD = re.compile(_UNIT)
# "ca. 200 g", "2-3 EL", "250g", "1 Dose (400 g)", "2 EL gehäuft", "3"
_PART = re.compile(
    r"(?P<prefix>ca\.\s*|(?:ca|circa|zirka|etwa|ungefähr)\s+)?"
    rf"(?P<first>{_NUM})"
    rf"(?:(?P<separator>\s*[-–—]\s*|\s+bis\s+)(?P<second>{_NUM}))?"
    rf"(?:\s*(?P<unit>{_UNIT}))?"
    r"(?P<tail>\s*\(.*|\s+[^\W\d_].*)?",
    re.IGNORECASE | re.DOTALL,
)
# A unit on its own: "Prise", "Dose (400 g)"
_BARE = re.compile(rf"(?P<unit>{_UNIT})(?P<tail>\s*\(.*)?", re.DOTALL)

_HALF = Fraction(1, 2)
# A rounded count that differs by more than this is worth a remark.
_NOTICE = Fraction(1, 100)
# Up to this much above a whole number, whole pieces are rounded down.
_PIECE_TOLERANCE = Fraction(1, 10)


@dataclass(frozen=True, slots=True)
class Scaled:
    """A description scaled to other servings.

    ``description`` is in the format of KitchenOwl, ready for the list and
    for display. ``scaled`` is False when nothing was recalculated.
    ``rounded_from`` is the exact number before rounding to whole pieces
    ("1.5"), None when nothing was rounded. ``packages`` names each part
    with a package unit as (canonical unit, whole packs, exact number),
    also when nothing was recalculated.
    """

    description: str
    scaled: bool
    rounded_from: str | None
    packages: tuple[tuple[str, int, float], ...]


@dataclass(frozen=True, slots=True)
class _Part:
    """One part of a description that starts with a number."""

    prefix: str  # "ca. " as written, else ""
    numbers: tuple[Fraction, ...]  # one number, or both ends of a range
    separator: str  # between the ends of a range, as written
    unit: str  # as written, "" for a bare number
    tail: str  # note in brackets or more words after the unit, as written


def _whole(value: object) -> int | None:
    """Return a whole number given as int or as a float like 4.0, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return None


def start_servings(base: int | None, default: int) -> int | None:
    """Return the servings a recipe opens with.

    ``default`` for a recipe of 2 to 8 servings. Otherwise ``base``: 1 or
    more than 8 often means "1 cake" or "12 pieces". None when ``base`` is
    unknown. A ``default`` outside 1 to 12 is pulled into that range.
    """
    servings = _whole(base)
    if servings is None or servings < 1:
        return None
    wanted = _whole(default)
    if wanted is None:
        wanted = DEFAULT_SERVINGS
    wanted = max(MIN_SERVINGS, min(MAX_DEFAULT_SERVINGS, wanted))
    return wanted if 2 <= servings <= 8 else servings


def _key(unit: object) -> str:
    """Return a unit the way the lookup spells it."""
    if not isinstance(unit, str):
        return ""
    return unit.strip().rstrip(".").lower()


def unit_class(unit: str) -> str:
    """Return how amounts of a unit are rounded.

    One of "mass", "volume", "spoon", "pinch", "package", "piece" and
    "other". No unit ("") is "piece", so is a single unknown word in any
    case ("große", "Große", "Eier"). "other" is left for known measures
    (mg, cl, dl, cm, mm, Tropfen, Portion) and for anything that is not a
    single word. Spelling and a trailing dot do not matter.
    """
    key = _key(unit)
    if not key:
        return _PIECE
    canonical = _LOOKUP.get(key)
    if canonical is not None:
        return _CLASS_OF.get(canonical, _OTHER)
    if _WORD.fullmatch(unit.strip()):
        return _PIECE
    return _OTHER


def _half_up(value: Fraction, step: Fraction | int) -> Fraction:
    """Round to a multiple of ``step``, a half goes up."""
    return math.floor(value / step + _HALF) * Fraction(step)


def _two_digits(value: Fraction) -> Fraction:
    """Round a number below 1 to two significant digits."""
    step = Fraction(1, 100)
    while value < step * 10 and step > Fraction(1, 10**12):
        step /= 10
    return _half_up(value, step)


def _round_metric(value: Fraction) -> Fraction:
    """Round grams or milliliters."""
    if value < 20:
        step = 1
    elif value < 250:
        step = 5
    elif value < 1000:
        step = 10
    else:
        step = 50
    if step == 10 and value % 10 == 5:
        # Already smooth: 375 stays 375 and is not pushed to 380.
        return value
    return _half_up(value, step) or _two_digits(value)


def _round_spoon(value: Fraction) -> Fraction:
    """Round spoons, cups and every unknown unit."""
    if value >= 1:
        return _half_up(value, _HALF)
    return max(_half_up(value, Fraction(1, 4)), Fraction(1, 4))


def _round_count(value: Fraction) -> Fraction:
    """Round up to whole pieces, a little above a whole number goes down."""
    whole = math.floor(value)
    if whole >= 1 and value - whole <= _PIECE_TOLERANCE:
        return Fraction(whole)
    return Fraction(max(1, math.ceil(value)))


def _round(value: Fraction, kind: str, big: bool) -> Fraction:
    """Round a calculated number by the class of its unit."""
    if kind in (_PACKAGE, _PIECE):
        return _round_count(value)
    if kind == _PINCH:
        return max(_half_up(value, 1), Fraction(1))
    if kind in (_MASS, _VOLUME):
        return _half_up(value, Fraction(1, 20)) if big else _round_metric(value)
    return _round_spoon(value)


def round_metric(value: float) -> float:
    """Round an amount in g or ml like a scaled weight or volume.

    For other modules that need the same smooth numbers. Returns 0.0 for
    anything that is not a positive number.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    if not math.isfinite(value) or value <= 0:
        return 0.0
    exact = Fraction(value).limit_denominator(1000)
    return float(_round_metric(exact)) if exact > 0 else 0.0


def _decimal(value: Fraction, digits: int) -> str:
    """Write a number with a dot and at most ``digits`` decimals, never 0."""
    scale = 10**digits
    units = max(1, math.floor(value * scale + _HALF))
    whole, rest = divmod(units, scale)
    if not rest:
        return str(whole)
    return f"{whole}.{rest:0{digits}d}".rstrip("0")


def _number(text: str, thousands: bool) -> Fraction | None:
    """Read one number of a part, None for 0 and for absurd numbers.

    With ``thousands`` "1.000" is 1000, else 1. "1,5" is 1.5.
    """
    text = text.strip()
    if text[-1] in _VULGAR:
        whole = text[:-1].strip()
        value = _VULGAR[text[-1]] + (int(whole) if whole else 0)
    elif "/" in text:
        *whole_part, fraction = text.split()
        top, _, bottom = fraction.partition("/")
        if not int(bottom):
            return None
        value = Fraction(int(top), int(bottom))
        if whole_part:
            value += int(whole_part[0])
    elif thousands and _THOUSANDS_RE.fullmatch(text):
        value = Fraction(int(text.replace(".", "")))
    else:
        value = Fraction(text.replace(",", "."))
    return value if 0 < value <= _MAX_NUMBER else None


def _read_part(text: str) -> _Part | None:
    """Split a part into number, unit and note; None when it has no number."""
    match = _PART.fullmatch(text)
    if match is None:
        return None
    unit = match["unit"] or ""
    canonical = _LOOKUP.get(_key(unit))
    tail = match["tail"] or ""
    if tail and not tail.lstrip().startswith("(") and canonical is None:
        # More words only after a known unit: "2 EL gehäuft", not "1 große
        # Zwiebel".
        return None
    # Nobody needs 1000 kg: "1.500 kg" is 1.5 kg.
    thousands = canonical not in _SMALLER_UNIT
    numbers = [_number(match["first"], thousands)]
    if match["second"] is not None:
        numbers.append(_number(match["second"], thousands))
    if any(number is None for number in numbers):
        return None
    return _Part(
        prefix=match["prefix"] or "",
        numbers=tuple(number for number in numbers if number is not None),
        separator=match["separator"] or "",
        unit=unit,
        tail=tail,
    )


def _read_bare(text: str) -> _Part | None:
    """Read a known unit alone ("Bund", "Dose (400 g)") as 1 of it.

    None for a unit of the class pinch ("Prise" stays alone), for unknown
    words ("etwas") and for everything else.
    """
    match = _BARE.fullmatch(text)
    if match is None or _key(match["unit"]) not in _LOOKUP:
        return None
    if unit_class(match["unit"]) not in _BARE_CLASSES:
        return None
    return _Part("", (Fraction(1),), "", match["unit"], match["tail"] or "")


def _write(part: _Part, numbers: list[Fraction], unit: str) -> str:
    """Write a part the way the KitchenOwl client writes descriptions."""
    texts = [_decimal(number, 3) for number in numbers]
    number = texts[0] if len(set(texts)) == 1 else part.separator.join(texts)
    if not unit:
        body = number
    elif unit.lower() in _SI_UNITS:
        body = f"{number}{unit}"
    else:
        body = f"{number} {unit}"
    return f"{part.prefix}{body}{part.tail}"


def _scale_part(part: _Part, factor: Fraction) -> tuple[str, Fraction, Fraction]:
    """Return the part scaled, its first number rounded and exact."""
    kind = unit_class(part.unit)
    unit = part.unit
    canonical = _LOOKUP.get(_key(unit), "")
    exact = [number * factor for number in part.numbers]
    first = exact[0]
    big = canonical in _SMALLER_UNIT
    if big and min(exact) < 1:
        exact = [number * 1000 for number in exact]
        unit = _SMALLER_UNIT[canonical]
        big = False
    rounded = [_round(number, kind, big) for number in exact]
    return _write(part, rounded, unit), rounded[0], first


def _split(text: str) -> list[str]:
    """Split at commas outside brackets, keeping every character.

    A comma between two digits ("1,5") is a decimal sign and stays.
    """
    parts: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0 and not _decimal_comma(text, index):
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return parts


def _decimal_comma(text: str, index: int) -> bool:
    """Return True if the comma at ``index`` stands between two digits."""
    before = text[index - 1] if index > 0 else ""
    after = text[index + 1] if index + 1 < len(text) else ""
    return before in _DIGITS and after in _DIGITS


_DIGITS = frozenset("0123456789")


def _convert(
    segment: str, factor: Fraction | None
) -> tuple[str, str, Fraction, Fraction] | None:
    """Return (segment, unit as written, whole count, exact number).

    None for a part without a readable number. A known unit alone counts
    as 1 (see :func:`_read_bare`). Without a factor the segment comes back
    as it is.
    """
    core = segment.strip()
    part = _read_part(core) or _read_bare(core)
    if part is None:
        return None
    if factor is None:
        first = part.numbers[0]
        return segment, part.unit, _round_count(first), first
    text, count, exact = _scale_part(part, factor)
    lead = segment[: len(segment) - len(segment.lstrip())]
    trail = segment[len(segment.rstrip()) :]
    return f"{lead}{text}{trail}", part.unit, count, exact


def _factor(base: object, servings: object) -> Fraction | None:
    """Return servings / base, None when unknown, absurd or exactly 1."""
    recipe = _whole(base)
    wanted = _whole(servings)
    if recipe is None or wanted is None or recipe == wanted:
        return None
    if not 1 <= recipe <= _MAX_BASE or not MIN_SERVINGS <= wanted <= MAX_SERVINGS:
        return None
    return Fraction(wanted, recipe)


def _plain_text(value: object) -> str:
    """Return something that is not a text as text ("" unless a number)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ""
    if isinstance(value, int):
        return str(value)
    if not math.isfinite(value):
        return ""
    return f"{value:.3f}".rstrip("0").rstrip(".")


def scale_description(
    description: str | None, base: int | None, servings: int | None
) -> Scaled:
    """Scale a description from ``base`` servings to ``servings``.

    With unknown ``base`` or ``servings``, or when both are equal, the text
    comes back character for character and ``scaled`` is False. Parts that
    cannot be read stay as they are. Anything but a text is never scaled
    (None gives ""). Never raises.
    """
    if not isinstance(description, str):
        return Scaled(_plain_text(description), False, None, ())
    text = description
    factor = _factor(base, servings)
    segments: list[str] = []
    packages: list[tuple[str, int, float]] = []
    rounded_from: str | None = None
    scaled = False
    for segment in _split(text):
        done = _convert(segment, factor)
        if done is None:
            segments.append(segment)
            continue
        new, written, count, exact = done
        segments.append(new)
        kind = unit_class(written)
        if kind == _PACKAGE:
            canonical = _LOOKUP[_key(written)]
            # Four decimals are plenty for a count of packs, but never 0.
            precise = max(round(float(exact), 4), 0.0001)
            packages.append((canonical, int(count), precise))
        if factor is None:
            continue
        scaled = True
        counted = kind in (_PACKAGE, _PIECE)
        if rounded_from is None and counted and abs(count - exact) > _NOTICE:
            rounded_from = _decimal(exact, 2)
    return Scaled(
        description=",".join(segments) if scaled else text,
        scaled=scaled,
        rounded_from=rounded_from,
        packages=tuple(packages),
    )
