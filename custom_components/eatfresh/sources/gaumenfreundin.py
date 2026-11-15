"""Gaumenfreundin: WordPress REST API of the WP Recipe Maker plugin.

Search and recipes come from ``wp-json/wp/v2/wprm_recipe``. The ingredients are
already split into amount, unit and name there. Pasted links to a blog post
are read through the page's JSON-LD instead; such recipes use the address as
id.
"""

from __future__ import annotations

from typing import Any

from ..errors import RecipeNotFound, SourceError
from ..ingredients import clean_name, format_amount, normalize_unit, parse_amount
from ..models import Ingredient, Recipe, SearchHit
from .base import (
    RecipeSource,
    first_int,
    html_to_text,
    minutes_or_none,
    unique_tags,
)
from .jsonld import async_recipe_from_html

API_URL = "https://www.gaumenfreundin.de/wp-json/wp/v2/wprm_recipe"
MAX_PER_PAGE = 50


def _http_url(value: object) -> str | None:
    if isinstance(value, str) and value.strip().lower().startswith(("http://", "https://")):
        return value.strip()
    return None


def _rating(recipe: dict[str, Any]) -> float | None:
    rating = recipe.get("rating")
    if not isinstance(rating, dict):
        return None
    try:
        count = int(rating.get("count") or 0)
        average = float(rating.get("average"))
    except (TypeError, ValueError):
        return None
    return round(average, 2) if count > 0 and average > 0 else None


class GaumenfreundinSource(RecipeSource):
    """Recipes of gaumenfreundin.de."""

    id = "gaumenfreundin"
    name = "Gaumenfreundin"
    default_enabled = True
    searchable = True
    hosts = ("www.gaumenfreundin.de", "gaumenfreundin.de")

    async def search(self, query: str, limit: int = 20) -> list[SearchHit]:
        """Search recipes by text."""
        query = query.strip()
        if not query:
            return []
        params = {
            "search": query,
            "per_page": max(1, min(int(limit), MAX_PER_PAGE)),
            "_fields": "id,link,title,recipe",
        }
        data = await self._client.get_json(API_URL, params)
        if not isinstance(data, list):
            raise SourceError("Unexpected answer from gaumenfreundin.de")
        hits: list[SearchHit] = []
        for item in data:
            if not isinstance(item, dict) or item.get("id") is None or not item.get("link"):
                continue
            recipe = item.get("recipe") if isinstance(item.get("recipe"), dict) else {}
            title_raw = (item.get("title") or {}).get("rendered") if isinstance(item.get("title"), dict) else None
            title = html_to_text(recipe.get("name") or title_raw)
            if not title:
                continue
            hits.append(
                SearchHit(
                    source=self.id,
                    id=str(item["id"]),
                    title=title,
                    url=str(item["link"]),
                    image=_http_url(recipe.get("image_url")),
                    total_time=minutes_or_none(recipe.get("total_time")),
                    rating=_rating(recipe),
                )
            )
        return hits[:limit]

    def id_from_url(self, url: str) -> str:
        """Blog post addresses are used as ids."""
        return url.strip()

    async def get(self, recipe_id: str) -> Recipe:
        """Return a recipe by numeric id (API) or by page address (JSON-LD)."""
        recipe_id = recipe_id.strip()
        if recipe_id.lower().startswith(("http://", "https://")):
            if not self.matches_url(recipe_id):
                raise RecipeNotFound("Not an address of gaumenfreundin.de")
            page = await self._client.get_text(recipe_id)
            # A pasted link: the canonical address of the page (without
            # tracking parameters) is saved, the same one the search gives.
            return await async_recipe_from_html(
                page,
                source=self.id,
                recipe_id=recipe_id,
                url=recipe_id,
                canonical=True,
            )
        if not recipe_id.isdigit():
            raise RecipeNotFound("Invalid recipe id")
        data = await self._client.get_json(f"{API_URL}/{recipe_id}")
        if not isinstance(data, dict) or not isinstance(data.get("recipe"), dict):
            raise RecipeNotFound("No recipe data")
        return self._to_recipe(recipe_id, data)

    def _to_recipe(self, recipe_id: str, item: dict[str, Any]) -> Recipe:
        recipe: dict[str, Any] = item["recipe"]
        title = html_to_text(recipe.get("name"))
        ingredients = self._ingredients(recipe)
        steps = self._steps(recipe)
        url = str(item.get("link") or "")
        if not title or not url or not (ingredients or steps):
            raise RecipeNotFound("No recipe data")
        tag_values: list[str] = []
        tags = recipe.get("tags")
        if isinstance(tags, dict):
            for terms in tags.values():
                if isinstance(terms, list):
                    tag_values.extend(
                        term["name"] for term in terms if isinstance(term, dict) and term.get("name")
                    )
        return Recipe(
            source=self.id,
            id=recipe_id,
            url=url,
            title=title,
            description=html_to_text(recipe.get("summary")) or None,
            image=_http_url(recipe.get("image_url")),
            servings=first_int(recipe.get("servings")),
            prep_time=minutes_or_none(recipe.get("prep_time")),
            cook_time=minutes_or_none(recipe.get("cook_time")),
            total_time=minutes_or_none(recipe.get("total_time")),
            ingredients=ingredients,
            steps=steps,
            tags=unique_tags(tag_values),
        )

    @staticmethod
    def _ingredients(recipe: dict[str, Any]) -> list[Ingredient]:
        result: list[Ingredient] = []
        groups = recipe.get("ingredients")
        for group in groups if isinstance(groups, list) else []:
            entries = group.get("ingredients") if isinstance(group, dict) else None
            for entry in entries if isinstance(entries, list) else []:
                if not isinstance(entry, dict):
                    continue
                name = clean_name(html_to_text(entry.get("name")))
                if not name:
                    continue
                amount_text = html_to_text(entry.get("amount"))
                amount = parse_amount(amount_text)
                unit = normalize_unit(html_to_text(entry.get("unit")))
                notes = [html_to_text(entry.get("notes"))]
                if amount is None and amount_text:
                    notes.insert(0, amount_text)
                note = ", ".join(item for item in notes if item) or None
                raw = " ".join(
                    part for part in (amount_text, html_to_text(entry.get("unit")), name) if part
                )
                if html_to_text(entry.get("notes")):
                    raw = f"{raw}, {html_to_text(entry.get('notes'))}"
                result.append(
                    Ingredient(
                        name=name,
                        amount=amount,
                        unit=unit if amount is not None else None,
                        note=note,
                        raw=raw,
                    )
                )
        return result

    @staticmethod
    def _steps(recipe: dict[str, Any]) -> list[str]:
        steps: list[str] = []
        groups = recipe.get("instructions")
        for group in groups if isinstance(groups, list) else []:
            entries = group.get("instructions") if isinstance(group, dict) else None
            for entry in entries if isinstance(entries, list) else []:
                text = html_to_text(entry.get("text")) if isinstance(entry, dict) else ""
                if text:
                    steps.append(text)
        return steps
