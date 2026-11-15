"""Küchengötter: HTML search page plus JSON-LD of the recipe page.

The search page (``/suche/<text>``) lists recipe teasers; the recipe page
carries schema.org JSON-LD without ``totalTime`` (the total is prep plus cook
time, which the JSON-LD reader computes). The recipe id is the last part of
the page path, for example ``spaghetti-mit-basilikumsauce-100``.
"""

from __future__ import annotations

import re
from urllib.parse import quote, urljoin, urlsplit

from ..errors import RecipeNotFound
from ..models import Recipe, SearchHit
from .base import RecipeSource, html_to_text, host_of
from .jsonld import async_recipe_from_html

BASE_URL = "https://www.kuechengoetter.de"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*-\d+$")
_PATH_RE = re.compile(r"^/rezepte/([a-z0-9][a-z0-9-]*-\d+)/?$")
_ARTICLE_SPLIT = '<article class="c-teaser-search-recipe"'
_LINK_RE = re.compile(
    r'<a\s+class="c-teaser-search-recipe__link"\s+href="([^"]+)"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_IMG_RE = re.compile(r'<img\b[^>]*?\bsrc="([^"]+)"', re.DOTALL)
_CAPTION_RE = re.compile(r'class="u-font-caption">\s*([^<]*?)\s*<')
_TIME_RE = re.compile(r"(?:(\d+)\s*Std\.?)?\s*(?:(\d+)\s*Min\.?)?")


def _minutes(caption: str) -> int | None:
    if "Min" not in caption and "Std" not in caption:
        return None
    match = _TIME_RE.search(caption)
    if match is None:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    total = hours * 60 + minutes
    return total if total > 0 else None


class KuechengoetterSource(RecipeSource):
    """Recipes of kuechengoetter.de."""

    id = "kuechengoetter"
    name = "Küchengötter"
    default_enabled = True
    searchable = True
    hosts = ("www.kuechengoetter.de", "kuechengoetter.de")

    async def search(self, query: str, limit: int = 20) -> list[SearchHit]:
        """Search recipes by text (first result page only)."""
        query = query.strip()
        if not query:
            return []
        page = await self._client.get_text(f"{BASE_URL}/suche/{quote(query, safe='')}")
        hits: list[SearchHit] = []
        seen: set[str] = set()
        for block in page.split(_ARTICLE_SPLIT)[1:]:
            link = _LINK_RE.search(block)
            if link is None:
                continue
            url = urljoin(BASE_URL + "/", html_to_text(link.group(1)))
            path_match = _PATH_RE.match(urlsplit(url).path)
            title = html_to_text(link.group(2))
            if path_match is None or not title or path_match.group(1) in seen:
                continue
            recipe_id = path_match.group(1)
            seen.add(recipe_id)
            image_match = _IMG_RE.search(block)
            image = None
            if image_match:
                candidate = urljoin(BASE_URL + "/", html_to_text(image_match.group(1)))
                if candidate.startswith(("http://", "https://")):
                    image = candidate
            minutes = next(
                (m for m in map(_minutes, _CAPTION_RE.findall(block)) if m is not None), None
            )
            hits.append(
                SearchHit(
                    source=self.id,
                    id=recipe_id,
                    title=title,
                    url=f"{BASE_URL}/rezepte/{recipe_id}",
                    image=image,
                    total_time=minutes,
                )
            )
            if len(hits) >= limit:
                break
        return hits

    def id_from_url(self, url: str) -> str:
        """Return ``<slug>-<number>`` from a recipe address."""
        match = _PATH_RE.match(urlsplit(url.strip()).path)
        if match is None:
            raise RecipeNotFound("Not a recipe address")
        return match.group(1)

    async def get(self, recipe_id: str) -> Recipe:
        """Read the recipe page."""
        recipe_id = recipe_id.strip()
        if not _ID_RE.match(recipe_id):
            raise RecipeNotFound("Invalid recipe id")
        url = f"{BASE_URL}/rezepte/{recipe_id}"
        page = await self._client.get_text(url)
        return await async_recipe_from_html(page, source=self.id, recipe_id=recipe_id, url=url)
