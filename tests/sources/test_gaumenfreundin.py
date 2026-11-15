"""Tests for the Gaumenfreundin source (WordPress REST, invented data)."""

from __future__ import annotations

import re

import pytest
from aioresponses import aioresponses

from custom_components.eatfresh.errors import RecipeNotFound, SourceBlocked, SourceError
from custom_components.eatfresh.http import HttpClient
from custom_components.eatfresh.sources.gaumenfreundin import GaumenfreundinSource

from .conftest import load_json, load_text, requested_urls

API = "https://www.gaumenfreundin.de/wp-json/wp/v2/wprm_recipe"
SEARCH_URL = re.compile(r"^" + re.escape(API) + r"\?.*$")
PAGE = "https://www.gaumenfreundin.de/beispiel-gemuesepfanne/"


@pytest.fixture
def source(client: HttpClient) -> GaumenfreundinSource:
    return GaumenfreundinSource(client)


def test_flags(source: GaumenfreundinSource) -> None:
    assert source.id == "gaumenfreundin"
    assert source.default_enabled is True
    assert source.searchable is True
    assert "www.gaumenfreundin.de" in source.hosts
    assert source.matches_url("https://www.gaumenfreundin.de/x/")
    assert source.matches_url("https://gaumenfreundin.de/x/")
    assert not source.matches_url("https://example.com/x/")


async def test_search(source: GaumenfreundinSource, mock: aioresponses) -> None:
    mock.get(SEARCH_URL, payload=load_json("gaumenfreundin/search.json"))
    hits = await source.search("Suppe", limit=10)
    assert [hit.id for hit in hits] == ["1001", "1002"]
    first = hits[0]
    assert first.key == "gaumenfreundin:1001"
    assert first.title == "Beispiel-Kürbissuppe: schnell & cremig"
    assert first.url == "https://www.gaumenfreundin.de/beispiel-kuerbissuppe/"
    assert first.image.endswith("beispiel-kuerbissuppe.jpg")
    assert first.total_time == 30
    assert first.rating == 4.5
    assert hits[1].rating is None
    url = requested_urls(mock)[0]
    assert "search=Suppe" in url
    assert "per_page=10" in url


async def test_search_limit(source: GaumenfreundinSource, mock: aioresponses) -> None:
    mock.get(SEARCH_URL, payload=load_json("gaumenfreundin/search.json"))
    assert len(await source.search("Suppe", limit=1)) == 1


async def test_search_nothing_found(source: GaumenfreundinSource, mock: aioresponses) -> None:
    mock.get(SEARCH_URL, payload=[])
    assert await source.search("gibtesnicht") == []


async def test_search_empty_query_makes_no_request(
    source: GaumenfreundinSource, mock: aioresponses
) -> None:
    assert await source.search("   ") == []
    assert not mock.requests


async def test_search_blocked(source: GaumenfreundinSource, mock: aioresponses) -> None:
    mock.get(SEARCH_URL, status=403)
    with pytest.raises(SourceBlocked):
        await source.search("Suppe")


async def test_search_unexpected_answer(source: GaumenfreundinSource, mock: aioresponses) -> None:
    mock.get(SEARCH_URL, payload={"code": "rest_invalid_param"})
    with pytest.raises(SourceError):
        await source.search("Suppe")


async def test_get(source: GaumenfreundinSource, mock: aioresponses) -> None:
    mock.get(f"{API}/1001", payload=load_json("gaumenfreundin/recipe.json"))
    recipe = await source.get("1001")
    assert recipe.key == "gaumenfreundin:1001"
    assert recipe.title == "Beispiel-Kürbissuppe: schnell & cremig"
    assert recipe.url == "https://www.gaumenfreundin.de/beispiel-kuerbissuppe/"
    assert recipe.description == "Eine erfundene Beispielsuppe für den Test."
    assert recipe.servings == 4
    assert recipe.prep_time == 10
    assert recipe.cook_time == 20
    assert recipe.total_time == 30
    assert recipe.image.endswith("beispiel-kuerbissuppe.jpg")
    assert recipe.tags == ["Suppe", "Einfach", "Herbst"]
    assert recipe.steps[0] == "Kürbis würfeln und die Zwiebel hacken."
    assert len(recipe.steps) == 3
    by_name = {ingredient.name: ingredient for ingredient in recipe.ingredients}
    assert len(recipe.ingredients) == 9
    assert (by_name["Zwiebel"].amount, by_name["Zwiebel"].unit) == (0.5, None)
    assert (by_name["Olivenöl"].amount, by_name["Olivenöl"].unit) == (2.0, "EL")
    assert (by_name["Currypulver"].amount, by_name["Currypulver"].unit) == (1.5, "TL")
    assert by_name["Knoblauch"].unit == "Zehe"
    assert by_name["Muskat"].note == "frisch gerieben"
    assert by_name["Muskat"].raw == "1 Prise Muskat, frisch gerieben"
    assert by_name["Salz und Pfeffer"].amount is None
    assert by_name["Salz und Pfeffer"].unit is None


async def test_get_cleans_plural_notation_in_units(
    source: GaumenfreundinSource, mock: aioresponses
) -> None:
    mock.get(f"{API}/1002", payload=load_json("gaumenfreundin/search.json")[1])
    recipe = await source.get("1002")
    tomatoes = recipe.ingredients[1]
    assert (tomatoes.amount, tomatoes.unit, tomatoes.name, tomatoes.note) == (
        1.0,
        "Dose",
        "Tomaten",
        "gehackt",
    )


async def test_get_by_url_uses_json_ld(source: GaumenfreundinSource, mock: aioresponses) -> None:
    mock.get(PAGE, body=load_text("gaumenfreundin/page.html"))
    recipe = await source.get_by_url(PAGE)
    assert recipe.source == "gaumenfreundin"
    assert recipe.id == PAGE
    assert recipe.title == "Beispiel-Gemüsepfanne"
    assert recipe.servings == 4
    assert recipe.total_time == 25
    assert [step for step in recipe.steps] == ["Gemüse schneiden.", "Im Öl braten."]
    assert recipe.tags == ["Hauptgericht", "Pfanne", "Schnell"]
    # The same recipe works again through get() with the address as id.
    mock.get(PAGE, body=load_text("gaumenfreundin/page.html"))
    assert (await source.get(recipe.id)).title == recipe.title


async def test_get_by_url_of_other_host(source: GaumenfreundinSource, mock: aioresponses) -> None:
    with pytest.raises(RecipeNotFound):
        await source.get_by_url("https://example.com/x/")
    with pytest.raises(RecipeNotFound):
        await source.get("https://example.com/x/")
    assert not mock.requests


@pytest.mark.parametrize("recipe_id", ["abc", "12 3", "../1", ""])
async def test_get_invalid_id(source: GaumenfreundinSource, mock: aioresponses, recipe_id: str) -> None:
    with pytest.raises(RecipeNotFound):
        await source.get(recipe_id)
    assert not mock.requests


async def test_get_missing(source: GaumenfreundinSource, mock: aioresponses) -> None:
    mock.get(f"{API}/9999", status=404, payload={"code": "rest_post_invalid_id"})
    with pytest.raises(RecipeNotFound):
        await source.get("9999")


async def test_get_without_recipe_data(source: GaumenfreundinSource, mock: aioresponses) -> None:
    mock.get(f"{API}/5", payload={"id": 5, "link": "https://www.gaumenfreundin.de/x/", "recipe": []})
    with pytest.raises(RecipeNotFound):
        await source.get("5")


async def test_get_blocked(source: GaumenfreundinSource, mock: aioresponses) -> None:
    mock.get(f"{API}/1001", status=429)
    with pytest.raises(SourceBlocked):
        await source.get("1001")


async def test_page_without_recipe(source: GaumenfreundinSource, mock: aioresponses) -> None:
    mock.get(PAGE, body=load_text("jsonld/no_recipe.html"))
    with pytest.raises(RecipeNotFound):
        await source.get_by_url(PAGE)
