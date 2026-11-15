"""Tests for the source registry and URL routing."""

from __future__ import annotations

import pytest

from custom_components.eatfresh.errors import RecipeNotFound
from custom_components.eatfresh.http import HttpClient
from custom_components.eatfresh.sources import SOURCE_CLASSES, build_sources, source_for_url
from custom_components.eatfresh.sources.base import RecipeSource


def test_source_ids_are_unique_and_complete() -> None:
    ids = [cls.id for cls in SOURCE_CLASSES]
    assert ids == ["gaumenfreundin", "emmi", "kuechengoetter", "chefkoch", "jsonld"]
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize("cls", SOURCE_CLASSES, ids=lambda cls: cls.id)
def test_every_source_declares_hosts_and_names(cls: type[RecipeSource]) -> None:
    assert cls.name
    if cls.id != "jsonld":
        assert cls.hosts
        assert all(host == host.lower() and "/" not in host for host in cls.hosts)


def test_only_chefkoch_is_off_by_default() -> None:
    assert [cls.id for cls in SOURCE_CLASSES if not cls.default_enabled] == ["chefkoch"]


def test_jsonld_is_not_searchable() -> None:
    searchable = {cls.id: cls.searchable for cls in SOURCE_CLASSES}
    assert searchable == {
        "gaumenfreundin": True,
        "emmi": True,
        "kuechengoetter": True,
        "chefkoch": True,
        "jsonld": False,
    }


def test_chefkoch_images_come_from_declared_hosts() -> None:
    chefkoch = next(cls for cls in SOURCE_CLASSES if cls.id == "chefkoch")
    assert "img.chefkoch-cdn.de" in chefkoch.hosts


def test_build_sources_always_includes_jsonld(client: HttpClient) -> None:
    sources = build_sources(client, [])
    assert list(sources) == ["jsonld"]
    sources = build_sources(client, ["emmi", "gaumenfreundin", "unbekannt"])
    assert list(sources) == ["gaumenfreundin", "emmi", "jsonld"]
    assert all(isinstance(source, RecipeSource) for source in sources.values())


def test_source_for_url(client: HttpClient) -> None:
    sources = build_sources(client, ["gaumenfreundin", "emmi", "kuechengoetter", "chefkoch"])
    assert source_for_url(sources, "https://emmikochteinfach.de/x/").id == "emmi"
    assert source_for_url(sources, "https://www.kuechengoetter.de/rezepte/x-1").id == "kuechengoetter"
    assert source_for_url(sources, "https://www.chefkoch.de/rezepte/1/x.html").id == "chefkoch"
    assert source_for_url(sources, "https://example.com/rezept").id == "jsonld"


def test_source_for_url_falls_back_when_source_is_off(client: HttpClient) -> None:
    sources = build_sources(client, ["gaumenfreundin"])
    assert source_for_url(sources, "https://emmikochteinfach.de/x/").id == "jsonld"


def test_chefkoch_link_is_refused_while_chefkoch_is_off(client: HttpClient) -> None:
    sources = build_sources(client, ["gaumenfreundin"])
    with pytest.raises(RecipeNotFound):
        source_for_url(sources, "https://www.chefkoch.de/rezepte/1/x.html")


def test_source_for_url_without_fallback(client: HttpClient) -> None:
    sources = build_sources(client, ["emmi"])
    del sources["jsonld"]
    with pytest.raises(RecipeNotFound):
        source_for_url(sources, "https://example.com/rezept")


def test_blocked_hosts_while_chefkoch_is_off() -> None:
    from custom_components.eatfresh.sources import blocked_hosts

    blocked = blocked_hosts(["gaumenfreundin", "emmi"])
    assert blocked == {"api.chefkoch.de", "chefkoch.de", "img.chefkoch-cdn.de"}
    assert blocked_hosts(["chefkoch"]) == frozenset()


def test_blocked_hosts_keep_hosts_of_enabled_sources() -> None:
    from custom_components.eatfresh.sources import blocked_hosts

    class Shared(RecipeSource):
        id = "shared"
        name = "Shared"
        default_enabled = False
        hosts = ("www.shared.example", "cdn.common.example")

    class Common(RecipeSource):
        id = "common"
        name = "Common"
        hosts = ("cdn.common.example",)

    assert blocked_hosts([], (Shared, Common)) == {"shared.example"}
