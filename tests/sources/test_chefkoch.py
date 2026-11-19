"""Tests for the Chefkoch source (JSON API, invented data)."""

from __future__ import annotations

import re

import pytest
from aioresponses import aioresponses

from custom_components.eatfresh.errors import RecipeNotFound, SourceBlocked, SourceError
from custom_components.eatfresh.http import HttpClient
from custom_components.eatfresh.sources.chefkoch import ChefkochSource

from .conftest import load_json, requested_urls

API = "https://api.chefkoch.de/v2/recipes"
SEARCH_URL = re.compile(r"^" + re.escape(API) + r"\?.*$")
RID = "100000000000001"


@pytest.fixture
def source(client: HttpClient) -> ChefkochSource:
    return ChefkochSource(client)


def test_flags(source: ChefkochSource) -> None:
    assert source.id == "chefkoch"
    assert source.default_enabled is False
    assert source.searchable is True
    for host in ("api.chefkoch.de", "www.chefkoch.de", "img.chefkoch-cdn.de"):
        assert host in source.hosts


def test_matches_only_recipe_pages(source: ChefkochSource) -> None:
    assert source.matches_url(f"https://www.chefkoch.de/rezepte/{RID}/Beispiel.html")
    assert source.matches_url(f"https://chefkoch.de/rezepte/{RID}/Beispiel.html")
    assert not source.matches_url("https://img.chefkoch-cdn.de/x.jpg")
    assert not source.matches_url("https://example.com/rezepte/1/x.html")


async def test_search(source: ChefkochSource, mock: aioresponses) -> None:
    mock.get(SEARCH_URL, payload=load_json("chefkoch/search.json"))
    hits = await source.search("Kartoffelsuppe", limit=5)
    # The Plus recipe is left out.
    assert [hit.id for hit in hits] == ["100000000000001", "100000000000002"]
    first, second = hits
    assert first.key == f"chefkoch:{RID}"
    assert first.title == "Beispiel-Kartoffelsuppe"
    assert first.url == f"https://www.chefkoch.de/rezepte/{RID}/Beispiel-{RID}.html"
    assert first.image == (
        f"https://img.chefkoch-cdn.de/rezepte/{RID}/bilder/90001/crop-420x280/beispiel-{RID}.jpg"
    )
    assert first.total_time == 20
    assert first.rating == 4.67
    assert second.rating is None  # no votes yet
    url = requested_urls(mock)[0]
    assert "query=Kartoffelsuppe" in url
    assert "limit=5" in url


async def test_search_nothing_found(source: ChefkochSource, mock: aioresponses) -> None:
    mock.get(SEARCH_URL, payload=load_json("chefkoch/search_empty.json"))
    assert await source.search("gibtesnicht") == []


async def test_search_empty_query(source: ChefkochSource, mock: aioresponses) -> None:
    assert await source.search("") == []
    assert not mock.requests


async def test_search_blocked(source: ChefkochSource, mock: aioresponses) -> None:
    mock.get(SEARCH_URL, status=429)
    with pytest.raises(SourceBlocked):
        await source.search("Suppe")


async def test_search_unexpected_answer(source: ChefkochSource, mock: aioresponses) -> None:
    mock.get(SEARCH_URL, payload=[])
    with pytest.raises(SourceError):
        await source.search("Suppe")


async def test_get(source: ChefkochSource, mock: aioresponses) -> None:
    mock.get(f"{API}/{RID}", payload=load_json("chefkoch/recipe.json"))
    recipe = await source.get(RID)
    assert recipe.key == f"chefkoch:{RID}"
    assert recipe.url == f"https://www.chefkoch.de/rezepte/{RID}/Beispiel-{RID}.html"
    assert recipe.title == "Beispiel-Kartoffelsuppe"
    assert recipe.description == "Eine erfundene Suppe"
    assert recipe.servings == 4
    assert (recipe.prep_time, recipe.cook_time, recipe.total_time) == (20, 30, 50)
    assert recipe.image == (
        f"https://img.chefkoch-cdn.de/rezepte/{RID}/bilder/90001/crop-960x540/beispiel-{RID}.jpg"
    )
    assert recipe.steps == [
        "Kartoffeln schälen und würfeln.",
        "Mit Brühe 30 Minuten kochen.",
        "Abschmecken und servieren.",
    ]
    assert recipe.tags == ["Hauptspeise", "Eintopf"]
    assert [(i.amount, i.unit, i.name, i.note) for i in recipe.ingredients] == [
        (1.0, "kg", "Kartoffeln", "mehlig kochend"),
        (1.0, "Bund", "Suppengemüse", None),
        (1.5, "l", "Brühe", None),
        (None, None, "Salz", None),
        (None, None, "Pfeffer", None),
        (2.0, None, "Würstchen", None),
    ]
    assert recipe.ingredients[0].raw == "1 kg Kartoffeln, mehlig kochend"
    assert recipe.ingredients[2].raw == "1,5 Liter Brühe"


async def test_get_by_url(source: ChefkochSource, mock: aioresponses) -> None:
    mock.get(f"{API}/{RID}", payload=load_json("chefkoch/recipe.json"))
    recipe = await source.get_by_url(f"https://www.chefkoch.de/rezepte/{RID}/Beispiel-{RID}.html")
    assert recipe.id == RID


async def test_get_by_url_of_other_page(source: ChefkochSource, mock: aioresponses) -> None:
    with pytest.raises(RecipeNotFound):
        await source.get_by_url("https://www.chefkoch.de/magazin/artikel/1,0/x.html")
    with pytest.raises(RecipeNotFound):
        await source.get_by_url("https://example.com/rezepte/1/x.html")
    assert not mock.requests


async def test_not_a_recipe(source: ChefkochSource, mock: aioresponses) -> None:
    mock.get(f"{API}/1234", payload=load_json("chefkoch/not_a_recipe.json"))
    with pytest.raises(RecipeNotFound):
        await source.get("1234")


async def test_get_missing(source: ChefkochSource, mock: aioresponses) -> None:
    mock.get(f"{API}/1234", status=404)
    with pytest.raises(RecipeNotFound):
        await source.get("1234")


async def test_get_blocked(source: ChefkochSource, mock: aioresponses) -> None:
    mock.get(f"{API}/{RID}", status=403)
    with pytest.raises(SourceBlocked):
        await source.get(RID)


@pytest.mark.parametrize("recipe_id", ["", "abc", "1/2", "../1"])
async def test_get_invalid_id(source: ChefkochSource, mock: aioresponses, recipe_id: str) -> None:
    with pytest.raises(RecipeNotFound):
        await source.get(recipe_id)
    assert not mock.requests
