"""Tests for the Küchengötter source (HTML search plus JSON-LD, invented data)."""

from __future__ import annotations

import pytest
from aioresponses import aioresponses

from custom_components.eatfresh.errors import RecipeNotFound, SourceBlocked
from custom_components.eatfresh.http import HttpClient
from custom_components.eatfresh.sources.kuechengoetter import KuechengoetterSource

from .conftest import load_text, requested_urls

BASE = "https://www.kuechengoetter.de"
RECIPE_ID = "beispiel-nudelauflauf-12345"


@pytest.fixture
def source(client: HttpClient) -> KuechengoetterSource:
    return KuechengoetterSource(client)


def test_flags(source: KuechengoetterSource) -> None:
    assert source.id == "kuechengoetter"
    assert source.searchable is True
    assert source.default_enabled is True
    assert "www.kuechengoetter.de" in source.hosts
    assert source.matches_url(f"{BASE}/rezepte/{RECIPE_ID}")
    assert not source.matches_url("https://example.com/rezepte/x-1")


async def test_search(source: KuechengoetterSource, mock: aioresponses) -> None:
    mock.get(f"{BASE}/suche/beispiel%20auflauf", body=load_text("kuechengoetter/search.html"))
    hits = await source.search("beispiel auflauf")
    assert [hit.id for hit in hits] == [RECIPE_ID, "beispiel-eintopf-67890"]
    first, second = hits
    assert first.key == f"kuechengoetter:{RECIPE_ID}"
    assert first.title == "Beispiel-Nudelauflauf mit Käse"
    assert first.url == f"{BASE}/rezepte/{RECIPE_ID}"
    assert first.image == f"{BASE}/uploads/media/210x210/01/12345-beispiel-nudelauflauf.jpg?v=2-12"
    assert first.total_time == 45
    assert second.total_time == 90
    assert requested_urls(mock) == [f"{BASE}/suche/beispiel%20auflauf"]


async def test_search_limit(source: KuechengoetterSource, mock: aioresponses) -> None:
    mock.get(f"{BASE}/suche/x", body=load_text("kuechengoetter/search.html"))
    assert len(await source.search("x", limit=1)) == 1


async def test_search_ignores_navigation_links(source: KuechengoetterSource, mock: aioresponses) -> None:
    mock.get(f"{BASE}/suche/nichts", body=load_text("kuechengoetter/search_empty.html"))
    assert await source.search("nichts") == []


async def test_search_query_is_encoded(source: KuechengoetterSource, mock: aioresponses) -> None:
    mock.get(f"{BASE}/suche/k%C3%A4se%2Fsahne%3Fx", body=load_text("kuechengoetter/search_empty.html"))
    assert await source.search("käse/sahne?x") == []


async def test_search_empty_query(source: KuechengoetterSource, mock: aioresponses) -> None:
    assert await source.search(" ") == []
    assert not mock.requests


async def test_search_blocked(source: KuechengoetterSource, mock: aioresponses) -> None:
    mock.get(f"{BASE}/suche/x", status=403)
    with pytest.raises(SourceBlocked):
        await source.search("x")


async def test_get(source: KuechengoetterSource, mock: aioresponses) -> None:
    mock.get(f"{BASE}/rezepte/{RECIPE_ID}", body=load_text("kuechengoetter/recipe.html"))
    recipe = await source.get(RECIPE_ID)
    assert recipe.key == f"kuechengoetter:{RECIPE_ID}"
    assert recipe.url == f"{BASE}/rezepte/{RECIPE_ID}"
    assert recipe.title == "Beispiel-Nudelauflauf mit Käse"
    assert recipe.description == "Ein erfundener Auflauf für den Test."
    assert recipe.servings == 4  # "Zutaten für 4-6 Personen"
    # The page has no totalTime: it is prep plus cook time.
    assert (recipe.prep_time, recipe.cook_time, recipe.total_time) == (20, 25, 45)
    assert recipe.image.startswith(f"{BASE}/uploads/media/630x630/")
    assert recipe.steps == ["Die Nudeln kochen.", "Alles in eine Form schichten und 25 Minuten backen."]
    assert [(i.amount, i.unit, i.name, i.note) for i in recipe.ingredients] == [
        (250.0, "g", "Penne", None),
        (200.0, "g", "Gouda", "gerieben"),
        (1.0, None, "Zwiebel", None),
        (2.0, None, "Knoblauchzehen", None),
        (1.0, "TL", "Salz", None),
        (200.0, "ml", "Sahne", None),
    ]


async def test_get_by_url(source: KuechengoetterSource, mock: aioresponses) -> None:
    mock.get(f"{BASE}/rezepte/{RECIPE_ID}", body=load_text("kuechengoetter/recipe.html"))
    recipe = await source.get_by_url(f"{BASE}/rezepte/{RECIPE_ID}?utm_source=x")
    assert recipe.id == RECIPE_ID


@pytest.mark.parametrize(
    "url",
    ["https://example.com/rezepte/x-1", f"{BASE}/rezepte/rezepte-finden", f"{BASE}/suche/x"],
)
async def test_get_by_url_of_other_page(source: KuechengoetterSource, mock: aioresponses, url: str) -> None:
    with pytest.raises(RecipeNotFound):
        await source.get_by_url(url)
    assert not mock.requests


async def test_page_without_recipe(source: KuechengoetterSource, mock: aioresponses) -> None:
    mock.get(f"{BASE}/rezepte/leer-1", body=load_text("jsonld/no_recipe.html"))
    with pytest.raises(RecipeNotFound):
        await source.get("leer-1")


async def test_get_missing_page(source: KuechengoetterSource, mock: aioresponses) -> None:
    mock.get(f"{BASE}/rezepte/weg-2", status=404)
    with pytest.raises(RecipeNotFound):
        await source.get("weg-2")


async def test_get_blocked(source: KuechengoetterSource, mock: aioresponses) -> None:
    mock.get(f"{BASE}/rezepte/{RECIPE_ID}", status=429)
    with pytest.raises(SourceBlocked):
        await source.get(RECIPE_ID)


@pytest.mark.parametrize("recipe_id", ["", "kein-id", "../x-1", "a/b-1", "x-1?y"])
async def test_get_invalid_id(source: KuechengoetterSource, mock: aioresponses, recipe_id: str) -> None:
    with pytest.raises(RecipeNotFound):
        await source.get(recipe_id)
    assert not mock.requests
