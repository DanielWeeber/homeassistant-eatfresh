"""Pasted links are saved under the canonical address of the page."""

from __future__ import annotations

import json

import pytest
from aioresponses import aioresponses

from custom_components.eatfresh.http import HttpClient
from custom_components.eatfresh.sources.gaumenfreundin import GaumenfreundinSource
from custom_components.eatfresh.sources.jsonld import (
    JsonLdSource,
    canonical_address,
    recipe_from_html,
)

PAGE = "https://example.com/rezepte/suppe/"
PASTED = "https://www.example.com/rezepte/suppe/amp/?utm_source=pinterest&fbclid=x#jump"


def page(*, link: str | None = None, **node: object) -> str:
    """Return a recipe page with an optional canonical link and node fields."""
    recipe = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": "Suppe",
        "recipeIngredient": ["1 Karotte"],
        "recipeInstructions": ["Kochen."],
        **node,
    }
    head = f'<link rel="canonical" href="{link}">' if link else ""
    return (
        f"<html><head>{head}"
        f'<script type="application/ld+json">{json.dumps(recipe)}</script>'
        "</head><body></body></html>"
    )


def test_canonical_link_wins() -> None:
    recipe = recipe_from_html(
        page(link=PAGE, url="https://example.com/other/"),
        source="jsonld",
        recipe_id=PASTED,
        url=PASTED,
        canonical=True,
    )
    assert recipe.url == PAGE
    # The key stays the pasted address; only the stored address changes.
    assert recipe.id == PASTED


def test_without_canonical_flag_the_address_stays() -> None:
    recipe = recipe_from_html(
        page(link=PAGE), source="jsonld", recipe_id=PASTED, url=PASTED
    )
    assert recipe.url == PASTED


@pytest.mark.parametrize(
    ("link", "node", "expected"),
    [
        # Relative canonical link.
        ("/rezepte/suppe/", {}, "https://www.example.com/rezepte/suppe/"),
        # No link: address of the recipe data.
        (None, {"url": PAGE}, PAGE),
        (None, {"mainEntityOfPage": {"@id": PAGE}}, PAGE),
        (None, {"mainEntityOfPage": PAGE}, PAGE),
        # Another site is never taken over.
        ("https://evil.example.org/x", {}, PASTED),
        (None, {"url": "https://evil.example.org/x"}, PASTED),
        # Only http(s).
        ("javascript:alert(1)", {}, PASTED),
        ("ftp://example.com/x", {"url": "data:text/html,x"}, PASTED),
        # A bad link is skipped, the next candidate is used.
        ("https://evil.example.org/x", {"url": PAGE}, PAGE),
        (None, {}, PASTED),
    ],
)
def test_canonical_candidates(link: str | None, node: dict, expected: str) -> None:
    recipe = recipe_from_html(
        page(link=link, **node),
        source="jsonld",
        recipe_id=PASTED,
        url=PASTED,
        canonical=True,
    )
    assert recipe.url == expected


def test_canonical_address_same_host_without_www() -> None:
    assert canonical_address("https://example.com/a", "https://www.example.com/a/") == (
        "https://www.example.com/a/"
    )
    assert canonical_address("https://example.com/a", "https://sub.example.com/a") == (
        "https://example.com/a"
    )


async def test_pasted_link_gets_canonical_address(
    client: HttpClient, mock: aioresponses
) -> None:
    pasted = "https://www.example.com/rezepte/suppe/?utm_source=pinterest"
    mock.get(pasted, body=page(link=PAGE))
    recipe = await JsonLdSource(client).get(pasted)
    assert recipe.url == PAGE
    assert recipe.key == f"jsonld:{pasted}"


async def test_gaumenfreundin_link_gets_canonical_address(
    client: HttpClient, mock: aioresponses
) -> None:
    canonical = "https://www.gaumenfreundin.de/kuerbissuppe/"
    pasted = "https://gaumenfreundin.de/kuerbissuppe/?utm_source=pinterest"
    mock.get(pasted, body=page(link=canonical))
    recipe = await GaumenfreundinSource(client).get_by_url(pasted)
    assert recipe.url == canonical


def test_diet_of_the_recipe_data_becomes_a_tag() -> None:
    recipe = recipe_from_html(
        page(
            suitableForDiet=["https://schema.org/VeganDiet", "LowFatDiet"],
            keywords="Schnell, Einfach",
        ),
        source="jsonld",
        recipe_id=PAGE,
        url=PAGE,
    )
    assert recipe.tags == ["Vegan", "Schnell", "Einfach"]
    recipe = recipe_from_html(
        page(suitableForDiet="http://schema.org/VegetarianDiet"),
        source="jsonld",
        recipe_id=PAGE,
        url=PAGE,
    )
    assert recipe.tags == ["Vegetarian"]
