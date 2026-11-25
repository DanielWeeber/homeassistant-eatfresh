"""Tests for scaling the amounts of a recipe to other servings."""

from __future__ import annotations

import dataclasses
import inspect
import re

import pytest

from custom_components.eatfresh import portions
from custom_components.eatfresh.portions import (
    DEFAULT_SERVINGS,
    MAX_DEFAULT_SERVINGS,
    MAX_SERVINGS,
    MIN_SERVINGS,
    PACKAGE_UNITS,
    Scaled,
    round_metric,
    scale_description,
    start_servings,
    unit_class,
)

# Descriptions as EatFresh writes them today.
WRITTEN = [
    "250g",
    "1.5kg",
    "2 EL",
    "3",
    "1 Dose, (400 g)",
    "0.5 Bund",
    "Prise",
    "(nach Geschmack)",
    "250g, (Type 405)",
    "1 Pck.",
    "200ml",
    "1 Msp.",
    "2 Zehe, (gepresst)",
    "0.25l",
    "500mg",
]
# Descriptions typed by hand in KitchenOwl.
TYPED = [
    "1/2 Bund",
    "½ TL",
    "2-3",
    "ca. 200 g",
    "etwas",
    "1 große",
    "",
    "   ",
    "1 1/2 EL",
    "1½ l",
    "2–3 Dosen",
    "1,5 kg",
    "  2  EL ,(gehäuft)  ",
    "2 EL gehäuft",
    "1 kleine Dose",
    "2 x 400 g",
    "1 Dose (400 g, abgetropft), 1 TL",
]


def scale(text: object, base: object, servings: object) -> str:
    return scale_description(text, base, servings).description  # type: ignore[arg-type]


def test_constants() -> None:
    assert (MIN_SERVINGS, MAX_SERVINGS) == (1, 99)
    assert (DEFAULT_SERVINGS, MAX_DEFAULT_SERVINGS) == (3, 12)


def test_module_is_pure() -> None:
    imports = [
        line
        for line in inspect.getsource(portions).splitlines()
        if line.startswith(("import ", "from "))
    ]
    assert not [line for line in imports if "homeassistant" in line]
    assert not [line for line in imports if "aiohttp" in line]
    assert not [line for line in imports if "kitchenowl" in line]


# --- start_servings ---------------------------------------------------------


@pytest.mark.parametrize(
    ("base", "default", "expected"),
    [
        (None, 3, None),
        (0, 3, None),
        (-2, 3, None),
        (1, 3, 1),  # "1 cake"
        (2, 3, 3),
        (4, 3, 3),
        (8, 3, 3),
        (9, 3, 9),  # "12 pieces"
        (12, 3, 12),
        (120, 3, 120),
        (4, 5, 5),
        (4, 1, 1),
        (4, 12, 12),
        (3, 3, 3),
        # A default outside 1 to 12 is pulled into the range
        (4, 99, 12),
        (4, 0, 1),
        (4, None, 3),
        (4, "5", 3),
        # Odd types for the servings of the recipe
        (4.0, 3, 3),
        (4.5, 3, None),
        ("4", 3, None),
        (True, 3, None),
    ],
)
def test_start_servings(base: object, default: object, expected: int | None) -> None:
    assert start_servings(base, default) == expected  # type: ignore[arg-type]


# --- unit_class -------------------------------------------------------------


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        ("g", "mass"),
        ("G", "mass"),
        ("Gramm", "mass"),
        ("kg", "mass"),
        ("Kilo", "mass"),
        ("ml", "volume"),
        ("l", "volume"),
        ("Liter", "volume"),
        ("EL", "spoon"),
        ("el", "spoon"),
        ("Esslöffel", "spoon"),
        ("TL", "spoon"),
        ("Tasse", "spoon"),
        ("Tassen", "spoon"),
        ("Prise", "pinch"),
        ("Msp.", "pinch"),
        ("Msp", "pinch"),
        ("Schuss", "pinch"),
        ("Spritzer", "pinch"),
        ("Handvoll", "pinch"),
        ("Dose", "package"),
        ("Dosen", "package"),
        ("Pck.", "package"),
        ("pck", "package"),
        ("Packung", "package"),
        ("Becher", "package"),
        ("Glas", "package"),
        ("Gläser", "package"),
        ("Flasche", "package"),
        ("Tüte", "package"),
        ("Beutel", "package"),
        ("Würfel", "package"),
        ("Rolle", "package"),
        ("Kästchen", "package"),
        ("Bund", "package"),
        ("Kopf", "package"),
        ("Knolle", "package"),
        ("Kugel", "package"),
        ("Stange", "package"),
        ("Tube", "package"),
        ("Tafel", "package"),
        ("Netz", "package"),
        ("Schale", "package"),
        ("can", "package"),
        ("cans", "package"),
        ("tin", "package"),
        ("pack", "package"),
        ("package", "package"),
        ("jar", "package"),
        ("bottle", "package"),
        ("bunch", "package"),
        ("bag", "package"),
        ("", "piece"),
        ("  ", "piece"),
        ("Stück", "piece"),
        ("Stk.", "piece"),
        ("Zehe", "piece"),
        ("Zehen", "piece"),
        ("Scheibe", "piece"),
        ("Blatt", "piece"),
        ("Blätter", "piece"),
        ("Zweig", "piece"),
        ("Stiel", "piece"),
        # A describing word: the number counts pieces
        ("große", "piece"),
        ("kleine", "piece"),
        ("mittelgroßer", "piece"),
        ("mg", "other"),
        ("cl", "other"),
        ("dl", "other"),
        ("cm", "other"),
        ("Portion", "other"),
        ("Paprika", "piece"),  # an unknown word counts pieces
        ("Tropfen", "other"),
    ],
)
def test_unit_class(unit: str, expected: str) -> None:
    assert unit_class(unit) == expected


def test_unit_class_survives_odd_input() -> None:
    assert unit_class(None) == "piece"  # type: ignore[arg-type]
    assert unit_class(5) == "piece"  # type: ignore[arg-type]


def test_package_units() -> None:
    for spelling in (
        "dose",
        "dosen",
        "pck",
        "pck.",
        "packung",
        "päckchen",
        "becher",
        "glas",
        "gläser",
        "bund",
        "tüte",
        "beutel",
        "netz",
        "schale",
        "can",
        "tins",
        "jar",
        "bottle",
        "bunch",
        "bag",
    ):
        assert spelling in PACKAGE_UNITS, spelling
    for spelling in ("g", "kg", "ml", "el", "tl", "prise", "stück", "zehe", "", "x"):
        assert spelling not in PACKAGE_UNITS, spelling
    assert all(spelling == spelling.lower() for spelling in PACKAGE_UNITS)
    assert all(unit_class(spelling) == "package" for spelling in PACKAGE_UNITS)


# --- nothing to scale -------------------------------------------------------


@pytest.mark.parametrize("text", WRITTEN + TYPED)
@pytest.mark.parametrize(
    ("base", "servings"),
    [(4, 4), (1, 1), (None, 3), (4, None), (None, None), (120, 120)],
)
def test_same_or_unknown_servings_keep_every_character(
    text: str, base: int | None, servings: int | None
) -> None:
    result = scale_description(text, base, servings)
    assert result.description == text
    assert result.scaled is False
    assert result.rounded_from is None


@pytest.mark.parametrize(
    ("base", "servings"),
    [
        (0, 3),
        (-4, 3),
        (4, 0),
        (4, -1),
        (4, 100),
        (4, 10**9),
        (10**30, 3),
        (1001, 3),
        ("4", 3),
        (4, "3"),
        (4.5, 3),
        (4, 2.5),
        (True, 3),
        (4, True),
        (float("nan"), 3),
        (float("inf"), 3),
        (4, float("nan")),
        ([4], 3),
    ],
)
def test_absurd_servings_keep_every_character(base: object, servings: object) -> None:
    for text in WRITTEN + TYPED:
        result = scale_description(text, base, servings)  # type: ignore[arg-type]
        assert result.description == text
        assert result.scaled is False
        assert result.rounded_from is None


def test_whole_floats_count_as_servings() -> None:
    assert scale("500g", 4.0, 3.0) == "375g"


@pytest.mark.parametrize(
    "text", ["Prise", "(nach Geschmack)", "etwas", "", "   ", "1 große Zwiebel"]
)
def test_text_without_a_readable_number_is_not_scaled(text: str) -> None:
    result = scale_description(text, 4, 3)
    assert result == Scaled(text, False, None, result.packages)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, ""), (3, "3"), (2.5, "2.5"), (True, ""), (["2 EL"], ""), (b"2 EL", "")],
)
def test_no_text_is_never_scaled(value: object, expected: str) -> None:
    for base, servings in ((4, 3), (4, 4), (None, None)):
        assert scale_description(value, base, servings) == Scaled(  # type: ignore[arg-type]
            expected, False, None, ()
        )


# --- examples of the contract -----------------------------------------------


def test_can_is_rounded_up() -> None:
    assert scale_description("1 Dose", 2, 3) == Scaled(
        "2 Dose", True, "1.5", (("Dose", 2, 1.5),)
    )


def test_eggs_are_rounded_up() -> None:
    assert scale_description("3", 4, 3) == Scaled("3", True, "2.25", ())


@pytest.mark.parametrize(
    ("text", "base", "servings", "expected"),
    [
        ("500g", 4, 3, "375g"),
        ("1kg", 4, 3, "750g"),
        ("1 EL", 4, 3, "0.75 EL"),
        ("1 Prise", 4, 2, "1 Prise"),
    ],
)
def test_contract_examples(text: str, base: int, servings: int, expected: str) -> None:
    result = scale_description(text, base, servings)
    assert result == Scaled(expected, True, None, ())


# --- real descriptions ------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "base", "servings", "expected", "rounded_from"),
    [
        # As EatFresh writes them, from 4 to 3 servings
        ("250g", 4, 3, "190g", None),
        ("1.5kg", 4, 3, "1.15kg", None),
        ("2 EL", 4, 3, "1.5 EL", None),
        ("3", 4, 3, "3", "2.25"),
        ("1 Dose, (400 g)", 4, 3, "1 Dose, (400 g)", "0.75"),
        ("0.5 Bund", 4, 3, "1 Bund", "0.38"),
        ("250g, (Type 405)", 4, 3, "190g, (Type 405)", None),
        ("1 Pck.", 4, 3, "1 Pck.", "0.75"),
        ("200ml", 4, 3, "150ml", None),
        ("1 Msp.", 4, 3, "1 Msp.", None),
        ("2 Zehe, (gepresst)", 4, 3, "2 Zehe, (gepresst)", "1.5"),
        ("0.25l", 4, 3, "190ml", None),
        ("500mg", 4, 3, "375mg", None),
        # The same from 2 to 3 servings
        ("250g", 2, 3, "375g", None),
        ("1.5kg", 2, 3, "2.25kg", None),
        ("2 EL", 2, 3, "3 EL", None),
        ("3", 2, 3, "5", "4.5"),
        ("1 Dose, (400 g)", 2, 3, "2 Dose, (400 g)", "1.5"),
        ("0.5 Bund", 2, 3, "1 Bund", "0.75"),
        ("1 Pck.", 2, 3, "2 Pck.", "1.5"),
        ("200ml", 2, 3, "300ml", None),
        # Typed by hand
        ("1/2 Bund", 4, 3, "1 Bund", "0.38"),
        ("½ TL", 4, 3, "0.5 TL", None),
        ("2-3", 4, 3, "2-3", "1.5"),
        ("ca. 200 g", 4, 3, "ca. 150g", None),
        ("1 große", 4, 3, "1 große", "0.75"),
        ("2 kleine", 2, 3, "3 kleine", None),
        ("1 1/2 EL", 4, 8, "3 EL", None),
        ("1½ l", 4, 1, "375ml", None),
        ("¾ l", 3, 1, "250ml", None),
        ("2–3 Dosen", 2, 3, "3–5 Dosen", None),
        ("2 Paprika", 4, 3, "2 Paprika", "1.5"),
        ("2 EL gehäuft", 2, 3, "3 EL gehäuft", None),
        # Parts that cannot be read stay as they are
        ("1 kleine Dose", 2, 3, "1 kleine Dose", None),
        ("2 x 400 g", 2, 3, "2 x 400 g", None),
        ("-2 EL", 2, 3, "-2 EL", None),
        ("1/0 Bund", 2, 3, "1/0 Bund", None),
        ("0g", 2, 3, "0g", None),
        ("0 Dose", 2, 3, "0 Dose", None),
        (".5 kg", 2, 3, ".5 kg", None),
        ("1. Dose", 2, 3, "1. Dose", None),
        ("1e3 g", 2, 3, "1e3 g", None),
        ("2 TK-Packung", 2, 3, "2 TK-Packung", None),
        ("2 °C", 2, 3, "2 °C", None),
    ],
)
def test_real_descriptions(
    text: str, base: int, servings: int, expected: str, rounded_from: str | None
) -> None:
    result = scale_description(text, base, servings)
    assert result.description == expected
    assert result.rounded_from == rounded_from


# --- reading ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # A comma between digits is a decimal sign, else it separates
        ("1,5 kg", "2.25kg"),
        ("2 EL, 2 TL", "3 EL, 3 TL"),
        # Commas inside brackets do not separate
        ("1 Dose, (400 g, abgetropft)", "2 Dose, (400 g, abgetropft)"),
        ("1 Dose (400 g, abgetropft), 2 TL", "2 Dose (400 g, abgetropft), 3 TL"),
        ("(a (b, 2 c), 2 d), 2 EL", "(a (b, 2 c), 2 d), 3 EL"),
        ("2 EL, (offen, 2", "3 EL, (offen, 2"),
        ("2 EL), 2 TL", "2 EL), 3 TL"),
        # White space around the parts stays
        ("2 EL,2 TL ,  2", "3 EL,3 TL ,  3"),
        ("  2  EL ,(gehäuft)  ", "  3 EL ,(gehäuft)  "),
        # A note right after the unit stays
        ("2 EL (gehäuft)", "3 EL (gehäuft)"),
        ("2 Dose(400 g)", "3 Dose(400 g)"),
        ("2 (mittelgroß)", "3 (mittelgroß)"),
        # Unreadable parts stay, the others are scaled, the order stays
        ("etwas, 2 EL, Prise, 2", "etwas, 3 EL, Prise, 3"),
        # "ca." and its relatives stay in front
        ("ca. 2 EL", "ca. 3 EL"),
        ("ca.200g", "ca.300g"),
        ("Ca. 2 Dose", "Ca. 3 Dose"),
        ("etwa 2 EL", "etwa 3 EL"),
        ("circa 200 ml", "circa 300ml"),
        # Ranges: both ends are scaled
        ("2-4", "3-6"),
        ("2 - 4 EL", "3 - 6 EL"),
        ("2–4 TL", "3–6 TL"),
        ("2 bis 4 Zehe", "3 bis 6 Zehe"),
        ("1-2 kg", "1.5-3kg"),
        # The unit stays as it was written
        ("2 Dosen", "3 Dosen"),
        ("2 Packung", "3 Packung"),
        ("2 el", "3 el"),
        ("200G", "300G"),
        ("2 Liter", "3 Liter"),
        ("2EL", "3 EL"),
        ("200 g", "300g"),
        ("2 Stück", "3 Stück"),
        ("2 m²", "3 m²"),
    ],
)
def test_reading_and_writing(text: str, expected: str) -> None:
    assert scale(text, 2, 3) == expected


def test_range_that_ends_up_equal_becomes_one_number() -> None:
    assert scale_description("1-2 Dose", 2, 1) == Scaled(
        "1 Dose", True, "0.5", (("Dose", 1, 0.5),)
    )


def test_range_across_one_kilogram_is_written_in_grams() -> None:
    assert scale("0.8-1.2 kg", 4, 3) == "600-900g"
    assert scale("1-2 l", 4, 3) == "750-1500ml"


@pytest.mark.parametrize(
    "text",
    [
        "99999999999999999999g",
        "1000001g",
        "9" * 5000 + " Dose",
        "1/" + "9" * 5000,
        "1." + "3" * 5000 + "kg",
        "(" * 3000 + "2 EL",
        "2 EL" + ")" * 3000,
        "," * 3000,
    ],
)
def test_absurd_numbers_stay(text: str) -> None:
    result = scale_description(text, 2, 3)
    assert result.description == text
    assert result.packages == ()


def test_largest_number_is_still_scaled() -> None:
    assert scale("1000000g", 1, 99) == "99000000g"
    assert scale("1000000", 1, 99) == "99000000"


# --- rounding ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "base", "servings", "expected"),
    [
        # g and ml: step 1 below 20
        ("17g", 2, 1, "9g"),  # 8.5
        ("25g", 2, 1, "13g"),  # 12.5
        ("2g", 4, 3, "2g"),  # 1.5
        ("25g", 4, 3, "19g"),  # 18.75
        # step 5 below 250
        ("30g", 4, 3, "25g"),  # 22.5
        ("50g", 4, 3, "40g"),  # 37.5
        ("100g", 3, 1, "35g"),  # 33.3
        ("125g", 4, 3, "95g"),  # 93.75
        ("330g", 4, 3, "250g"),  # 247.5
        ("250ml", 4, 3, "190ml"),  # 187.5
        # step 10 below 1000
        ("1000g", 3, 1, "330g"),  # 333.3
        ("503g", 4, 3, "380g"),  # 377.25
        ("750g", 4, 3, "560g"),  # 562.5
        ("700ml", 4, 3, "525ml"),  # an exact multiple of 5 stays
        ("500g", 4, 3, "375g"),
        ("1300g", 4, 3, "975g"),
        # step 50 from 1000
        ("1500g", 4, 3, "1150g"),  # 1125
        ("2000g", 3, 2, "1350g"),  # 1333.3
        ("800g", 2, 4, "1600g"),  # stays in g
        ("1340ml", 4, 3, "1000ml"),  # 1005
        # never 0: two significant digits
        ("1g", 4, 1, "0.25g"),
        ("1g", 8, 3, "0.38g"),  # 0.375
        ("1g", 3, 1, "0.33g"),
        ("1g", 100, 1, "0.01g"),
        ("1g", 1000, 1, "0.001g"),
        ("0.5g", 1000, 1, "0.001g"),  # the smallest number that can be written
        ("1ml", 3, 2, "1ml"),  # 0.67
        # kg and l: below 1 in g or ml
        ("1kg", 3, 1, "330g"),
        ("0.5kg", 2, 3, "750g"),
        ("1l", 4, 2, "500ml"),
        ("1 Liter", 4, 3, "750ml"),
        ("1 L", 4, 3, "750ml"),
        ("0.002kg", 4, 3, "2g"),  # 1.5 g
        # from 1: step 0.05
        ("0.5kg", 2, 4, "1kg"),
        ("2kg", 4, 3, "1.5kg"),
        ("1kg", 3, 4, "1.35kg"),  # 1.333
        ("1.5l", 4, 3, "1.15l"),  # 1.125
        ("1l", 2, 3, "1.5l"),
        ("2 Liter", 4, 3, "1.5 Liter"),
        # spoon: step 0.5 from 1
        ("3 EL", 4, 3, "2.5 EL"),  # 2.25
        ("1 EL", 4, 5, "1.5 EL"),  # 1.25
        ("1.5 EL", 4, 3, "1 EL"),  # 1.125
        ("1 Tasse", 2, 3, "1.5 Tasse"),
        # below 1: step 0.25, at least 0.25
        ("1 TL", 4, 1, "0.25 TL"),
        ("1 EL", 3, 2, "0.75 EL"),  # 0.667
        ("1 TL", 8, 1, "0.25 TL"),  # 0.125
        ("1 TL", 20, 1, "0.25 TL"),  # 0.05
        ("1 EL", 10, 9, "1 EL"),  # 0.9
        # pinch: whole number, at least 1
        ("1 Prise", 4, 6, "2 Prise"),  # 1.5
        ("2 Prise", 4, 5, "3 Prise"),  # 2.5
        ("1 Msp.", 4, 3, "1 Msp."),
        ("1 Schuss", 2, 5, "3 Schuss"),  # 2.5
        ("1 Handvoll", 4, 9, "2 Handvoll"),  # 2.25
        ("1 Spritzer", 4, 1, "1 Spritzer"),  # 0.25
        # package: up to whole packs, a little above goes down, never below 1
        ("1 Dose", 2, 3, "2 Dose"),
        ("2 Dose", 25, 26, "2 Dose"),  # 2.08
        ("1 Dose", 10, 11, "1 Dose"),  # 1.1
        ("1 Dose", 10, 12, "2 Dose"),  # 1.2
        ("1 Dose", 4, 1, "1 Dose"),  # 0.25
        ("1 Dose", 1000, 1, "1 Dose"),
        ("3 Becher", 4, 3, "3 Becher"),  # 2.25
        ("2 Bund", 4, 2, "1 Bund"),
        ("4 Glas", 4, 3, "3 Glas"),
        ("1 can", 2, 3, "2 can"),
        # piece: like package
        ("4", 4, 3, "3"),
        ("2 Zehe", 4, 3, "2 Zehe"),  # 1.5
        ("1 Scheibe", 4, 3, "1 Scheibe"),
        ("10 Blatt", 4, 3, "8 Blatt"),  # 7.5
        ("10", 10, 11, "11"),
        ("20", 20, 21, "21"),
        ("1", 99, 1, "1"),
        # other: like spoon
        ("5 cm", 4, 3, "4 cm"),  # 3.75
        ("2 cl", 4, 3, "1.5 cl"),
        ("4 dl", 4, 1, "1 dl"),
        ("1 Portion", 4, 1, "0.25 Portion"),
    ],
)
def test_rounding(text: str, base: int, servings: int, expected: str) -> None:
    assert scale(text, base, servings) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (8.5, 9.0),
        (19.4, 19.0),
        (22.0, 20.0),
        (249.0, 250.0),
        (333.33, 330.0),
        (375.0, 375.0),
        (377.0, 380.0),
        (1005.0, 1000.0),
        (1125.0, 1150.0),
        (0.375, 0.38),
        (0.4, 0.4),
        (99.99999999999999, 100.0),
        (200.00000000000003, 200.0),
        (200, 200.0),
    ],
)
def test_round_metric(value: float, expected: float) -> None:
    assert round_metric(value) == expected


@pytest.mark.parametrize(
    "value", [0, -5, float("nan"), float("inf"), None, "200", True, 1e-12]
)
def test_round_metric_survives_odd_input(value: object) -> None:
    assert round_metric(value) == 0.0  # type: ignore[arg-type]


_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_GOOD_NUMBER = re.compile(r"\d+(?:\.\d{1,3})?")
_BRACKETS = re.compile(r"\([^()]*\)")
_EXPONENT = re.compile(r"\d[eE][+-]?\d")
_NEGATIVE = re.compile(r"(?:^|[\s,])-\s*\d")


@pytest.mark.parametrize("text", WRITTEN + TYPED)
def test_numbers_stay_clean(text: str) -> None:
    """Never 0, no negative numbers, no float tails, no exponent."""
    for base in (*range(1, 13), 24, 100, 1000):
        for servings in (*range(1, 13), 50, 99):
            result = scale_description(text, base, servings)
            if not result.scaled:
                assert result.description == text
                continue
            outside = _BRACKETS.sub("", result.description)
            assert not _EXPONENT.search(outside), result
            assert not _NEGATIVE.search(outside), result
            for number in _NUMBER.findall(outside):
                assert _GOOD_NUMBER.fullmatch(number), result
                assert float(number) > 0, result
                assert not number.endswith(".0"), result
            if result.rounded_from is not None:
                assert re.fullmatch(r"\d+(?:\.\d{1,2})?", result.rounded_from)
                assert float(result.rounded_from) > 0
            for unit, count, exact in result.packages:
                assert unit_class(unit) == "package"
                assert isinstance(count, int)
                assert count >= 1
                assert exact > 0


@pytest.mark.parametrize(
    ("text", "base", "servings"),
    [("250g", 4, 3), ("1.5kg", 2, 3), ("200ml", 4, 3), ("2l", 4, 3), ("500mg", 4, 3)],
)
def test_weights_and_volumes_stay_without_a_space(
    text: str, base: int, servings: int
) -> None:
    assert re.fullmatch(r"\d+(?:\.\d+)?(?:mg|g|kg|ml|l)", scale(text, base, servings))


@pytest.mark.parametrize("text", ["2 EL", "1 Dose", "3 Zehe", "1 Pck.", "2 Prise"])
def test_other_units_keep_their_unit_and_a_space(text: str) -> None:
    unit = text.split(" ", 1)[1]
    for servings in range(1, 13):
        if servings == 4:
            continue
        assert re.fullmatch(
            rf"\d+(?:\.\d+)? {re.escape(unit)}", scale(text, 4, servings)
        )


def test_result_reads_the_same_again() -> None:
    """What was written can be read and scaled again."""
    for text in WRITTEN:
        once = scale_description(text, 4, 3)
        again = scale_description(once.description, 3, 3)
        assert again.description == once.description
        assert [pack[:2] for pack in again.packages] == [
            pack[:2] for pack in once.packages
        ]


# --- rounded_from -----------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "base", "servings", "expected"),
    [
        ("2 Dose", 25, 26, "2.08"),
        ("1 Dose", 3, 1, "0.33"),
        ("2 Dose", 3, 1, "0.67"),
        ("1 Dose", 8, 1, "0.13"),  # 0.125, a half goes up
        ("1 Dose", 1000, 1, "0.01"),  # never "0"
        ("4 Glas", 4, 3, None),  # exactly 3
        ("200", 199, 1, None),  # 1.005 is close enough to 1
        ("2 EL", 4, 3, None),  # only whole pieces are remarked
        ("1 Prise", 4, 3, None),
        ("500g", 4, 3, None),
        # the first part that was rounded
        ("3 EL, 4 Glas, 1 Dose, 3", 2, 3, "1.5"),
        ("3, 1 Dose", 2, 3, "4.5"),
    ],
)
def test_rounded_from(
    text: str, base: int, servings: int, expected: str | None
) -> None:
    assert scale_description(text, base, servings).rounded_from == expected


# --- packages ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "base", "servings", "expected"),
    [
        # Also without scaling
        ("1 Dose", 4, 4, (("Dose", 1, 1.0),)),
        ("1 Dose", None, None, (("Dose", 1, 1.0),)),
        ("1 Dose, (400 g)", None, 3, (("Dose", 1, 1.0),)),
        (
            "2 Dose, 1 Bund, 250g, Glas, 3",
            4,
            4,
            (("Dose", 2, 2.0), ("Bund", 1, 1.0), ("Glas", 1, 1.0)),
        ),
        # A broken count on the list: whole packs to buy and the exact number
        ("0.5 Bund", 4, 4, (("Bund", 1, 0.5),)),
        ("1.5 Dose", None, None, (("Dose", 2, 1.5),)),
        # The unit is the canonical spelling
        ("2 Dosen", 4, 4, (("Dose", 2, 2.0),)),
        ("1 Packung", 2, 3, (("Pck.", 2, 1.5),)),
        ("1 Pck.", 2, 3, (("Pck.", 2, 1.5),)),
        ("2 Gläser", 4, 4, (("Glas", 2, 2.0),)),
        ("2 cans", 4, 4, (("can", 2, 2.0),)),
        # A unit alone counts as one pack
        ("Dose", 4, 4, (("Dose", 1, 1.0),)),
        ("Dose", None, None, (("Dose", 1, 1.0),)),
        ("Dose (400 g)", 4, 4, (("Dose", 1, 1.0),)),
        ("Dose", 2, 3, (("Dose", 2, 1.5),)),
        # Scaled: packs after rounding and the exact number
        ("1 Dose", 2, 3, (("Dose", 2, 1.5),)),
        ("1 Dose", 3, 1, (("Dose", 1, 0.3333),)),
        ("2 Dose", 25, 26, (("Dose", 2, 2.08),)),
        ("0.0001 Dose", 4, 1, (("Dose", 1, 0.0001),)),  # never 0
        ("4 Glas", 4, 3, (("Glas", 3, 3.0),)),
        ("1 Dose, 1 Becher", 2, 3, (("Dose", 2, 1.5), ("Becher", 2, 1.5))),
        # A range counts with its lower end
        ("2-3 Dose", 2, 3, (("Dose", 3, 3.0),)),
        # No package unit
        ("250g", 4, 3, ()),
        ("3", 4, 3, ()),
        ("2 Zehe", 4, 3, ()),
        ("2 EL", 4, 3, ()),
        ("Prise", 4, 3, ()),
        ("0 Dose", 4, 3, ()),
        ("", 4, 3, ()),
    ],
)
def test_packages(
    text: str,
    base: int | None,
    servings: int | None,
    expected: tuple[tuple[str, int, float], ...],
) -> None:
    assert scale_description(text, base, servings).packages == expected


def test_scaled_is_frozen() -> None:
    result = scale_description("1 Dose", 2, 3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.scaled = False  # type: ignore[misc]


# --- changes after the independent review of 0.5.0 -------------------------

# Neighbours that must not change: (text, base, servings, description).
NEIGHBOURS = [
    ("250g, (Type 405)", 4, 8, "500g, (Type 405)"),
    ("1 Dose, (400 g)", 4, 8, "2 Dose, (400 g)"),
    ("1.125kg", 4, 8, "2.25kg"),
    ("0.125 l", 4, 8, "250ml"),
    ("2 EL", 4, 8, "4 EL"),
    ("1 große", 4, 3, "1 große"),
    ("2-3", 4, 8, "4-6"),
    ("0.5 Bund", 4, 8, "1 Bund"),
    ("2.25", 4, 8, "5"),
    ("2 EL, 2 TL", 4, 8, "4 EL, 4 TL"),
    ("2 EL,2 TL", 4, 8, "4 EL,4 TL"),
]


@pytest.mark.parametrize(("text", "base", "servings", "expected"), NEIGHBOURS)
def test_review_neighbours_stay(
    text: str, base: int, servings: int, expected: str
) -> None:
    assert scale(text, base, servings) == expected


# Every new reading, unchanged with factor 1 and unknown base.
NEW_READINGS = [
    "1,5 kg",
    "1,5 EL",
    "1,5 Dose",
    "1,25 l, (kalt)",
    "1.000 g",
    "1.250 g",
    "1.500 kg",
    "Dose",
    "Bund",
    "EL",
    "Zehe (gepresst)",
    "1 Große",
    "3 Eier",
    "2 EL gehäuft",
    "1 Prise Salz",
    "2  EL  gehäuft ",
]


@pytest.mark.parametrize("text", NEW_READINGS)
@pytest.mark.parametrize(("base", "servings"), [(4, 4), (None, 3), (None, None)])
def test_review_new_readings_keep_every_character(
    text: str, base: int | None, servings: int | None
) -> None:
    result = scale_description(text, base, servings)
    assert result.description == text
    assert result.scaled is False
    assert result.rounded_from is None


# 1: a comma between digits is a decimal sign.
@pytest.mark.parametrize(
    ("text", "base", "servings", "expected"),
    [
        ("1,5 kg", 4, 8, "3kg"),
        ("1,5 EL", 4, 8, "3 EL"),
        ("1,5kg", 4, 8, "3kg"),
        ("0,5 l", 4, 8, "1l"),
        ("0,5 l", 4, 2, "250ml"),
        ("1,5-2 kg", 4, 8, "3-4kg"),
        ("1,25 l, (kalt)", 4, 8, "2.5l, (kalt)"),
        ("1,5 kg, 2 EL", 4, 8, "3kg, 4 EL"),
        ("2, 3 EL", 4, 8, "4, 6 EL"),  # a comma and a space separate
        ("2 ,3 EL", 4, 8, "4 ,6 EL"),
        ("1,5", 4, 8, "3"),
    ],
)
def test_review_decimal_comma(
    text: str, base: int, servings: int, expected: str
) -> None:
    assert scale(text, base, servings) == expected


@pytest.mark.parametrize(
    ("text", "base", "servings", "expected"),
    [
        ("1,5 Dose", None, None, (("Dose", 2, 1.5),)),
        ("1,5 Dose", 4, 4, (("Dose", 2, 1.5),)),
        ("1,5 Dose", 2, 4, (("Dose", 3, 3.0),)),
        ("Dose", None, None, (("Dose", 1, 1.0),)),
        ("Dose", 2, 6, (("Dose", 3, 3.0),)),
        ("Bund, 1,5 Glas", None, None, (("Bund", 1, 1.0), ("Glas", 2, 1.5))),
    ],
)
def test_review_packages_follow_the_new_reading(
    text: str,
    base: int | None,
    servings: int | None,
    expected: tuple[tuple[str, int, float], ...],
) -> None:
    assert scale_description(text, base, servings).packages == expected


# 2: a unit alone counts as 1, pinch stays alone.
@pytest.mark.parametrize(
    ("text", "base", "servings", "expected", "rounded_from"),
    [
        ("Dose", 2, 6, "3 Dose", None),
        ("Bund", 4, 12, "3 Bund", None),
        ("Bund", 4, 8, "2 Bund", None),
        ("Dose", 2, 3, "2 Dose", "1.5"),
        ("Dose", 4, 2, "1 Dose", "0.5"),
        ("Dose (400 g)", 2, 4, "2 Dose (400 g)", None),
        ("EL", 4, 8, "2 EL", None),
        ("EL", 4, 2, "0.5 EL", None),
        ("TL", 2, 3, "1.5 TL", None),
        ("Zehe", 2, 4, "2 Zehe", None),
        ("Stück", 2, 4, "2 Stück", None),
        ("  Bund ", 4, 8, "  2 Bund ", None),
        ("Dosen", 2, 4, "2 Dosen", None),
        ("Prise", 4, 8, "Prise", None),
        ("Msp.", 4, 8, "Msp.", None),
        ("Handvoll", 4, 8, "Handvoll", None),
        ("etwas", 4, 8, "etwas", None),
        ("g", 4, 8, "g", None),
        ("Salz", 4, 8, "Salz", None),
    ],
)
def test_review_unit_alone(
    text: str, base: int, servings: int, expected: str, rounded_from: str | None
) -> None:
    result = scale_description(text, base, servings)
    assert result.description == expected
    assert result.rounded_from == rounded_from
    assert result.scaled is (expected != text)


# 3: a dot for thousands, but never in numbers EatFresh writes itself.
@pytest.mark.parametrize(
    ("text", "base", "servings", "expected"),
    [
        ("1.000 g", 4, 2, "500g"),
        ("1.000 g", 4, 8, "2000g"),
        ("1.250 g", 4, 8, "2500g"),
        ("1.000g", 4, 2, "500g"),
        ("2.500 ml", 4, 2, "1250ml"),
        ("12.500 g", 4, 2, "6250g"),
        ("1.000-1.500 g", 4, 2, "500-750g"),
        ("ca. 1.000 g", 4, 2, "ca. 500g"),
        # Not thousands: no 0 at the end, not three digits, a 0 in front
        ("1.125kg", 4, 8, "2.25kg"),
        ("1.125 g", 4, 8, "2g"),  # 2.25 g
        ("0.5 Bund", 4, 8, "1 Bund"),
        ("2.25", 4, 8, "5"),
        ("2.5", 4, 8, "5"),
        ("0.250 g", 4, 8, "1g"),  # 0.5 g
        ("1.50 g", 4, 8, "3g"),
        ("1.0005 g", 4, 8, "2g"),
        # Nobody needs 1000 kg
        ("1.500 kg", 4, 8, "3kg"),
        ("1.250 l", 4, 8, "2.5l"),
    ],
)
def test_review_thousands(text: str, base: int, servings: int, expected: str) -> None:
    assert scale(text, base, servings) == expected


def test_review_written_numbers_stay_decimals() -> None:
    """Every number EatFresh writes is read back as the same number."""
    for text in ("1.125kg", "0.5 Bund", "2.25", "0.125 l", "1.375 EL", "2.75"):
        for base in range(1, 13):
            once = scale_description(text, 4, base)
            again = scale_description(once.description, base, base)
            assert again.description == once.description
            assert scale(once.description, base, base * 2) != once.description


# 4: a single unknown word after the number counts pieces.
@pytest.mark.parametrize(
    ("text", "base", "servings", "expected", "rounded_from"),
    [
        ("1 Große", 4, 3, "1 Große", "0.75"),
        ("1 große", 4, 3, "1 große", "0.75"),
        ("3 Eier", 4, 3, "3 Eier", "2.25"),
        ("2 Paprika", 4, 3, "2 Paprika", "1.5"),
        ("2 Paprika", 4, 8, "4 Paprika", None),
        ("1 Ei", 4, 2, "1 Ei", "0.5"),
        # Known units keep their class
        ("1 Prise", 4, 3, "1 Prise", None),
        ("1 EL", 4, 3, "0.75 EL", None),
        ("1 TL", 4, 3, "0.75 TL", None),
        ("1 Dose", 4, 3, "1 Dose", "0.75"),
        ("5 cm", 4, 3, "4 cm", None),
        ("2 cl", 4, 3, "1.5 cl", None),
        ("4 Tropfen", 4, 3, "3 Tropfen", None),
        ("100 mg", 4, 3, "75mg", None),
    ],
)
def test_review_unknown_word_counts_pieces(
    text: str, base: int, servings: int, expected: str, rounded_from: str | None
) -> None:
    result = scale_description(text, base, servings)
    assert result.description == expected
    assert result.rounded_from == rounded_from


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        ("Große", "piece"),
        ("Eier", "piece"),
        ("Paprika", "piece"),
        ("Bd.", "piece"),
        ("Prise", "pinch"),
        ("EL", "spoon"),
        ("TL", "spoon"),
        ("Dose", "package"),
        ("mg", "other"),
        ("cl", "other"),
        ("dl", "other"),
        ("cm", "other"),
        ("mm", "other"),
        ("Tropfen", "other"),
        ("große Zwiebel", "other"),
        ("°C", "other"),
        ("2", "other"),
    ],
)
def test_review_unit_class(unit: str, expected: str) -> None:
    assert unit_class(unit) == expected


def test_review_known_units_keep_their_class() -> None:
    for spelling, canonical in portions._LOOKUP.items():
        expected = portions._CLASS_OF.get(canonical, "other")
        assert unit_class(spelling) == expected, spelling


# 5: more words after a known unit stay as they are.
@pytest.mark.parametrize(
    ("text", "base", "servings", "expected"),
    [
        ("2 EL gehäuft", 4, 8, "4 EL gehäuft"),
        ("2 EL gehäuft", 4, 3, "1.5 EL gehäuft"),
        ("1 Prise Salz", 4, 8, "2 Prise Salz"),
        ("1 Prise Salz", 4, 3, "1 Prise Salz"),
        ("1 Dose Tomaten (400 g)", 2, 3, "2 Dose Tomaten (400 g)"),
        ("250 g Mehl", 4, 8, "500g Mehl"),
        ("1 kg Kartoffeln, festkochend", 4, 2, "500g Kartoffeln, festkochend"),
        ("2  EL  gehäuft ", 4, 8, "4 EL  gehäuft "),
        ("2 EL gehäuft, 1 TL", 4, 8, "4 EL gehäuft, 2 TL"),
        ("ca. 2 EL gut gehäuft", 4, 8, "ca. 4 EL gut gehäuft"),
        # An unknown word in front of more words: nothing is read
        ("1 große Zwiebel", 4, 8, "1 große Zwiebel"),
        ("1 kleine Dose", 4, 8, "1 kleine Dose"),
        # Numbers after the unit are no words
        ("2 x 400 g", 2, 3, "2 x 400 g"),
    ],
)
def test_review_words_after_the_unit(
    text: str, base: int, servings: int, expected: str
) -> None:
    assert scale(text, base, servings) == expected
