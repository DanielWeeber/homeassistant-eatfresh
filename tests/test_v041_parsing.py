"""Reading fixes of 0.4.1: real ingredient lines of the audit of 19 Nov 2026."""

from __future__ import annotations

import pytest

from custom_components.eatfresh.ingredients import (
    adjectives_first,
    clean_name,
    clean_note,
    finish_ingredients,
    normalize_unit,
    parse_ingredient,
)
from custom_components.eatfresh.sources.chefkoch import ChefkochSource
from custom_components.eatfresh.sources.gaumenfreundin import GaumenfreundinSource


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations() -> None:
    """These tests need no Home Assistant instance."""


@pytest.fixture(autouse=True)
def setup_dependencies() -> None:
    """These tests need no Home Assistant instance."""


def read(line: str) -> tuple[float | None, str | None, str, str | None]:
    """Read one page line the way the page sources do."""
    items = finish_ingredients([parse_ingredient(line)])
    assert len(items) == 1
    item = items[0]
    return item.amount, item.unit, item.name, item.note


# 1. A comma splits the name only after a noun.
@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            "50 g gemahlene, geschälte Mandeln (blanchiert)",
            (50.0, "g", "gemahlene, geschälte Mandeln", "blanchiert"),
        ),
        ("2 große, reife Tomaten", (2.0, None, "große, reife Tomaten", None)),
        # Counter examples: a noun stands before the comma.
        ("250 g Mehl, Type 405", (250.0, "g", "Mehl", "Type 405")),
        ("1 Eigelb, Größe M", (1.0, None, "Eigelb", "Größe M")),
        ("5 EL Wasser, oder Rum", (5.0, "EL", "Wasser", "oder Rum")),
        ("1 Stück Zitrone, gewachst", (1.0, "Stück", "Zitrone", "gewachst")),
        (
            "40 g Hartkäse ital. Art, gerieben",
            (40.0, "g", "Hartkäse ital. Art", "gerieben"),
        ),
        ("400 g Kirschtomaten (Dose)", (400.0, "g", "Kirschtomaten", "Dose")),
        ("4 Eigelbe, zimmerwarm", (4.0, None, "Eigelbe", "zimmerwarm")),
        ("1 Zwiebel", (1.0, None, "Zwiebel", None)),
        ("200 g Zucker, brauner", (200.0, "g", "Zucker", "brauner")),
        # English lines: the same result as before 0.4.1.
        ("1 cup flour, sifted", (1.0, None, "cup flour", "sifted")),
        ("1 onion, finely chopped", (1.0, None, "onion", "finely chopped")),
        ("2 cloves garlic, minced", (2.0, None, "cloves garlic", "minced")),
        ("1 can tomatoes, crushed", (1.0, None, "can tomatoes", "crushed")),
        ("butter, melted", (None, None, "butter, melted", None)),
    ],
)
def test_comma_needs_a_noun(line: str, expected: tuple) -> None:
    """Rule 1: no split behind "gemahlene,", split behind a noun."""
    assert read(line) == expected


# 2. Package spellings.
@pytest.mark.parametrize(
    "line",
    [
        "1 Päck. Bourbon-Vanillezucker",
        "1 Päckchen Bourbon-Vanillezucker",
        "1 Pkg. Bourbon-Vanillezucker",
        "1 Pck Bourbon-Vanillezucker",
        "1 Pck. Bourbon-Vanillezucker",
    ],
)
def test_package_unit(line: str) -> None:
    """Rule 2: every spelling gives "Pck."."""
    assert read(line) == (1.0, "Pck.", "Bourbon-Vanillezucker", None)


def test_package_unit_with_note() -> None:
    """Rule 2 on the real line of the Spritzgebäck recipe."""
    line = "1 Päck. Bourbon Vanillezucker (alternativ das Mark einer Vanilleschote)"
    assert read(line) == (
        1.0,
        "Pck.",
        "Bourbon Vanillezucker",
        "alternativ das Mark einer Vanilleschote",
    )
    assert normalize_unit("Päck.") == "Pck."


# 3. No comma at the start of a Chefkoch note.
def test_note_without_leading_comma() -> None:
    """Rule 3."""
    assert clean_note(", feiner") == "feiner"
    assert clean_note(", , ca. 400 g") == "ca. 400 g"
    assert clean_note("nach Belieben;") == "nach Belieben"
    assert clean_note("") is None
    assert clean_note(None) is None


def _chefkoch(name: str, amount: float, unit: str = "", info: str = ""):
    entry = {"name": name, "amount": amount, "unit": unit, "usageInfo": info}
    data = {"ingredientGroups": [{"ingredients": [entry]}]}
    items = ChefkochSource._ingredients(data)
    assert len(items) == 1
    return items[0]


def test_chefkoch_note_has_no_leading_comma() -> None:
    """Rule 3 with the real entries of the audit."""
    zucker = _chefkoch("Zucker", 200.0, "g", ", feiner")
    assert (zucker.name, zucker.note) == ("Zucker", "feiner")
    assert zucker.raw == "200 g Zucker, feiner"
    tomaten = _chefkoch("Pizzatomaten", 1.0, "Dose", ", ca. 400 g")
    assert tomaten.note == "ca. 400 g"
    chili = _chefkoch("Chilipulver", 3.0, "TL", ", nach belieben")
    assert chili.note == "nach belieben"


# 4. Adjectives behind the noun move in front of it (Chefkoch).
@pytest.mark.parametrize(
    ("name", "amount", "info", "expected", "note"),
    [
        ("Butter, weiche", 130.0, "", "weiche Butter", None),
        ("Linsen, rote", 175.0, "", "rote Linsen", None),
        (
            "Haselnüsse, gemahlene",
            400.0,
            ", oder Walnüsse oder Mandeln",
            "gemahlene Haselnüsse",
            "oder Walnüsse oder Mandeln",
        ),
        ("Zucker, brauner", 200.0, "", "brauner Zucker", None),
        # Counter examples stay as they are.
        ("Mehl, Type 405", 300.0, "", "Mehl, Type 405", None),
        ("Eigelb, Größe M", 1.0, "", "Eigelb, Größe M", None),
        ("Wasser, oder Rum", 5.0, "", "Wasser, oder Rum", None),
        ("Zitrone, gewachst", 1.0, "", "Zitrone, gewachst", None),
        ("Hartkäse ital. Art, gerieben", 40.0, "", "Hartkäse ital. Art, gerieben", None),
        ("Zwiebel", 1.0, "", "Zwiebel", None),
    ],
)
def test_chefkoch_adjectives(
    name: str, amount: float, info: str, expected: str, note: str | None
) -> None:
    """Rule 4."""
    item = _chefkoch(name, amount, "g", info)
    assert (item.name, item.note) == (expected, note)


def test_adjectives_first_limits() -> None:
    """Rule 4 touches only one or two inflected adjectives."""
    assert adjectives_first("Butter, weiche, kalte") == "weiche kalte Butter"
    assert adjectives_first("Butter, weiche, kalte, feine") == "Butter, weiche, kalte, feine"
    assert adjectives_first("Mehl, Type 405") == "Mehl, Type 405"
    assert adjectives_first("Butter (Süßrahm), weiche") == "Butter (Süßrahm), weiche"
    assert adjectives_first("Salz, bitte") == "Salz, bitte"


# 5. Plural brackets.
@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("1 Zwiebel(n)", (1.0, None, "Zwiebel", None)),
        ("2 Zwiebel(n)", (2.0, None, "Zwiebeln", None)),
        ("1 Ei(er)", (1.0, None, "Ei", None)),
        ("2 Ei(er), Gr. M", (2.0, None, "Eier", "Gr. M")),
        ("3 Ei(er)", (3.0, None, "Eier", None)),
        ("1/2 Zwiebel(n)", (0.5, None, "Zwiebeln", None)),
        ("1 kg Kartoffel(n)", (1.0, "kg", "Kartoffeln", None)),
        ("2 kg Kartoffel(n)", (2.0, "kg", "Kartoffeln", None)),
        ("1 Pck. Zwiebel(n)", (1.0, "Pck.", "Zwiebeln", None)),
        ("2 Zehe(n) Knoblauch", (2.0, "Zehe", "Knoblauch", None)),
        ("4 Kartoffel(n), festkochend", (4.0, None, "Kartoffeln", "festkochend")),
        ("Zwiebel(n)", (None, None, "Zwiebeln", None)),
        ("Ei(er)", (None, None, "Eier", None)),
    ],
)
def test_plural_brackets(line: str, expected: tuple) -> None:
    """Rule 5 on lines."""
    assert read(line) == expected


def test_plural_in_chefkoch_and_clean_name() -> None:
    """Rule 5 for sources that send the amount apart from the name."""
    assert _chefkoch("Ei(er)", 2.0, "", "Gr. M").name == "Eier"
    assert _chefkoch("Zwiebel(n)", 1.0).name == "Zwiebel"
    assert clean_name("Zwiebel(n)", 3.0) == "Zwiebeln"
    assert clean_name("Zwiebel(n)") == "Zwiebeln"
    assert clean_name("Zwiebel(n)", 1.0) == "Zwiebel"
    assert clean_name("Kartoffel(n)", 1.0, "kg") == "Kartoffeln"
    assert clean_name("Kartoffel(n)", 2.0, "kg") == "Kartoffeln"
    assert _chefkoch("Kartoffel(n)", 1.0, "kg").name == "Kartoffeln"
    assert _chefkoch("Tomate(n), passierte", 500.0, "g").name == "passierte Tomaten"


def test_plural_in_gaumenfreundin_fields() -> None:
    """Rule 5 for the WPRM fields, plus rule 7."""
    entries = [
        {"name": "Ei(er)", "amount": "2", "unit": "", "notes": ""},
        {"name": "Ei(er)", "amount": "1", "unit": "", "notes": ""},
        {"name": "Kartoffel(n)", "amount": "1", "unit": "kg", "notes": ""},
        {"name": "Salz & Pfeffer", "amount": "", "unit": "", "notes": ""},
    ]
    items = GaumenfreundinSource._ingredients({"ingredients": [{"ingredients": entries}]})
    assert [item.name for item in items] == ["Eier", "Ei", "Kartoffeln", "Salz", "Pfeffer"]


# 6. "nach Geschmack Salz".
@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("nach Geschmack Salz", (None, None, "Salz", "nach Geschmack")),
        ("nach Geschmack Pfeffer", (None, None, "Pfeffer", "nach Geschmack")),
        ("nach Geschmack Zucker", (None, None, "Zucker", "nach Geschmack")),
        ("nach Belieben Chilipulver", (None, None, "Chilipulver", "nach Belieben")),
        ("nach Bedarf Wasser", (None, None, "Wasser", "nach Bedarf")),
        # Not at the start or with an amount: unchanged.
        (
            "80 g Gelee nach Geschmack (z.B. Johannisbeergelee)",
            (80.0, "g", "Gelee nach Geschmack", "z.B. Johannisbeergelee"),
        ),
        ("nach Geschmack", (None, None, "nach Geschmack", None)),
    ],
)
def test_vague_amount_first(line: str, expected: tuple) -> None:
    """Rule 6."""
    assert read(line) == expected


# 7. Salz und Pfeffer.
def test_salt_and_pepper_pair() -> None:
    """Rule 7: exactly this pair, both orders, "&"."""
    for line, names in [
        ("Salz und Pfeffer", ["Salz", "Pfeffer"]),
        ("Pfeffer und Salz", ["Pfeffer", "Salz"]),
        ("Salz & Pfeffer", ["Salz", "Pfeffer"]),
    ]:
        items = finish_ingredients([parse_ingredient(line)])
        assert [item.name for item in items] == names
        assert all(item.amount is None and item.unit is None for item in items)


@pytest.mark.parametrize(
    "line",
    [
        "Salz, Pfeffer",
        "Salz und Muskat",
        "Salz und Salz",
        "Fett und Mehl für das Blech",
        "Pfeffer und Salz zum Würzen",
        "1 Prise Salz und Pfeffer",
    ],
)
def test_other_pairs_stay(line: str) -> None:
    """Rule 7 splits nothing but the pair without an amount."""
    items = finish_ingredients([parse_ingredient(line)])
    assert len(items) == 1


# 8. Brackets inside brackets.
def test_nested_brackets_in_note() -> None:
    """Rule 8 on the real Spritzgebäck line."""
    line = (
        "250 g Butter, zimmerwarm (bitte echte Markenbutter (Süßrahm) verwenden "
        "und keine Streichzart-Variante)"
    )
    amount, unit, name, note = read(line)
    assert (amount, unit, name) == (250.0, "g", "Butter")
    assert note == (
        "zimmerwarm, bitte echte Markenbutter (Süßrahm) verwenden und keine Streichzart-Variante"
    )
    assert "  " not in note


def test_note_order_follows_the_line() -> None:
    """Rule 8: brackets in the name come first, then the comma text, then its brackets."""
    assert read("1 EL Butter ( für die Form bzw. Förmchen)")[3] == "für die Form bzw. Förmchen"
    assert read("2 Gewürzgurken (Glas), abgetropft")[3] == "Glas, abgetropft"
    assert read("1 kg Kartoffeln (festkochend)") == (1.0, "kg", "Kartoffeln", "festkochend")
    assert read("1 Bund Suppengemüse (Alternative: 4 Möhren, 1 Stange Lauch)")[3] == (
        "Alternative: 4 Möhren, 1 Stange Lauch"
    )
    # An unbalanced bracket does not lose text.
    assert read("250 g Mehl (Type 405")[2] == "Mehl Type 405"


def test_adjectives_first_leaves_articles_and_counts() -> None:
    assert adjectives_first("Zitrone, eine") == "Zitrone, eine"
    assert adjectives_first("Möhren, einige") == "Möhren, einige"
    assert adjectives_first("Linsen, rote") == "rote Linsen"
