"""Tests for the pack count suggested for Picnic products."""

from __future__ import annotations

import dataclasses

import pytest

from custom_components.eatfresh import picnic_amount, portions
from custom_components.eatfresh.picnic_amount import (
    MAX_SUGGESTED,
    REST_LIMIT,
    Split,
    fits_rest,
    parse_quantity,
    suggest_amount,
    suggest_split,
)


@pytest.mark.parametrize(
    ("description", "unit_quantity", "expected"),
    [
        # Examples of the contract
        ("500g", "1kg", 1),
        ("1500g", "4 x 250g", 2),
        # Gram and kilogram
        ("1 kg", "500g", 2),
        ("2 kg", "1kg", 2),
        ("750 g", "500 g", 2),
        ("510 g", "500g", 1),  # within 10 percent of a pack
        ("1050 g", "500g", 2),
        ("250 gram", "250 gram", 1),
        ("1,5 kg", "500g", 3),
        ("1.5kg", "500g", 3),
        ("0,5 kg", "1kg", 1),
        # Milliliter and liter
        ("500 ml", "1L", 1),
        ("1,5 l", "500 ml", 3),
        ("2 Liter", "1 l", 2),
        ("1/2 l", "250 ml", 2),
        # Multipacks
        ("1 kg", "4x250g", 1),
        ("2 l", "6 × 0,33 l", 1),  # 1980 ml, within 10 percent
        ("3 l", "6 × 0,33 l", 2),
        # Pieces
        ("6 Stück", "4 Stück", 2),
        ("3", "5 Stück", 1),
        ("8", "4 Stück", 2),
        ("2 Bund", "1 Stück", 2),
        # Text without a number
        ("etwas", "500g", 1),
        ("", "500g", 1),
        ("nach Geschmack", "1kg", 1),
        # Unknown pack size
        ("500 g", "", 1),
        ("500 g", "Packung", 1),
        ("500 g", None, 1),
        (None, "500g", 1),
        # Different kinds of quantity
        ("3 Zwiebeln", "1kg", 1),
        ("500 ml", "500 g", 1),
        ("2 kg", "5 Stück", 1),
        # Text around the quantity
        ("ca. 500 g", "250g", 2),
        ("Kartoffeln 2 kg", "1kg", 2),
    ],
)
def test_suggest_amount(description: str, unit_quantity: str, expected: int) -> None:
    assert suggest_amount(description, unit_quantity) == expected


def test_suggest_amount_has_an_upper_limit() -> None:
    assert suggest_amount("100 kg", "100g") == MAX_SUGGESTED


def test_zero_is_no_quantity() -> None:
    assert parse_quantity("0 g") is None
    assert suggest_amount("0 g", "500 g") == 1
    assert suggest_amount("500 g", "0 g") == 1


def test_parse_quantity_units() -> None:
    assert parse_quantity("1kg") == (1000.0, "mass")
    assert parse_quantity("250 mg") == (0.25, "mass")
    assert parse_quantity("33 cl") == (330.0, "volume")
    assert parse_quantity("4 x 500g") == (2000.0, "mass")
    assert parse_quantity("5 Stück") == (5.0, "count")
    assert parse_quantity("3") == (3.0, "count")
    assert parse_quantity("1/0 l") is None
    assert parse_quantity(42) is None  # type: ignore[arg-type]


# --- 0.5.0: counts of packs, the rest of the last pack ----------------------


def test_package_units_have_one_source() -> None:
    assert picnic_amount.PACKAGE_UNITS is portions.PACKAGE_UNITS
    assert REST_LIMIT == 0.6


@pytest.mark.parametrize(
    ("description", "unit_quantity", "expected"),
    [
        # A count with a package unit and a single pack: the count
        ("2 Dose", "400 g", 2),
        ("2 Dosen", "400 ml", 2),
        ("1 Dose, (400 g)", "400 g", 1),
        ("2 Dose, (400 g)", "800 g", 2),
        ("3 Pck.", "250 g", 3),
        ("2 Packung", "1 kg", 2),
        ("2 Becher", "200 g", 2),
        ("1 Glas", "720 ml", 1),
        ("3 Bund", "ca. 30 g", 3),
        ("2 cans", "400 g", 2),
        ("1.5 Dose", "400 g", 2),
        ("2.1 Dose", "400 g", 2),  # within 10 percent of a pack
        ("2.2 Dose", "400 g", 3),
        ("0.5 Bund", "1 Stück", 1),
        ("30 Dose", "400 g", MAX_SUGGESTED),
        # A multipack: divided by the packs in it, rounded up
        ("2 Dose", "3 x 200 g", 1),
        ("3 Dose", "3 x 200 g", 1),
        ("4 Dose", "3 x 200 g", 2),
        ("6 Flasche", "6 × 0,33 l", 1),
        ("7 Flasche", "6 × 0,33 l", 2),
        # A product counted in pieces is one pack, the pieces do not divide
        ("2 Dose", "4 Stück", 2),
        ("5 Dose", "4 Stück", 5),
        ("2 Bund", "1 Stück", 2),
        # An unknown pack size is a single pack
        ("2 Becher", "", 2),
        ("2 Becher", None, 2),
        ("2 Becher", "Packung", 2),
        # Everything else as before: no package unit, no count
        ("2 EL", "500 ml", 1),
        ("2 Zehe", "1 Stück", 2),
        ("2 Zehe", "100 g", 1),
        ("3 Zwiebeln", "1kg", 1),
        ("Dose", "400 g", 1),
        ("0 Dose", "400 g", 1),
        ("2 Dose", "0 x 200 g", 1),
    ],
)
def test_suggest_amount_counts_packs(
    description: str, unit_quantity: str | None, expected: int
) -> None:
    assert suggest_amount(description, unit_quantity) == expected


@pytest.mark.parametrize(
    ("description", "unit_quantity", "expected"),
    [
        # Examples of the contract
        ("600g", "500 g", Split(2, 0, "100 g")),
        ("1000g", "500 g", Split(2, 0, None)),
        # Weight and volume
        ("700g", "500 g", Split(2, 0, "200 g")),
        ("800g", "500 g", Split(2, 0, "300 g")),  # exactly the limit
        ("810g", "500 g", Split(2, 0, None)),  # more than 60 percent of a pack
        ("510g", "500 g", Split(1, 0, None)),  # within 10 percent, 1 pack
        ("550g", "500 g", Split(1, 0, None)),
        ("560g", "500 g", Split(2, 0, "60 g")),
        ("500g", "500 g", Split(1, 0, None)),
        ("200g", "500 g", Split(1, 0, "200 g")),  # a smaller pack would do
        ("300g", "500 g", Split(1, 0, "300 g")),
        ("400g", "500 g", Split(1, 0, None)),
        ("1.5 l", "1 l", Split(2, 0, "500 ml")),
        ("1,2 kg", "1kg", Split(2, 0, "200 g")),
        ("3 l", "2 l", Split(2, 0, "1 l")),
        ("3 kg", "2 kg", Split(2, 0, "1 kg")),
        ("2.5 l", "2 l", Split(2, 0, "500 ml")),
        ("1133 g", "500 g", Split(3, 0, "135 g")),  # 133 g, rounded smoothly
        ("100 kg", "100g", Split(MAX_SUGGESTED, 0, None)),
        # Multipacks count with all their packs
        ("1500g", "4 x 250g", Split(2, 0, "500 g")),
        ("600g", "4 x 250g", Split(1, 0, "600 g")),
        ("2.5 l", "6 × 0,33 l", Split(2, 0, "520 ml")),
        ("4 Dose", "3 x 200 g", Split(2, 0, "200 g")),
        ("3 Dose", "3 x 200 g", Split(1, 0, None)),
        # Pieces
        ("6 Stück", "4 Stück", Split(2, 0, "2 Stück")),
        ("3", "10 Stück", Split(1, 0, "3 Stück")),
        ("12", "10 Stk.", Split(2, 0, "2 Stk.")),
        ("3", "6er Pack", Split(1, 0, "3")),
        ("8", "10 Stück", Split(1, 0, None)),
        ("2 Bund", "1 Stück", Split(2, 0, None)),
        ("0.5 Bund", "1 Stück", Split(1, 0, None)),  # a pack of one has no rest
        # A count of packs on the list
        ("2 Dose", "400 g", Split(2, 0, None)),
        ("1.5 Dose", "400 ml", Split(2, 0, "200 ml")),
        ("2 Becher", None, Split(2, 0, None)),
        # Cannot be read: as suggest_amount, no rest
        ("etwas", "500 g", Split(1, 0, None)),
        ("", "500 g", Split(1, 0, None)),
        (None, "500 g", Split(1, 0, None)),
        ("500 g", "", Split(1, 0, None)),
        ("500 g", None, Split(1, 0, None)),
        ("500 g", "Packung", Split(1, 0, None)),
        ("500 ml", "500 g", Split(1, 0, None)),
        ("3 Zwiebeln", "1kg", Split(1, 0, None)),
        ("0 g", "500 g", Split(1, 0, None)),
        ("500 g", "0 g", Split(1, 0, None)),
    ],
)
def test_suggest_split(
    description: str | None, unit_quantity: str | None, expected: Split
) -> None:
    assert suggest_split(description, unit_quantity) == expected
    assert expected.amount == suggest_amount(description, unit_quantity)


@pytest.mark.parametrize(
    ("exact_count", "unit_quantity", "expected"),
    [
        # Examples of the contract
        (1.5, "400 ml", Split(2, 0, "200 ml")),
        (0.75, "400 ml", Split(1, 0, None)),
        (0.5, "400 ml", Split(1, 0, "200 ml")),
        (1.6, "400 ml", Split(2, 0, "240 ml")),
        (1.61, "400 ml", Split(2, 0, None)),
        (2.0, "400 ml", Split(2, 0, None)),
        (2.08, "400 ml", Split(2, 0, None)),  # within 10 percent
        (2.25, "400 ml", Split(3, 0, "100 ml")),
        (1.3333, "1 l", Split(2, 0, "330 ml")),
        (2, "400 ml", Split(2, 0, None)),
        (25.5, "400 ml", Split(MAX_SUGGESTED, 0, None)),
        # A multipack: the exact number counts single packs
        (4, "3 x 200 g", Split(2, 0, "200 g")),
        (3.5, "3 x 200 g", Split(2, 0, "100 g")),
        (1.5, "3 x 200 g", Split(1, 0, "300 g")),
        # A product counted in pieces is one pack, the pieces do not divide
        (1.5, "4 Stück", Split(2, 0, "2 Stück")),
        (1.5, "1 Stück", Split(2, 0, None)),
        # Unknown pack size: the packs, but no rest
        (1.5, "", Split(2, 0, None)),
        (1.5, None, Split(2, 0, None)),
        (1.5, "Packung", Split(2, 0, None)),
    ],
)
def test_suggest_split_with_exact_count(
    exact_count: float, unit_quantity: str | None, expected: Split
) -> None:
    assert suggest_split("2 Dose", unit_quantity, exact_count=exact_count) == expected


@pytest.mark.parametrize(
    "exact_count",
    [None, 0, -1.5, float("nan"), float("inf"), "1.5", True, [1.5]],
)
def test_bad_exact_count_is_ignored(exact_count: object) -> None:
    assert suggest_split("2 Dose", "400 ml", exact_count=exact_count) == Split(  # type: ignore[arg-type]
        2, 0, None
    )


def test_exact_count_wins_over_the_text() -> None:
    assert suggest_split("etwas", "400 ml", exact_count=1.5) == Split(2, 0, "200 ml")
    assert suggest_split(None, "400 ml", exact_count=1.5) == Split(2, 0, "200 ml")


@pytest.mark.parametrize(
    ("description", "unit_quantity", "exact_count", "small", "expected"),
    [
        # Examples of the contract
        ("2 Dose", "400 ml", 1.5, "200 ml", Split(1, 1, "200 ml")),
        ("2 Dose", "400 ml", 1.5, None, Split(2, 0, "200 ml")),
        # The small packs cover the rest with less than one main pack
        ("600g", "500 g", None, "100 g", Split(1, 1, "100 g")),
        ("600g", "500 g", None, "250g", Split(1, 1, "100 g")),
        ("700g", "500 g", None, "100 g", Split(1, 2, "200 g")),
        ("800g", "500 g", None, "125 g", Split(1, 3, "300 g")),  # 375 g
        ("710g", "500 g", None, "200 g", Split(1, 1, "210 g")),  # 10 percent
        ("200g", "500 g", None, "250 g", Split(0, 1, "200 g")),
        ("1500g", "4 x 250g", None, "500 g", Split(1, 1, "500 g")),
        ("1500g", "4 x 250g", None, "2 x 250 g", Split(1, 1, "500 g")),
        ("4 Dose", "3 x 200 g", None, "200 g", Split(1, 1, "200 g")),
        ("6 Stück", "10 Stück", None, "6 Stück", Split(0, 1, "6 Stück")),
        ("1.5 l", "1 l", None, "0,5 l", Split(1, 1, "500 ml")),
        ("740g", "500 g", None, "200 g", Split(1, 2, "240 g")),  # 400 g
        ("1500g", "4 x 250g", None, "400 g", Split(1, 2, "500 g")),  # 800 g
        # They would hold as much as a main pack, or more
        ("800g", "500 g", None, "250 g", Split(2, 0, "300 g")),
        ("640 ml", "400 ml", None, "200 ml", Split(2, 0, "240 ml")),
        ("1600g", "4 x 250g", None, "520 g", Split(2, 0, "600 g")),  # 1040 g
        ("1600g", "4 x 250g", None, "400 g", Split(1, 2, "600 g")),  # 800 g
        # Not smaller than the main pack
        ("600g", "500 g", None, "500 g", Split(2, 0, "100 g")),
        ("600g", "500 g", None, "1 kg", Split(2, 0, "100 g")),
        # Another kind, or cannot be read
        ("600g", "500 g", None, "100 ml", Split(2, 0, "100 g")),
        ("600g", "500 g", None, "2 Stück", Split(2, 0, "100 g")),
        ("600g", "500 g", None, "klein", Split(2, 0, "100 g")),
        ("600g", "500 g", None, "", Split(2, 0, "100 g")),
        ("600g", "500 g", None, "0 g", Split(2, 0, "100 g")),
        # Too many small packs
        ("300g", "500 g", None, "10 g", Split(1, 0, "300 g")),
        ("300g", "500 g", None, "15 g", Split(0, 20, "300 g")),
        # No rest: the small pack is not used
        ("1000g", "500 g", None, "100 g", Split(2, 0, None)),
        ("900g", "500 g", None, "100 g", Split(2, 0, None)),
        ("etwas", "500 g", None, "100 g", Split(1, 0, None)),
        ("2 Dose", None, 1.5, "200 ml", Split(2, 0, None)),
    ],
)
def test_suggest_split_with_a_smaller_pack(
    description: str,
    unit_quantity: str | None,
    exact_count: float | None,
    small: str | None,
    expected: Split,
) -> None:
    result = suggest_split(
        description,
        unit_quantity,
        exact_count=exact_count,
        small_unit_quantity=small,
    )
    assert result == expected
    assert result.amount >= 1 or result.small_amount >= 1


def test_split_never_suggests_nothing() -> None:
    """Amounts stay in range, amount 0 only together with a small pack."""
    texts = ["50g", "600g", "1.5 l", "3", "2 Dose", "etwas", "", None, "0.5 Bund"]
    packs = ["500 g", "4 x 250g", "1 l", "10 Stück", "1 Stück", "", None, "0 g"]
    for description in texts:
        for unit_quantity in packs:
            for small in (*packs, "100 g", "200 ml", "2 Stück"):
                for exact in (None, 0.2, 1.5, 7.3, 1e9):
                    result = suggest_split(
                        description,
                        unit_quantity,
                        exact_count=exact,
                        small_unit_quantity=small,
                    )
                    assert 0 <= result.amount <= MAX_SUGGESTED
                    assert 0 <= result.small_amount <= MAX_SUGGESTED
                    assert result.amount + result.small_amount >= 1
                    if result.small_amount:
                        assert result.rest is not None
                    if result.rest is not None:
                        assert parse_quantity(result.rest) is not None
                        assert "e" not in result.rest.split(" ")[0]


def test_split_is_frozen() -> None:
    result = suggest_split("600g", "500 g")
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.amount = 5  # type: ignore[misc]


@pytest.mark.parametrize(
    ("rest", "unit_quantity", "main_unit_quantity", "expected"),
    [
        ("200 ml", "200 ml", "400 ml", True),
        ("200 ml", "250 ml", "400 ml", True),
        ("200 ml", "0,25 l", "400 ml", True),
        ("200 ml", "2 x 100 ml", "400 ml", True),
        ("100 g", "125g", "500 g", True),
        ("500 g", "500 g", "1kg", True),
        ("2 Stück", "4 Stück", "10 Stück", True),
        # Up to 10 percent short still covers the rest
        ("200 ml", "185 ml", "400 ml", True),
        ("220 ml", "200 ml", "400 ml", True),
        ("200 ml", "180 ml", "400 ml", False),
        ("200 ml", "150 ml", "400 ml", False),
        # Not smaller than the main pack
        ("200 ml", "400 ml", "400 ml", False),
        ("200 ml", "500 ml", "400 ml", False),
        ("200 ml", "2 x 200 ml", "400 ml", False),
        # Another kind
        ("200 ml", "200 g", "400 ml", False),
        ("200 ml", "200 ml", "400 g", False),
        ("200 g", "200 ml", "400 ml", False),
        ("2 Stück", "200 g", "400 g", False),
        # Something is missing or cannot be read
        (None, "200 ml", "400 ml", False),
        ("", "200 ml", "400 ml", False),
        ("200 ml", None, "400 ml", False),
        ("200 ml", "klein", "400 ml", False),
        ("200 ml", "200 ml", None, False),
        ("200 ml", "200 ml", "", False),
        ("etwas", "200 ml", "400 ml", False),
        ("200 ml", "0 ml", "400 ml", False),
        (200, "200 ml", "400 ml", False),
    ],
)
def test_fits_rest(
    rest: str | None,
    unit_quantity: str | None,
    main_unit_quantity: str | None,
    expected: bool,
) -> None:
    assert fits_rest(rest, unit_quantity, main_unit_quantity) is expected


def test_rest_of_a_split_fits_the_small_pack_it_used() -> None:
    result = suggest_split(
        "2 Dose", "400 ml", exact_count=1.5, small_unit_quantity="200 ml"
    )
    assert result == Split(1, 1, "200 ml")
    assert fits_rest(result.rest, "200 ml", "400 ml") is True


# --- changes after the independent review of 0.5.0 -------------------------


@pytest.mark.parametrize(
    ("exact_count", "unit_quantity", "expected"),
    [
        # 6: remembered packs against a product counted in pieces
        (1.5, "6 Stück", Split(2, 0, "3 Stück")),
        (1.0, "6 Stück", Split(1, 0, None)),
        (2.0, "6 Stück", Split(2, 0, None)),
        (3.0, "4 Stück", Split(3, 0, None)),
        (0.5, "10 Stück", Split(1, 0, "5 Stück")),
        # Only a multipack divides
        (4, "3 x 200 g", Split(2, 0, "200 g")),
        (6, "6 × 0,33 l", Split(1, 0, None)),
        (7, "6 × 0,33 l", Split(2, 0, "330 ml")),
        (3, "2 x 1 Stück", Split(2, 0, "1 Stück")),
        # Single packs as before
        (1.5, "400 ml", Split(2, 0, "200 ml")),
        (1.5, "", Split(2, 0, None)),
    ],
)
def test_review_exact_count_is_packs_of_the_product(
    exact_count: float, unit_quantity: str, expected: Split
) -> None:
    assert suggest_split("2 Pck.", unit_quantity, exact_count=exact_count) == expected


@pytest.mark.parametrize(
    ("description", "unit_quantity", "expected"),
    [
        # Without remembered packs: a count of packs is packs of the product
        ("2 Dose", "4 Stück", 2),
        ("2 Pck.", "4 Stück", 2),
        ("5 Dose", "4 Stück", 5),
        ("1 Becher", "6 Stück", 1),
        ("3 Dosen", "10 Stück", 3),
        # Only a multipack divides
        ("4 Dose", "3 x 200 g", 2),
        ("2 Dose", "3 x 200 g", 1),
        # Pieces or a bare number against pieces still divide
        ("6 Stück", "4 Stück", 2),
        ("6", "4 Stück", 2),
        ("3", "5 Stück", 1),
    ],
)
def test_review_package_count_is_packs_of_the_product(
    description: str, unit_quantity: str, expected: int
) -> None:
    assert suggest_amount(description, unit_quantity) == expected
    assert suggest_split(description, unit_quantity).amount == expected


@pytest.mark.parametrize(
    ("description", "unit_quantity", "expected"),
    [
        # 3: a dot for thousands
        ("1.000 g", "500 g", 2),
        ("1.250 g", "500 g", 3),
        ("2.000 ml", "1 l", 2),
        ("500 g", "1.000 g", 1),
        # Not thousands
        ("1.125kg", "500 g", 3),  # 1125 g, not 1125 kg
        ("1.5 kg", "500 g", 3),
        ("1,5 l", "500 ml", 3),
        ("0.250 kg", "250 g", 1),
        ("1.500 kg", "1 kg", 2),  # 1.5 kg, nobody needs 1500 kg
        ("1.000 l", "1 l", 1),
    ],
)
def test_review_thousands(description: str, unit_quantity: str, expected: int) -> None:
    assert suggest_amount(description, unit_quantity) == expected


def test_review_thousands_in_parse_quantity() -> None:
    assert parse_quantity("1.000 g") == (1000.0, "mass")
    assert parse_quantity("1.125 g") == (1.125, "mass")
    assert parse_quantity("1.500 kg") == (1500.0, "mass")


def test_review_both_ways_agree() -> None:
    """The list text and the remembered exact count give the same packs."""
    for count in (1, 2, 3, 5):
        for product in ("4 Stück", "6 Stück", "1 Stück", "400 g", "3 x 200 g", ""):
            text = suggest_split(f"{count} Dose", product)
            exact = suggest_split(f"{count} Dose", product, exact_count=float(count))
            assert text == exact, (count, product)
            assert text.amount == suggest_amount(f"{count} Dose", product)
