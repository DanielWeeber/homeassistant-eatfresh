"""Tests for the generic JSON-LD reader and the "paste a link" source."""

from __future__ import annotations


import pytest
from aioresponses import aioresponses

from custom_components.eatfresh.errors import RecipeNotFound, SourceBlocked, SourceError
from custom_components.eatfresh.http import HttpClient
from custom_components.eatfresh.sources.jsonld import (
    JsonLdSource,
    find_recipe_node,
    parse_duration,
    recipe_from_html,
)

from .conftest import load_text

URL = "https://example.com/rezepte/beispiel"


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        ("PT1H20M", 80),
        ("PT45M", 45),
        ("PT2H", 120),
        ("P0DT1H30M", 90),
        ("P1DT2H", 1560),
        ("PT90S", 2),
        ("PT1.5H", 90),
        ("pt10m", 10),
        ("PT0S", None),
        ("PT0M", None),
        ("", None),
        ("1 Stunde", None),
        (None, None),
        (30, None),
    ],
)
def test_parse_duration(text: object, minutes: int | None) -> None:
    assert parse_duration(text) == minutes


def test_graph_with_sections_and_object_image() -> None:
    recipe = recipe_from_html(
        load_text("jsonld/graph.html"), source="jsonld", recipe_id=URL, url=URL
    )
    assert recipe.title == "Beispiel-Salat"
    assert recipe.image == "https://example.com/img/salat.jpg"
    assert recipe.servings == 2
    assert recipe.total_time == 15
    assert recipe.steps == ["Salat waschen.", "Marinade rühren.", "Alles mischen."]
    assert [(i.amount, i.unit, i.name) for i in recipe.ingredients] == [
        (1.0, "Kopf", "Salat"),
        (2.0, "EL", "Essig"),
    ]


def test_top_level_list_text_instructions_and_relative_image() -> None:
    recipe = recipe_from_html(
        load_text("jsonld/list.html"), source="jsonld", recipe_id=URL, url=URL
    )
    assert recipe.title == "Beispiel-Brot"
    assert recipe.image == "https://example.com/bilder/brot.jpg"
    assert recipe.servings == 1
    assert (recipe.prep_time, recipe.cook_time, recipe.total_time) == (30, 60, 90)
    assert recipe.steps == ["Teig kneten.", "Gehen lassen.", "Backen."]
    assert recipe.tags == ["Backen", "Brot"]
    assert recipe.ingredients[1].name == "Hefe"
    assert recipe.ingredients[1].unit == "Würfel"


def test_no_recipe_in_page() -> None:
    with pytest.raises(RecipeNotFound):
        recipe_from_html(
            load_text("jsonld/no_recipe.html"), source="jsonld", recipe_id=URL, url=URL
        )


def test_broken_json_is_skipped() -> None:
    assert find_recipe_node(load_text("jsonld/broken.html")) is None


def test_page_without_script() -> None:
    assert find_recipe_node("<html><body>nichts</body></html>") is None


def test_recipe_without_title_or_content_is_refused() -> None:
    page = '<script type="application/ld+json">{"@type":"Recipe","name":"Leer"}</script>'
    with pytest.raises(RecipeNotFound):
        recipe_from_html(page, source="jsonld", recipe_id=URL, url=URL)


def test_image_reference_by_id_and_single_string_yield() -> None:
    page = (
        '<script type="application/ld+json">{"@graph":['
        '{"@type":"ImageObject","@id":"#img","url":"https://example.com/a.jpg"},'
        '{"@type":"Recipe","name":"X","image":{"@id":"#img"},"recipeYield":"Für 6 Personen",'
        '"recipeIngredient":"1 Ei","recipeInstructions":[{"@type":"HowToStep","name":"Kochen"}]}]}'
        "</script>"
    )
    recipe = recipe_from_html(page, source="jsonld", recipe_id=URL, url=URL)
    assert recipe.image == "https://example.com/a.jpg"
    assert recipe.servings == 6
    assert recipe.steps == ["Kochen"]
    assert recipe.ingredients[0].name == "Ei"


def test_type_given_as_schema_url() -> None:
    page = (
        '<script type="application/ld+json; charset=utf-8">'
        '{"@type":"http://schema.org/Recipe","name":"Y","recipeIngredient":["2 Eier"]}</script>'
    )
    assert recipe_from_html(page, source="jsonld", recipe_id=URL, url=URL).title == "Y"


class TestJsonLdSource:
    """The source around the reader."""

    def test_flags(self, client: HttpClient) -> None:
        source = JsonLdSource(client)
        assert source.id == "jsonld"
        assert source.searchable is False
        assert source.default_enabled is True
        assert source.matches_url("https://example.org/a")
        assert not source.matches_url("mailto:a@example.org")
        assert not source.matches_url("ftp://example.org/a")

    async def test_search_returns_nothing(self, client: HttpClient) -> None:
        assert await JsonLdSource(client).search("suppe") == []

    async def test_get(self, client: HttpClient, mock: aioresponses) -> None:
        mock.get(URL, body=load_text("jsonld/graph.html"))
        recipe = await JsonLdSource(client).get(URL)
        assert recipe.source == "jsonld"
        assert recipe.id == URL
        assert recipe.url == URL
        assert recipe.key == f"jsonld:{URL}"
        assert recipe.title == "Beispiel-Salat"

    async def test_get_by_url_strips_blanks(self, client: HttpClient, mock: aioresponses) -> None:
        mock.get(URL, body=load_text("jsonld/graph.html"))
        recipe = await JsonLdSource(client).get_by_url(f"  {URL}\n")
        assert recipe.id == URL

    async def test_page_without_recipe(self, client: HttpClient, mock: aioresponses) -> None:
        mock.get(URL, body=load_text("jsonld/no_recipe.html"))
        with pytest.raises(RecipeNotFound):
            await JsonLdSource(client).get(URL)

    async def test_blocked(self, client: HttpClient, mock: aioresponses) -> None:
        mock.get(URL, status=403)
        with pytest.raises(SourceBlocked):
            await JsonLdSource(client).get(URL)

    async def test_captcha_page(self, client: HttpClient, mock: aioresponses) -> None:
        mock.get(URL, body=load_text("jsonld/captcha.html"))
        with pytest.raises(SourceBlocked):
            await JsonLdSource(client).get(URL)

    async def test_missing_page(self, client: HttpClient, mock: aioresponses) -> None:
        mock.get(URL, status=404)
        with pytest.raises(RecipeNotFound):
            await JsonLdSource(client).get(URL)

    async def test_server_error(self, client: HttpClient, mock: aioresponses) -> None:
        mock.get(URL, status=500, body="boom")
        with pytest.raises(SourceError) as info:
            await JsonLdSource(client).get(URL)
        assert not isinstance(info.value, SourceBlocked)

    async def test_private_name_makes_no_request(
        self, client: HttpClient, mock: aioresponses, fake_dns: dict[str, list[str]]
    ) -> None:
        fake_dns["nas.example.net"] = ["172.16.5.5"]
        with pytest.raises(RecipeNotFound):
            await JsonLdSource(client).get("https://nas.example.net/rezept")
        assert not mock.requests

    async def test_private_address_makes_no_request(
        self, client: HttpClient, mock: aioresponses
    ) -> None:
        with pytest.raises(RecipeNotFound):
            await JsonLdSource(client).get("http://10.20.30.40/rezept")
        assert not mock.requests


async def test_large_page_is_parsed_off_the_event_loop(
    client: HttpClient, mock: aioresponses, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A big page is parsed in a worker thread, a small one directly."""
    import threading

    from custom_components.eatfresh.sources import jsonld

    threads: list[str] = []
    original = jsonld.recipe_from_html

    def spy(*args, **kwargs):
        threads.append(threading.current_thread().name)
        return original(*args, **kwargs)

    monkeypatch.setattr(jsonld, "recipe_from_html", spy)
    # The mocked network cannot carry a real 256 kB body; lower the limit.
    assert jsonld.EXECUTOR_MIN_CHARS <= 512_000
    page = load_text("jsonld/graph.html")
    monkeypatch.setattr(jsonld, "EXECUTOR_MIN_CHARS", len(page) + 1000)
    big = page.replace("</body>", "<!--" + " " * 2000 + "--></body>")
    assert len(big) > jsonld.EXECUTOR_MIN_CHARS
    mock.get(URL, body=big)
    mock.get(URL + "-klein", body=page)
    source = JsonLdSource(client)
    big_recipe = await source.get(URL)
    small_recipe = await source.get(URL + "-klein")
    assert big_recipe.title == small_recipe.title
    main = threading.main_thread().name
    assert threads[0] != main
    assert threads[1] == main


async def test_link_source_refuses_switched_off_hosts(
    session, mock: aioresponses
) -> None:
    """A key like ``jsonld:https://www.chefkoch.de/...`` makes no request."""
    from custom_components.eatfresh.http import HostBlocked
    from custom_components.eatfresh.sources import blocked_hosts

    client = HttpClient(
        session, "EatFresh-Test/0.1", min_interval=0, blocked_hosts=blocked_hosts([])
    )
    source = JsonLdSource(client)
    with pytest.raises(HostBlocked):
        await source.get("https://www.chefkoch.de/rezepte/1/x.html")
    mock.get("https://kurz.example.com/abc", status=301,
             headers={"Location": "https://www.chefkoch.de/rezepte/1/x.html"})
    with pytest.raises(HostBlocked):
        await source.get_by_url("https://kurz.example.com/abc")
    assert [str(url) for (_m, url) in mock.requests] == ["https://kurz.example.com/abc"]
