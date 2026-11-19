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
    "Pck.": (
        "pck",
        "pkg",
        "pk",
        "päck",
        "paeck",
        "päckchen",
        "paeckchen",
        "packung",
        "packungen",
        "päckchens",
    ),
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
_PLURAL_SUFFIX_RE = re.compile(r"(?<=[^\W\d_])\((?:n|en|e|er|s|r)\)")
# Suffixes that make a real plural ("Ei(er)" -> "Eier"); "(s)" and "(r)" are
# only dropped.
_PLURAL_ENDINGS = ("n", "en", "e", "er")
_UNIT_SUFFIX_RE = re.compile(r"^([^\W\d_]+\.?)\((?:n|en|e|er|s|r)\)")
_CAPITAL_WORD_RE = re.compile(r"[^\W\d_][\w-]*")
_PAIR_RE = re.compile(r"^(salz|pfeffer)\s*(?:und|&)\s*(salz|pfeffer)$", re.IGNORECASE)
_VAGUE_AMOUNT_RE = re.compile(
    r"^(?P<phrase>nach\s+(?:geschmack|belieben|bedarf))\s+(?P<name>\S.*)$", re.IGNORECASE
)
# Lower case words that end like an inflected adjective but are none.
_NOT_ADJECTIVES = frozenset(
    "oder aber bitte sonst etwa eher sehr gerne lieber weniger wahlweise ohne "
    "ggf evtl eventuell mehr viele andere alternativ optional beliebige "
    "beliebiger beliebiges nötige nötiger nötiges eine einer eines einige "
    "wenige keine keiner keines".split()
)
_ADJECTIVE_RE = re.compile(r"^[a-zäöüß]{3,}(?:e|er|es)$")
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


def resolve_plural(text: str, amount: float | None, unit: str | None = None) -> str:
    """Resolve a plural suffix in brackets by the amount and the unit.

    The singular is used only for an amount of exactly 1 with no unit:
    ``1 Ei(er)`` gives ``Ei``. Every other case gives the plural (``2 Ei(er)``
    gives ``Eier``, ``1 kg Kartoffel(n)`` gives ``Kartoffeln``, ``Zwiebel(n)``
    without an amount gives ``Zwiebeln``), so that one ingredient does not
    split into two articles. ``(s)`` and ``(r)`` are always dropped.
    """
    singular = amount == 1 and not unit

    def pick(match: re.Match[str]) -> str:
        ending = match.group(0)[1:-1]
        if ending in _PLURAL_ENDINGS and not singular:
            return ending
        return ""

    return _PLURAL_SUFFIX_RE.sub(pick, text)


def clean_name(
    text: str | None, amount: float | None = None, unit: str | None = None
) -> str:
    """Tidy an ingredient name given on its own.

    A plural suffix is resolved by ``amount`` and ``unit`` (see
    :func:`resolve_plural`): "Kartoffel(n)" gives "Kartoffel" for an amount of
    1 without a unit, otherwise "Kartoffeln".
    """
    if text is None:
        return ""
    return _tidy_name(resolve_plural(_clean(str(text)), amount, unit))


def adjectives_first(name: str) -> str:
    """Move trailing adjectives in front of the noun: "Butter, weiche" -> "weiche Butter".

    Only for a noun followed by a comma and one or two lower case, inflected
    adjectives. Anything else ("Mehl, Type 405", "Wasser, oder Rum") stays as
    it is.
    """
    noun, comma, tail = name.partition(",")
    if not comma or "," in noun or "(" in name:
        return name
    noun = noun.strip()
    words = [word for word in re.split(r"[\s,]+", tail.strip()) if word]
    if not noun or not noun[0].isupper() or not 1 <= len(words) <= 2:
        return name
    for word in words:
        if word in _NOT_ADJECTIVES or _ADJECTIVE_RE.match(word) is None:
            return name
    return f"{' '.join(words)} {noun}"


def clean_note(text: str | None) -> str | None:
    """Tidy a note: no comma or semicolon at the start or end, one space."""
    if text is None:
        return None
    cleaned = _SPACE_RE.sub(" ", str(text)).strip(" ,;")
    return cleaned or None


def split_vague_amount(ingredient: Ingredient) -> Ingredient:
    """Turn "nach Geschmack Salz" (no amount) into name "Salz", note "nach Geschmack"."""
    if ingredient.amount is not None or ingredient.unit is not None:
        return ingredient
    match = _VAGUE_AMOUNT_RE.match(ingredient.name)
    if match is None:
        return ingredient
    note = ", ".join(item for item in (match.group("phrase"), ingredient.note) if item)
    return Ingredient(
        name=_tidy_name(match.group("name")),
        amount=None,
        unit=None,
        note=note,
        raw=ingredient.raw,
    )


def split_pair(ingredient: Ingredient) -> list[Ingredient]:
    """Split "Salz und Pfeffer" (no amount) into two ingredients.

    Only this pair, in both orders and with "&". Everything else comes back
    unchanged as a one-item list.
    """
    if ingredient.amount is not None or ingredient.unit is not None:
        return [ingredient]
    match = _PAIR_RE.match(ingredient.name.strip())
    if match is None or match.group(1).lower() == match.group(2).lower():
        return [ingredient]
    return [
        Ingredient(name=part.capitalize(), note=ingredient.note, raw=ingredient.raw)
        for part in (match.group(1), match.group(2))
    ]


def finish_ingredients(items: list[Ingredient]) -> list[Ingredient]:
    """Apply the rules every source shares to a list of ingredients."""
    result: list[Ingredient] = []
    for item in items:
        result.extend(split_pair(split_vague_amount(item)))
    return result


def format_amount(amount: float | None) -> str:
    """Format a quantity the German way: ``1.5`` -> ``1,5``, ``2.0`` -> ``2``."""
    if amount is None:
        return ""
    text = f"{amount:.3f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _has_capital_word(text: str) -> bool:
    """Return True if a word of ``text`` starts with a capital (a noun)."""
    return any(word[0].isupper() for word in _CAPITAL_WORD_RE.findall(text))


def _split_top_level_comma(text: str) -> tuple[str, str | None]:
    """Split at the first comma outside brackets.

    Exception: "gemahlene, geschälte Mandeln" is one name. The part before the
    comma holds no capitalized word (no noun yet) and the part after it does
    (the noun comes later). "onion, finely chopped" and "butter, melted" have
    no noun after the comma and are split as always.
    """
    depth = 0
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            before, _ = _extract_brackets(text[:index])
            after, _ = _extract_brackets(text[index + 1 :])
            if _has_capital_word(before) or not _has_capital_word(after):
                return text[:index], text[index + 1 :]
    return text, None


def _extract_brackets(text: str) -> tuple[str, list[str]]:
    """Remove outermost ``(...)`` groups and return the text plus their contents.

    A group inside a group stays in the note as written.
    """
    notes: list[str] = []
    kept: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(text):
        if char == "(":
            if depth == 0:
                start = index
            depth += 1
        elif char == ")":
            if depth == 0:
                kept.append(" ")
                continue
            depth -= 1
            if depth == 0:
                inner = _SPACE_RE.sub(" ", text[start + 1 : index]).strip()
                if inner:
                    notes.append(inner)
                kept.append(" ")
        elif depth == 0:
            kept.append(char)
    if depth > 0:
        # Unbalanced bracket: keep its text as part of the line.
        kept.append(" " + text[start + 1 :].replace("(", " ").replace(")", " "))
    return _SPACE_RE.sub(" ", "".join(kept)).strip(), notes


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


def _drop_unit_suffix(rest: str) -> str:
    """Drop a plural suffix after a leading unit word: "Zehe(n) Knoblauch"."""
    match = _UNIT_SUFFIX_RE.match(rest)
    if match is None or match.group(1).rstrip(".").lower() not in _UNIT_LOOKUP:
        return rest
    return match.group(1) + rest[match.end() :]


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
        unit, rest = _take_unit(_drop_unit_suffix(rest))
        rest = rest.lstrip(" .") if unit is not None else rest
    else:
        word = _WORD_RE.match(text)
        if word and word.group(1).lower() in _NUMBER_WORDS:
            candidate_unit, after = _take_unit(
                _drop_unit_suffix(text[word.end() :].lstrip())
            )
            if candidate_unit is not None:
                amount = _NUMBER_WORDS[word.group(1).lower()]
                unit, rest = candidate_unit, after

    has_amount = amount is not None
    rest = resolve_plural(rest, amount, unit)

    # Notes keep the order of the line: brackets in the name, then the text
    # after the comma, then its brackets.
    if has_amount:
        name_part, tail = _split_top_level_comma(rest)
        name_part, bracket_notes = _extract_brackets(name_part)
        notes.extend(bracket_notes)
        if tail is not None:
            tail_text, tail_notes = _extract_brackets(tail)
            if _tidy_name(tail_text):
                notes.append(_tidy_name(tail_text))
            notes.extend(tail_notes)
    else:
        name_part, bracket_notes = _extract_brackets(rest)
        notes.extend(bracket_notes)

    name = _tidy_name(name_part)
    if not name and unit is not None:
        # "2 Becher": the unit word is all we know.
        name, unit = unit, None
    note = ", ".join(item for item in notes if item) or None
    return Ingredient(name=name, amount=amount, unit=unit, note=note, raw=raw)
