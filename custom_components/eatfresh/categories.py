"""Canonical recipe categories and how EatFresh suggests them.

Pure Python: no Home Assistant imports. A category is suggested from what the
recipe source says about the recipe (its tags and keywords) and from the
title. Ingredients are never used. "Vegetarian" and "Vegan" need more: a
whole tag of the source that says exactly that (or the diet of the recipe
data, which the JSON-LD reader turns into such a tag). A part of a longer tag
("Vegane Alternativen", "vegetarisch möglich") or the title never counts.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .models import Recipe

_WORD_RE = re.compile(r"[^\W\d_]+")
# A tag counts as a whole tag ("exact") only if it has no punctuation:
# letters, digits, blanks and hyphens. "vegan?", "Vegan!" or "#vegan" do not.
_CLEAN_TAG_RE = re.compile(r"[^\W_]+(?:[\s-]+[^\W_]+)*")


def _normalize(text: str) -> str:
    """Return lower case words separated by one space (ß becomes ss)."""
    return " ".join(_WORD_RE.findall(text.casefold()))


@dataclass(frozen=True, slots=True)
class Category:
    """One canonical category with its names and the words that point to it."""

    id: str
    de: str
    en: str
    # Whole words or phrases (after normalizing) anywhere in a tag or the title.
    words: frozenset[str]
    # Endings of German compound words, for example "kartoffelsuppe".
    suffixes: frozenset[str] = frozenset()
    # Words that count only when they are the whole tag, for example "main".
    exact: frozenset[str] = frozenset()
    # Words or phrases that never point to the category, although a word or
    # an ending would match (a "Pfannkuchen" is not baked).
    excluded: frozenset[str] = frozenset()

    def name(self, language: str) -> str:
        """Return the name of the category in a language (German or English)."""
        return self.de if _is_german(language) else self.en


def _words(*items: str) -> frozenset[str]:
    return frozenset(_normalize(item) for item in items)


CATEGORIES: tuple[Category, ...] = (
    Category(
        id="starter",
        de="Vorspeise",
        en="Starter",
        words=_words(
            "vorspeise",
            "vorspeisen",
            "starter",
            "starters",
            "appetizer",
            "appetizers",
            "appetiser",
            "appetisers",
            "antipasti",
            "antipasto",
            "fingerfood",
        ),
        suffixes=_words("vorspeise", "vorspeisen"),
    ),
    Category(
        id="main",
        de="Hauptspeise",
        en="Main course",
        words=_words(
            "hauptspeise",
            "hauptspeisen",
            "hauptgericht",
            "hauptgerichte",
            "hauptgang",
            "main course",
            "main courses",
            "main dish",
            "main dishes",
            "entree",
            "entrée",
        ),
        exact=_words("main", "mains", "dinner", "abendessen", "mittagessen"),
    ),
    Category(
        id="dessert",
        de="Nachspeise",
        en="Dessert",
        words=_words(
            "nachspeise",
            "nachspeisen",
            "nachtisch",
            "dessert",
            "desserts",
            "süßspeise",
            "süßspeisen",
        ),
        suffixes=_words("dessert", "nachspeise", "nachtisch"),
    ),
    Category(
        id="vegetarian",
        de="Vegetarisch",
        en="Vegetarian",
        # Only whole tags: never from the title or a part of a longer tag.
        words=frozenset(),
        exact=_words(
            "vegetarisch",
            "vegetarische",
            "vegetarisches",
            "vegetarische rezepte",
            "vegetarische gerichte",
            "vegetarische küche",
            "vegetarische hauptgerichte",
            "vegetarian",
            "vegetarian recipes",
            "vegetarian dishes",
            "veggie",
        ),
    ),
    Category(
        id="vegan",
        de="Vegan",
        en="Vegan",
        # Only whole tags: never from the title or a part of a longer tag.
        words=frozenset(),
        exact=_words(
            "vegan",
            "vegane",
            "veganes",
            "vegane rezepte",
            "vegane gerichte",
            "vegane küche",
            "vegan recipes",
            "vegan dishes",
        ),
    ),
    Category(
        id="pasta",
        de="Pasta",
        en="Pasta",
        words=_words(
            "pasta",
            "nudeln",
            "nudel",
            "spaghetti",
            "lasagne",
            "lasagna",
            "penne",
            "tagliatelle",
            "fusilli",
            "rigatoni",
            "ravioli",
            "tortellini",
            "maccheroni",
            "macaroni",
            "spätzle",
            "noodles",
        ),
        suffixes=_words("nudeln", "pasta", "spaghetti", "spätzle"),
    ),
    Category(
        id="soup",
        de="Suppe",
        en="Soup",
        words=_words(
            "suppe",
            "suppen",
            "eintopf",
            "eintöpfe",
            "soup",
            "soups",
            "stew",
            "stews",
            "chowder",
        ),
        suffixes=_words("suppe", "suppen", "eintopf"),
    ),
    Category(
        id="salad",
        de="Salat",
        en="Salad",
        words=_words("salat", "salate", "salad", "salads"),
        suffixes=_words("salat", "salate"),
    ),
    Category(
        id="baking",
        de="Backen",
        en="Baking",
        words=_words(
            "backen",
            "gebäck",
            "kuchen",
            "torte",
            "torten",
            "brot",
            "brötchen",
            "plätzchen",
            "kekse",
            "muffin",
            "muffins",
            "baking",
            "cake",
            "cakes",
            "bread",
            "cookies",
            "brownies",
            "scones",
        ),
        suffixes=_words(
            "kuchen", "torte", "gebäck", "brot", "brötchen", "plätzchen", "cake", "cakes"
        ),
        # Made in the pan or put together, not baked.
        excluded=_words(
            "pfannkuchen",
            "eierkuchen",
            "reibekuchen",
            "kartoffelpfannkuchen",
            "pancake",
            "pancakes",
            "butterbrot",
            "butterbrote",
            "pausenbrot",
            "abendbrot",
            "schulbrot",
            "käsebrot",
            "wurstbrot",
            "schinkenbrot",
            "fischbrötchen",
            "fish cake",
            "fish cakes",
            "crab cake",
            "crab cakes",
            "potato cake",
            "potato cakes",
            "rice cake",
            "rice cakes",
        ),
    ),
    Category(
        id="breakfast",
        de="Frühstück",
        en="Breakfast",
        words=_words(
            "frühstück", "breakfast", "brunch", "müsli", "porridge", "granola"
        ),
        suffixes=_words("frühstück"),
    ),
)

# Words in front of a keyword that turn it around ("nicht vegan").
_NEGATIONS = _words("nicht", "kein", "keine", "ohne", "non", "not", "no")
# Short endings would match too much (a keyword with fewer letters in front
# of the ending is only matched as a whole word).
_MIN_SUFFIX_PREFIX = 3


def _is_german(language: str) -> bool:
    return (language or "").lower().replace("_", "-").split("-")[0] == "de"


def category_names(language: str) -> list[str]:
    """Return the names of all canonical categories in a language."""
    return [category.name(language) for category in CATEGORIES]


def canonical_category(name: str) -> Category | None:
    """Return the category whose German or English name is ``name``."""
    wanted = _normalize(name)
    for category in CATEGORIES:
        if wanted in (_normalize(category.de), _normalize(category.en)):
            return category
    return None


def _without_excluded(category: Category, tokens: list[str]) -> list[str]:
    """Return the tokens with the excluded words of a category blanked out."""
    if not category.excluded:
        return tokens
    result = list(tokens)
    for phrase in category.excluded:
        parts = phrase.split(" ")
        for index in range(len(result) - len(parts) + 1):
            if result[index : index + len(parts)] == parts:
                result[index : index + len(parts)] = [""] * len(parts)
    return result


def _matches(category: Category, tokens: list[str], whole: str | None) -> bool:
    """Return True if the words of one text point to the category."""
    if whole is not None and whole in category.exact:
        return True
    tokens = _without_excluded(category, tokens)
    for index, token in enumerate(tokens):
        if not token:
            continue
        if index and tokens[index - 1] in _NEGATIONS:
            continue
        for word in category.words:
            parts = word.split(" ")
            if tokens[index : index + len(parts)] == parts:
                return True
        for suffix in category.suffixes:
            if (
                token.endswith(suffix)
                and len(token) - len(suffix) >= _MIN_SUFFIX_PREFIX
            ):
                return True
    return False


def suggest_categories(recipe: Recipe, language: str) -> list[str]:
    """Return the canonical categories that fit a recipe, in a language.

    Uses the tags and keywords of the source and the title, never the
    ingredients. Vegetarian and vegan need a whole tag that says so. The
    order follows ``CATEGORIES``.
    """
    texts: list[tuple[list[str], str | None]] = []
    for tag in recipe.tags:
        if isinstance(tag, str) and (normalized := _normalize(tag)):
            whole = normalized if _CLEAN_TAG_RE.fullmatch(tag.strip()) else None
            texts.append((normalized.split(" "), whole))
    if recipe.title and (title := _normalize(recipe.title)):
        texts.append((title.split(" "), None))

    found = {
        category.id
        for category in CATEGORIES
        if any(_matches(category, tokens, whole) for tokens, whole in texts)
    }
    # A vegan recipe is vegetarian as well (both said by the source).
    if "vegan" in found:
        found.add("vegetarian")
    return [category.name(language) for category in CATEGORIES if category.id in found]
