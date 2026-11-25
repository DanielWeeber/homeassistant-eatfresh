"""Shared fixtures for the EatFresh core tests.

The KitchenOwl client and the recipe sources are replaced by fakes, so these
tests only check the Home Assistant side of the integration.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from aioresponses import aioresponses
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.eatfresh.const import (
    CONF_HOUSEHOLD_ID,
    CONF_SHOPPINGLIST_ID,
    CONF_TOKEN,
    CONF_URL,
    DOMAIN,
)
from custom_components.eatfresh.errors import RecipeNotFound
from custom_components.eatfresh.models import Ingredient, Recipe, SearchHit

KITCHENOWL_URL = "https://kitchenowl.example.com"
TOKEN = "test-token"
RECIPE_HOST = "recipes.example.com"
IMAGE_HOST = "images.example.com"


# A public address for invented host names; tests never reach it.
PUBLIC_TEST_IP = "93.184.215.14"


class _CompatResponse(aiohttp.ClientResponse):
    """aioresponses 0.7.9 does not pass ``stream_writer`` that aiohttp 3.14 needs."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("stream_writer", SimpleNamespace(output_size=0))
        super().__init__(*args, **kwargs)


@contextmanager
def mock_network() -> Iterator[aioresponses]:
    """Replace the network with aioresponses (with the aiohttp 3.14 shim)."""
    with (
        patch("aioresponses.core.ClientResponse", _CompatResponse),
        aioresponses() as mocked,
    ):
        yield mocked


@pytest.fixture
def mock() -> Iterator[aioresponses]:
    """Replace the network for aiohttp sessions."""
    with mock_network() as mocked:
        yield mocked


@pytest.fixture(autouse=True)
def fake_dns() -> Iterator[dict[str, list[str]]]:
    """Answer DNS lookups of the address check without a network.

    Unknown names resolve to ``PUBLIC_TEST_IP``; tests add their own entries.
    """
    table: dict[str, list[str]] = {}

    async def resolve(host: str, port: int) -> list[str]:
        return table.get(host, [PUBLIC_TEST_IP])

    with patch("custom_components.eatfresh.http.resolve_host", resolve):
        yield table


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in all tests."""


@pytest.fixture(autouse=True)
async def setup_dependencies(hass: HomeAssistant) -> None:
    """Set up http and websocket_api. Frontend files are not installed in tests."""
    hass.config.components.add("frontend")
    hass.config.components.add("panel_custom")
    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "websocket_api", {})


def make_recipe(
    source: str = "fakea", recipe_id: str = "r1", image: str | None = None
) -> Recipe:
    """Return a small invented recipe."""
    return Recipe(
        source=source,
        id=recipe_id,
        url=f"https://{RECIPE_HOST}/{source}/{recipe_id}",
        title=f"Test recipe {recipe_id}",
        image=image or f"https://{IMAGE_HOST}/{recipe_id}.jpg",
        servings=2,
        total_time=30,
        ingredients=[Ingredient(name="flour", amount=250, unit="g", raw="250 g flour")],
        steps=["Mix.", "Bake."],
    )


def make_hit(source: str, recipe_id: str) -> SearchHit:
    """Return a search hit."""
    return SearchHit(
        source=source,
        id=recipe_id,
        title=f"Hit {recipe_id}",
        url=f"https://{RECIPE_HOST}/{source}/{recipe_id}",
        image=f"https://{IMAGE_HOST}/{recipe_id}.jpg",
        total_time=20,
    )


class FakeSource:
    """Stand-in for RecipeSource with mocked network methods."""

    id: ClassVar[str] = "fake"
    name: ClassVar[str] = "Fake"
    default_enabled: ClassVar[bool] = True
    searchable: ClassVar[bool] = True
    hosts: ClassVar[tuple[str, ...]] = (RECIPE_HOST, IMAGE_HOST)

    def __init__(self, client: Any = None) -> None:
        """Create mocks for the network methods."""
        self.client = client
        self.search = AsyncMock(
            side_effect=lambda query, limit=20: [
                make_hit(self.id, f"{self.id}-1"),
                make_hit(self.id, f"{self.id}-2"),
            ]
        )
        self.get = AsyncMock(side_effect=lambda rid: make_recipe(self.id, rid))
        self.get_by_url = AsyncMock(
            side_effect=lambda url: make_recipe(self.id, url.rsplit("/", 1)[-1])
        )

    def matches_url(self, url: str) -> bool:
        """Match URLs that contain the source id."""
        return f"/{self.id}/" in url


class FakeA(FakeSource):
    id = "fakea"
    name = "Fake A"


class FakeB(FakeSource):
    id = "fakeb"
    name = "Fake B"


class FakeChefkoch(FakeSource):
    id = "chefkoch"
    name = "Chefkoch"
    default_enabled = False


class FakeJsonld(FakeSource):
    id = "jsonld"
    name = "Recipe link"
    searchable = False
    hosts = ()

    def matches_url(self, url: str) -> bool:
        """Match every URL."""
        return True


FAKE_CLASSES = (FakeA, FakeB, FakeChefkoch, FakeJsonld)


def fake_build_sources(client: Any, enabled: Iterable[str]) -> dict[str, FakeSource]:
    """Build fake sources like the real build_sources (jsonld always on)."""
    wanted = set(enabled) | {"jsonld"}
    return {cls.id: cls(client) for cls in FAKE_CLASSES if cls.id in wanted}


def fake_source_for_url(sources: dict[str, FakeSource], url: str) -> FakeSource:
    """Pick the first matching searchable source, else jsonld."""
    for source in sources.values():
        if source.searchable and source.matches_url(url):
            return source
    if "jsonld" in sources:
        return sources["jsonld"]
    raise RecipeNotFound(url)


@pytest.fixture
def mock_client() -> MagicMock:
    """Return a fake KitchenOwl client."""
    client = MagicMock()
    client.get_user = AsyncMock(return_value={"id": 1, "username": "tester"})
    client.list_households = AsyncMock(
        return_value=[{"id": 1, "name": "Home"}, {"id": 5, "name": "Holiday"}]
    )
    client.list_shoppinglists = AsyncMock(
        return_value=[{"id": 2, "name": "Groceries"}, {"id": 3, "name": "Market"}]
    )
    client.list_recipes = AsyncMock(
        return_value=[
            {
                "id": 11,
                "name": "Soup",
                "source": f"https://{RECIPE_HOST}/fakea/soup",
                "photo": "abc123.jpg",
                "time": 25,
                "yields": 4,
                "tags": ["Suppe"],
            },
            {"id": 12, "name": "Bread", "source": None, "photo": None, "tags": []},
        ]
    )
    client.get_recipe = AsyncMock(return_value={"id": 11, "name": "Soup"})
    client.find_by_source = AsyncMock(return_value=None)
    client.create_recipe = AsyncMock(return_value=42)
    client.add_recipe_to_shoppinglist = AsyncMock(return_value=3)
    # Nothing to restore: the recipe comes back as None, so it is read again.
    client.restore_recipe_items = AsyncMock(
        return_value={"restored": [], "missing": [], "recipe": None}
    )
    client.fetch_photo = AsyncMock(return_value=(b"\xff\xd8photo", "image/jpeg"))
    client.list_tags = AsyncMock(return_value=["Suppe", "Schnell"])
    client.set_recipe_tags = AsyncMock(side_effect=lambda recipe_id, tags: list(tags))
    client.list_planner = AsyncMock(return_value=[])
    client.add_planner_entry = AsyncMock(return_value=None)
    client.remove_planner_entry = AsyncMock(return_value=None)

    async def recipe_ids(household_id: int, *, fresh: bool = False) -> set[int]:
        # Like the real client: the recipes of the list plus a created one.
        ids = {int(item["id"]) for item in client.list_recipes.return_value}
        if client.create_recipe.await_count and isinstance(
            client.create_recipe.return_value, int
        ):
            ids.add(client.create_recipe.return_value)
        return ids

    client.recipe_ids = AsyncMock(side_effect=recipe_ids)

    async def recipe_summary(household_id: int, recipe_id: int) -> dict | None:
        # Like the real client: one recipe of the (cached) recipe list.
        for item in client.list_recipes.return_value:
            if int(item["id"]) == int(recipe_id):
                return dict(item)
        return None

    client.recipe_summary = AsyncMock(side_effect=recipe_summary)
    # 0.5.0, shopping: categories and entries of the list.
    client.list_categories = AsyncMock(return_value=[])
    client.create_category = AsyncMock(
        side_effect=lambda household_id, name: {
            "id": 90,
            "name": name,
            "default_key": None,
        }
    )
    client.set_item_category = AsyncMock(return_value=None)
    client.remove_from_shoppinglist = AsyncMock(return_value=None)
    client.add_item_to_shoppinglist = AsyncMock(return_value=None)
    client.get_item = AsyncMock(
        side_effect=lambda item_id: {"id": item_id, "name": "Item", "category": None}
    )
    return client


@pytest.fixture
def mock_sources() -> Generator[MagicMock]:
    """Replace the source registry with fakes."""
    build = MagicMock(side_effect=fake_build_sources)
    with (
        patch("custom_components.eatfresh.SOURCE_CLASSES", FAKE_CLASSES),
        patch("custom_components.eatfresh.build_sources", build),
        patch("custom_components.eatfresh.config_flow.SOURCE_CLASSES", FAKE_CLASSES),
        patch("custom_components.eatfresh.sources.SOURCE_CLASSES", FAKE_CLASSES),
        patch("custom_components.eatfresh.sources.source_for_url", fake_source_for_url),
    ):
        yield build


@pytest.fixture
def patch_client(mock_client: MagicMock) -> Generator[MagicMock]:
    """Make every KitchenOwlClient() return the fake client."""
    with (
        patch(
            "custom_components.eatfresh.KitchenOwlClient", return_value=mock_client
        ) as init_cls,
        patch(
            "custom_components.eatfresh.config_flow.KitchenOwlClient",
            return_value=mock_client,
        ),
    ):
        yield init_cls


@pytest.fixture
def panel_dir(tmp_path: Path) -> Generator[Path]:
    """Point the panel at a temporary folder with a built panel file."""
    (tmp_path / "eatfresh-panel.js").write_text("export {};\n", encoding="utf-8")
    with patch("custom_components.eatfresh.panel.FRONTEND_DIR", tmp_path):
        yield tmp_path


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return the config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="EatFresh",
        unique_id="1",
        data={
            CONF_URL: KITCHENOWL_URL,
            CONF_TOKEN: TOKEN,
            CONF_HOUSEHOLD_ID: 1,
            CONF_SHOPPINGLIST_ID: 2,
        },
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    patch_client: MagicMock,
    mock_sources: MagicMock,
    panel_dir: Path,
    aioclient_mock: AiohttpClientMocker,
) -> AsyncGenerator[MockConfigEntry]:
    """Set up EatFresh with fakes. HTTP of the image proxy is mocked."""
    config_entry.add_to_hass(hass)
    with patch(
        "custom_components.eatfresh.async_create_public_session",
        side_effect=lambda hass: aioclient_mock.create_session(hass.loop),
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    yield config_entry
