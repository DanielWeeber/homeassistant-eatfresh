"""Tests for the Emmi kocht einfach source (WordPress search plus JSON-LD)."""

from __future__ import annotations

import re

import pytest
from aioresponses import aioresponses

from custom_components.eatfresh.errors import RecipeNotFound, SourceBlocked, SourceError
from custom_components.eatfresh.http import HttpClient
from custom_components.eatfresh.sources.emmi import EmmiSource

from .conftest import load_json, load_text, requested_urls

SEARCH_URL = re.compile(r"^https://emmikochteinfach\.de/wp-json/wp/v2/posts\?.*$")
PAGE = "https://emmikochteinfach.de/beispiel-gulaschsuppe/"


@pytest.fixture
def source(client: HttpClient) -> EmmiSource:
    return EmmiSource(client)


def test_flags(source: EmmiSource) -> None:
    assert source.id == "emmi"
    assert source.searchable is True
    assert source.default_enabled is True
    assert "emmikochteinfach.de" in source.hosts
    assert source.matches_url(PAGE)
    assert source.matches_url("https://www.emmikochteinfach.de/x/")
    assert not source.matches_url("https://example.com/x/")


async def test_search(source: EmmiSource, mock: aioresponses) -> None:
    mock.get(SEARCH_URL, payload=load_json("emmi/search.json"))
    hits = await source.search("Suppe", limit=5)
    assert [hit.id for hit in hits] == ["beispiel-gulaschsuppe", "beispiel-ratgeber-vorratsschrank"]
    first = hits[0]
    assert first.key == "emmi:beispiel-gulaschsuppe"
    assert first.title == "Beispiel-Gulaschsuppe – herzhaft"
    assert first.url == PAGE
    assert first.image == "https://emmikochteinfach.de/wp-content/uploads/2026/01/Beispiel-Gulaschsuppe-1.jpg"
    assert hits[1].image is None
    url = requested_urls(mock)[0]
    assert "search=Suppe" in url
    assert "per_page=5" in url


async def test_search_nothing_found(source: EmmiSource, mock: aioresponses) -> None:
    mock.get(SEARCH_URL, payload=[])
    assert await source.search("gibtesnicht") == []


async def test_search_empty_query(source: EmmiSource, mock: aioresponses) -> None:
    assert await source.search("") == []
    assert not mock.requests


async def test_search_ignores_foreign_links(source: EmmiSource, mock: aioresponses) -> None:
    mock.get(
        SEARCH_URL,
        payload=[{"id": 1, "link": "https://example.com/x/", "title": {"rendered": "Fremd"}}],
    )
    assert await source.search("x") == []


async def test_search_blocked(source: EmmiSource, mock: aioresponses) -> None:
    mock.get(SEARCH_URL, status=429)
    with pytest.raises(SourceBlocked):
        await source.search("Suppe")


async def test_search_unexpected_answer(source: EmmiSource, mock: aioresponses) -> None:
    mock.get(SEARCH_URL, payload={"code": "rest_forbidden"})
    with pytest.raises(SourceError):
        await source.search("Suppe")


async def test_get(source: EmmiSource, mock: aioresponses) -> None:
    mock.get(PAGE, body=load_text("emmi/recipe.html"))
    recipe = await source.get("beispiel-gulaschsuppe")
    assert recipe.key == "emmi:beispiel-gulaschsuppe"
    assert recipe.url == PAGE
    assert recipe.title == "Beispiel-Gulaschsuppe"
    assert recipe.description == "Eine erfundene Suppe & ihre Geschichte."
    assert recipe.servings == 4
    assert (recipe.prep_time, recipe.cook_time, recipe.total_time) == (25, 80, 105)
    assert recipe.image.endswith("Beispiel-Gulaschsuppe-1.jpg")
    assert recipe.steps == ["Das Fleisch kräftig anbraten.", "Mit Brühe auffüllen und 80 Minuten köcheln."]
    names = [(i.amount, i.unit, i.name, i.note) for i in recipe.ingredients]
    assert names == [
        (500.0, "g", "Rindergulasch", None),
        (2.0, None, "große Zwiebeln", "gewürfelt"),
        (1.0, "EL", "Paprikapulver", "edelsüß"),
        (1.0, "l", "Brühe", None),
        (0.5, "TL", "Kümmel", None),
        (None, None, "Salz und Pfeffer", None),
    ]


async def test_get_by_url(source: EmmiSource, mock: aioresponses) -> None:
    mock.get(PAGE, body=load_text("emmi/recipe.html"))
    recipe = await source.get_by_url("https://emmikochteinfach.de/beispiel-gulaschsuppe")
    assert recipe.id == "beispiel-gulaschsuppe"


async def test_get_by_url_of_other_host(source: EmmiSource, mock: aioresponses) -> None:
    with pytest.raises(RecipeNotFound):
        await source.get_by_url("https://example.com/beispiel/")
    assert not mock.requests


async def test_post_without_recipe(source: EmmiSource, mock: aioresponses) -> None:
    mock.get(
        "https://emmikochteinfach.de/beispiel-ratgeber-vorratsschrank/",
        body=load_text("emmi/no_recipe.html"),
    )
    with pytest.raises(RecipeNotFound):
        await source.get("beispiel-ratgeber-vorratsschrank")


async def test_get_missing_page(source: EmmiSource, mock: aioresponses) -> None:
    mock.get("https://emmikochteinfach.de/gibt-es-nicht/", status=404)
    with pytest.raises(RecipeNotFound):
        await source.get("gibt-es-nicht")


async def test_get_blocked(source: EmmiSource, mock: aioresponses) -> None:
    mock.get(PAGE, status=403)
    with pytest.raises(SourceBlocked):
        await source.get("beispiel-gulaschsuppe")


@pytest.mark.parametrize("recipe_id", ["", "../etc/passwd", "a b", "https://example.com/x", "x?y=1"])
async def test_get_invalid_id(source: EmmiSource, mock: aioresponses, recipe_id: str) -> None:
    with pytest.raises(RecipeNotFound):
        await source.get(recipe_id)
    assert not mock.requests
