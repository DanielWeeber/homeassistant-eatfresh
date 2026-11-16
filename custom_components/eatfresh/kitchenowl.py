"""Client for the KitchenOwl REST API (tested against KitchenOwl 0.8.1).

Pure Python: no Home Assistant imports. The client never deletes recipes,
items or lists; the only DELETE it sends removes a meal plan entry.

Facts taken from the KitchenOwl 0.8.1 backend source:

* Authentication is ``Authorization: Bearer <token>`` (a long-lived token).
* All times (``time``, ``prep_time``, ``cook_time``) are minutes, ``yields``
  is the number of servings.
* ``POST /api/household/<id>/recipe`` requires ``name`` and ``description``;
  a ``photo`` containing a ``/`` is downloaded by the server itself, and a
  failed download silently leaves the recipe without a photo.
* Shopping list entries are merged by ``description_merger``. See
  :func:`item_description` for the format it understands.
* ``POST /api/recipe/<id>`` changes only the fields that are sent; ``tags``
  replaces the tag links (names, case sensitive, created when missing).
* The meal plan (``/api/household/<id>/planner``) stores a real date per
  entry. See :meth:`KitchenOwlClient.list_planner`.
"""

from __future__ import annotations

import math
import re
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

import aiohttp

from .errors import EatFreshError, KitchenOwlAuthError, KitchenOwlError, RecipeNotFound
from .models import Ingredient, Recipe

REQUEST_TIMEOUT = 20  # seconds
# How long ``find_by_source`` may reuse the last list of recipes. Creating a
# recipe through this client drops the copy at once.
RECIPE_LIST_TTL = 120.0  # seconds
# A "fresh" list of recipe ids may be this old, so repeated lookups of an
# unknown id do not load the whole list again every time.
RECIPE_LIST_FRESH_AGE = 5.0  # seconds
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
_NUMBERED_LINE = re.compile(r"^\s*(?:schritt|step)?\s*\d+\s*[.):]\s+(.*)$", re.IGNORECASE)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
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


# Query parameters that only track where a click came from. They never change
# the recipe, so ``normalize_source`` drops them.
_TRACKING_PARAMS = frozenset(
    {
        "fbclid",
        "gclid",
        "gclsrc",
        "dclid",
        "gbraid",
        "wbraid",
        "msclkid",
        "yclid",
        "twclid",
        "ttclid",
        "igshid",
        "igsh",
        "li_fat_id",
        "mc_cid",
        "mc_eid",
        "mkt_tok",
        "_ga",
        "_gl",
        "_hsenc",
        "_hsmi",
        "oly_anon_id",
        "oly_enc_id",
        "vero_id",
        "s_cid",
        "ncid",
        "amp",
        # Share buttons and referrers ("?ref=pin", "?share=1"). Parameters
        # that can name a recipe ("id", "p", "s" and unknown ones) stay.
        "ref",
        "share",
    }
)
_TRACKING_PREFIXES = ("utm_", "pk_", "mtm_", "hsa_")
_DEFAULT_PORTS = {":80", ":443"}


def _is_tracking(name: str) -> bool:
    key = name.strip().lower()
    return key in _TRACKING_PARAMS or key.startswith(_TRACKING_PREFIXES)


def normalize_source(url: str) -> str:
    """Return a comparable form of a recipe address.

    Two spellings of the same page give the same text: the scheme (http,
    https or none), the case of the host, a leading ``www.``, a default
    port, a trailing slash, an ``amp`` path segment at the start or the end
    (AMP pages), percent encoding in the path (``k%C3%BCrbis`` is
    ``kürbis``), the fragment and tracking parameters (``utm_*``,
    ``fbclid``, ``gclid``, ``ref``, ``share`` and the like) do not matter.
    Other query parameters are kept, in sorted order.
    """
    text = url.strip()
    if not text:
        return ""
    parts = urlsplit(text if "//" in text else f"//{text}")
    host = parts.netloc.rsplit("@", 1)[-1].lower().rstrip(".")
    for port in _DEFAULT_PORTS:
        if host.endswith(port):
            host = host[: -len(port)]
    host = host.removeprefix("www.")
    # Decode each segment on its own; an encoded slash stays "%2F".
    segments = [
        unquote(segment).replace("/", "%2F")
        for segment in parts.path.split("/")
        if segment
    ]
    if segments and segments[-1].lower() == "amp":
        segments.pop()
    if segments and segments[0].lower() == "amp":
        segments.pop(0)
    path = "/" + "/".join(segments) if segments else ""
    params = sorted(
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking(name)
    )
    query = f"?{urlencode(params)}" if params else ""
    return f"{host}{path}{query}"


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


def _clean_tags(tags: list[str]) -> list[str]:
    """Return tag names trimmed and without duplicates (case-insensitive)."""
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            continue
        name = " ".join(tag.split())
        if name and name.lower() not in seen:
            seen.add(name.lower())
            result.append(name)
    return result


def _tag_names(raw: Any) -> list[str]:
    """Return tag names from KitchenOwl's ``[{id, name, ...}]``."""
    if not isinstance(raw, list):
        return []
    names = [t.get("name") for t in raw if isinstance(t, dict)]
    return _clean_tags([n for n in names if isinstance(n, str)])


def _item_names(raw: Any) -> list[str]:
    """Return the names of the items of a recipe (``[{name, ...}]``)."""
    if not isinstance(raw, list):
        return []
    return [
        name
        for item in raw
        if isinstance(item, dict) and isinstance(name := item.get("name"), str) and name
    ]


def _day_to_ms(day: date) -> int:
    """Return midnight UTC of ``day`` in milliseconds (KitchenOwl's format)."""
    midnight = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return (midnight - _EPOCH) // timedelta(milliseconds=1)


def _ms_to_day(value: Any) -> date | None:
    """Return the date of a ``cooking_date``; ``None`` for "no day"."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < -2_208_988_800_000:  # before 1900, covers the "no day" value
        return None
    try:
        return (_EPOCH + timedelta(milliseconds=value)).date()
    except OverflowError:
        return None


def _split_description(text: str) -> tuple[str | None, list[str]]:
    """Split a KitchenOwl description into (text before the steps, steps).

    EatFresh writes a short text, a blank line and numbered lines. Everything
    before the first numbered line is the text; each numbered line starts a
    step, following lines up to a blank line belong to it, and a paragraph
    after a blank line becomes a step of its own. Without numbered lines
    (a recipe written in the KitchenOwl app) every paragraph is one step.
    Nothing is dropped: only the numbers are removed.
    """
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    first = next((i for i, line in enumerate(lines) if _NUMBERED_LINE.match(line)), None)
    if first is None:
        paragraphs = [
            "\n".join(part.strip() for part in block.split("\n") if part.strip())
            for block in re.split(r"\n\s*\n", "\n".join(lines))
        ]
        return None, [p for p in paragraphs if p]
    before = "\n".join(lines[:first]).strip()
    steps: list[list[str]] = []
    blank_before = False
    for line in lines[first:]:
        if not line.strip():
            blank_before = True
            continue
        match = _NUMBERED_LINE.match(line)
        if match:
            steps.append([match.group(1).strip()])
        elif blank_before or not steps:
            steps.append([line.strip()])
        else:
            steps[-1].append(line.strip())
        blank_before = False
    return before or None, [" ".join(part for part in step if part) for step in steps]


def _positive_minutes(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value) if value > 0 else None


def recipe_to_model(data: dict) -> Recipe:
    """Turn a KitchenOwl recipe (from ``get_recipe``) into a :class:`Recipe`.

    ``source`` is ``"kitchenowl"`` and ``id`` the KitchenOwl recipe id. The
    description is split into text and numbered steps (see
    :func:`_split_description`). Ingredients keep name and the KitchenOwl
    description as ``raw`` (``"<description> <name>"``); amount and unit are
    not parsed. Whether an ingredient is optional is not carried over.
    """
    try:
        recipe_id = int(data["id"])
    except (KeyError, TypeError, ValueError) as err:
        raise KitchenOwlError("KitchenOwl recipe has no id") from err
    description, steps = _split_description(str(data.get("description") or ""))
    ingredients: list[Ingredient] = []
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        name = " ".join(str(item.get("name") or "").split())
        if not name:
            continue
        note = " ".join(str(item.get("description") or "").split())
        ingredients.append(
            Ingredient(name=name, raw=f"{note} {name}" if note else name)
        )
    photo = data.get("photo")
    source = data.get("source")
    return Recipe(
        source="kitchenowl",
        id=str(recipe_id),
        url=source.strip() if isinstance(source, str) else "",
        title=" ".join(str(data.get("name") or "").split()),
        description=description,
        image=photo if isinstance(photo, str) and photo else None,
        servings=_positive_minutes(data.get("yields")),
        prep_time=_positive_minutes(data.get("prep_time")),
        cook_time=_positive_minutes(data.get("cook_time")),
        total_time=_positive_minutes(data.get("time")),
        ingredients=ingredients,
        steps=steps,
        tags=_tag_names(data.get("tags")),
    )


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
    def _error_for(status: int, path: str, body: str) -> EatFreshError:
        # KitchenOwl answers 403 for a recipe of a household the user of the
        # token is not in. The token is fine, so this is no reason to log in
        # again.
        if status == 403 and path.startswith("/api/recipe/"):
            return RecipeNotFound(f"KitchenOwl refused the recipe ({path})")
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

    async def list_shoppinglist_items(self, shoppinglist_id: int) -> list[dict]:
        """Return the open entries of a list as ``[{id, name, description}]``.

        Read only: nothing on the list is changed or removed. Uses
        ``GET /api/shoppinglist/<id>/items`` (KitchenOwl 0.8.1). KitchenOwl
        keeps no "checked" state on the server: an entry that is bought is
        taken off the list, so every row it returns is open. The order is the
        one of the server (by name). ``description`` is the amount text and
        is ``""`` when there is none. Rows without an id or a name are
        skipped.
        """
        path = f"/api/shoppinglist/{int(shoppinglist_id)}/items"
        data = self._expect(await self._request("GET", path), list, path)
        items: list[dict] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            name = row.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            try:
                item_id = int(row["id"])
            except (KeyError, TypeError, ValueError):
                continue
            description = row.get("description")
            items.append(
                {
                    "id": item_id,
                    "name": name,
                    "description": description if isinstance(description, str) else "",
                }
            )
        return items

    async def list_recipes(self, household_id: int) -> list[dict]:
        """Return all recipes of a household, reduced to the fields we use.

        Fields: id, name, source, photo, time, yields, ``tags`` (names) and
        ``items`` (names of the ingredients, for the search of the collection).
        """
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
                "tags": _tag_names(item.get("tags")),
                "items": _item_names(item.get("items")),
            }
            for item in data
        ]
        self._recipe_lists[int(household_id)] = (time.monotonic(), recipes)
        return [
            {**item, "tags": list(item["tags"]), "items": list(item["items"])}
            for item in recipes
        ]

    async def _cached_recipes(
        self, household_id: int, max_age: float = RECIPE_LIST_TTL
    ) -> list[dict]:
        """Return the recipe list, reusing a copy younger than ``max_age``."""
        cached = self._recipe_lists.get(int(household_id))
        if cached is not None and time.monotonic() - cached[0] < max_age:
            return cached[1]
        return await self.list_recipes(household_id)

    async def recipe_ids(self, household_id: int, *, fresh: bool = False) -> set[int]:
        """Return the ids of all recipes of a household.

        Reuses the recipe list for a short time (see ``RECIPE_LIST_TTL``);
        with ``fresh`` only a list younger than ``RECIPE_LIST_FRESH_AGE`` is
        reused, so an unknown id loads the list at most every few seconds.
        """
        recipes = await self._cached_recipes(
            household_id, RECIPE_LIST_FRESH_AGE if fresh else RECIPE_LIST_TTL
        )
        ids: set[int] = set()
        for recipe in recipes:
            try:
                ids.add(int(recipe["id"]))
            except (KeyError, TypeError, ValueError):
                continue
        return ids

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

    async def list_tags(self, household_id: int) -> list[str]:
        """Return the names of all tags of a household (``GET .../tag``)."""
        path = f"/api/household/{int(household_id)}/tag"
        data = self._expect(await self._request("GET", path), list, path)
        return _tag_names(data)

    async def set_recipe_tags(self, recipe_id: int, tags: list[str]) -> list[str]:
        """Replace the tags of a recipe and return the names now stored.

        Sends only ``tags`` to ``POST /api/recipe/<id>``; KitchenOwl leaves
        every other field (name, description, items, times, source, photo)
        as it is, creates missing tags and unlinks tags not in the list.
        Names are trimmed and duplicates (any case) dropped. Does not delete
        the tags themselves.
        """
        names = _clean_tags(list(tags))
        path = f"/api/recipe/{int(recipe_id)}"
        # The cached recipe list carries tags, so it is out of date now.
        self.forget_recipes()
        try:
            data = self._expect(
                await self._request("POST", path, json={"tags": names}), dict, path
            )
        finally:
            self.forget_recipes()
        return _tag_names(data.get("tags"))

    async def list_planner(self, household_id: int) -> list[dict]:
        """Return the meal plan as ``[{recipe_id, name, photo, date}]``.

        KitchenOwl 0.8.1 stores one row per recipe and day: ``cooking_date``
        is a timestamp (ms) of midnight UTC of a real date, so the date is
        that timestamp read in UTC. A recipe can be planned on several days.
        A recipe planned without a day is stored as 0001-01-01; it comes
        back with ``date`` set to ``None``. (The ``day`` weekday number the
        server also sends is ignored: it is -1 for anything after a week.)
        """
        path = f"/api/household/{int(household_id)}/planner"
        data = self._expect(await self._request("GET", path), list, path)
        entries: list[dict] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            recipe = item.get("recipe") if isinstance(item.get("recipe"), dict) else {}
            try:
                recipe_id = int(item.get("recipe_id", recipe.get("id")))
            except (TypeError, ValueError):
                continue
            entries.append(
                {
                    "recipe_id": recipe_id,
                    "name": recipe.get("name") or "",
                    "photo": recipe.get("photo") or None,
                    "date": _ms_to_day(item.get("cooking_date")),
                }
            )
        return entries

    async def add_planner_entry(
        self, household_id: int, recipe_id: int, day: date
    ) -> None:
        """Plan a recipe on a day (``POST .../planner/recipe``).

        ``day`` is sent as midnight UTC, the way KitchenOwl stores it.
        Planning the same recipe on the same day again changes nothing; a
        recipe that was planned without a day loses that entry (the server
        replaces it).
        """
        if not isinstance(day, date) or isinstance(day, datetime):
            raise KitchenOwlError("The planner needs a date")
        path = f"/api/household/{int(household_id)}/planner/recipe"
        body = {"recipe_id": int(recipe_id), "cooking_date": _day_to_ms(day)}
        await self._request("POST", path, json=body)

    async def remove_planner_entry(
        self, household_id: int, recipe_id: int, day: date | None
    ) -> None:
        """Take a recipe out of the meal plan; the recipe itself stays.

        With ``day`` only that day's entry goes; with ``None`` only the entry
        without a day (other days stay). Removing an entry that does not
        exist is not an error. This is the only DELETE the client sends.
        """
        if day is not None and (not isinstance(day, date) or isinstance(day, datetime)):
            raise KitchenOwlError("The planner needs a date")
        path = f"/api/household/{int(household_id)}/planner/recipe/{int(recipe_id)}"
        body: dict[str, Any] = {} if day is None else {"cooking_date": _day_to_ms(day)}
        await self._request("DELETE", path, json=body)

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
