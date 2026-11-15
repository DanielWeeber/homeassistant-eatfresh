"""Parser for German ingredient lines.

Pure Python, no Home Assistant imports. The main entry point is
:func:`parse_ingredient`; :func:`parse_amount` and :func:`normalize_unit` are
reused by sources whose data already comes split into amount, unit and name.
"""

from __future__ import annotations

import html
import re

from .models import Ingredient

# Unicode vulgar fractions -> value.
_FRACTIONS: dict[str, float] = {
    "½": 0.5,
    "⅓": 1 / 3,
    "⅔": 2 / 3,
    "¼": 0.25,
    "¾": 0.75,
    "⅕": 0.2,
    "⅖": 0.4,
    "⅗": 0.6,
    "⅘": 0.8,
    "⅙": 1 / 6,
    "⅚": 5 / 6,
    "⅛": 0.125,
    "⅜": 0.375,
    "⅝": 0.625,
    "⅞": 0.875,
}
_FRACTION_CHARS = "".join(_FRACTIONS)

# Canonical unit -> spellings (lower case, without trailing dot).
_UNIT_SPELLINGS: dict[str, tuple[str, ...]] = {
    "g": ("g", "gr", "gramm"),
    "kg": ("kg", "kilo", "kilogramm"),
    "mg": ("mg", "milligramm"),
    "ml": ("ml", "milliliter"),
    "cl": ("cl", "centiliter"),
    "dl": ("dl", "deziliter"),
    "l": ("l", "liter"),
    "EL": ("el", "essl", "esslöffel", "essloeffel"),
    "TL": ("tl", "teel", "teelöffel", "teeloeffel"),
    "Stück": ("stück", "stueck", "stk", "stck", "st"),
    "Bund": ("bund", "bünde", "buend"),
    "Dose": ("dose", "dosen"),
    "Pck.": ("pck", "pkg", "pk", "päckchen", "paeckchen", "packung", "packungen", "päckchens"),
    "Prise": ("prise", "prisen"),
    "Msp.": ("msp", "messerspitze", "messerspitzen"),
    "Zehe": ("zehe", "zehen"),
    "Scheibe": ("scheibe", "scheiben"),
    "Becher": ("becher",),
    "Tasse": ("tasse", "tassen"),
    "Glas": ("glas", "gläser", "glaeser"),
    "Flasche": ("flasche", "flaschen"),
    "Schuss": ("schuss", "schüsse", "schuesse"),
    "Handvoll": ("handvoll", "handvolle"),
    "Stange": ("stange", "stangen"),
    "Zweig": ("zweig", "zweige"),
    "Stiel": ("stiel", "stiele"),
    "Blatt": ("blatt", "blätter", "blaetter"),
    "Kugel": ("kugel", "kugeln"),
    "Würfel": ("würfel", "wuerfel"),
    "Tüte": ("tüte", "tüten", "tuete", "tueten"),
    "Kästchen": ("kästchen", "kaestchen"),
    "Knolle": ("knolle", "knollen"),
    "Kopf": ("kopf", "köpfe", "koepfe"),
    "Rolle": ("rolle", "rollen"),
    "Portion": ("portion", "portionen"),
}
_UNIT_LOOKUP: dict[str, str] = {
    spelling: canonical
    for canonical, spellings in _UNIT_SPELLINGS.items()
    for spelling in spellings
}

_NUMBER_WORDS = {"ein": 1.0, "eine": 1.0, "einen": 1.0, "einem": 1.0, "einer": 1.0}

_ODD_SPACES = ("\u00a0", "\u202f", "\u2009", "\u2007", "\u2002", "\u2003")
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_PLURAL_SUFFIX_RE = re.compile(r"(?<=[^\W\d_])\((?:n|en|e|s|r)\)")
_APPROX_RE = re.compile(r"^(?:ca\.?|circa|etwa|ungefähr|zirka|je)\s+", re.IGNORECASE)
_BULLET_RE = re.compile(r"^[-–•*·]\s+")

_NUM = r"\d+(?:[.,]\d+)?"
_FRAC_CLASS = f"[{_FRACTION_CHARS}]"
# One quantity: mixed number, simple fraction, vulgar fraction, number with
# optional vulgar fraction, plain decimal. Order matters (longest first).
_QUANTITY = (
    rf"(?:\d+\s*{_FRAC_CLASS}"
    rf"|\d+\s+\d+/\d+"
    rf"|\d+/\d+"
    rf"|{_FRAC_CLASS}"
    rf"|[1-9]\d{{0,2}}(?:\.\d{{3}})+(?![\d,])"
    rf"|{_NUM})"
)
_RANGE_SEP = r"(?:\s*[-–—]\s*|\s+bis\s+)"
_AMOUNT_RE = re.compile(rf"^(?P<first>{_QUANTITY})(?:{_RANGE_SEP}(?P<second>{_QUANTITY}))?")
_WORD_RE = re.compile(r"^([^\W\d_]+\.?)", re.UNICODE)


def _clean(text: str) -> str:
    """Unescape entities, drop tags, normalize white space."""
    text = html.unescape(text)
    if "<" in text and ">" in text:
        text = _TAG_RE.sub(" ", text)
    for char in _ODD_SPACES:
        text = text.replace(char, " ")
    text = text.replace("\u200b", "")
    return _SPACE_RE.sub(" ", text).strip()


def parse_amount(text: str | None) -> float | None:
    """Parse one quantity such as ``1,5``, ``1/2``, ``½``, ``1 ½`` or ``1.000``.

    Returns None when the text is not a plain quantity. A range yields its
    lower bound.
    """
    if text is None:
        return None
    cleaned = _clean(str(text))
    if not cleaned:
        return None
    match = _AMOUNT_RE.match(cleaned)
    if match is None:
        return None
    return _amount_from_match(match)


def _quantity_value(text: str) -> float:
    text = text.strip()
    if text and text[-1] in _FRACTIONS:
        whole = text[:-1].strip()
        return (float(whole.replace(",", ".")) if whole else 0.0) + _FRACTIONS[text[-1]]
    if text in _FRACTIONS:
        return _FRACTIONS[text]
    mixed = re.fullmatch(r"(\d+)\s+(\d+)/(\d+)", text)
    if mixed:
        denominator = int(mixed.group(3))
        if denominator == 0:
            return float(mixed.group(1))
        return int(mixed.group(1)) + int(mixed.group(2)) / denominator
    simple = re.fullmatch(r"(\d+)/(\d+)", text)
    if simple:
        denominator = int(simple.group(2))
        return int(simple.group(1)) / denominator if denominator else 0.0
    if re.fullmatch(r"[1-9]\d{0,2}(?:\.\d{3})+", text):
        return float(text.replace(".", ""))
    return float(text.replace(",", "."))


def _amount_from_match(match: re.Match[str]) -> float:
    # A range such as "1-2" keeps its lower bound.
    return round(_quantity_value(match.group("first")), 4)


def normalize_unit(text: str | None) -> str | None:
    """Return the canonical spelling of a known unit, else the cleaned text.

    ``Zehen`` -> ``Zehe``, ``Esslöffel`` -> ``EL``, ``Liter`` -> ``l``.
    Empty input gives None.
    """
    if text is None:
        return None
    cleaned = _clean(str(text))
    if not cleaned:
        return None
    cleaned = _PLURAL_SUFFIX_RE.sub("", cleaned)
    key = cleaned.rstrip(".").lower()
    return _UNIT_LOOKUP.get(key, cleaned)


def clean_name(text: str | None) -> str:
    """Tidy an ingredient name given on its own ("Kartoffel(n)" -> "Kartoffel")."""
    if text is None:
        return ""
    return _tidy_name(_PLURAL_SUFFIX_RE.sub("", _clean(str(text))))


def format_amount(amount: float | None) -> str:
    """Format a quantity the German way: ``1.5`` -> ``1,5``, ``2.0`` -> ``2``."""
    if amount is None:
        return ""
    text = f"{amount:.3f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _split_top_level_comma(text: str) -> tuple[str, str | None]:
    """Split at the first comma that is not inside brackets."""
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            return text[:index], text[index + 1 :]
    return text, None


def _extract_brackets(text: str) -> tuple[str, list[str]]:
    """Remove ``(...)`` groups and return the text plus their contents."""
    notes: list[str] = []

    def collect(match: re.Match[str]) -> str:
        inner = match.group(1).strip()
        if inner:
            notes.append(inner)
        return " "

    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\(([^()]*)\)", collect, text)
    # Unbalanced bracket leftovers.
    text = text.replace("(", " ").replace(")", " ")
    return _SPACE_RE.sub(" ", text).strip(), notes


def _tidy_name(name: str) -> str:
    name = _SPACE_RE.sub(" ", name).strip(" ,;:-–—")
    return name.strip()


def _take_unit(rest: str) -> tuple[str | None, str]:
    """Take a leading unit word from ``rest`` if it is a known unit."""
    match = _WORD_RE.match(rest)
    if match is None:
        return None, rest
    word = match.group(1)
    canonical = _UNIT_LOOKUP.get(word.rstrip(".").lower())
    if canonical is None:
        return None, rest
    # "g" etc. must stand alone: no further letters (the regex already took
    # the full word), so "Gurke" never matches "g".
    return canonical, rest[match.end() :].lstrip()


def parse_ingredient(line: str) -> Ingredient:
    """Split a German ingredient line into amount, unit, name and note.

    >>> parse_ingredient("250 g Mehl (Type 405)").name
    'Mehl'

    ``raw`` keeps the original wording (entities resolved, white space
    normalized). Lines without a quantity ("Salz und Pfeffer") keep the whole
    text as name.
    """
    raw = _clean(line)
    text = _BULLET_RE.sub("", raw)
    text = _PLURAL_SUFFIX_RE.sub("", text)
    text = _APPROX_RE.sub("", text).strip()
    notes: list[str] = []

    amount: float | None = None
    unit: str | None = None
    rest = text

    match = _AMOUNT_RE.match(text)
    if match is not None and (
        match.end() == len(text) or not text[match.end()].isdigit()
    ):
        amount = _amount_from_match(match)
        rest = text[match.end() :].lstrip()
        # Bracket right after the amount: "1 (400 g) Dose Tomaten".
        lead = re.match(r"^\(([^()]*)\)\s*", rest)
        if lead:
            if lead.group(1).strip():
                notes.append(lead.group(1).strip())
            rest = rest[lead.end() :]
        rest = rest.lstrip(" .")
        unit, rest = _take_unit(rest)
        rest = rest.lstrip(" .") if unit is not None else rest
    else:
        word = _WORD_RE.match(text)
        if word and word.group(1).lower() in _NUMBER_WORDS:
            candidate_unit, after = _take_unit(text[word.end() :].lstrip())
            if candidate_unit is not None:
                amount = _NUMBER_WORDS[word.group(1).lower()]
                unit, rest = candidate_unit, after

    has_amount = amount is not None
    rest, bracket_notes = _extract_brackets(rest)
    notes.extend(bracket_notes)

    if has_amount:
        name_part, tail = _split_top_level_comma(rest)
        if tail is not None and tail.strip():
            notes.append(_tidy_name(tail))
    else:
        name_part = rest

    name = _tidy_name(name_part)
    if not name and unit is not None:
        # "2 Becher": the unit word is all we know.
        name, unit = unit, None
    note = ", ".join(item for item in notes if item) or None
    return Ingredient(name=name, amount=amount, unit=unit, note=note, raw=raw)
