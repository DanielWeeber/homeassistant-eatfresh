"""Tests for the German ingredient line parser."""

from __future__ import annotations

import pytest

from custom_components.eatfresh.ingredients import (
    clean_name,
    format_amount,
    normalize_unit,
    parse_amount,
    parse_ingredient,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations() -> None:
    """These tests need no Home Assistant instance."""


@pytest.fixture(autouse=True)
def setup_dependencies() -> None:
    """These tests need no Home Assistant instance."""


# line -> (amount, unit, name, note)
CASES = [
    ("250 g Mehl (Type 405)", (250.0, "g", "Mehl", "Type 405")),
    ("250g Mehl", (250.0, "g", "Mehl", None)),
    ("1,5 l Milch", (1.5, "l", "Milch", None)),
    ("1.5 l Milch", (1.5, "l", "Milch", None)),
    ("1/2 TL Salz", (0.5, "TL", "Salz", None)),
    ("½ Bund Petersilie", (0.5, "Bund", "Petersilie", None)),
    ("1 ½ Tassen Zucker", (1.5, "Tasse", "Zucker", None)),
    ("1½ EL Öl", (1.5, "EL", "Öl", None)),
    ("1 1/2 kg Kartoffeln", (1.5, "kg", "Kartoffeln", None)),
    ("¾ l Brühe", (0.75, "l", "Brühe", None)),
    ("1-2 Zwiebeln", (1.0, None, "Zwiebeln", None)),
    ("2 – 3 Scheiben Brot", (2.0, "Scheibe", "Brot", None)),
    ("1 bis 2 EL Honig", (1.0, "EL", "Honig", None)),
    ("200-250 g Zucker", (200.0, "g", "Zucker", None)),
    ("3 Zehen Knoblauch", (3.0, "Zehe", "Knoblauch", None)),
    ("2 Zehe(n) Knoblauch, fein gehackt", (2.0, "Zehe", "Knoblauch", "fein gehackt")),
    ("2 Dose(n) Tomaten", (2.0, "Dose", "Tomaten", None)),
    ("1 Pck. Vanillezucker", (1.0, "Pck.", "Vanillezucker", None)),
    ("1 Päckchen Backpulver", (1.0, "Pck.", "Backpulver", None)),
    ("1 Prise Salz", (1.0, "Prise", "Salz", None)),
    ("eine Prise Zucker", (1.0, "Prise", "Zucker", None)),
    ("1 Becher Sahne", (1.0, "Becher", "Sahne", None)),
    ("2 Stück Äpfel", (2.0, "Stück", "Äpfel", None)),
    ("2 Stk. Äpfel", (2.0, "Stück", "Äpfel", None)),
    ("3 Eier (Größe M)", (3.0, None, "Eier", "Größe M")),
    ("2 Zwiebeln, gewürfelt", (2.0, None, "Zwiebeln", "gewürfelt")),
    ("200 g Mehl (Type 405), gesiebt", (200.0, "g", "Mehl", "Type 405, gesiebt")),
    ("1 (400 g) Dose Kidneybohnen", (1.0, "Dose", "Kidneybohnen", "400 g")),
    ("1.000 g Kartoffeln", (1000.0, "g", "Kartoffeln", None)),
    ("0.125 l Sahne", (0.125, "l", "Sahne", None)),
    ("ca. 200ml Wasser", (200.0, "ml", "Wasser", None)),
    ("2 EL Öl", (2.0, "EL", "Öl", None)),
    ("2 Esslöffel Öl", (2.0, "EL", "Öl", None)),
    ("1 Liter Brühe", (1.0, "l", "Brühe", None)),
    ("1 Gurke", (1.0, None, "Gurke", None)),
    ("1 Kopf Salat", (1.0, "Kopf", "Salat", None)),
    ("2 Msp. Zimt", (2.0, "Msp.", "Zimt", None)),
    ("1 Glas Gurken", (1.0, "Glas", "Gurken", None)),
    ("1 Schuss Essig", (1.0, "Schuss", "Essig", None)),
    ("- 2 EL Butter", (2.0, "EL", "Butter", None)),
    ("1 kg Kartoffel(n)", (1.0, "kg", "Kartoffel", None)),
    ("1 Knoblauchzehe", (1.0, None, "Knoblauchzehe", None)),
    ("2 Becher", (2.0, None, "Becher", None)),
    # Lines without a quantity keep the whole text as name.
    ("Salz und Pfeffer", (None, None, "Salz und Pfeffer", None)),
    ("Salz, Pfeffer", (None, None, "Salz, Pfeffer", None)),
    ("Saft von 1 Zitrone", (None, None, "Saft von 1 Zitrone", None)),
    ("etwas Muskat", (None, None, "etwas Muskat", None)),
    ("Butter (zum Braten)", (None, None, "Butter", "zum Braten")),
]


@pytest.mark.parametrize(("line", "expected"), CASES, ids=[case[0] for case in CASES])
def test_parse_ingredient(line: str, expected: tuple) -> None:
    ingredient = parse_ingredient(line)
    amount, unit, name, note = expected
    assert ingredient.amount == pytest.approx(amount) if amount is not None else ingredient.amount is None
    assert ingredient.unit == unit
    assert ingredient.name == name
    assert ingredient.note == note


def test_third_fractions_are_rounded() -> None:
    assert parse_ingredient("⅓ l Milch").amount == pytest.approx(0.3333, abs=1e-4)


def test_html_entities_are_resolved() -> None:
    ingredient = parse_ingredient("2&nbsp;EL Öl &amp; Essig")
    assert (ingredient.amount, ingredient.unit, ingredient.name) == (2.0, "EL", "Öl & Essig")
    assert ingredient.raw == "2 EL Öl & Essig"


def test_html_tags_are_removed() -> None:
    assert parse_ingredient("<b>2</b> EL Mehl").name == "Mehl"


def test_non_breaking_space_between_amount_and_unit() -> None:
    ingredient = parse_ingredient("250 g Butter")
    assert (ingredient.amount, ingredient.unit, ingredient.name) == (250.0, "g", "Butter")


def test_raw_keeps_the_line() -> None:
    assert parse_ingredient("250 g Mehl (Type 405)").raw == "250 g Mehl (Type 405)"


def test_empty_line() -> None:
    ingredient = parse_ingredient("   ")
    assert ingredient.name == ""
    assert ingredient.amount is None


def test_as_dict_roundtrip() -> None:
    ingredient = parse_ingredient("2 EL Öl")
    assert ingredient.as_dict() == {
        "name": "Öl",
        "amount": 2.0,
        "unit": "EL",
        "note": None,
        "raw": "2 EL Öl",
    }


@pytest.mark.parametrize(
    ("text", "value"),
    [("1", 1.0), ("1,5", 1.5), ("1/2", 0.5), ("½", 0.5), ("1 ½", 1.5), ("1-2", 1.0),
     ("2.000", 2000.0), (" 3 ", 3.0), ("", None), ("viel", None), (None, None)],
)
def test_parse_amount(text: str | None, value: float | None) -> None:
    assert parse_amount(text) == value


@pytest.mark.parametrize(
    ("text", "unit"),
    [("Zehen", "Zehe"), ("Esslöffel", "EL"), ("el", "EL"), ("Liter", "l"), ("Pck", "Pck."),
     ("Dose(n)", "Dose"), ("Gramm", "g"), ("Schälchen", "Schälchen"), ("", None), (None, None)],
)
def test_normalize_unit(text: str | None, unit: str | None) -> None:
    assert normalize_unit(text) == unit


def test_clean_name_and_format_amount() -> None:
    assert clean_name(" Kartoffel(n) ") == "Kartoffel"
    assert clean_name(None) == ""
    assert format_amount(1.5) == "1,5"
    assert format_amount(2.0) == "2"
    assert format_amount(0.333333) == "0,333"
    assert format_amount(None) == ""
