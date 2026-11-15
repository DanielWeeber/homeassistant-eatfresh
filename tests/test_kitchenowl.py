"""Tests for the KitchenOwl client. HTTP is mocked, no network."""

from __future__ import annotations

from datetime import date, datetime

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.eatfresh.errors import (
    KitchenOwlAuthError,
    KitchenOwlError,
    RecipeNotFound,
)
from custom_components.eatfresh.kitchenowl import (
    KitchenOwlClient,
    _build_description,
    item_description,
    recipe_to_model,
)
from custom_components.eatfresh.models import Ingredient, Recipe

BASE = "https://kitchenowl.example.com"
TOKEN = "secret-token"


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as sess:
        yield sess


@pytest.fixture
def client(session):
    return KitchenOwlClient(session, BASE, TOKEN)


def last_request(mock, method: str):
    """Return (url, kwargs) of the last request with this method."""
    for (req_method, url), calls in reversed(list(mock.requests.items())):
        if req_method == method:
            return url, calls[-1].kwargs
    raise AssertionError(f"no {method} request")


def make_recipe(**overrides) -> Recipe:
    data = {
        "source": "jsonld",
        "id": "https://rezepte.example.com/kuchen",
        "url": "https://rezepte.example.com/kuchen",
        "title": "Käsekuchen",
        "description": "Cremig und einfach.",
        "image": "https://rezepte.example.com/img/kuchen.jpg",
        "servings": 8,
        "prep_time": 20,
        "cook_time": 60,
        "total_time": 80,
        "ingredients": [
            Ingredient(name="Mehl", amount=250, unit="g", note="Type 405"),
            Ingredient(name="Eier", amount=3),
        ],
        "steps": ["Teig kneten.", "2. Backen."],
        "tags": ["Kuchen", "Kuchen", " "],
    }
    data.update(overrides)
    return Recipe(**data)


# ---------------------------------------------------------- item_description


@pytest.mark.parametrize(
    ("ingredient", "expected"),
    [
        (Ingredient(name="Mehl", amount=250, unit="g"), "250g"),
        (Ingredient(name="Mehl", amount=250.0, unit="Gramm"), "250g"),
        (Ingredient(name="Milch", amount=1.5, unit="L"), "1.5l"),
        (Ingredient(name="Milch", amount=0.5, unit="Liter"), "0.5l"),
        (Ingredient(name="Zucker", amount=1.25, unit="kg"), "1.25kg"),
        (Ingredient(name="Öl", amount=2, unit="EL"), "2 EL"),
        (Ingredient(name="Öl", amount=2, unit="Esslöffel"), "2 EL"),
        (Ingredient(name="Salz", amount=1, unit="Prise"), "1 Prise"),
        (Ingredient(name="Eier", amount=3), "3"),
        (Ingredient(name="Zwiebel", amount=2, unit="Stück"), "2"),
        (Ingredient(name="Petersilie", amount=0.333333, unit="Bund"), "0.333 Bund"),
        (Ingredient(name="Pfeffer"), ""),
        (Ingredient(name="Pfeffer", amount=0), ""),
        (Ingredient(name="Pfeffer", amount=float("nan"), unit="g"), ""),
        (Ingredient(name="Salz", unit="Prise"), "Prise"),
        (Ingredient(name="Mehl", amount=250, unit="g", note="Type 405"), "250g, (Type 405)"),
        (Ingredient(name="Mehl", amount=250, unit="g", note="(Type 405)"), "250g, (Type 405)"),
        (Ingredient(name="Butter", amount=1, unit="Stück", note="weich, in Würfeln"), "1, (weich; in Würfeln)"),
        (Ingredient(name="Dill", note="2 Zweige"), "(2 Zweige)"),
        (Ingredient(name="Mehl", amount=1, unit="g,x"), "1 g x"),
    ],
)
def test_item_description(ingredient, expected):
    assert item_description(ingredient) == expected


def test_item_description_note_does_not_start_with_digit_or_unit():
    # A bracket keeps the note from being read as NUMBER or SI unit.
    description = item_description(Ingredient(name="x", amount=1, unit="g", note="5 g mehr"))
    assert description == "1g, (5 g mehr)"
    assert all(part.strip().startswith(("1", "(")) for part in description.split(","))


# ------------------------------------------------------------------- reading


async def test_get_user(client, mock):
    mock.get(f"{BASE}/api/user", payload={"id": 1, "username": "tester"})
    assert (await client.get_user())["id"] == 1
    _, kwargs = last_request(mock, "GET")
    assert kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert kwargs["timeout"].total == 20


async def test_base_url_with_slash_and_api_suffix(session, mock):
    mock.get(f"{BASE}/api/user", payload={"id": 2}, repeat=True)
    for url in (f"{BASE}/", f"{BASE}/api", f"{BASE}/api/"):
        assert (await KitchenOwlClient(session, url, TOKEN).get_user())["id"] == 2


async def test_list_households(client, mock):
    mock.get(f"{BASE}/api/household", payload=[{"id": 1, "name": "Home", "member": []}])
    assert await client.list_households() == [{"id": 1, "name": "Home"}]


async def test_list_shoppinglists(client, mock):
    mock.get(
        f"{BASE}/api/household/1/shoppinglist",
        payload=[{"id": 5, "name": "Weekly", "items": [], "recentItems": []}],
    )
    assert await client.list_shoppinglists(1) == [{"id": 5, "name": "Weekly"}]


async def test_list_recipes(client, mock):
    mock.get(
        f"{BASE}/api/household/1/recipe",
        payload=[
            {
                "id": 7,
                "name": "Cake",
                "source": "https://a.example.com/x",
                "photo": "abc.jpg",
                "time": 30,
                "yields": 4,
                "items": [],
                "tags": [{"id": 2, "name": "Backen"}, {"id": 3, "name": "Süß"}],
            }
        ],
    )
    assert await client.list_recipes(1) == [
        {
            "id": 7,
            "name": "Cake",
            "source": "https://a.example.com/x",
            "photo": "abc.jpg",
            "time": 30,
            "yields": 4,
            "tags": ["Backen", "Süß"],
        }
    ]


async def test_get_recipe(client, mock):
    mock.get(f"{BASE}/api/recipe/7", payload={"id": 7, "items": []})
    assert (await client.get_recipe(7))["id"] == 7


# ------------------------------------------------------------ find_by_source


@pytest.mark.parametrize(
    "stored",
    [
        "https://rezepte.example.com/kuchen",
        "https://rezepte.example.com/kuchen/",
        "http://rezepte.example.com/kuchen",
        "HTTP://Rezepte.Example.com/kuchen/#zutaten",
    ],
)
async def test_find_by_source_matches(client, mock, stored):
    mock.get(
        f"{BASE}/api/household/1/recipe",
        payload=[
            {"id": 1, "name": "A", "source": None},
            {"id": 2, "name": "B", "source": "https://other.example.com/kuchen"},
            {"id": 3, "name": "C", "source": stored},
        ],
    )
    assert await client.find_by_source(1, "https://rezepte.example.com/kuchen/") == 3


async def test_find_by_source_query_matters_and_none(client, mock):
    mock.get(
        f"{BASE}/api/household/1/recipe",
        payload=[{"id": 1, "name": "A", "source": "https://a.example.com/r?id=1"}],
        repeat=True,
    )
    assert await client.find_by_source(1, "https://a.example.com/r?id=2") is None
    assert await client.find_by_source(1, "https://a.example.com/r?id=1") == 1
    assert await client.find_by_source(1, "") is None


# ------------------------------------------------------------- create_recipe


async def test_create_recipe_body(client, mock):
    mock.post(f"{BASE}/api/household/1/recipe", payload={"id": 42})
    assert await client.create_recipe(1, make_recipe()) == 42
    _, kwargs = last_request(mock, "POST")
    body = kwargs["json"]
    assert body["name"] == "Käsekuchen"
    assert body["description"] == "Cremig und einfach.\n\n1. Teig kneten.\n2. Backen."
    assert body["source"] == "https://rezepte.example.com/kuchen"
    assert body["photo"] == "https://rezepte.example.com/img/kuchen.jpg"
    assert (body["time"], body["prep_time"], body["cook_time"], body["yields"]) == (80, 20, 60, 8)
    assert body["tags"] == ["Kuchen"]
    assert body["items"] == [
        {"name": "Mehl", "description": "250g, (Type 405)", "optional": False},
        {"name": "Eier", "description": "3", "optional": False},
    ]
    assert kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"


async def test_create_recipe_minimal(client, mock):
    mock.post(f"{BASE}/api/household/1/recipe", payload={"id": 1})
    recipe = make_recipe(
        description=None, image=None, servings=None, prep_time=None,
        cook_time=None, total_time=None, ingredients=[], steps=[], tags=[],
    )
    await client.create_recipe(1, recipe)
    _, kwargs = last_request(mock, "POST")
    body = kwargs["json"]
    # KitchenOwl requires "description", so it is always sent.
    assert body["description"] == ""
    assert not {"photo", "time", "prep_time", "cook_time", "yields"} & body.keys()


async def test_create_recipe_total_time_from_parts_and_non_http_image(client, mock):
    mock.post(f"{BASE}/api/household/1/recipe", payload={"id": 1})
    await client.create_recipe(
        1, make_recipe(total_time=None, image="data:image/png;base64,AAAA")
    )
    _, kwargs = last_request(mock, "POST")
    assert kwargs["json"]["time"] == 80
    assert "photo" not in kwargs["json"]


async def test_create_recipe_merges_duplicate_names(client, mock):
    mock.post(f"{BASE}/api/household/1/recipe", payload={"id": 1})
    ingredients = [
        Ingredient(name="Salz", amount=1, unit="Prise"),
        Ingredient(name="salz", amount=2, unit="g"),
        Ingredient(name="  ", amount=1),
    ]
    await client.create_recipe(1, make_recipe(ingredients=ingredients))
    _, kwargs = last_request(mock, "POST")
    assert kwargs["json"]["items"] == [
        {"name": "Salz", "description": "1 Prise, 2g", "optional": False}
    ]


async def test_create_recipe_needs_title(client, mock):
    with pytest.raises(KitchenOwlError):
        await client.create_recipe(1, make_recipe(title="  "))


async def test_create_recipe_without_id(client, mock):
    mock.post(f"{BASE}/api/household/1/recipe", payload={"name": "x"})
    with pytest.raises(KitchenOwlError):
        await client.create_recipe(1, make_recipe())


# ------------------------------------------------ add_recipe_to_shoppinglist


async def test_add_recipe_to_shoppinglist(client, mock):
    mock.get(
        f"{BASE}/api/recipe/7",
        payload={
            "id": 7,
            "items": [
                {"id": 11, "name": "Mehl", "description": "250g", "optional": False},
                {"id": 12, "name": "Salz", "description": None, "optional": True},
            ],
        },
    )
    mock.post(f"{BASE}/api/shoppinglist/5/recipeitems", payload={"msg": "DONE"})
    assert await client.add_recipe_to_shoppinglist(5, 7) == 2
    _, kwargs = last_request(mock, "POST")
    assert kwargs["json"] == {
        "items": [
            {"id": 11, "name": "Mehl", "description": "250g", "optional": False},
            {"id": 12, "name": "Salz", "description": "", "optional": True},
        ]
    }


async def test_add_recipe_without_items_does_not_post(client, mock):
    mock.get(f"{BASE}/api/recipe/7", payload={"id": 7, "items": []})
    assert await client.add_recipe_to_shoppinglist(5, 7) == 0
    assert not any(method == "POST" for method, _ in mock.requests)


# --------------------------------------------------------------- fetch_photo


async def test_fetch_photo(client, mock):
    mock.get(
        f"{BASE}/api/upload/abc-123.jpg", body=b"\xff\xd8data", content_type="image/jpeg"
    )
    assert await client.fetch_photo("abc-123.jpg") == (b"\xff\xd8data", "image/jpeg")


@pytest.mark.parametrize("name", ["", "../x.jpg", "a/b.jpg", "a\\b.jpg"])
async def test_fetch_photo_rejects_bad_names(client, mock, name):
    with pytest.raises(KitchenOwlError):
        await client.fetch_photo(name)


# -------------------------------------------------------------------- errors


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_errors(client, mock, status):
    mock.get(f"{BASE}/api/user", status=status, payload={"msg": "nope"})
    with pytest.raises(KitchenOwlAuthError):
        await client.get_user()


async def test_malformed_token_422_is_auth_error(client, mock):
    mock.get(f"{BASE}/api/user", status=422, payload={"msg": "Not enough segments"})
    with pytest.raises(KitchenOwlAuthError):
        await client.get_user()


async def test_other_422_is_plain_error(client, mock):
    mock.post(f"{BASE}/api/household/1/recipe", status=422, payload={"msg": "bad field"})
    with pytest.raises(KitchenOwlError) as err:
        await client.create_recipe(1, make_recipe())
    assert not isinstance(err.value, KitchenOwlAuthError)


@pytest.mark.parametrize("status", [400, 404, 500, 502])
async def test_server_errors(client, mock, status):
    mock.get(f"{BASE}/api/household", status=status, body="boom")
    with pytest.raises(KitchenOwlError) as err:
        await client.list_households()
    assert not isinstance(err.value, KitchenOwlAuthError)
    assert TOKEN not in str(err.value)


async def test_connection_error(client, mock):
    mock.get(f"{BASE}/api/user", exception=aiohttp.ClientConnectionError("down"))
    with pytest.raises(KitchenOwlError):
        await client.get_user()


async def test_timeout_error(client, mock):
    mock.get(f"{BASE}/api/user", exception=TimeoutError())
    with pytest.raises(KitchenOwlError):
        await client.get_user()


async def test_invalid_json_and_wrong_shape(client, mock):
    mock.get(f"{BASE}/api/user", body="<html>", content_type="text/html")
    with pytest.raises(KitchenOwlError):
        await client.get_user()
    mock.get(f"{BASE}/api/household", payload={"not": "a list"})
    with pytest.raises(KitchenOwlError):
        await client.list_households()


async def test_client_never_deletes(client, mock):
    mock.get(f"{BASE}/api/household/1/recipe", payload=[])
    mock.post(f"{BASE}/api/household/1/recipe", payload={"id": 1})
    mock.post(f"{BASE}/api/recipe/1", payload={"id": 1, "tags": []})
    mock.get(f"{BASE}/api/household/1/tag", payload=[])
    mock.get(f"{BASE}/api/household/1/planner", payload=[])
    mock.post(f"{BASE}/api/household/1/planner/recipe", payload={"id": 1})
    await client.find_by_source(1, "https://a.example.com")
    await client.create_recipe(1, make_recipe())
    await client.list_tags(1)
    await client.set_recipe_tags(1, ["A"])
    await client.list_planner(1)
    await client.add_planner_entry(1, 1, date(2026, 11, 20))
    assert not any(method == "DELETE" for method, _ in mock.requests)


async def test_only_delete_is_planner_entry(client, mock):
    mock.delete(
        f"{BASE}/api/household/1/planner/recipe/7", payload={"id": 7}, repeat=True
    )
    await client.remove_planner_entry(1, 7, date(2026, 11, 20))
    await client.remove_planner_entry(1, 7, None)
    deletes = [str(url) for (method, url) in mock.requests if method == "DELETE"]
    assert deletes == [f"{BASE}/api/household/1/planner/recipe/7"]


# ------------------------------------------------------- recipe list cache


def _recipe_gets(mock) -> int:
    return sum(
        len(calls)
        for (method, url), calls in mock.requests.items()
        if method == "GET" and str(url).endswith("/api/household/1/recipe")
    )


async def test_find_by_source_reuses_the_list_for_a_short_time(client, mock, monkeypatch):
    mock.get(
        f"{BASE}/api/household/1/recipe",
        payload=[{"id": 1, "name": "A", "source": "https://a.example.com/r"}],
        repeat=True,
    )
    assert await client.find_by_source(1, "https://a.example.com/r") == 1
    assert await client.find_by_source(1, "https://a.example.com/x") is None
    assert _recipe_gets(mock) == 1

    # Older than the time limit: fetched again.
    from custom_components.eatfresh import kitchenowl

    real = kitchenowl.time.monotonic
    monkeypatch.setattr(
        kitchenowl.time, "monotonic", lambda: real() + kitchenowl.RECIPE_LIST_TTL + 1
    )
    assert await client.find_by_source(1, "https://a.example.com/r") == 1
    assert _recipe_gets(mock) == 2


async def test_create_recipe_drops_the_cached_list(client, mock):
    mock.get(
        f"{BASE}/api/household/1/recipe",
        payload=[{"id": 1, "name": "A", "source": "https://a.example.com/r"}],
        repeat=True,
    )
    mock.post(f"{BASE}/api/household/1/recipe", payload={"id": 7})
    assert await client.find_by_source(1, "https://a.example.com/new") is None
    assert await client.create_recipe(1, make_recipe()) == 7
    await client.find_by_source(1, "https://a.example.com/new")
    assert _recipe_gets(mock) == 2


async def test_collection_list_is_fresh_and_feeds_the_cache(client, mock):
    mock.get(
        f"{BASE}/api/household/1/recipe",
        payload=[{"id": 1, "name": "A", "source": "https://a.example.com/r"}],
        repeat=True,
    )
    await client.list_recipes(1)
    await client.list_recipes(1)
    assert _recipe_gets(mock) == 2
    assert await client.find_by_source(1, "https://a.example.com/r") == 1
    assert _recipe_gets(mock) == 2


async def test_find_by_source_fresh_ignores_the_cached_list(client, mock):
    """A recipe added in KitchenOwl after the list was cached is still found."""
    mock.get(f"{BASE}/api/household/1/recipe", payload=[])
    mock.get(
        f"{BASE}/api/household/1/recipe",
        payload=[{"id": 8, "name": "N", "source": "https://a.example.com/new"}],
    )
    assert await client.find_by_source(1, "https://a.example.com/new") is None
    # The cached (empty) list is still young: without ``fresh`` it is reused.
    assert _recipe_gets(mock) == 1
    assert await client.find_by_source(1, "https://a.example.com/new", fresh=True) == 8
    assert _recipe_gets(mock) == 2


# ------------------------------------------------------------------- tags


async def test_list_tags(client, mock):
    mock.get(
        f"{BASE}/api/household/1/tag",
        payload=[{"id": 1, "name": "Pasta"}, {"id": 2, "name": " Süß "}, {"id": 3}],
    )
    assert await client.list_tags(1) == ["Pasta", "Süß"]


async def test_list_tags_wrong_shape(client, mock):
    mock.get(f"{BASE}/api/household/1/tag", payload={"x": 1})
    with pytest.raises(KitchenOwlError):
        await client.list_tags(1)


async def test_set_recipe_tags_sends_only_tags(client, mock):
    mock.post(
        f"{BASE}/api/recipe/7",
        payload={"id": 7, "tags": [{"name": "Pasta"}, {"name": "Vegan"}]},
    )
    result = await client.set_recipe_tags(7, [" Pasta ", "Vegan", "pasta", "", "  "])
    assert result == ["Pasta", "Vegan"]
    _, kwargs = last_request(mock, "POST")
    assert kwargs["json"] == {"tags": ["Pasta", "Vegan"]}


async def test_set_recipe_tags_empty_list_clears(client, mock):
    mock.post(f"{BASE}/api/recipe/7", payload={"id": 7, "tags": []})
    assert await client.set_recipe_tags(7, []) == []
    _, kwargs = last_request(mock, "POST")
    assert kwargs["json"] == {"tags": []}


async def test_set_recipe_tags_drops_cached_list(client, mock):
    mock.get(f"{BASE}/api/household/1/recipe", payload=[], repeat=True)
    mock.post(f"{BASE}/api/recipe/7", payload={"id": 7, "tags": []})
    await client.find_by_source(1, "https://a.example.com")
    await client.set_recipe_tags(7, ["A"])
    await client.find_by_source(1, "https://a.example.com")
    assert _recipe_gets(mock) == 2


async def test_set_recipe_tags_auth_error(client, mock):
    mock.post(f"{BASE}/api/recipe/7", status=401)
    with pytest.raises(KitchenOwlAuthError):
        await client.set_recipe_tags(7, ["A"])


async def test_recipe_of_other_household_is_no_token_error(client, mock):
    """KitchenOwl answers 403 for a recipe of another household: not found."""
    mock.post(f"{BASE}/api/recipe/7", status=403)
    mock.get(f"{BASE}/api/recipe/7", status=403)
    with pytest.raises(RecipeNotFound):
        await client.set_recipe_tags(7, ["A"])
    with pytest.raises(RecipeNotFound) as err:
        await client.get_recipe(7)
    assert not isinstance(err.value, KitchenOwlAuthError)


async def test_403_elsewhere_is_still_a_token_error(client, mock):
    mock.get(f"{BASE}/api/household/1/planner", status=403)
    with pytest.raises(KitchenOwlAuthError):
        await client.list_planner(1)


async def test_set_recipe_tags_missing_recipe(client, mock):
    mock.post(f"{BASE}/api/recipe/7", status=404, body="Requested resource not found")
    with pytest.raises(KitchenOwlError):
        await client.set_recipe_tags(7, ["A"])


# ---------------------------------------------------------------- planner

# 2026-11-20 00:00 UTC and the "no day" value KitchenOwl 0.8.1 uses.
NOV_20_MS = 1795132800000
NO_DAY_MS = -62135596800000


def _entry(recipe_id: int, cooking_date: int, **recipe) -> dict:
    return {
        "recipe_id": recipe_id,
        "cooking_date": cooking_date,
        "day": 4,
        "recipe": {"id": recipe_id, "name": f"R{recipe_id}", "photo": None, **recipe},
    }


async def test_list_planner_dates_and_no_day(client, mock):
    mock.get(
        f"{BASE}/api/household/1/planner",
        payload=[
            _entry(7, NO_DAY_MS),
            _entry(8, NOV_20_MS, photo="p.jpg"),
            _entry(8, NOV_20_MS + 2 * 86400000),
            {"recipe_id": "x"},
            "junk",
        ],
    )
    assert await client.list_planner(1) == [
        {"recipe_id": 7, "name": "R7", "photo": None, "date": None},
        {"recipe_id": 8, "name": "R8", "photo": "p.jpg", "date": date(2026, 11, 20)},
        {"recipe_id": 8, "name": "R8", "photo": None, "date": date(2026, 11, 22)},
    ]


async def test_list_planner_reads_utc_not_local_time(client, mock):
    # 23:59 UTC is still the same day, whatever time zone the server runs in.
    mock.get(
        f"{BASE}/api/household/1/planner",
        payload=[_entry(7, NOV_20_MS + 86399000), _entry(7, None)],
    )
    result = await client.list_planner(1)
    assert [e["date"] for e in result] == [date(2026, 11, 20), None]


async def test_list_planner_wrong_shape_and_error(client, mock):
    mock.get(f"{BASE}/api/household/1/planner", payload={"x": 1})
    with pytest.raises(KitchenOwlError):
        await client.list_planner(1)
    mock.get(f"{BASE}/api/household/1/planner", status=500)
    with pytest.raises(KitchenOwlError):
        await client.list_planner(1)


async def test_add_planner_entry_sends_midnight_utc(client, mock):
    mock.post(f"{BASE}/api/household/1/planner/recipe", payload={"id": 7})
    await client.add_planner_entry(1, 7, date(2026, 11, 20))
    _, kwargs = last_request(mock, "POST")
    assert kwargs["json"] == {"recipe_id": 7, "cooking_date": NOV_20_MS}


async def test_add_planner_entry_errors(client, mock):
    with pytest.raises(KitchenOwlError):
        await client.add_planner_entry(1, 7, None)  # type: ignore[arg-type]
    with pytest.raises(KitchenOwlError):
        await client.add_planner_entry(1, 7, datetime(2026, 11, 20, 12))  # type: ignore[arg-type]
    mock.post(f"{BASE}/api/household/1/planner/recipe", status=404)
    with pytest.raises(KitchenOwlError):
        await client.add_planner_entry(1, 7, date(2026, 11, 20))
    mock.post(f"{BASE}/api/household/1/planner/recipe", status=401)
    with pytest.raises(KitchenOwlAuthError):
        await client.add_planner_entry(1, 7, date(2026, 11, 20))


async def test_remove_planner_entry_with_and_without_day(client, mock):
    url = f"{BASE}/api/household/1/planner/recipe/7"
    mock.delete(url, payload={"id": 7}, repeat=True)
    await client.remove_planner_entry(1, 7, date(2026, 11, 20))
    _, kwargs = last_request(mock, "DELETE")
    assert kwargs["json"] == {"cooking_date": NOV_20_MS}
    await client.remove_planner_entry(1, 7, None)
    _, kwargs = last_request(mock, "DELETE")
    assert kwargs["json"] == {}


async def test_remove_planner_entry_errors(client, mock):
    with pytest.raises(KitchenOwlError):
        await client.remove_planner_entry(1, 7, "2026-11-20")  # type: ignore[arg-type]
    mock.delete(f"{BASE}/api/household/1/planner/recipe/7", status=404)
    with pytest.raises(KitchenOwlError):
        await client.remove_planner_entry(1, 7, date(2026, 11, 20))
    mock.delete(f"{BASE}/api/household/1/planner/recipe/7", status=403)
    with pytest.raises(KitchenOwlAuthError):
        await client.remove_planner_entry(1, 7, None)


# ---------------------------------------------------------- recipe_to_model


def _stored(**overrides) -> dict:
    data = {
        "id": 12,
        "name": " Käsekuchen ",
        "description": "Cremig und einfach.\n\n1. Teig kneten.\n2. Backen.",
        "source": "https://rezepte.example.com/kuchen",
        "photo": "abc123.jpg",
        "time": 80,
        "prep_time": 20,
        "cook_time": 60,
        "yields": 8,
        "items": [
            {"id": 1, "name": "Mehl", "description": "250g, (Type 405)", "optional": False},
            {"id": 2, "name": "Salz", "description": "", "optional": True},
        ],
        "tags": [{"id": 1, "name": "Backen"}, {"id": 2, "name": "backen"}],
    }
    data.update(overrides)
    return data


def test_recipe_to_model_full():
    recipe = recipe_to_model(_stored())
    assert recipe.source == "kitchenowl"
    assert recipe.id == "12"
    assert recipe.key == "kitchenowl:12"
    assert recipe.url == "https://rezepte.example.com/kuchen"
    assert recipe.title == "Käsekuchen"
    assert recipe.image == "abc123.jpg"
    assert (recipe.servings, recipe.prep_time, recipe.cook_time, recipe.total_time) == (
        8,
        20,
        60,
        80,
    )
    assert recipe.description == "Cremig und einfach."
    assert recipe.steps == ["Teig kneten.", "Backen."]
    assert recipe.tags == ["Backen"]
    assert [(i.name, i.raw) for i in recipe.ingredients] == [
        ("Mehl", "250g, (Type 405) Mehl"),
        ("Salz", "Salz"),
    ]


def test_recipe_to_model_roundtrip_of_eatfresh_recipe():
    original = make_recipe(steps=["Teig kneten.", "Im Ofen backen, bis es duftet."])
    body = {"description": _build_description(original)}
    recipe = recipe_to_model(_stored(**body))
    assert recipe.description == original.description
    assert recipe.steps == original.steps


def test_recipe_to_model_empty_fields():
    recipe = recipe_to_model(
        {"id": 3, "name": "Nur Name", "description": None, "source": None, "photo": None,
         "time": None, "yields": 0, "items": None, "tags": None}
    )
    assert recipe.url == ""
    assert recipe.image is None
    assert recipe.description is None
    assert recipe.steps == []
    assert recipe.ingredients == []
    assert recipe.tags == []
    assert recipe.total_time is None
    assert recipe.servings is None


def test_recipe_to_model_app_text_keeps_paragraphs():
    recipe = recipe_to_model(
        _stored(description="Erst rühren.\nDann kochen.\n\nWarm servieren.")
    )
    assert recipe.description is None
    assert recipe.steps == ["Erst rühren.\nDann kochen.", "Warm servieren."]


def test_recipe_to_model_text_before_steps_and_continuations():
    recipe = recipe_to_model(
        _stored(
            description=(
                "Tipp: vorheizen.\n\nZweiter Absatz.\r\n\r\n"
                "1) Mischen\r\n   und ruhen lassen.\r\n2. Backen.\n\nGuten Appetit!"
            )
        )
    )
    assert recipe.description == "Tipp: vorheizen.\n\nZweiter Absatz."
    assert recipe.steps == ["Mischen und ruhen lassen.", "Backen.", "Guten Appetit!"]


def test_recipe_to_model_does_not_lose_text():
    text = "Zutaten bereitstellen, 3.5 kg Mehl.\n- Punkt A\n- Punkt B"
    recipe = recipe_to_model(_stored(description=text))
    assert recipe.description is None
    assert recipe.steps == [text]


def test_recipe_to_model_needs_id():
    with pytest.raises(KitchenOwlError):
        recipe_to_model({"name": "x"})
    with pytest.raises(KitchenOwlError):
        recipe_to_model({"id": "abc"})


def test_recipe_to_model_ignores_junk_items_and_tags():
    recipe = recipe_to_model(
        _stored(items=["x", {"name": " "}, {"name": "Ei", "description": None}], tags="x")
    )
    assert [i.name for i in recipe.ingredients] == ["Ei"]
    assert recipe.ingredients[0].raw == "Ei"
    assert recipe.tags == []
