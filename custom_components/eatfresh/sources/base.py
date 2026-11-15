"""Base class and shared helpers for recipe sources.

Pure Python, no Home Assistant imports.
"""

from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod
from typing import ClassVar
from urllib.parse import urlsplit

from ..errors import RecipeNotFound
from ..http import HttpClient
from ..models import Recipe, SearchHit

_BREAK_RE = re.compile(r"<\s*(?:br\s*/?|/p|/li|/div|/h[1-6])\s*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_ODD_SPACES = (" ", " ", " ")


def html_to_text(value: object, *, keep_lines: bool = False) -> str:
    """Turn a snippet of HTML or text into plain text.

    With ``keep_lines`` paragraph and line breaks become newlines, otherwise
    all white space collapses to single spaces.
    """
    if value is None:
        return ""
    text = str(value)
    text = _BREAK_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    for char in _ODD_SPACES:
        text = text.replace(char, " ")
    if keep_lines:
        lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n"))
        return "\n".join(line for line in lines if line)
    return re.sub(r"\s+", " ", text).strip()


def first_int(value: object) -> int | None:
    """Return the first whole number found in ``value`` (number, text or list)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = int(value)
        return number if number > 0 else None
    if isinstance(value, (list, tuple)):
        for item in value:
            found = first_int(item)
            if found is not None:
                return found
        return None
    match = re.search(r"\d+", str(value))
    if match:
        number = int(match.group(0))
        return number if number > 0 else None
    return None


def minutes_or_none(value: object) -> int | None:
    """Return a positive number of minutes or None (zero means unknown)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(round(float(str(value).strip())))
    except ValueError:
        return None
    return number if number > 0 else None


def unique_tags(values: object, limit: int = 12) -> list[str]:
    """Return cleaned, de-duplicated tag texts in order, at most ``limit``."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values if isinstance(values, (list, tuple)) else []:
        tag = html_to_text(value)
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            result.append(tag)
    return result[:limit]


def host_of(url: str) -> str:
    """Return the lower-case host name of ``url`` (empty if none)."""
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


class RecipeSource(ABC):
    """A place recipes can be searched in and read from."""

    id: ClassVar[str]
    name: ClassVar[str]
    default_enabled: ClassVar[bool] = True
    searchable: ClassVar[bool] = True
    # Every host name of the source, including image hosts: the image proxy
    # only serves these.
    hosts: ClassVar[tuple[str, ...]] = ()

    def __init__(self, client: HttpClient) -> None:
        """Keep the shared HTTP client."""
        self._client = client

    @abstractmethod
    async def search(self, query: str, limit: int = 20) -> list[SearchHit]:
        """Return up to ``limit`` hits for ``query``."""

    @abstractmethod
    async def get(self, recipe_id: str) -> Recipe:
        """Return the full recipe for an id made by this source."""

    def matches_url(self, url: str) -> bool:
        """Return True if ``url`` points to a page of this source."""
        return host_of(url) in self.hosts

    def id_from_url(self, url: str) -> str:
        """Return the recipe id for a page address of this source."""
        raise RecipeNotFound("Not a recipe address of this source")

    async def get_by_url(self, url: str) -> Recipe:
        """Return the recipe behind a page address of this source."""
        if not self.matches_url(url):
            raise RecipeNotFound("Not an address of this source")
        return await self.get(self.id_from_url(url))
