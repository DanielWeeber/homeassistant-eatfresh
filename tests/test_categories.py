"""Tests for the canonical categories and their suggestions."""

from __future__ import annotations

import pytest

from custom_components.eatfresh.categories import (
    CATEGORIES,
    canonical_category,
    category_names,
    suggest_categories,
)
from custom_components.eatfresh.models import Recipe


def recipe(title: str = "Untitled", tags: list[str] | None = None) -> Recipe:
    """Return an invented recipe with a title and tags."""
    return Recipe(
        source="fakea",
        id="1",
        url="https://recipes.example.com/1",
        title=title,
        tags=tags or [],
    )


def test_canonical_names() -> None:
    assert category_names("de") == [
        "Vorspeise",
        "Hauptspeise",
        "Nachspeise",
        "Vegetarisch",
        "Vegan",
        "Pasta",
        "Suppe",
        "Salat",
        "Backen",
        "Frühstück",
    ]
    assert category_names("en") == [
        "Starter",
        "Main course",
        "Dessert",
        "Vegetarian",
        "Vegan",
        "Pasta",
        "Soup",
        "Salad",
        "Baking",
        "Breakfast",
    ]
    assert len({category.id for category in CATEGORIES}) == 10


@pytest.mark.parametrize(
    ("language", "expected"),
    [("de", "Nachspeise"), ("de-AT", "Nachspeise"), ("de_CH", "Nachspeise"),
     ("en", "Dessert"), ("en-GB", "Dessert"), ("fr", "Dessert"), ("", "Dessert")],
)
def test_language_choice(language: str, expected: str) -> None:
    assert suggest_categories(recipe(tags=["Dessert"]), language) == [expected]


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        (["Vorspeise"], ["Vorspeise"]),
        (["Vorspeisen", "Party"], ["Vorspeise"]),
        (["Fingerfood"], ["Vorspeise"]),
        (["Hauptspeise"], ["Hauptspeise"]),
        (["Hauptgericht"], ["Hauptspeise"]),
        (["Abendessen"], ["Hauptspeise"]),
        (["Nachtisch"], ["Nachspeise"]),
        (["Süßspeise"], ["Nachspeise"]),
        (["Vegetarisch"], ["Vegetarisch"]),
        (["Vegan"], ["Vegetarisch", "Vegan"]),
        (["Nudeln"], ["Pasta"]),
        (["Bandnudeln"], ["Pasta"]),
        (["Spätzle"], ["Pasta"]),
        (["Eintopf"], ["Suppe"]),
        (["Kartoffelsuppe"], ["Suppe"]),
        (["Nudelsalat"], ["Salat"]),
        (["Kuchen"], ["Backen"]),
        (["Schokoladenkuchen"], ["Backen"]),
        (["Plätzchen", "Weihnachten"], ["Backen"]),
        (["Bananenbrot"], ["Backen"]),
        (["Frühstück"], ["Frühstück"]),
        (["Sonntagsfrühstück"], ["Frühstück"]),
        (["Brunch"], ["Frühstück"]),
        (["Hauptspeise", "Vegetarisch", "Pasta"], ["Hauptspeise", "Vegetarisch", "Pasta"]),
        (["Schnell", "Einfach", "Sommer"], []),
        (["Nicht vegan"], []),
        (["ohne Nudeln"], []),
    ],
)
def test_german_tags(tags: list[str], expected: list[str]) -> None:
    assert suggest_categories(recipe(tags=tags), "de") == expected


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        (["Starter"], ["Starter"]),
        (["Appetizers"], ["Starter"]),
        (["Main course"], ["Main course"]),
        (["Main"], ["Main course"]),
        (["Dinner"], ["Main course"]),
        (["Dessert"], ["Dessert"]),
        (["Vegetarian"], ["Vegetarian"]),
        (["vegan"], ["Vegetarian", "Vegan"]),
        (["Non-vegetarian"], []),
        (["Noodles"], ["Pasta"]),
        (["Soup"], ["Soup"]),
        (["Stew"], ["Soup"]),
        (["Salad"], ["Salad"]),
        (["Cake"], ["Baking"]),
        (["Cheesecake"], ["Baking"]),
        (["Bread"], ["Baking"]),
        (["Breakfast"], ["Breakfast"]),
        (["Quick", "Easy"], []),
    ],
)
def test_english_tags(tags: list[str], expected: list[str]) -> None:
    assert suggest_categories(recipe(tags=tags), "en") == expected


@pytest.mark.parametrize(
    ("title", "language", "expected"),
    [
        ("Cremige Kürbissuppe", "de", ["Suppe"]),
        # The title never makes a recipe vegetarian or vegan.
        ("Vegetarische Lasagne", "de", ["Pasta"]),
        ("Vegane Bolognese mit Spaghetti", "de", ["Pasta"]),
        ("Veggie-Burger mit Bacon", "de", []),
        ("Griechischer Salat", "de", ["Salat"]),
        ("Apfelkuchen vom Blech", "de", ["Backen"]),
        ("Spaghetti carbonara", "en", ["Pasta"]),
        ("Tomato soup", "en", ["Soup"]),
        ("Banana bread", "en", ["Baking"]),
        ("Hähnchen mit Reis", "de", []),
        ("Chicken with rice", "en", []),
    ],
)
def test_title(title: str, language: str, expected: list[str]) -> None:
    assert suggest_categories(recipe(title=title), language) == expected


def test_title_and_tags_are_combined_without_duplicates() -> None:
    result = suggest_categories(
        recipe(title="Linsensuppe", tags=["Suppe", "Soup", "Hauptgericht"]), "de"
    )
    assert result == ["Hauptspeise", "Suppe"]


def test_main_only_counts_as_whole_tag() -> None:
    """"Main" in a title or inside a longer tag is no category."""
    assert suggest_categories(recipe(title="Main street burger"), "en") == []
    assert suggest_categories(recipe(tags=["Main ingredient: rice"]), "en") == []


def test_ingredients_never_make_a_recipe_vegetarian() -> None:
    """Only the source decides about vegetarian and vegan."""
    item = recipe(title="Gemüsepfanne", tags=["Gemüse", "Tofu", "Linsen"])
    assert suggest_categories(item, "de") == []


def test_short_words_do_not_match_inside_other_words() -> None:
    """Keywords only match whole words, except German compound endings."""
    assert suggest_categories(recipe(title="Tortellini-Auflauf"), "de") == ["Pasta"]
    assert suggest_categories(recipe(title="Suppengrün schneiden"), "de") == []
    assert suggest_categories(recipe(title="Salatdressing"), "de") == []


def test_broken_tags_are_ignored() -> None:
    item = recipe(tags=["", "   ", 5, None, "Dessert"])  # type: ignore[list-item]
    assert suggest_categories(item, "en") == ["Dessert"]


@pytest.mark.parametrize(
    ("name", "expected"),
    [("Nachspeise", "dessert"), ("dessert", "dessert"), ("FRÜHSTÜCK", "breakfast"),
     ("Main course", "main"), ("Schnell", None), ("", None)],
)
def test_canonical_category(name: str, expected: str | None) -> None:
    found = canonical_category(name)
    assert (found.id if found else None) == expected
