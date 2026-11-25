"""EatFresh 0.5.0: a smaller Picnic pack for the rest of the last pack.

The exact pack counts of a transfer to the list are remembered
(``list_exact``), the shopping list proposes a split (``suggest_split``), a
smaller product is remembered per ingredient (``picnic/map_small``), and a
transfer to Picnic puts both products into the cart; "undo" takes both out.
Only the fake Picnic of the tests is used.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import EVENT_HOMEASSISTANT_FINAL_WRITE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.eatfresh.const import STORAGE_KEY
from custom_components.eatfresh.errors import KitchenOwlError
from custom_components.eatfresh.portions import scale_description
from custom_components.eatfresh.store import FavoritesStore, list_count

from .test_picnic import FakeClient, FakePicnic, cart_model, error_object
from .test_websocket_api import WS
from .test_websocket_picnic import no_pause  # noqa: F401  (fixture)

MAIN = {"id": "s4001", "name": "Tomaten gehackt", "unit_quantity": "400 g", "price": 99}
SMALL = {"id": "s2001", "name": "Tomaten klein", "unit_quantity": "200 g", "price": 79}

RECIPE = {
    "id": 11,
    "name": "Soup",
    "yields": 4,
    "items": [
        {"id": 201, "name": "Tomaten", "description": "2 Dosen", "optional": False},
        {"id": 202, "name": "Salz", "description": "1 Prise", "optional": False},
    ],
}


async def _save(hass: HomeAssistant) -> None:
    hass.bus.async_fire(EVENT_HOMEASSISTANT_FINAL_WRITE)
    await hass.async_block_till_done()


@pytest.fixture
def rows(mock_client: MagicMock) -> list[dict[str, Any]]:
    """The shopping list as KitchenOwl has it (change it in a test)."""
    current = [
        {"id": 201, "name": "Tomaten", "description": "2 Dose"},
        {"id": 203, "name": "Milch", "description": "1 l"},
    ]
    mock_client.list_shoppinglist_items = AsyncMock(
        side_effect=lambda list_id: [dict(row) for row in current]
    )
    mock_client.get_recipe = AsyncMock(return_value=RECIPE)
    return current


@pytest.fixture
async def ws(
    init_integration: MockConfigEntry, hass_ws_client, rows: list[dict[str, Any]]
) -> WS:
    helper = WS(await hass_ws_client())
    helper.entry = init_integration  # type: ignore[attr-defined]
    return helper


@pytest.fixture
def fake(hass: HomeAssistant) -> FakePicnic:
    return FakePicnic(hass, FakeClient())


def store_of(ws: WS) -> FavoritesStore:
    return ws.entry.runtime_data.store  # type: ignore[attr-defined]


async def map_both(ws: WS, small: bool = True) -> None:
    msg = await ws.call("eatfresh/picnic/map", name="Tomaten", product=MAIN)
    assert msg["success"], msg
    if small:
        msg = await ws.call("eatfresh/picnic/map_small", name="Tomaten", product=SMALL)
        assert msg["success"], msg


def item_of(result: dict[str, Any], item_id: int) -> dict[str, Any]:
    return next(item for item in result["items"] if item["item_id"] == item_id)


# ----- store ------------------------------------------------------------------


async def test_upgrade_from_0_4_1_keeps_everything(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """A file of 0.4.1 (1.4) keeps all data and gains ``list_exact``."""
    old = {
        "favorites": {},
        "hidden": {"12": "2026-11-02T10:00:00+00:00"},
        "week_lists": {},
        "week_list_done": {},
        "picnic_map": {
            "milch": {
                "product_id": "s1",
                "name": "Milch",
                "unit_quantity": "1 l",
                "price": 119,
                "amount": 2,
            }
        },
        "picnic_skip": ["salz"],
        "picnic_sent": {
            "203": {"product_id": "s1", "amount": 2, "at": "2026-11-24T10:00:00+00:00"}
        },
        "ingredients": {},
        "ingredient_meta": {},
    }
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 4,
        "key": STORAGE_KEY,
        "data": old,
    }
    store = FavoritesStore(hass)
    await store.async_load()
    assert store.picnic_product("Milch")["amount"] == 2
    assert store.picnic_small("Milch") is None
    assert store.picnic_sent(203)["amount"] == 2
    assert "small" not in store.picnic_sent(203)
    assert store.list_exact(201) is None
    store.async_set_picnic_skip("Zucker", True)
    await _save(hass)
    saved = hass_storage[STORAGE_KEY]
    assert saved["minor_version"] == 5
    for key in ("hidden", "picnic_map", "picnic_sent", "ingredients"):
        assert saved["data"][key] == old[key]
    assert saved["data"]["list_exact"] == {}


async def test_new_parts_load_and_broken_parts_drop(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    hass_storage[STORAGE_KEY] = {
        "version": 1,
        "minor_version": 5,
        "key": STORAGE_KEY,
        "data": {
            "picnic_map": {
                "tomaten": {
                    "product_id": "s4001",
                    "name": "Tomaten gehackt",
                    "unit_quantity": "400 g",
                    "price": 99,
                    "amount": None,
                    "small": {
                        "product_id": "s2001",
                        "name": "Tomaten klein",
                        "unit_quantity": "200 g",
                        "price": 79,
                    },
                },
                "mais": {
                    "product_id": "s3",
                    "name": "Mais",
                    "unit_quantity": None,
                    "price": None,
                    "amount": None,
                    "small": {"product_id": "", "name": "x"},
                },
            },
            "picnic_sent": {
                "201": {
                    "product_id": "s4001",
                    "amount": 0,
                    "at": "2026-11-24T10:00:00+00:00",
                    "small": {"product_id": "s2001", "amount": 1},
                },
                # Amount 0 without a smaller product: broken.
                "202": {
                    "product_id": "s1",
                    "amount": 0,
                    "at": "2026-11-24T10:00:00+00:00",
                },
            },
            "list_exact": {
                "201": {
                    "unit": "Dose",
                    "count": 2,
                    "exact": 1.5,
                    "at": "2026-11-24T10:00:00+00:00",
                },
                "202": {
                    "unit": "Dose",
                    "count": 0,
                    "exact": 1.5,
                    "at": "2026-11-24T10:00:00+00:00",
                },
                "203": "nonsense",
                "x": {
                    "unit": "Dose",
                    "count": 2,
                    "exact": 1.5,
                    "at": "2026-11-24T10:00:00+00:00",
                },
            },
        },
    }
    store = FavoritesStore(hass)
    await store.async_load()
    assert store.picnic_small("Tomaten") == {
        "product_id": "s2001",
        "name": "Tomaten klein",
        "unit_quantity": "200 g",
        "price": 79,
    }
    assert store.picnic_small("Mais") is None
    assert store.picnic_product("Mais") is not None
    assert store.picnic_sent(201)["small"] == {"product_id": "s2001", "amount": 1}
    assert store.picnic_sent(202) is None
    assert store.list_exact(201)["exact"] == 1.5
    assert store.list_exact(202) is None
    assert store.list_exact(203) is None


async def test_list_exact_sums_and_drops_other_units(hass: HomeAssistant) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    store.async_add_list_exact(201, [("Dose", 2, 1.5)])
    store.async_add_list_exact(201, [("Dose", 1, 0.75)])
    assert store.list_exact(201)["count"] == 3
    assert store.list_exact(201)["exact"] == 2.25
    # Another unit for the same item: the row goes.
    store.async_add_list_exact(201, [("Glas", 1, 0.75)])
    assert store.list_exact(201) is None
    # Two units in one text: no row.
    store.async_add_list_exact(202, [("Dose", 1, 0.75), ("Glas", 1, 0.75)])
    assert store.list_exact(202) is None
    # Two parts of the same unit are summed.
    store.async_add_list_exact(203, [("Dose", 1, 0.75), ("Dose", 1, 0.5)])
    assert store.list_exact(203)["count"] == 2
    assert store.list_exact(203)["exact"] == 1.25
    assert list_count("2 Dosen, 1 Dose", "Dose") == 3
    assert list_count("400g", "Dose") == 0


async def test_list_exact_prune(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    store = FavoritesStore(hass)
    await store.async_load()
    store.async_add_list_exact(201, [("Dose", 2, 1.5)])
    store.async_add_list_exact(202, [("Dose", 2, 1.5)])
    store.async_add_list_exact(203, [("Dose", 2, 1.5)])
    store.async_prune_list_exact(
        [
            {"id": 201, "name": "Tomaten", "description": "2 Dose"},
            # Changed by hand: 3 instead of 2.
            {"id": 202, "name": "Mais", "description": "3 Dose"},
        ]
    )
    assert store.list_exact(201) is not None
    assert store.list_exact(202) is None  # count does not fit
    assert store.list_exact(203) is None  # not on the list
    freezer.tick(timedelta(days=14, minutes=1))
    assert store.valid_list_exact(201, "2 Dose") is None
    assert store.list_exact(201) is None


# ----- transfer to the list -----------------------------------------------------


async def test_transfer_remembers_exact_counts(
    hass: HomeAssistant, ws: WS, mock_client: MagicMock, rows: list[dict[str, Any]]
) -> None:
    """4 to 3 servings: "2 Dosen" stays 2 cans on the list, 1.5 exactly."""
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11], servings=3)
    assert msg["success"], msg
    # One read of the list before the transfer, and (0.5.0, shopping) one
    # more by the category writes in the background after it.
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_client.list_shoppinglist_items.await_count == 2
    row = store_of(ws).list_exact(201)
    assert row is not None
    assert (row["unit"], row["count"], row["exact"]) == ("Dose", 2, 1.5)
    assert store_of(ws).list_exact(202) is None  # a pinch is no pack

    msg = await ws.call("eatfresh/shopping")
    tomatoes = item_of(msg["result"], 201)
    assert tomatoes["exact"] == "1.5"
    assert tomatoes["rest"] is None  # no product yet
    assert item_of(msg["result"], 203)["exact"] is None


async def test_failed_read_clears_and_transfer_goes_on(
    ws: WS, mock_client: MagicMock
) -> None:
    store_of(ws).async_add_list_exact(301, [("Dose", 1, 0.5)])
    mock_client.list_shoppinglist_items.side_effect = KitchenOwlError("down")
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11], servings=3)
    assert msg["success"], msg
    assert mock_client.add_recipe_to_shoppinglist.await_count == 1
    assert store_of(ws).list_exact(301) is None
    # Filled again from this transfer.
    assert store_of(ws).list_exact(201)["exact"] == 1.5


async def test_read_before_transfer_drops_gone_items(ws: WS) -> None:
    store_of(ws).async_add_list_exact(999, [("Dose", 1, 0.5)])
    msg = await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11], servings=3)
    assert msg["success"], msg
    assert store_of(ws).list_exact(999) is None


async def test_list_changed_by_hand_gives_no_proposal(
    ws: WS, rows: list[dict[str, Any]]
) -> None:
    await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11], servings=3)
    await map_both(ws)
    rows[0]["description"] = "3 Dose"
    msg = await ws.call("eatfresh/shopping")
    tomatoes = item_of(msg["result"], 201)
    assert tomatoes["exact"] is None
    assert tomatoes["small_amount"] == 0
    assert store_of(ws).list_exact(201) is None


# ----- shopping view --------------------------------------------------------------


async def test_shopping_proposes_the_smaller_pack(ws: WS) -> None:
    await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11], servings=3)
    await map_both(ws, small=False)
    tomatoes = item_of((await ws.call("eatfresh/shopping"))["result"], 201)
    assert tomatoes["amount"] == 2
    assert tomatoes["rest"] == "200 g"
    assert tomatoes["small"] is None
    assert tomatoes["small_amount"] == 0

    msg = await ws.call("eatfresh/picnic/map_small", name="Tomaten", product=SMALL)
    assert msg["success"]
    tomatoes = item_of((await ws.call("eatfresh/shopping"))["result"], 201)
    assert tomatoes["amount"] == 1
    assert tomatoes["small_amount"] == 1
    assert tomatoes["rest"] == "200 g"
    assert tomatoes["small"] == SMALL
    assert tomatoes["product"] == MAIN


async def test_fixed_amount_wins_over_the_split(ws: WS) -> None:
    await ws.call("eatfresh/shopping_list/add", kitchenowl_ids=[11], servings=3)
    msg = await ws.call("eatfresh/picnic/map", name="Tomaten", product=MAIN, amount=3)
    assert msg["success"]
    await ws.call("eatfresh/picnic/map_small", name="Tomaten", product=SMALL)
    tomatoes = item_of((await ws.call("eatfresh/shopping"))["result"], 201)
    assert tomatoes["amount"] == 3
    # A remembered fixed count: no proposal for the rest (changed after the
    # review: it said "200 g" here before).
    assert tomatoes["small_amount"] == 0
    assert tomatoes["rest"] is None
    assert tomatoes["small"] == SMALL


async def test_map_small(ws: WS) -> None:
    msg = await ws.call("eatfresh/picnic/map_small", name="Tomaten", product=SMALL)
    assert msg["error"]["code"] == "not_found"
    await map_both(ws)
    # A new main product keeps the smaller one.
    other = {**MAIN, "id": "s4002"}
    await ws.call("eatfresh/picnic/map", name="Tomaten", product=other)
    assert store_of(ws).picnic_small("Tomaten")["product_id"] == "s2001"
    msg = await ws.call("eatfresh/picnic/map_small", name="Tomaten", product=None)
    assert msg["success"]
    assert store_of(ws).picnic_small("Tomaten") is None
    await ws.call("eatfresh/picnic/map_small", name="tomaten ", product=SMALL)
    await ws.call("eatfresh/picnic/unmap", name="Tomaten")
    assert store_of(ws).picnic_small("Tomaten") is None


# ----- search -------------------------------------------------------------------


async def test_search_marks_hits_for_the_rest(ws: WS, fake: FakePicnic) -> None:
    msg = await ws.call(
        "eatfresh/picnic/search", query="Milch", rest="1 kg", main_unit_quantity="5kg"
    )
    assert msg["success"], msg
    hits = msg["result"]["products"]
    assert hits and all("fits_rest" in hit for hit in hits)
    msg = await ws.call("eatfresh/picnic/search", query="Milch", rest="x" * 31)
    assert msg["error"]["code"] == "invalid_format"


async def test_search_fits_rest_values(ws: WS, fake: FakePicnic) -> None:
    from .test_picnic import new_result  # noqa: PLC0415

    fake.client.result = new_result(
        {"id": "a", "name": "Klein", "unit_quantity": "250 g", "display_price": 1},
        {"id": "b", "name": "Groß", "unit_quantity": "500 g", "display_price": 1},
    )
    msg = await ws.call(
        "eatfresh/picnic/search",
        query="Tomaten",
        rest="200 g",
        main_unit_quantity="400 g",
    )
    assert [hit["fits_rest"] for hit in msg["result"]["products"]] == [True, False]
    msg = await ws.call("eatfresh/picnic/search", query="Tomaten")
    assert [hit["fits_rest"] for hit in msg["result"]["products"]] == [False, False]


# ----- send ---------------------------------------------------------------------


def send(
    item_id: int,
    amount: int,
    small_amount: int | None = None,
    product_id: str = MAIN["id"],
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "item_id": item_id,
        "product_id": product_id,
        "amount": amount,
    }
    if small_amount is not None:
        item["small_amount"] = small_amount
    return item


async def test_send_puts_both_products_in(ws: WS, fake: FakePicnic) -> None:
    await map_both(ws)
    msg = await ws.call("eatfresh/picnic/send", items=[send(201, 1, 1)])
    assert msg["success"], msg
    assert msg["result"] == {
        "sent": [
            {"item_id": 201, "product_id": "s4001", "amount": 1, "small_amount": 1}
        ],
        "failed": [],
    }
    assert fake.added == [("s4001", 1), ("s2001", 1)]
    mark = store_of(ws).picnic_sent(201)
    assert mark["small"]["product_id"] == "s2001"
    assert mark["small"]["amount"] == 1
    assert not mark.get("uncertain")
    # The list shows what is in the cart, not the proposal.
    tomatoes = item_of((await ws.call("eatfresh/shopping"))["result"], 201)
    assert (tomatoes["amount"], tomatoes["small_amount"]) == (1, 1)
    assert tomatoes["small"] == SMALL
    assert tomatoes["sent_at"] is not None
    fake.refresh.assert_awaited_once()


async def test_small_product_comes_from_the_store(ws: WS, fake: FakePicnic) -> None:
    await map_both(ws)
    # Only small_amount comes from the panel; the product is the remembered one.
    msg = await ws.call("eatfresh/picnic/send", items=[send(201, 0, 2)])
    assert msg["result"]["sent"] == [
        {"item_id": 201, "product_id": "s4001", "amount": 0, "small_amount": 2}
    ]
    assert fake.added == [("s2001", 2)]
    tomatoes = item_of((await ws.call("eatfresh/shopping"))["result"], 201)
    assert (tomatoes["amount"], tomatoes["small_amount"]) == (0, 2)


async def test_small_amount_without_small_product(ws: WS, fake: FakePicnic) -> None:
    await map_both(ws, small=False)
    msg = await ws.call(
        "eatfresh/picnic/send", items=[send(201, 0, 1), send(203, 1, 1, "s9")]
    )
    result = msg["result"]
    # Only a smaller product asked for, none remembered: nothing goes in.
    assert result["failed"][0]["item_id"] == 201
    assert result["failed"][0]["code"] == "error"
    # With a main product the smaller pieces are ignored.
    assert result["sent"] == [
        {"item_id": 203, "product_id": "s9", "amount": 1, "small_amount": 0}
    ]
    assert fake.added == [("s9", 1)]


async def test_small_fails_after_main(ws: WS, fake: FakePicnic) -> None:
    """Main in, small not: sent (small_amount 0) and failed; the run stops."""
    await map_both(ws)
    fake.client.unknown = {"s2001"}
    msg = await ws.call(
        "eatfresh/picnic/send", items=[send(201, 1, 1), send(203, 1, None, "s9")]
    )
    result = msg["result"]
    assert result["sent"] == [
        {"item_id": 201, "product_id": "s4001", "amount": 1, "small_amount": 0}
    ]
    assert [(f["item_id"], f["code"]) for f in result["failed"]] == [
        (201, "not_added"),
        (203, "not_tried"),
    ]
    assert fake.added == [("s4001", 1), ("s2001", 1)]
    mark = store_of(ws).picnic_sent(201)
    assert mark["amount"] == 1
    assert "small" not in mark
    assert not mark.get("uncertain")
    fake.refresh.assert_not_awaited()


async def test_small_unclear_after_main(ws: WS, fake: FakePicnic) -> None:
    await map_both(ws)
    fake.client.add_errors = {2: RuntimeError("odd")}
    msg = await ws.call("eatfresh/picnic/send", items=[send(201, 1, 1)])
    result = msg["result"]
    assert result["sent"][0]["small_amount"] == 0
    assert result["failed"][0]["code"] == "maybe_sent"
    mark = store_of(ws).picnic_sent(201)
    assert mark["uncertain"] is True
    assert mark["small"]["amount"] == 1
    # Never taken out while unclear.
    msg = await ws.call("eatfresh/picnic/undo", item_id=201)
    assert msg["error"]["code"] == "picnic_error"
    assert fake.client.removed == []


async def test_only_small_fails(ws: WS, fake: FakePicnic) -> None:
    await map_both(ws)
    fake.client.unknown = {"s2001"}
    msg = await ws.call("eatfresh/picnic/send", items=[send(201, 0, 1)])
    assert msg["result"]["sent"] == []
    assert msg["result"]["failed"][0]["code"] == "not_added"
    assert store_of(ws).picnic_sent(201) is None


async def test_main_fails_small_not_tried(ws: WS, fake: FakePicnic) -> None:
    await map_both(ws)
    fake.client.unknown = {"s4001"}
    msg = await ws.call("eatfresh/picnic/send", items=[send(201, 1, 1)])
    assert msg["result"]["sent"] == []
    assert msg["result"]["failed"][0]["code"] == "not_added"
    assert fake.added == [("s4001", 1)]
    assert store_of(ws).picnic_sent(201) is None


@pytest.mark.parametrize(
    "item",
    [
        {"item_id": 201, "product_id": "s1", "amount": 0},
        {"item_id": 201, "product_id": "s1", "amount": 0, "small_amount": 0},
        {"item_id": 201, "product_id": "s1", "amount": 1, "small_amount": 21},
        {"item_id": 201, "product_id": "s1", "amount": 21},
        {"item_id": 201, "product_id": "s1", "amount": 1, "small_amount": -1},
    ],
)
async def test_send_validation(ws: WS, fake: FakePicnic, item: dict[str, Any]) -> None:
    msg = await ws.call("eatfresh/picnic/send", items=[item])
    assert msg["error"]["code"] == "invalid_format"
    assert fake.client.starts == []


# ----- undo ---------------------------------------------------------------------


async def test_undo_takes_both_out(ws: WS, fake: FakePicnic) -> None:
    await map_both(ws)
    await ws.call("eatfresh/picnic/send", items=[send(201, 2, 1)])
    msg = await ws.call("eatfresh/picnic/undo", item_id=201)
    assert msg["success"], msg
    assert fake.client.removed == [("s4001", 2), ("s2001", 1)]
    assert fake.client.cart == {}
    assert store_of(ws).picnic_sent(201) is None


async def test_undo_only_small(ws: WS, fake: FakePicnic) -> None:
    await map_both(ws)
    await ws.call("eatfresh/picnic/send", items=[send(201, 0, 1)])
    msg = await ws.call("eatfresh/picnic/undo", item_id=201)
    assert msg["success"], msg
    assert fake.client.removed == [("s2001", 1)]


async def test_undo_second_refused_main_not_twice(ws: WS, fake: FakePicnic) -> None:
    """Picnic refuses taking out the smaller one: a second undo takes only it."""
    await map_both(ws)
    await ws.call("eatfresh/picnic/send", items=[send(201, 1, 1)])
    client = fake.client
    real_remove = client.remove_product

    def remove(product_id: str, count: int = 1) -> Any:
        if product_id == "s2001" and len(client.removed) < 2:
            client.removed.append((product_id, count))
            return cart_model(error_object())
        return real_remove(product_id, count)

    client.remove_product = remove  # type: ignore[method-assign]
    msg = await ws.call("eatfresh/picnic/undo", item_id=201)
    assert not msg["success"]
    mark = store_of(ws).picnic_sent(201)
    assert mark["amount"] == 0
    assert mark["small"]["amount"] == 1
    assert not mark.get("uncertain")
    msg = await ws.call("eatfresh/picnic/undo", item_id=201)
    assert msg["success"], msg
    assert client.removed == [("s4001", 1), ("s2001", 1), ("s2001", 1)]
    assert client.cart == {}
    assert store_of(ws).picnic_sent(201) is None


async def test_undo_second_unclear(ws: WS, fake: FakePicnic) -> None:
    """Unclear answer for the smaller one: "maybe", and nothing goes out again."""
    await map_both(ws)
    await ws.call("eatfresh/picnic/send", items=[send(201, 1, 1)])
    client = fake.client
    real_remove = client.remove_product

    def remove(product_id: str, count: int = 1) -> Any:
        if product_id == "s2001":
            client.removed.append((product_id, count))
            return client._cart()  # unchanged: not clear it is out
        return real_remove(product_id, count)

    client.remove_product = remove  # type: ignore[method-assign]
    msg = await ws.call("eatfresh/picnic/undo", item_id=201)
    assert not msg["success"]
    mark = store_of(ws).picnic_sent(201)
    assert mark["uncertain"] is True
    assert mark["amount"] == 0
    msg = await ws.call("eatfresh/picnic/undo", item_id=201)
    assert msg["error"]["code"] == "picnic_error"
    assert client.removed == [("s4001", 1), ("s2001", 1)]
    # "Is not in the cart" clears the mark without a call.
    msg = await ws.call("eatfresh/picnic/undo", item_id=201, remove=False)
    assert msg["success"]
    assert store_of(ws).picnic_sent(201) is None


# ----- after the review (0.5.0) -----------------------------------------------------


async def test_exact_only_when_the_list_says_another_number(
    ws: WS, rows: list[dict[str, Any]]
) -> None:
    """ "1.5 Dose" on the list needs no "calculated 1.5" (numbers compared)."""
    store = store_of(ws)
    store.async_add_list_exact(201, list_count_parts("1.5 Dose"))
    rows[0]["description"] = "1.5 Dose"
    tomatoes = item_of((await ws.call("eatfresh/shopping"))["result"], 201)
    assert store.list_exact(201) is not None  # the row is valid
    assert tomatoes["exact"] is None
    # "2 Dose" on the list, 1.5 exactly: the hint stays.
    store.async_remove_list_exact(201)
    store.async_add_list_exact(201, [("Dose", 2, 1.5)])
    rows[0]["description"] = "2 Dose"
    tomatoes = item_of((await ws.call("eatfresh/shopping"))["result"], 201)
    assert tomatoes["exact"] == "1.5"


def list_count_parts(text: str) -> list[tuple[str, int, float]]:
    """The packs of a text as a transfer at factor 1 remembers them."""
    return list(scale_description(text, None, None).packages)


async def test_send_remembers_the_amount_text(
    ws: WS, fake: FakePicnic, rows: list[dict[str, Any]]
) -> None:
    await map_both(ws)
    msg = await ws.call("eatfresh/picnic/send", items=[send(201, 1, 1)])
    assert msg["result"]["sent"], msg
    assert store_of(ws).picnic_sent(201)["description"] == "2 Dose"
    # A second send of the same, unchanged entry is refused.
    msg = await ws.call("eatfresh/picnic/send", items=[send(201, 1)])
    assert msg["result"]["failed"][0]["code"] == "already_sent"


async def test_grown_entry_is_open_and_can_go_again(
    ws: WS, fake: FakePicnic, rows: list[dict[str, Any]]
) -> None:
    await map_both(ws, small=False)
    await ws.call("eatfresh/picnic/send", items=[send(201, 1)])
    rows[0]["description"] = "3 Dose"  # a later transfer added a can
    tomatoes = item_of((await ws.call("eatfresh/shopping"))["result"], 201)
    assert tomatoes["sent_at"] is None
    assert tomatoes["sent_uncertain"] is False
    assert tomatoes["cart_hint"] == "2 Dose"
    assert tomatoes["amount"] == 3  # the proposal, not the cart
    # Nothing goes in: the old mark (and the hint) stays.
    fake.client.unknown = {"s4001"}
    msg = await ws.call("eatfresh/picnic/send", items=[send(201, 1)])
    assert msg["result"]["failed"][0]["code"] == "not_added"
    assert store_of(ws).picnic_sent(201)["description"] == "2 Dose"
    # Sent again: a new mark with the new amount text.
    fake.client.unknown = set()
    msg = await ws.call("eatfresh/picnic/send", items=[send(201, 1)])
    assert msg["result"]["sent"], msg
    mark = store_of(ws).picnic_sent(201)
    assert (mark["description"], mark["amount"]) == ("3 Dose", 1)
    tomatoes = item_of((await ws.call("eatfresh/shopping"))["result"], 201)
    assert tomatoes["sent_at"] is not None
    assert tomatoes["cart_hint"] is None


async def test_undo_keeps_the_amount_text(ws: WS, fake: FakePicnic) -> None:
    """Shortened and unclear marks of "undo" keep the amount text sent."""
    await map_both(ws)
    await ws.call("eatfresh/picnic/send", items=[send(201, 1, 1)])
    client = fake.client
    real_remove = client.remove_product

    def remove(product_id: str, count: int = 1) -> Any:
        if product_id == "s2001":
            client.removed.append((product_id, count))
            return client._cart()  # unchanged: not clear it is out
        return real_remove(product_id, count)

    client.remove_product = remove  # type: ignore[method-assign]
    msg = await ws.call("eatfresh/picnic/undo", item_id=201)
    assert not msg["success"]
    mark = store_of(ws).picnic_sent(201)
    assert (mark["amount"], mark["uncertain"]) == (0, True)
    assert mark["description"] == "2 Dose"
