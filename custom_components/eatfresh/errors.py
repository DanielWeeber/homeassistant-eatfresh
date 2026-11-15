"""Exceptions of EatFresh. Pure Python, no Home Assistant imports."""

from __future__ import annotations


class EatFreshError(Exception):
    """Base class for all EatFresh errors."""


class SourceError(EatFreshError):
    """A recipe source could not deliver (network, format, timeout)."""


class SourceBlocked(SourceError):
    """A recipe source refused the request (403, 429, captcha). Do not retry."""


class RecipeNotFound(SourceError):
    """The page or id holds no recipe."""


class KitchenOwlError(EatFreshError):
    """KitchenOwl could not be reached or answered with an error."""


class KitchenOwlAuthError(KitchenOwlError):
    """KitchenOwl rejected the token (401 or 403)."""
