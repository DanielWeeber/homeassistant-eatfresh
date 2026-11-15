"""Recipe sources of EatFresh. Pure Python, no Home Assistant imports."""

from __future__ import annotations

from collections.abc import Iterable

from ..errors import RecipeNotFound
from ..http import HttpClient, base_domain, host_matches
from .base import RecipeSource
from .chefkoch import ChefkochSource
from .emmi import EmmiSource
from .gaumenfreundin import GaumenfreundinSource
from .jsonld import JsonLdSource
from .kuechengoetter import KuechengoetterSource

# The order is the order in the user interface; ``jsonld`` is always last.
SOURCE_CLASSES: tuple[type[RecipeSource], ...] = (
    GaumenfreundinSource,
    EmmiSource,
    KuechengoetterSource,
    ChefkochSource,
    JsonLdSource,
)

JSONLD_ID = JsonLdSource.id

__all__ = [
    "SOURCE_CLASSES",
    "RecipeSource",
    "blocked_hosts",
    "build_sources",
    "source_for_url",
]


def build_sources(client: HttpClient, enabled: Iterable[str]) -> dict[str, RecipeSource]:
    """Create the enabled sources. ``jsonld`` is always included.

    Unknown ids in ``enabled`` are ignored.
    """
    wanted = set(enabled) | {JSONLD_ID}
    return {cls.id: cls(client) for cls in SOURCE_CLASSES if cls.id in wanted}


def blocked_hosts(
    enabled: Iterable[str],
    classes: Iterable[type[RecipeSource]] | None = None,
) -> frozenset[str]:
    """Return the domains no request may go to, not even by link or redirect.

    These are the hosts of sources that are off by default (they need an
    explicit opt-in, like Chefkoch) and are not enabled. A domain that an
    enabled source also uses stays allowed. ``www.`` is dropped, so the bare
    domain and all its sub-domains are covered.
    """
    wanted = set(enabled)
    classes = tuple(SOURCE_CLASSES if classes is None else classes)
    allowed = {
        host for cls in classes if cls.id in wanted or cls.default_enabled
        for host in cls.hosts
    }
    blocked = {
        base_domain(host)
        for cls in classes
        if cls.id != JSONLD_ID and not cls.default_enabled and cls.id not in wanted
        for host in cls.hosts
    }
    return frozenset(
        domain for domain in blocked if not any(host_matches(host, {domain}) for host in allowed)
    )


def source_for_url(sources: dict[str, RecipeSource], url: str) -> RecipeSource:
    """Pick the source that reads ``url``; fall back to ``jsonld``.

    Raises ``RecipeNotFound`` if the address belongs to a source that is off by
    default and not enabled (Chefkoch), or if there is no fallback.
    """
    for source in sources.values():
        if source.id != JSONLD_ID and source.matches_url(url):
            return source
    for cls in SOURCE_CLASSES:
        if cls.id not in sources and not cls.default_enabled and _matches_class(cls, url):
            raise RecipeNotFound(f"The source {cls.name} is switched off")
    fallback = sources.get(JSONLD_ID)
    if fallback is None:
        raise RecipeNotFound("No source for this address")
    return fallback


def _matches_class(cls: type[RecipeSource], url: str) -> bool:
    # Sources decide on their own which pages they read; ask a throwaway
    # instance that never touches the network.
    return cls(None).matches_url(url)  # type: ignore[arg-type]
