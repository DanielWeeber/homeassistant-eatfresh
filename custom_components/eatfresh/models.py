"""Shared data model for EatFresh.

Pure Python: no Home Assistant imports, so sources and clients stay testable
on their own. This file is the contract between all parts of the integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def make_key(source: str, recipe_id: str) -> str:
    """Return the stable key of a recipe across the integration."""
    return f"{source}:{recipe_id}"


def split_key(key: str) -> tuple[str, str]:
    """Split a key into source id and recipe id.

    The recipe id may itself contain colons (for example a URL).
    """
    source, sep, recipe_id = key.partition(":")
    if not sep or not source or not recipe_id:
        raise ValueError(f"Invalid recipe key: {key!r}")
    return source, recipe_id


@dataclass(slots=True)
class Ingredient:
    """One ingredient line of a recipe."""

    name: str
    amount: float | None = None
    unit: str | None = None
    note: str | None = None
    raw: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON serializable dict."""
        return {
            "name": self.name,
            "amount": self.amount,
            "unit": self.unit,
            "note": self.note,
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Ingredient:
        """Create an ingredient from a dict made by as_dict."""
        return cls(
            name=data["name"],
            amount=data.get("amount"),
            unit=data.get("unit"),
            note=data.get("note"),
            raw=data.get("raw", ""),
        )


@dataclass(slots=True)
class SearchHit:
    """One result of a recipe search. Times are minutes."""

    source: str
    id: str
    title: str
    url: str
    image: str | None = None
    total_time: int | None = None
    rating: float | None = None

    @property
    def key(self) -> str:
        """Return the stable key of this recipe."""
        return make_key(self.source, self.id)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON serializable dict."""
        return {
            "key": self.key,
            "source": self.source,
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "image": self.image,
            "total_time": self.total_time,
            "rating": self.rating,
        }


@dataclass(slots=True)
class Recipe:
    """A full recipe in the common EatFresh format. Times are minutes."""

    source: str
    id: str
    url: str
    title: str
    description: str | None = None
    image: str | None = None
    servings: int | None = None
    prep_time: int | None = None
    cook_time: int | None = None
    total_time: int | None = None
    ingredients: list[Ingredient] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Return the stable key of this recipe."""
        return make_key(self.source, self.id)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON serializable dict."""
        return {
            "key": self.key,
            "source": self.source,
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "description": self.description,
            "image": self.image,
            "servings": self.servings,
            "prep_time": self.prep_time,
            "cook_time": self.cook_time,
            "total_time": self.total_time,
            "ingredients": [item.as_dict() for item in self.ingredients],
            "steps": list(self.steps),
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Recipe:
        """Create a recipe from a dict made by as_dict."""
        return cls(
            source=data["source"],
            id=data["id"],
            url=data["url"],
            title=data["title"],
            description=data.get("description"),
            image=data.get("image"),
            servings=data.get("servings"),
            prep_time=data.get("prep_time"),
            cook_time=data.get("cook_time"),
            total_time=data.get("total_time"),
            ingredients=[
                Ingredient.from_dict(item) for item in data.get("ingredients", [])
            ],
            steps=list(data.get("steps", [])),
            tags=list(data.get("tags", [])),
        )
