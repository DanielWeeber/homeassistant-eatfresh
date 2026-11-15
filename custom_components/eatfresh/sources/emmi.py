"""Emmi kocht einfach: WordPress search plus JSON-LD of the recipe page.

The search lists blog posts; not every post holds a recipe. Such a post fails
in ``get`` with ``RecipeNotFound``. The recipe id is the page slug.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from ..errors import RecipeNotFound, SourceError
from ..models import Recipe, SearchHit
from .base import RecipeSource, html_to_text
from .jsonld import async_recipe_from_html

BASE_URL = "https://emmikochteinfach.de"
SEARCH_URL = f"{BASE_URL}/wp-json/wp/v2/posts"
MAX_PER_PAGE = 50
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_%\-]*(?:/[A-Za-z0-9_%\-]+)*$")


def _slug_of(url: str) -> str | None:
    parts = urlsplit(url)
    slug = parts.path.strip("/")
    return slug if slug and _SLUG_RE.match(slug) else None


class EmmiSource(RecipeSource):
    """Recipes of emmikochteinfach.de."""

    id = "emmi"
    name = "Emmi kocht einfach"
    default_enabled = True
    searchable = True
    hosts = ("emmikochteinfach.de", "www.emmikochteinfach.de")

    async def search(self, query: str, limit: int = 20) -> list[SearchHit]:
        """Search posts by text."""
        query = query.strip()
        if not query:
            return []
        params = {
            "search": query,
            "per_page": max(1, min(int(limit), MAX_PER_PAGE)),
            "_fields": "id,link,title,yoast_head_json",
        }
        data = await self._client.get_json(SEARCH_URL, params)
        if not isinstance(data, list):
            raise SourceError("Unexpected answer from emmikochteinfach.de")
        hits: list[SearchHit] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            link = str(item.get("link") or "")
            slug = _slug_of(link) if self.matches_url(link) else None
            title_obj = item.get("title")
            title = html_to_text(title_obj.get("rendered") if isinstance(title_obj, dict) else None)
            if not slug or not title:
                continue
            hits.append(
                SearchHit(
                    source=self.id,
                    id=slug,
                    title=title,
                    url=link,
                    image=self._image(item.get("yoast_head_json")),
                )
            )
        return hits[:limit]

    @staticmethod
    def _image(meta: object) -> str | None:
        if not isinstance(meta, dict):
            return None
        images = meta.get("og_image")
        if isinstance(images, list):
            for image in images:
                url = image.get("url") if isinstance(image, dict) else None
                if isinstance(url, str) and url.startswith(("http://", "https://")):
                    return url
        return None

    def id_from_url(self, url: str) -> str:
        """The id is the path of the page."""
        slug = _slug_of(url)
        if slug is None:
            raise RecipeNotFound("Not a recipe address")
        return slug

    async def get(self, recipe_id: str) -> Recipe:
        """Read the recipe of the page ``<slug>/``."""
        slug = recipe_id.strip().strip("/")
        if not _SLUG_RE.match(slug):
            raise RecipeNotFound("Invalid recipe id")
        url = f"{BASE_URL}/{slug}/"
        page = await self._client.get_text(url)
        return await async_recipe_from_html(page, source=self.id, recipe_id=slug, url=url)
