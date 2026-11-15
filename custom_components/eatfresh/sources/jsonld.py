"""Generic recipe reader for schema.org JSON-LD, plus the "paste a link" source.

Pure Python, no Home Assistant imports, no HTML library: the standard
``html.parser`` finds the ``<script type="application/ld+json">`` blocks.
"""

from __future__ import annotations

import asyncio
from functools import partial
import json
import re
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from ..errors import RecipeNotFound
from ..ingredients import parse_ingredient
from ..kitchenowl import normalize_source
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
    """Collect all ``application/ld+json`` scripts and the canonical link."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.blocks: list[str] = []
        self.canonical: str | None = None
        self._current: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "link" and self.canonical is None:
            rel = next((v or "" for k, v in attrs if k == "rel"), "")
            href = next((v for k, v in attrs if k == "href"), None)
            if "canonical" in rel.lower().split() and href and href.strip():
                self.canonical = unescape(href.strip())
            return
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
    return _parse_page(html_text)[0]


def _parse_page(html_text: str) -> tuple[list[Any], str | None]:
    """Return the JSON-LD documents and the canonical link of a page."""
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
    return documents, parser.canonical


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
    found = _find_recipe(html_text)
    return None if found is None else (found[0], found[1])


def _find_recipe(
    html_text: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], str | None] | None:
    """Like :func:`find_recipe_node`, plus the canonical link of the page."""
    documents, canonical = _parse_page(html_text)
    nodes: list[dict[str, Any]] = []
    for document in documents:
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
    return candidates[0], index, canonical


def _same_site(host: str, other: str) -> bool:
    """Return True if two hosts are equal, a leading ``www.`` aside."""
    return bool(host) and host.removeprefix("www.") == other.removeprefix("www.")


def canonical_address(
    url: str,
    canonical: str | None,
    node: dict[str, Any] | None = None,
) -> str:
    """Return the canonical address of a recipe page, or ``url``.

    Candidates in this order: ``<link rel="canonical">``, then ``url`` and
    ``mainEntityOfPage`` of the recipe data. A candidate counts only if it
    is an http(s) address on the same host as ``url`` (``www.`` aside), so a
    page cannot point the recipe at another site, and only if it names the
    same page: after :func:`normalize_source` host, path and the remaining
    query parameters must be equal. A start page, an overview or parent
    page or any other path (a wrongly set up plugin) is never taken over;
    otherwise all recipes of a site would get one address and a heart would
    find the wrong recipe.
    """
    candidates: list[Any] = [canonical]
    if node is not None:
        candidates.append(node.get("url"))
        page = node.get("mainEntityOfPage")
        if isinstance(page, dict):
            page = page.get("@id") or page.get("url")
        candidates.append(page)
    host = host_of(url)
    page_address = normalize_source(url)
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        absolute = urljoin(url, candidate.strip())
        if urlsplit(absolute).scheme not in ("http", "https"):
            continue
        if _same_site(host_of(absolute), host) and (
            normalize_source(absolute) == page_address
        ):
            return absolute
    return url


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


# schema.org ``suitableForDiet`` values that EatFresh turns into a tag.
_DIET_TAGS = {"vegandiet": "Vegan", "vegetariandiet": "Vegetarian"}


def _diet_tags(node: dict[str, Any]) -> list[str]:
    """Return "Vegan"/"Vegetarian" when the recipe data names that diet."""
    tags: list[str] = []
    for entry in _text_list(node.get("suitableForDiet")):
        name = entry.strip().rstrip("/").rsplit("/", 1)[-1].lower()
        if (tag := _DIET_TAGS.get(name)) is not None and tag not in tags:
            tags.append(tag)
    return tags


def _tags(node: dict[str, Any]) -> list[str]:
    # The diet comes first, so the limit never cuts it off.
    tags: list[str] = _diet_tags(node)
    seen: set[str] = {tag.lower() for tag in tags}
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
    html_text: str,
    *,
    source: str,
    recipe_id: str,
    url: str,
    canonical: bool = False,
) -> Recipe:
    """Read the JSON-LD recipe of a page. Raises ``RecipeNotFound`` if none.

    With ``canonical`` (a pasted link) the recipe address becomes the
    canonical address of the page (see :func:`canonical_address`), so the
    same page pasted with tracking parameters or another spelling is saved
    only once.
    """
    found = _find_recipe(html_text)
    if found is None:
        raise RecipeNotFound("The page holds no recipe data")
    node, index, link = found
    if canonical:
        url = canonical_address(url, link, node)
    return recipe_from_node(node, index, source=source, recipe_id=recipe_id, url=url)


async def async_recipe_from_html(
    html_text: str,
    *,
    source: str,
    recipe_id: str,
    url: str,
    canonical: bool = False,
) -> Recipe:
    """Like :func:`recipe_from_html`, but large pages are parsed off the loop."""
    parse = partial(
        recipe_from_html,
        html_text,
        source=source,
        recipe_id=recipe_id,
        url=url,
        canonical=canonical,
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
        return await async_recipe_from_html(
            page, source=self.id, recipe_id=url, url=url, canonical=True
        )
