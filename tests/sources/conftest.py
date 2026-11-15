"""Fixtures for the recipe source tests: no real network, invented pages."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.eatfresh.http import HttpClient

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations() -> None:
    """The source tests need no Home Assistant instance."""


@pytest.fixture(autouse=True)
def setup_dependencies() -> None:
    """The source tests need no Home Assistant instance."""


def load_text(relative: str) -> str:
    """Read a fixture file as text."""
    return (FIXTURES / relative).read_text(encoding="utf-8")


def load_json(relative: str) -> Any:
    """Read a fixture file as JSON."""
    return json.loads(load_text(relative))


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    """A real session; aioresponses answers its requests."""
    async with aiohttp.ClientSession() as client_session:
        yield client_session


@pytest.fixture
def client(session: aiohttp.ClientSession) -> HttpClient:
    """HTTP client without a pause between requests."""
    return HttpClient(session, "EatFresh-Test/0.1", min_interval=0)


def requested_urls(mock: aioresponses) -> list[str]:
    """Return the URLs (with query) that were requested, in order."""
    return [str(url) for (_method, url) in mock.requests]
