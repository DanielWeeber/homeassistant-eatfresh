"""Tests for sorting ingredients into supermarket departments."""

from __future__ import annotations

import time

import pytest

from custom_components.eatfresh.departments import (
    DEPARTMENTS,
    KITCHENOWL_DEFAULT_KEYS,
    OTHER,
    classify,
    department_name,
    match_category_name,
)

# Names exactly as they came from a real shopping list.
REAL_NAMES = [
    ("Knollensellerie", "fruits_vegetables"),
    ("Lauch", "fruits_vegetables"),
    ("Mozzarella", "dairy"),
    ("Champignons", "fruits_vegetables"),
    ("Passierte Tomaten", "canned"),
    ("Gemüsebrühwürfel", "spices"),
    ("Salz", "spices"),
    ("Butter", "dairy"),
    ("Sahne", "dairy"),
    ("Curry", "spices"),
    ("Zwiebel", "fruits_vegetables"),
    ("Pfeffer", "spices"),
    ("Kartoffeln", "fruits_vegetables"),
    ("Gemüsebrühe", "spices"),
    ("Wasser", "drinks"),
    ("Wiener Würstchen", "meat_fish"),
    ("Muskat", "spices"),
    ("Hokkaido-Kürbis", "fruits_vegetables"),
    ("Kürbisfleisch", "fruits_vegetables"),
    ("Zwiebeln", "fruits_vegetables"),
    ("Rinderhackfleisch", "meat_fish"),
    ("Kochschinken", "meat_fish"),
    ("Rigatoni", "grain"),
    ("Möhren", "fruits_vegetables"),
    ("Petersilienwurzel", "fruits_vegetables"),
    ("Créme Fraîche", "dairy"),
    ("geräucherten Bauchspeck", "meat_fish"),
    ("Sahne zum Kochen", "dairy"),
]

TRAPS = [
    # Longer matches beat shorter ones.
    ("Kokosmilch", "canned"),
    ("Paprikapulver", "spices"),
    ("Paprika edelsüß", "spices"),
    ("Paprika, edelsüß", "spices"),
    ("Paprika", "fruits_vegetables"),
    ("Paprikaschote", "fruits_vegetables"),
    ("rote Paprika", "fruits_vegetables"),
    ("Fruchtfleisch", "fruits_vegetables"),
    ("Melonenfleisch", "fruits_vegetables"),
    ("Tomatenmark", "canned"),
    ("gehackte Tomaten", "canned"),
    ("Tomaten, gehackt", "canned"),
    ("Tomaten", "fruits_vegetables"),
    ("Kidneybohnen", "canned"),
    ("Mais", "canned"),
    ("Kichererbsen", "canned"),
    ("Thunfisch", "canned"),
    ("Erdnussbutter", "snacks"),
    ("Buttermilch", "dairy"),
    ("Eier", "dairy"),
    ("Ei", "dairy"),
    ("Brühwürfel", "spices"),
    ("Muskatnuss", "spices"),
    ("Leberkäse", "meat_fish"),
    ("gehackte Mandeln", "baking"),
    ("Öl zum Braten", "spices"),
    ("Saft von 1 Zitrone", "fruits_vegetables"),
    ("Zitronensaft", "fruits_vegetables"),
    ("Orangensaft", "drinks"),
    ("Agavendicksaft", "baking"),
]

DEPARTMENT_TABLE = {
    "fruits_vegetables": [
        "Knoblauch",
        "Knoblauchzehen",
        "Ingwer",
        "Zitrone",
        "frische Petersilie",
        "Basilikum",
        "Schnittlauch",
        "rote Zwiebel",
        "Frühlingszwiebeln",
        "Zucchini",
        "Kirschtomaten",
        "Feldsalat",
        "Rotkohl",
        "Äpfel",
        "Bananen",
        "Erdbeeren",
    ],
    "spices": [
        "Oregano getrocknet",
        "getrockneter Oregano",
        "Thymian, getrocknet",
        "Ingwer gemahlen",
        "Zimt",
        "Salz und Pfeffer",
        "frisch gemahlener Pfeffer",
        "Cayennepfeffer",
        "Olivenöl",
        "Rapsöl",
        "Öl",
        "Essig",
        "Balsamico",
        "Senf",
        "Sojasauce",
        "Sojasoße",
        "Ketchup",
        "Kräuter der Provence",
    ],
    "baking": [
        "Mehl",
        "Mehl (Type 405)",
        "Zucker",
        "Puderzucker",
        "Hefe",
        "Trockenhefe",
        "Backpulver",
        "Vanillezucker",
        "Speisestärke",
        "Gemahlene Mandeln",
    ],
    "grain": [
        "Nudeln",
        "Spaghetti",
        "Reis",
        "Basmatireis",
        "Couscous",
        "Linsen",
        "rote Linsen",
        "Haferflocken",
        "Glasnudeln",
    ],
    "meat_fish": [
        "Hackfleisch",
        "Hähnchenbrust",
        "Hähnchenbrustfilet",
        "Schinken",
        "Speck",
        "Würstchen",
        "Lachs",
        "Lachsfilet",
        "Garnelen",
        "Bratwurst",
    ],
    "refrigerated": [
        "Blätterteig",
        "Gnocchi",
        "Tofu",
        "frische Tortellini",
        "Schupfnudeln",
    ],
    "bread": ["Toast", "Brötchen", "Baguette", "Toastbrot", "Fladenbrot"],
    "drinks": ["Wein", "Weißwein", "Rotwein", "Saft", "Apfelsaft", "Mineralwasser"],
    "dairy": [
        "Milch",
        "Schlagsahne",
        "saure Sahne",
        "Schmand",
        "Creme fraiche",
        "Crème fraîche",
        "Frischkäse",
        "Bergkäse",
        "geriebener Käse",
        "Quark",
        "Joghurt",
        "Feta",
    ],
    "canned": [
        "Mais aus der Dose",
        "Kichererbsen (Dose)",
        "Tomaten aus der Dose",
        "stückige Tomaten",
        "Kokosmilch",
        "Oliven",
        "Kapern",
    ],
    "freezer": [
        "TK-Erbsen",
        "Erbsen (TK)",
        "Blattspinat (tiefgekühlt)",
        "tiefgekühlte Himbeeren",
        "Tiefkühlerbsen",
        "Fischstäbchen",
        "Erbsen",
    ],
    "snacks": ["Schokolade", "Chips", "Honig", "Marmelade"],
    "hygiene": ["Backpapier", "Alufolie", "Küchenrolle"],
}

ENGLISH = [
    ("tomatoes", "fruits_vegetables"),
    ("onions", "fruits_vegetables"),
    ("garlic", "fruits_vegetables"),
    ("eggs", "dairy"),
    ("heavy cream", "dairy"),
    ("olive oil", "spices"),
    ("salt", "spices"),
    ("chicken breasts", "meat_fish"),
    ("flour", "baking"),
    ("rice", "grain"),
    ("coconut milk", "canned"),
    ("white wine", "drinks"),
]


@pytest.mark.parametrize(("name", "expected"), REAL_NAMES)
def test_real_names(name: str, expected: str) -> None:
    assert classify(name) == expected


@pytest.mark.parametrize(("name", "expected"), TRAPS)
def test_traps(name: str, expected: str) -> None:
    assert classify(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [(name, key) for key, names in DEPARTMENT_TABLE.items() for name in names],
)
def test_departments_table(name: str, expected: str) -> None:
    assert classify(name) == expected


@pytest.mark.parametrize(("name", "expected"), ENGLISH)
def test_english(name: str, expected: str) -> None:
    assert classify(name) == expected


@pytest.mark.parametrize(
    "name",
    ["KNOBLAUCH", "knoblauch", "  Knoblauch  ", "Knoblauch, gepresst", "Knoblauch!"],
)
def test_case_and_noise(name: str) -> None:
    assert classify(name) == "fruits_vegetables"


@pytest.mark.parametrize(
    "name",
    [None, "", "   ", 42, 3.5, "12345", "!!!", "x" * 100_000, "Xyzzy", ["Salz"]],
)
def test_robust_unknown(name: object) -> None:
    assert classify(name) == OTHER  # type: ignore[arg-type]


def test_long_text_never_raises() -> None:
    assert classify("Salz " * 50_000) == "spices"


def test_departments_order() -> None:
    assert DEPARTMENTS[0] == "fruits_vegetables"
    assert DEPARTMENTS[-1] == OTHER
    assert len(DEPARTMENTS) == len(set(DEPARTMENTS)) == 14
    for key in KITCHENOWL_DEFAULT_KEYS.values():
        assert key in DEPARTMENTS


def test_kitchenowl_default_keys() -> None:
    assert set(KITCHENOWL_DEFAULT_KEYS) == {
        "bread",
        "canned",
        "dairy",
        "drinks",
        "freezer",
        "fruits_vegetables",
        "grain",
        "hygiene",
        "refrigerated",
        "snacks",
    }
    assert all(key == value for key, value in KITCHENOWL_DEFAULT_KEYS.items())


def test_department_names() -> None:
    assert department_name("fruits_vegetables", "de") == "🥬 Obst und Gemüse"
    assert department_name("meat_fish", "de") == "🥩 Fleisch, Wurst und Fisch"
    assert department_name("spices", "de") == "🧂 Gewürze, Öl und Soßen"
    assert department_name("freezer", "de") == "❄️ Tiefkühl"
    assert department_name("other", "de") == "🛒 Sonstiges"
    assert department_name("dairy", "en") == "🥛 Dairy and eggs"
    assert department_name("dairy", "fr") == "🥛 Dairy and eggs"
    assert department_name("unknown", "de") == "🛒 Sonstiges"
    for key in DEPARTMENTS:
        assert department_name(key, "de")
        assert department_name(key, "en")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("🥬 Obst und Gemüse", "fruits_vegetables"),
        ("Obst und Gemüse", "fruits_vegetables"),
        ("Obst & Gemüse", "fruits_vegetables"),
        ("🥛 Milchprodukte", "dairy"),
        ("🥫 Konserven", "canned"),
        ("🍹 Getränke", "drinks"),
        ("Fruits and Vegetables", "fruits_vegetables"),
        ("Fruits & Vegetables", "fruits_vegetables"),
        ("Dairy", "dairy"),
        ("dairy", "dairy"),
        ("❄️ Tiefkühl", "freezer"),
        ("Frozen", "freezer"),
        ("Hygiene", "hygiene"),
        ("Snacks", "snacks"),
    ],
)
def test_match_category_name(name: str, expected: str) -> None:
    assert match_category_name(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Tiefgekühlt", "freezer"),
        ("❄️ Tiefgekühlt", "freezer"),
        ("tiefgekühlt", "freezer"),
        ("Tiefgekühltes", "freezer"),
        ("Gekühltes", "refrigerated"),
        ("🧊 Gekühltes", "refrigerated"),
        ("Gekühlt", "refrigerated"),
        ("Kühlregal", "refrigerated"),
        ("Tiefkühl", "freezer"),
    ],
)
def test_match_category_name_chilled_and_frozen(name: str, expected: str) -> None:
    """Fix 7 after the review: "Tiefgekühlt" and "Gekühltes" are known."""
    assert match_category_name(name) == expected


def test_match_own_names() -> None:
    for key in DEPARTMENTS:
        assert match_category_name(department_name(key, "de")) == key
        assert match_category_name(department_name(key, "en")) == key


@pytest.mark.parametrize("name", [None, "", "  ", 7, "Werkzeug", "🔧", "x" * 10_000])
def test_match_category_name_unknown(name: object) -> None:
    assert match_category_name(name) is None  # type: ignore[arg-type]


def test_classify_is_fast() -> None:
    names = [name for name, _ in REAL_NAMES] * 40
    start = time.perf_counter()
    for name in names:
        classify(name)
    assert time.perf_counter() - start < 1.0
