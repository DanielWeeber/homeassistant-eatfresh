"""Tests for the pack count suggested for Picnic products."""

from __future__ import annotations

import pytest

from custom_components.eatfresh.picnic_amount import (
    MAX_SUGGESTED,
    parse_quantity,
    suggest_amount,
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
