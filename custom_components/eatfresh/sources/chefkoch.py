"""Chefkoch: JSON API ``api.chefkoch.de/v2``.

Off by default. The terms of use of chefkoch.de (section 5.1) forbid automatic
reading of their data; use is the responsibility of the user. Only call this
source on a direct user action, never in the background.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from ..errors import RecipeNotFound, SourceError
from ..ingredients import (
    adjectives_first,
    clean_name,
    clean_note,
    finish_ingredients,
    format_amount,
    normalize_unit,
)
from ..models import Ingredient, Recipe, SearchHit
from .base import RecipeSource, first_int, host_of, html_to_text, minutes_or_none, unique_tags

API_URL = "https://api.chefkoch.de/v2/recipes"
HIT_IMAGE_FORMAT = "crop-420x280"
RECIPE_IMAGE_FORMAT = "crop-960x540"
MAX_LIMIT = 50
_PATH_RE = re.compile(r"^/rezepte/(\d+)(?:/|$)")


def _image(template: object, image_format: str) -> str | None:
    """Fill the ``<format>`` placeholder of an image template."""
    if isinstance(template, str) and "<format>" in template:
        url = template.replace("<format>", image_format)
        if url.startswith("https://"):
            return url
    return None


class ChefkochSource(RecipeSource):
    """Recipes of chefkoch.de."""

    id = "chefkoch"
    name = "Chefkoch"
    default_enabled = False
    searchable = True
    hosts = ("api.chefkoch.de", "www.chefkoch.de", "chefkoch.de", "img.chefkoch-cdn.de")

    # Hosts of recipe pages (the others serve the API and the images).
    _PAGE_HOSTS = ("www.chefkoch.de", "chefkoch.de")

    async def search(self, query: str, limit: int = 20) -> list[SearchHit]:
        """Search recipes by text. Plus and premium recipes are left out."""
        query = query.strip()
        if not query:
            return []
        params = {"query": query, "limit": max(1, min(int(limit), MAX_LIMIT)), "offset": 0}
        data = await self._client.get_json(API_URL, params)
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            raise SourceError("Unexpected answer from chefkoch.de")
        hits: list[SearchHit] = []
        for entry in results:
            recipe = entry.get("recipe") if isinstance(entry, dict) else None
            if not isinstance(recipe, dict) or recipe.get("id") is None:
                continue
            if recipe.get("isPlus") or recipe.get("isPremium"):
                continue
            title = html_to_text(recipe.get("title"))
            url = recipe.get("siteUrl")
            if not title or not isinstance(url, str):
                continue
            rating = recipe.get("rating") if isinstance(recipe.get("rating"), dict) else {}
            votes = rating.get("numVotes") or 0
            value = rating.get("rating")
            hits.append(
                SearchHit(
                    source=self.id,
                    id=str(recipe["id"]),
                    title=title,
                    url=url,
                    image=_image(recipe.get("previewImageUrlTemplate"), HIT_IMAGE_FORMAT),
                    total_time=minutes_or_none(recipe.get("preparationTime")),
                    rating=round(float(value), 2)
                    if isinstance(value, (int, float)) and votes
                    else None,
                )
            )
        return hits[:limit]

    def matches_url(self, url: str) -> bool:
        """Accept recipe pages on chefkoch.de."""
        return host_of(url) in self._PAGE_HOSTS

    def id_from_url(self, url: str) -> str:
        """Return the numeric id from ``/rezepte/<id>/<slug>.html``."""
        match = _PATH_RE.match(urlsplit(url.strip()).path)
        if match is None:
            raise RecipeNotFound("Not a recipe address")
        return match.group(1)

    async def get(self, recipe_id: str) -> Recipe:
        """Return the recipe with this numeric id."""
        recipe_id = recipe_id.strip()
        if not recipe_id.isdigit():
            raise RecipeNotFound("Invalid recipe id")
        data = await self._client.get_json(f"{API_URL}/{recipe_id}")
        if not isinstance(data, dict) or not data.get("title"):
            # The API answers {"notification": ...} for ids that are no recipe.
            raise RecipeNotFound("No recipe data")
        ingredients = self._ingredients(data)
        steps = self._steps(data.get("instructions"))
        url = data.get("siteUrl")
        if not (ingredients or steps) or not isinstance(url, str):
            raise RecipeNotFound("No recipe data")
        tags = data.get("tags")
        return Recipe(
            source=self.id,
            id=recipe_id,
            url=url,
            title=html_to_text(data["title"]),
            description=html_to_text(data.get("subtitle")) or None,
            image=_image(data.get("previewImageUrlTemplate"), RECIPE_IMAGE_FORMAT),
            servings=first_int(data.get("servings")),
            prep_time=minutes_or_none(data.get("preparationTime")),
            cook_time=minutes_or_none(data.get("cookingTime")),
            total_time=minutes_or_none(data.get("totalTime")),
            ingredients=ingredients,
            steps=steps,
            tags=unique_tags(tags if isinstance(tags, list) else []),
        )

    @staticmethod
    def _ingredients(data: dict[str, Any]) -> list[Ingredient]:
        result: list[Ingredient] = []
        groups = data.get("ingredientGroups")
        for group in groups if isinstance(groups, list) else []:
            entries = group.get("ingredients") if isinstance(group, dict) else None
            for entry in entries if isinstance(entries, list) else []:
                if not isinstance(entry, dict):
                    continue
                value = entry.get("amount")
                amount = float(value) if isinstance(value, (int, float)) and value > 0 else None
                unit_text = html_to_text(entry.get("unit"))
                # "Butter, weiche" is read as "weiche Butter".
                name = adjectives_first(
                    clean_name(
                        entry.get("name"), amount, unit_text if amount is not None else None
                    )
                )
                if not name:
                    continue
                unit = normalize_unit(unit_text) if amount is not None else None
                # The API sometimes sends ", feiner": no comma at the start.
                info = clean_note(html_to_text(entry.get("usageInfo")))
                raw = " ".join(
                    part
                    for part in (
                        format_amount(amount),
                        unit_text if amount is not None else "",
                        name,
                    )
                    if part
                )
                if info:
                    raw = f"{raw}, {info}"
                result.append(
                    Ingredient(name=name, amount=amount, unit=unit, note=info, raw=raw)
                )
        return finish_ingredients(result)

    @staticmethod
    def _steps(text: object) -> list[str]:
        if not isinstance(text, str):
            return []
        cleaned = text.replace("\r", "")
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", cleaned) if part.strip()]
        if len(paragraphs) <= 1:
            paragraphs = [line.strip() for line in cleaned.split("\n") if line.strip()]
        return [html_to_text(part) for part in paragraphs if html_to_text(part)]
