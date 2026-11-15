"""Tests for the EatFresh WebSocket commands."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eatfresh.errors import (
    KitchenOwlAuthError,
    KitchenOwlError,
    RecipeNotFound,
    SourceBlocked,
    SourceError,
)

from custom_components.eatfresh.models import SearchHit

from .conftest import IMAGE_HOST, RECIPE_HOST, make_recipe


class WS:
    """Small helper around the test WebSocket client."""

    def __init__(self, client: Any) -> None:
        self.client = client

    async def call(self, msg_type: str, **kwargs: Any) -> dict[str, Any]:
        await self.client.send_json_auto_id({"type": msg_type, **kwargs})
        return await self.client.receive_json()


@pytest.fixture
async def ws(init_integration: MockConfigEntry, hass_ws_client) -> WS:
    """Return a connected WebSocket helper."""
    return WS(await hass_ws_client())


def sources_of(entry: MockConfigEntry) -> dict[str, Any]:
    return entry.runtime_data.sources


async def test_sources(ws: WS) -> None:
    """All known sources with their state."""
    msg = await ws.call("eatfresh/sources")
    assert msg["success"]
    assert msg["result"]["sources"] == [
        {"id": "fakea", "name": "Fake A", "enabled": True, "searchable": True},
        {"id": "fakeb", "name": "Fake B", "enabled": True, "searchable": True},
        {"id": "chefkoch", "name": "Chefkoch", "enabled": False, "searchable": True},
        {"id": "jsonld", "name": "Recipe link", "enabled": True, "searchable": False},
    ]


async def test_search_mixes_marks_and_signs(
    ws: WS, init_integration: MockConfigEntry
) -> None:
    """Hits are interleaved, carry favorite flags and signed images."""
    init_integration.runtime_data.store.async_set(
        "fakeb:fakeb-1",
        source="fakeb",
        recipe_id="fakeb-1",
        url="u",
        title="t",
        image=None,
        kitchenowl_id=7,
    )
    msg = await ws.call("eatfresh/search", query="  Pasta ")
    assert msg["success"]
    hits = msg["result"]["hits"]
    assert [hit["key"] for hit in hits] == [
        "fakea:fakea-1",
        "fakeb:fakeb-1",
        "fakea:fakea-2",
        "fakeb:fakeb-2",
    ]
    assert [hit["favorite"] for hit in hits] == [False, True, False, False]
    assert hits[0]["image"].startswith("/api/eatfresh/image?url=")
    assert "authSig=" in hits[0]["image"]
    assert msg["result"]["errors"] == []
    sources_of(init_integration)["fakea"].search.assert_awaited_once_with("Pasta", 20)


async def test_search_cache_and_filter(
    ws: WS, init_integration: MockConfigEntry
) -> None:
    """Repeated searches come from the cache; sources can be filtered."""
    fakea = sources_of(init_integration)["fakea"]
    fakeb = sources_of(init_integration)["fakeb"]
    await ws.call("eatfresh/search", query="pasta", sources=["fakea"], limit=5)
    msg = await ws.call("eatfresh/search", query="PASTA", sources=["fakea", "jsonld", "chefkoch"], limit=5)
    assert msg["success"]
    assert len(msg["result"]["hits"]) == 2
    assert fakea.search.await_count == 1
    fakeb.search.assert_not_awaited()


async def test_search_failing_source(
    ws: WS, init_integration: MockConfigEntry
) -> None:
    """A broken source shows up in errors, the others still deliver."""
    sources_of(init_integration)["fakea"].search.side_effect = SourceBlocked("429")
    msg = await ws.call("eatfresh/search", query="soup")
    assert msg["success"]
    assert msg["result"]["errors"] == [{"source": "fakea", "message": "429"}]
    assert {hit["source"] for hit in msg["result"]["hits"]} == {"fakeb"}

    sources_of(init_integration)["fakeb"].search.side_effect = ValueError("bug")
    msg = await ws.call("eatfresh/search", query="stew")
    assert msg["result"]["hits"] == []
    assert {err["source"] for err in msg["result"]["errors"]} == {"fakea", "fakeb"}


async def test_search_validation(ws: WS) -> None:
    """Empty queries and wrong limits are rejected."""
    msg = await ws.call("eatfresh/search", query="   ")
    assert not msg["success"]
    assert msg["error"]["code"] == "invalid_format"
    msg = await ws.call("eatfresh/search", query="x", limit=500)
    assert msg["error"]["code"] == "invalid_format"


async def test_recipe_by_key_and_url(
    ws: WS, init_integration: MockConfigEntry
) -> None:
    """Recipes load by key or by URL and are cached."""
    fakea = sources_of(init_integration)["fakea"]
    msg = await ws.call("eatfresh/recipe", key="fakea:r1")
    assert msg["success"]
    result = msg["result"]
    assert result["recipe"]["key"] == "fakea:r1"
    assert result["recipe"]["ingredients"][0]["name"] == "flour"
    assert "authSig=" in result["recipe"]["image"]
    assert result["favorite"] is False
    assert result["kitchenowl_id"] is None

    await ws.call("eatfresh/recipe", key="fakea:r1")
    assert fakea.get.await_count == 1

    msg = await ws.call("eatfresh/recipe", url=f"https://{RECIPE_HOST}/fakea/r1")
    assert msg["result"]["recipe"]["key"] == "fakea:r1"
    fakea.get_by_url.assert_not_awaited()  # known URL comes from the cache

    msg = await ws.call("eatfresh/recipe", url=f"https://{RECIPE_HOST}/fakea/r9")
    assert msg["result"]["recipe"]["key"] == "fakea:r9"
    fakea.get_by_url.assert_awaited_once()

    msg = await ws.call("eatfresh/recipe", url="https://blog.example.org/cake")
    assert msg["result"]["recipe"]["source"] == "jsonld"


async def test_recipe_errors(ws: WS, init_integration: MockConfigEntry) -> None:
    """Errors carry the agreed codes."""
    msg = await ws.call("eatfresh/recipe", key="no-colon")
    assert msg["error"]["code"] == "not_found"
    msg = await ws.call("eatfresh/recipe", key="chefkoch:1")
    assert msg["error"]["code"] == "not_found"
    msg = await ws.call("eatfresh/recipe")
    assert msg["error"]["code"] == "invalid_format"
    msg = await ws.call("eatfresh/recipe", key="a:1", url="https://x.example.com")
    assert msg["error"]["code"] == "invalid_format"

    fakea = sources_of(init_integration)["fakea"]
    for error, code in (
        (SourceBlocked("captcha"), "source_blocked"),
        (RecipeNotFound("gone"), "not_found"),
        (SourceError("timeout"), "source_error"),
    ):
        fakea.get.side_effect = error
        msg = await ws.call("eatfresh/recipe", key="fakea:new")
        assert msg["error"] == {"code": code, "message": str(error)}


async def test_favorite_flow(
    hass: HomeAssistant,
    ws: WS,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Heart: store first, then find_by_source, then create."""
    msg = await ws.call("eatfresh/favorite", key="fakea:r1")
    assert msg["result"] == {"kitchenowl_id": 42, "created": True}
    # First from the cached list, then once more with a fresh list.
    assert mock_client.find_by_source.await_args_list == [
        call(1, f"https://{RECIPE_HOST}/fakea/r1"),
        call(1, f"https://{RECIPE_HOST}/fakea/r1", fresh=True),
    ]
    created_recipe = mock_client.create_recipe.await_args.args[1]
    assert created_recipe.key == "fakea:r1"

    # Second heart comes from the store, no KitchenOwl call.
    msg = await ws.call("eatfresh/favorite", key="fakea:r1")
    assert msg["result"] == {"kitchenowl_id": 42, "created": False}
    assert mock_client.find_by_source.await_count == 2

    # Recipe already in KitchenOwl: no new recipe.
    mock_client.find_by_source.return_value = 99
    msg = await ws.call("eatfresh/favorite", key="fakeb:r2")
    assert msg["result"] == {"kitchenowl_id": 99, "created": False}
    assert mock_client.create_recipe.await_count == 1

    msg = await ws.call("eatfresh/recipe", key="fakea:r1")
    assert msg["result"]["favorite"] is True
    assert msg["result"]["kitchenowl_id"] == 42

    msg = await ws.call("eatfresh/favorites")
    favorites = msg["result"]["favorites"]
    assert {fav["key"] for fav in favorites} == {"fakea:r1", "fakeb:r2"}
    fav = next(f for f in favorites if f["key"] == "fakea:r1")
    assert fav["kitchenowl_id"] == 42
    assert fav["title"] == "Test recipe r1"
    assert "authSig=" in fav["image"]
    assert fav["added_at"]

    msg = await ws.call("eatfresh/unfavorite", key="fakea:r1")
    assert msg["success"] and msg["result"] == {}
    msg = await ws.call("eatfresh/favorites")
    assert [fav["key"] for fav in msg["result"]["favorites"]] == ["fakeb:r2"]
    mock_client.delete_recipe.assert_not_called()


async def test_same_recipe_with_two_keys(
    ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Search id and pasted link of one recipe share one heart, no duplicate."""
    page = f"https://{RECIPE_HOST}/fakea/123"
    link = f"http://{RECIPE_HOST.upper()}/fakea/123/#rezept"
    link_key = f"fakea:{link}"
    source = sources_of(init_integration)["fakea"]

    def get(recipe_id: str) -> Any:
        recipe = make_recipe("fakea", recipe_id)
        if recipe_id.startswith("http"):
            recipe.url = recipe_id
        return recipe

    source.get.side_effect = get
    source.search.side_effect = lambda query, limit=20: [
        SearchHit(source="fakea", id="123", title="T", url=page)
    ]

    msg = await ws.call("eatfresh/favorite", key="fakea:123")
    assert msg["result"] == {"kitchenowl_id": 42, "created": True}

    # The link way sees the heart and does not create a second entry.
    msg = await ws.call("eatfresh/recipe", key=link_key)
    assert msg["result"]["favorite"] is True
    assert msg["result"]["kitchenowl_id"] == 42
    msg = await ws.call("eatfresh/favorite", key=link_key)
    assert msg["result"] == {"kitchenowl_id": 42, "created": False}
    assert mock_client.create_recipe.await_count == 1
    assert mock_client.find_by_source.await_count == 2
    msg = await ws.call("eatfresh/favorites")
    assert [fav["key"] for fav in msg["result"]["favorites"]] == ["fakea:123"]

    # Removing the heart on the link way removes it for the search way too.
    msg = await ws.call("eatfresh/unfavorite", key=link_key)
    assert msg["success"]
    msg = await ws.call("eatfresh/favorites")
    assert msg["result"]["favorites"] == []

    # Heart set by link shows in the search hit with the numeric key.
    msg = await ws.call("eatfresh/favorite", key=link_key)
    assert msg["success"]
    msg = await ws.call("eatfresh/search", query="x", sources=["fakea"])
    assert msg["result"]["hits"][0]["key"] == "fakea:123"
    assert msg["result"]["hits"][0]["favorite"] is True
    msg = await ws.call("eatfresh/unfavorite", key="fakea:123")
    msg = await ws.call("eatfresh/favorites")
    assert msg["result"]["favorites"] == []
    mock_client.delete_recipe.assert_not_called()


async def test_favorite_kitchenowl_errors(
    ws: WS, mock_client: MagicMock
) -> None:
    """KitchenOwl errors map to their codes and nothing is stored."""
    mock_client.find_by_source.side_effect = KitchenOwlAuthError("401")
    msg = await ws.call("eatfresh/favorite", key="fakea:r1")
    assert msg["error"]["code"] == "kitchenowl_auth"
    mock_client.find_by_source.side_effect = KitchenOwlError("500")
    msg = await ws.call("eatfresh/favorite", key="fakea:r1")
    assert msg["error"]["code"] == "kitchenowl_error"
    msg = await ws.call("eatfresh/favorites")
    assert msg["result"]["favorites"] == []


async def test_collection(ws: WS, mock_client: MagicMock) -> None:
    """KitchenOwl recipes with signed photos."""
    msg = await ws.call("eatfresh/collection")
    recipes = msg["result"]["recipes"]
    assert recipes[0]["kitchenowl_id"] == 11
    assert recipes[0]["name"] == "Soup"
    assert recipes[0]["image"].startswith("/api/eatfresh/image?photo=abc123.jpg")
    assert recipes[0]["time"] == 25 and recipes[0]["yields"] == 4
    assert recipes[1]["image"] is None
    mock_client.list_recipes.assert_awaited_once_with(1)


async def test_shopping_list_add(ws: WS, mock_client: MagicMock) -> None:
    """Every recipe goes onto the configured list."""
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11, 12])
    assert msg["result"] == {"added": 6}
    assert [call.args for call in mock_client.add_recipe_to_shoppinglist.await_args_list] == [
        (2, 11),
        (2, 12),
    ]
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[])
    assert msg["error"]["code"] == "invalid_format"


async def test_jsonld_image_host_allowed(
    ws: WS, init_integration: MockConfigEntry
) -> None:
    """Opening a pasted link allows the image host of that recipe."""
    jsonld = sources_of(init_integration)["jsonld"]
    jsonld.get_by_url.side_effect = lambda url: make_recipe(
        "jsonld", url, image="https://cdn.blog.example.org/cake.jpg"
    )
    data = init_integration.runtime_data
    assert "cdn.blog.example.org" not in data.allowed_image_hosts()
    msg = await ws.call("eatfresh/recipe", url="https://blog.example.org/cake")
    assert msg["success"]
    assert "cdn.blog.example.org" in data.allowed_image_hosts()
    assert IMAGE_HOST in data.allowed_image_hosts()


async def test_not_loaded(
    hass: HomeAssistant, ws: WS, init_integration: MockConfigEntry
) -> None:
    """Commands answer with not_loaded after unload."""
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    msg = await ws.call("eatfresh/favorites")
    assert msg["error"]["code"] == "not_loaded"


# ----- review fixes ---------------------------------------------------------


@pytest.mark.parametrize(
    "image",
    [
        "http://127.0.0.1:8123/local/camera.jpg",
        "http://[::1]/snap.jpg",
        "http://172.16.5.5/snapshot.jpg",
        "http://camera.internal.example/snap.jpg",
    ],
)
async def test_private_photo_link_never_reaches_kitchenowl(
    ws: WS,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
    fake_dns: dict[str, list[str]],
    image: str,
) -> None:
    """KitchenOwl downloads the photo itself, so the link is checked first."""
    fake_dns["camera.internal.example"] = ["172.16.5.5"]
    sources_of(init_integration)["fakea"].get.side_effect = lambda rid: make_recipe(
        "fakea", rid, image=image
    )
    msg = await ws.call("eatfresh/favorite", key="fakea:r1")
    assert msg["success"], msg
    created = mock_client.create_recipe.await_args.args[1]
    assert created.image is None
    assert created.title == "Test recipe r1"


async def test_public_photo_link_is_kept(
    ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    msg = await ws.call("eatfresh/favorite", key="fakea:r1")
    assert msg["success"]
    created = mock_client.create_recipe.await_args.args[1]
    assert created.image == f"https://{IMAGE_HOST}/r1.jpg"


async def test_photo_on_blocked_host_is_left_out(
    ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    init_integration.runtime_data.blocked_hosts = frozenset({"chefkoch-cdn.de"})
    sources_of(init_integration)["fakea"].get.side_effect = lambda rid: make_recipe(
        "fakea", rid, image="https://img.chefkoch-cdn.de/a.jpg"
    )
    msg = await ws.call("eatfresh/favorite", key="fakea:r1")
    assert msg["success"]
    assert mock_client.create_recipe.await_args.args[1].image is None


async def test_only_web_addresses_from_sources(
    ws: WS, init_integration: MockConfigEntry
) -> None:
    """A hit or recipe with a javascript: or other address is not passed on."""
    from .conftest import make_hit

    bad = make_hit("fakea", "bad")
    bad.url = "javascript:alert(1)"
    good = make_hit("fakea", "good")
    sources_of(init_integration)["fakea"].search.side_effect = lambda q, limit=20: [
        bad,
        good,
    ]
    msg = await ws.call("eatfresh/search", query="suppe", sources=["fakea"])
    assert [hit["id"] for hit in msg["result"]["hits"]] == ["good"]

    def broken(rid: str):
        recipe = make_recipe("fakea", rid)
        recipe.url = "javascript:alert(1)"
        return recipe

    sources_of(init_integration)["fakea"].get.side_effect = broken
    msg = await ws.call("eatfresh/recipe", key="fakea:evil")
    assert msg["error"]["code"] == "not_found"


async def test_two_hearts_at_once_create_one_recipe(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """Two people set the same heart at the same moment: one KitchenOwl recipe."""
    import asyncio

    created: list[int] = []

    async def slow_find(
        household_id: int, url: str, fresh: bool = False
    ) -> int | None:
        await asyncio.sleep(0.01)
        return created[0] if created else None

    async def slow_create(household_id: int, recipe) -> int:
        await asyncio.sleep(0.01)
        created.append(42)
        return 42

    mock_client.find_by_source.side_effect = slow_find
    mock_client.create_recipe.side_effect = slow_create
    data = init_integration.runtime_data
    # The same recipe under two keys (search id and pasted link).
    recipe_a = make_recipe("fakea", "r1")
    recipe_b = make_recipe("jsonld", recipe_a.url)
    recipe_b.url = recipe_a.url + "/"
    results = await asyncio.gather(
        data.async_save_recipe(recipe_a),
        data.async_save_recipe(recipe_b),
        data.async_favorite("fakea:r1"),
    )
    assert mock_client.create_recipe.await_count == 1
    assert sorted(created_flag for _id, created_flag in results) == [False, False, True]
    assert {kitchenowl_id for kitchenowl_id, _ in results} == {42}
    assert data._save_locks == {}  # noqa: SLF001


async def test_rejected_token_starts_reauth(
    hass: HomeAssistant, ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """A token revoked while running leads to the reauthentication flow."""
    assert not hass.config_entries.flow.async_progress_by_handler("eatfresh")
    mock_client.list_recipes.side_effect = KitchenOwlAuthError("401")
    msg = await ws.call("eatfresh/collection")
    assert msg["error"]["code"] == "kitchenowl_auth"
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress_by_handler("eatfresh")
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]
    # A second error does not open a second flow.
    await ws.call("eatfresh/collection")
    await hass.async_block_till_done()
    assert len(hass.config_entries.flow.async_progress_by_handler("eatfresh")) == 1


async def test_other_errors_start_no_reauth(
    hass: HomeAssistant, ws: WS, mock_client: MagicMock
) -> None:
    mock_client.list_recipes.side_effect = KitchenOwlError("500")
    await ws.call("eatfresh/collection")
    await hass.async_block_till_done()
    assert not hass.config_entries.flow.async_progress_by_handler("eatfresh")


async def test_shopping_list_partial_success(ws: WS, mock_client: MagicMock) -> None:
    """If the third recipe fails, the answer says that two are on the list."""
    mock_client.add_recipe_to_shoppinglist.side_effect = [3, 4, KitchenOwlError("500")]
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11, 12, 13])
    assert not msg["success"]
    error = msg["error"]
    assert error["code"] == "kitchenowl_error"
    assert error["translation_key"] == "shopping_list_partial"
    assert error["translation_placeholders"]["added_recipes"] == "2"
    assert error["translation_placeholders"]["total"] == "3"
    assert error["translation_placeholders"]["added"] == "7"
    assert "2 of 3" in error["message"]


async def test_shopping_list_first_recipe_fails_plainly(
    ws: WS, mock_client: MagicMock
) -> None:
    mock_client.add_recipe_to_shoppinglist.side_effect = KitchenOwlAuthError("401")
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11, 12])
    assert msg["error"]["code"] == "kitchenowl_auth"
    assert "translation_key" not in msg["error"]


async def test_heart_finds_recipe_added_meanwhile(
    ws: WS, init_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The cached list misses a recipe; the fresh list before creating finds it."""

    async def find(household_id: int, url: str, fresh: bool = False) -> int | None:
        return 77 if fresh else None

    mock_client.find_by_source.side_effect = find
    msg = await ws.call("eatfresh/favorite", key="fakea:r1")
    assert msg["result"] == {"kitchenowl_id": 77, "created": False}
    mock_client.create_recipe.assert_not_awaited()
