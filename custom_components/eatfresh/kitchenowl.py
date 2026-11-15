"""Client for the KitchenOwl REST API (tested against KitchenOwl 0.8.1).

Pure Python: no Home Assistant imports. The client never deletes anything.

Facts taken from the KitchenOwl 0.8.1 backend source:

* Authentication is ``Authorization: Bearer <token>`` (a long-lived token).
* All times (``time``, ``prep_time``, ``cook_time``) are minutes, ``yields``
  is the number of servings.
* ``POST /api/household/<id>/recipe`` requires ``name`` and ``description``;
  a ``photo`` containing a ``/`` is downloaded by the server itself, and a
  failed download silently leaves the recipe without a photo.
* Shopping list entries are merged by ``description_merger``. See
  :func:`item_description` for the format it understands.
"""

from __future__ import annotations

import math
import re
import time
from typing import Any
from urllib.parse import quote, urlsplit

import aiohttp

from .errors import KitchenOwlAuthError, KitchenOwlError
from .models import Ingredient, Recipe

REQUEST_TIMEOUT = 20  # seconds
# How long ``find_by_source`` may reuse the last list of recipes. Creating a
# recipe through this client drops the copy at once.
RECIPE_LIST_TTL = 120.0  # seconds
_USER_AGENT = "EatFresh (Home Assistant integration)"

# Units the KitchenOwl merger converts between (written without a space).
_SI_UNITS = frozenset({"mg", "g", "kg", "ml", "l"})
# Spellings mapped to one canonical unit so that equal units merge.
_UNIT_ALIASES: dict[str, str] = {
    "mg": "mg",
    "milligramm": "mg",
    "g": "g",
    "gr": "g",
    "gr.": "g",
    "gramm": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "kilo": "kg",
    "kilogramm": "kg",
    "ml": "ml",
    "milliliter": "ml",
    "l": "l",
    "liter": "l",
    "litre": "l",
    "el": "EL",
    "esslöffel": "EL",
    "tl": "TL",
    "teelöffel": "TL",
}
# Units that only count pieces: written as a bare number (merges with "x").
_COUNT_UNITS = frozenset(
    {"x", "stk", "stk.", "stück", "stueck", "st", "st.", "piece", "pieces", "pc", "pcs"}
)
_STEP_NUMBER = re.compile(r"^\s*(?:schritt|step)?\s*\d+\s*[.):]\s*", re.IGNORECASE)
_AUTH_HINT = re.compile(r"token|segments|authorization|signature|jwt|subject", re.I)


def _format_number(value: float) -> str:
    """Return a number with a dot as decimal separator, at most 3 decimals."""
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text or "0"


def _clean_unit(unit: str | None) -> str:
    """Return the unit in its canonical spelling ("" means plain count)."""
    if not unit:
        return ""
    text = " ".join(unit.replace(",", " ").split())
    lowered = text.lower()
    if lowered in _COUNT_UNITS:
        return ""
    return _UNIT_ALIASES.get(lowered, text)


def _clean_note(note: str | None) -> str:
    """Return a note that is safe as one part of a description."""
    if not note:
        return ""
    text = " ".join(note.replace(",", ";").split())
    if text.startswith("(") and text.endswith(")") and text.count("(") == 1:
        text = text[1:-1].strip()
    return text


def item_description(ingredient: Ingredient) -> str:
    """Return the shopping list description KitchenOwl can add up.

    KitchenOwl splits a description at commas; each part is ``NUMBER? UNIT?``.
    Parts with the same unit are summed, g/kg/mg and ml/l are converted.
    Decimals use a dot (``1.5``). Weights and volumes are written without a
    space (``250g``), other units with one (``2 EL``), plain counts as a bare
    number (``3``). A note becomes its own trailing part in parentheses
    (``250g, (Type 405)``): the leading bracket keeps it from being read as
    a number or unit, so it never disturbs the sum.
    """
    unit = _clean_unit(ingredient.unit)
    amount = ingredient.amount
    parts: list[str] = []
    valid = (
        isinstance(amount, (int, float))
        and not isinstance(amount, bool)
        and math.isfinite(amount)
        and round(amount, 3) > 0
    )
    if valid:
        number = _format_number(float(amount))  # type: ignore[arg-type]
        if not unit:
            parts.append(number)
        elif unit in _SI_UNITS:
            parts.append(f"{number}{unit}")
        else:
            parts.append(f"{number} {unit}")
    elif unit and unit not in _SI_UNITS:
        parts.append(unit)
    note = _clean_note(ingredient.note)
    if note:
        parts.append(f"({note})")
    return ", ".join(parts)


def normalize_source(url: str) -> str:
    """Return a comparable form of a recipe address.

    Ignores http/https, case of the host, a trailing slash and the fragment.
    """
    text = url.strip()
    parts = urlsplit(text if "//" in text else f"//{text}")
    path = parts.path.rstrip("/")
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.netloc.lower()}{path}{query}"


def _minutes(value: int | None) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    return max(0, int(value))


def _build_description(recipe: Recipe) -> str:
    """Short text first, then the numbered steps (KitchenOwl renders Markdown)."""
    blocks: list[str] = []
    if recipe.description and recipe.description.strip():
        blocks.append(recipe.description.strip())
    steps = [
        " ".join(_STEP_NUMBER.sub("", step, count=1).split())
        for step in recipe.steps
        if step and step.strip()
    ]
    steps = [step for step in steps if step]
    if steps:
        blocks.append("\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1)))
    return "\n\n".join(blocks)


def _build_items(ingredients: list[Ingredient]) -> list[dict[str, Any]]:
    """Return recipe items; one entry per name (KitchenOwl allows one each)."""
    merged: dict[str, dict[str, Any]] = {}
    for ingredient in ingredients:
        name = " ".join(ingredient.name.split())
        if not name:
            continue
        description = item_description(ingredient)
        entry = merged.get(name.lower())
        if entry is None:
            merged[name.lower()] = {
                "name": name,
                "description": description,
                "optional": False,
            }
        elif description:
            entry["description"] = ", ".join(
                part for part in (entry["description"], description) if part
            )
    return list(merged.values())


class KitchenOwlClient:
    """Small async client for the parts of the KitchenOwl API EatFresh uses."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str, token: str) -> None:
        base = base_url.strip().rstrip("/")
        if base.lower().endswith("/api"):
            base = base[:-4].rstrip("/")
        self._session = session
        self._base = base
        self._token = token
        # household id -> (time of fetch, recipes), for find_by_source only.
        self._recipe_lists: dict[int, tuple[float, list[dict]]] = {}

    # ------------------------------------------------------------------ core

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        raw: bool = False,
    ) -> Any:
        """Send a request; return parsed JSON, or (bytes, content type) if raw."""
        url = f"{self._base}{path}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "*/*" if raw else "application/json",
            "User-Agent": _USER_AGENT,
        }
        try:
            async with self._session.request(
                method,
                url,
                params=params,
                json=json,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                status = response.status
                if status >= 400:
                    body = (await response.text())[:300]
                    raise self._error_for(status, path, body)
                if raw:
                    content_type = response.headers.get(
                        "Content-Type", "application/octet-stream"
                    )
                    return await response.read(), content_type
                try:
                    return await response.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError) as err:
                    raise KitchenOwlError(f"Invalid JSON from KitchenOwl ({path})") from err
        except KitchenOwlError:
            raise
        except TimeoutError as err:
            raise KitchenOwlError(f"KitchenOwl timed out ({path})") from err
        except aiohttp.ClientError as err:
            raise KitchenOwlError(f"KitchenOwl not reachable ({path}): {err}") from err

    @staticmethod
    def _error_for(status: int, path: str, body: str) -> KitchenOwlError:
        # flask-jwt-extended answers 422 for a malformed token.
        if status in (401, 403) or (status == 422 and _AUTH_HINT.search(body)):
            return KitchenOwlAuthError(f"KitchenOwl rejected the token (HTTP {status})")
        return KitchenOwlError(f"KitchenOwl error HTTP {status} ({path}): {body[:120]}")

    @staticmethod
    def _expect(data: Any, kind: type, path: str) -> Any:
        if not isinstance(data, kind):
            raise KitchenOwlError(f"Unexpected answer from KitchenOwl ({path})")
        return data

    # ------------------------------------------------------------------- API

    async def get_user(self) -> dict:
        """Return the user of the token (``GET /api/user``)."""
        path = "/api/user"
        return self._expect(await self._request("GET", path), dict, path)

    async def list_households(self) -> list[dict]:
        """Return ``[{id, name}]`` (``GET /api/household``)."""
        path = "/api/household"
        data = self._expect(await self._request("GET", path), list, path)
        return [{"id": item["id"], "name": item.get("name", "")} for item in data]

    async def list_shoppinglists(self, household_id: int) -> list[dict]:
        """Return ``[{id, name}]`` (``GET /api/household/<id>/shoppinglist``)."""
        path = f"/api/household/{int(household_id)}/shoppinglist"
        data = self._expect(await self._request("GET", path), list, path)
        return [{"id": item["id"], "name": item.get("name", "")} for item in data]

    async def list_recipes(self, household_id: int) -> list[dict]:
        """Return all recipes of a household, reduced to the fields we use."""
        path = f"/api/household/{int(household_id)}/recipe"
        data = self._expect(await self._request("GET", path), list, path)
        recipes = [
            {
                "id": item["id"],
                "name": item.get("name", ""),
                "source": item.get("source"),
                "photo": item.get("photo"),
                "time": item.get("time"),
                "yields": item.get("yields"),
            }
            for item in data
        ]
        self._recipe_lists[int(household_id)] = (time.monotonic(), recipes)
        return [dict(item) for item in recipes]

    async def _cached_recipes(self, household_id: int) -> list[dict]:
        """Return the recipe list, reusing a copy younger than RECIPE_LIST_TTL."""
        cached = self._recipe_lists.get(int(household_id))
        if cached is not None and time.monotonic() - cached[0] < RECIPE_LIST_TTL:
            return cached[1]
        return await self.list_recipes(household_id)

    def forget_recipes(self, household_id: int | None = None) -> None:
        """Drop the cached recipe list (of one household or of all)."""
        if household_id is None:
            self._recipe_lists.clear()
        else:
            self._recipe_lists.pop(int(household_id), None)

    async def get_recipe(self, recipe_id: int) -> dict:
        """Return one full recipe (``GET /api/recipe/<id>``)."""
        path = f"/api/recipe/{int(recipe_id)}"
        return self._expect(await self._request("GET", path), dict, path)

    async def find_by_source(
        self, household_id: int, url: str, *, fresh: bool = False
    ) -> int | None:
        """Return the id of the recipe whose ``source`` is this address.

        KitchenOwl cannot search by source, so all recipes are fetched; the
        list is reused for a short time (see ``RECIPE_LIST_TTL``). With
        ``fresh`` the list is always loaded again, so a recipe that was added
        in KitchenOwl in the meantime is found.
        """
        wanted = normalize_source(url)
        if not wanted:
            return None
        recipes = (
            await self.list_recipes(household_id)
            if fresh
            else await self._cached_recipes(household_id)
        )
        for recipe in recipes:
            source = recipe.get("source")
            if isinstance(source, str) and source.strip():
                if normalize_source(source) == wanted:
                    return int(recipe["id"])
        return None

    async def create_recipe(self, household_id: int, recipe: Recipe) -> int:
        """Create a recipe and return its id (``POST /api/household/<id>/recipe``)."""
        name = " ".join(recipe.title.split())
        if not name:
            raise KitchenOwlError("Recipe has no title")
        prep = _minutes(recipe.prep_time)
        cook = _minutes(recipe.cook_time)
        total = _minutes(recipe.total_time)
        if total is None and (prep is not None or cook is not None):
            total = (prep or 0) + (cook or 0)
        body: dict[str, Any] = {
            "name": name,
            "description": _build_description(recipe),
            "source": recipe.url,
            "items": _build_items(recipe.ingredients),
            "tags": [t for t in dict.fromkeys(t.strip() for t in recipe.tags) if t],
        }
        for field, value in (
            ("time", total),
            ("prep_time", prep),
            ("cook_time", cook),
            ("yields", _minutes(recipe.servings)),
        ):
            if value is not None:
                body[field] = value
        if recipe.image and recipe.image.startswith(("http://", "https://")):
            body["photo"] = recipe.image
        path = f"/api/household/{int(household_id)}/recipe"
        # Whatever happens, the cached list may now be out of date.
        self.forget_recipes(household_id)
        try:
            data = self._expect(
                await self._request("POST", path, json=body), dict, path
            )
        finally:
            self.forget_recipes(household_id)
        try:
            return int(data["id"])
        except (KeyError, TypeError, ValueError) as err:
            raise KitchenOwlError("KitchenOwl did not return a recipe id") from err

    async def add_recipe_to_shoppinglist(
        self, shoppinglist_id: int, recipe_id: int
    ) -> int:
        """Put all ingredients of a recipe on a list; return how many.

        Uses ``POST /api/shoppinglist/<id>/recipeitems``, the only call that
        merges amounts with entries already on the list.
        """
        recipe = await self.get_recipe(recipe_id)
        items = [
            {
                "id": int(item["id"]),
                "name": item["name"],
                "description": item.get("description") or "",
                "optional": bool(item.get("optional", False)),
            }
            for item in recipe.get("items") or []
            if isinstance(item, dict) and "id" in item and item.get("name")
        ]
        if not items:
            return 0
        path = f"/api/shoppinglist/{int(shoppinglist_id)}/recipeitems"
        await self._request("POST", path, json={"items": items})
        return len(items)

    async def fetch_photo(self, filename: str) -> tuple[bytes, str]:
        """Return a recipe photo as (content, content type)."""
        if not filename or "/" in filename or "\\" in filename or ".." in filename:
            raise KitchenOwlError("Invalid photo file name")
        path = f"/api/upload/{quote(filename, safe='')}"
        content, content_type = await self._request("GET", path, raw=True)
        return content, content_type
