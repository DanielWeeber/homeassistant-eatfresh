"""Generic recipe reader for schema.org JSON-LD, plus the "paste a link" source.

Pure Python, no Home Assistant imports, no HTML library: the standard
``html.parser`` finds the ``<script type="application/ld+json">`` blocks.
"""

from __future__ import annotations

import asyncio
from functools import partial
import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from ..errors import RecipeNotFound
from ..ingredients import parse_ingredient
from ..models import Ingredient, Recipe, SearchHit
from .base import RecipeSource, first_int, host_of, html_to_text

_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+(?:[.,]\d+)?)D)?"
    r"(?:T(?:(?P<hours>\d+(?:[.,]\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:[.,]\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:[.,]\d+)?)S)?)?$",
    re.IGNORECASE,
)
_MAX_TAGS = 12
# Pages larger than this are parsed in a worker thread, so a big page does not
# hold up the event loop (html.parser needs about 0.15 s per MB).
EXECUTOR_MIN_CHARS = 256_000


class _LdScriptParser(HTMLParser):
    """Collect the text of all ``application/ld+json`` script elements."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.blocks: list[str] = []
        self._current: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "script":
            return
        kind = next((v or "" for k, v in attrs if k == "type"), "")
        if kind.split(";")[0].strip().lower() == "application/ld+json":
            self._current = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._current is not None:
            self.blocks.append("".join(self._current))
            self._current = None


def parse_duration(value: object) -> int | None:
    """Convert an ISO-8601 duration such as ``PT1H20M`` to whole minutes.

    Returns None for missing, invalid or zero durations.
    """
    if not isinstance(value, str):
        return None
    match = _DURATION_RE.match(value.strip())
    if match is None:
        return None
    parts = {key: float(text.replace(",", ".")) for key, text in match.groupdict().items() if text}
    if not parts:
        return None
    total = (
        parts.get("days", 0) * 1440
        + parts.get("hours", 0) * 60
        + parts.get("minutes", 0)
        + parts.get("seconds", 0) / 60
    )
    minutes = int(round(total))
    return minutes if minutes > 0 else None


def _iter_json_blocks(html_text: str) -> list[Any]:
    parser = _LdScriptParser()
    try:
        parser.feed(html_text)
        parser.close()
    except Exception:  # noqa: BLE001 - broken markup must not stop the search
        pass
    documents: list[Any] = []
    for block in parser.blocks:
        text = block.strip()
        if text.startswith("<!--"):
            text = re.sub(r"^<!--|-->$", "", text).strip()
        try:
            documents.append(json.loads(text, strict=False))
        except ValueError:
            continue
    return documents


def _has_type(node: dict[str, Any], wanted: str) -> bool:
    kind = node.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    return any(
        isinstance(item, str) and item.rstrip("/").rsplit("/", 1)[-1] == wanted
        for item in kinds
    )


def _walk(value: Any, nodes: list[dict[str, Any]], depth: int = 0) -> None:
    if depth > 6:
        return
    if isinstance(value, list):
        for item in value:
            _walk(item, nodes, depth + 1)
    elif isinstance(value, dict):
        nodes.append(value)
        _walk(value.get("@graph"), nodes, depth + 1)
        _walk(value.get("mainEntity"), nodes, depth + 1)
        _walk(value.get("mainEntityOfPage"), nodes, depth + 1)


def find_recipe_node(html_text: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]] | None:
    """Find the schema.org ``Recipe`` in a page.

    Returns the recipe node and an index of all nodes by ``@id`` (to resolve
    references such as images), or None if the page holds no recipe.
    """
    nodes: list[dict[str, Any]] = []
    for document in _iter_json_blocks(html_text):
        _walk(document, nodes)
    index = {
        node["@id"]: node
        for node in nodes
        if isinstance(node.get("@id"), str) and len(node) > 1
    }
    candidates = [node for node in nodes if _has_type(node, "Recipe")]
    if not candidates:
        return None
    # Prefer a node that really carries ingredients.
    candidates.sort(key=lambda node: 0 if node.get("recipeIngredient") else 1)
    return candidates[0], index


def _resolve(value: Any, index: dict[str, dict[str, Any]]) -> Any:
    if isinstance(value, dict) and set(value) == {"@id"}:
        return index.get(value["@id"], value)
    return value


def _text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_text_list(item))
        return result
    return []


def _image_url(value: Any, index: dict[str, dict[str, Any]], base_url: str) -> str | None:
    value = _resolve(value, index)
    candidate: Any = None
    if isinstance(value, str):
        candidate = value
    elif isinstance(value, list):
        for item in value:
            found = _image_url(item, index, base_url)
            if found:
                return found
        return None
    elif isinstance(value, dict):
        candidate = value.get("url") or value.get("contentUrl")
        if not isinstance(candidate, str):
            return None
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    absolute = urljoin(base_url, candidate.strip())
    return absolute if urlsplit(absolute).scheme in ("http", "https") else None


def _steps(value: Any, index: dict[str, dict[str, Any]]) -> list[str]:
    value = _resolve(value, index)
    if value is None:
        return []
    if isinstance(value, str):
        return [line for line in html_to_text(value, keep_lines=True).split("\n") if line]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_steps(item, index))
        return result
    if isinstance(value, dict):
        if _has_type(value, "HowToSection") or "itemListElement" in value:
            return _steps(value.get("itemListElement"), index)
        text = value.get("text") or value.get("name")
        return _steps(text, index) if isinstance(text, str) else []
    return []


def _tags(node: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for field in ("recipeCategory", "recipeCuisine", "keywords"):
        for entry in _text_list(node.get(field)):
            for part in html_to_text(entry).split(","):
                tag = part.strip()
                if tag and tag.lower() not in seen:
                    seen.add(tag.lower())
                    tags.append(tag)
    return tags[:_MAX_TAGS]


def _ingredients(node: dict[str, Any]) -> list[Ingredient]:
    lines = _text_list(node.get("recipeIngredient") or node.get("ingredients"))
    result = []
    for line in lines:
        if html_to_text(line):
            ingredient = parse_ingredient(line)
            if ingredient.name:
                result.append(ingredient)
    return result


def recipe_from_node(
    node: dict[str, Any],
    index: dict[str, dict[str, Any]],
    *,
    source: str,
    recipe_id: str,
    url: str,
) -> Recipe:
    """Build a :class:`Recipe` from a schema.org ``Recipe`` node.

    Raises ``RecipeNotFound`` if the node has neither a title nor ingredients
    and steps.
    """
    title = html_to_text(_first_text(node.get("name")))
    ingredients = _ingredients(node)
    steps = _steps(node.get("recipeInstructions"), index)
    if not title or not (ingredients or steps):
        raise RecipeNotFound("The page holds no usable recipe")

    prep = parse_duration(node.get("prepTime"))
    cook = parse_duration(node.get("cookTime"))
    total = parse_duration(node.get("totalTime"))
    if total is None and prep is not None and cook is not None:
        total = prep + cook
    description = html_to_text(_first_text(node.get("description")), keep_lines=False)

    return Recipe(
        source=source,
        id=recipe_id,
        url=url,
        title=title,
        description=description or None,
        image=_image_url(node.get("image"), index, url),
        servings=first_int(node.get("recipeYield")),
        prep_time=prep,
        cook_time=cook,
        total_time=total,
        ingredients=ingredients,
        steps=steps,
        tags=_tags(node),
    )


def _first_text(value: Any) -> str | None:
    items = _text_list(value)
    return items[0] if items else None


def recipe_from_html(
    html_text: str, *, source: str, recipe_id: str, url: str
) -> Recipe:
    """Read the JSON-LD recipe of a page. Raises ``RecipeNotFound`` if none."""
    found = find_recipe_node(html_text)
    if found is None:
        raise RecipeNotFound("The page holds no recipe data")
    node, index = found
    return recipe_from_node(node, index, source=source, recipe_id=recipe_id, url=url)


async def async_recipe_from_html(
    html_text: str, *, source: str, recipe_id: str, url: str
) -> Recipe:
    """Like :func:`recipe_from_html`, but large pages are parsed off the loop."""
    parse = partial(
        recipe_from_html, html_text, source=source, recipe_id=recipe_id, url=url
    )
    if len(html_text) < EXECUTOR_MIN_CHARS:
        return parse()
    return await asyncio.get_running_loop().run_in_executor(None, parse)


class JsonLdSource(RecipeSource):
    """Read a recipe from any page that carries schema.org JSON-LD.

    The recipe id is the page address. This source is not searchable and is
    always active.
    """

    id = "jsonld"
    name = "Rezept-Link"
    default_enabled = True
    searchable = False
    # Any site is allowed here, so there is no fixed list. The image proxy has
    # to allow the host of the recipe page and its image host separately.
    hosts = ()

    async def search(self, query: str, limit: int = 20) -> list[SearchHit]:
        """This source cannot search."""
        return []

    def matches_url(self, url: str) -> bool:
        """Accept every http(s) address."""
        return urlsplit(url.strip()).scheme in ("http", "https") and bool(host_of(url))

    def id_from_url(self, url: str) -> str:
        """The id is the (trimmed) address itself."""
        return url.strip()

    async def get(self, recipe_id: str) -> Recipe:
        """Fetch the page and read its recipe."""
        url = recipe_id.strip()
        # HttpClient refuses addresses in private networks (DNS checked,
        # every redirect checked again).
        page = await self._client.get_text(url)
        return await async_recipe_from_html(page, source=self.id, recipe_id=url, url=url)
