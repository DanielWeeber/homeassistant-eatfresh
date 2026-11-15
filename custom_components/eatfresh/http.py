"""Polite HTTP client for recipe sources.

Pure Python plus aiohttp, no Home Assistant imports. The client is handed an
``aiohttp.ClientSession`` and adds:

* at most one request per host at a time,
* a minimum pause between two requests to the same host,
* a total timeout per request,
* a fixed User-Agent,
* a small error model: 403, 429 and captcha pages raise ``SourceBlocked``
  (never retried), 404 and 410 raise ``RecipeNotFound``, everything else
  raises ``SourceError``,
* protection against requests into the local network: every address (also
  every redirect target) must be http(s) and resolve only to public IP
  addresses. Redirects are followed one by one, at most ``MAX_REDIRECTS``,
* a list of blocked hosts (hosts of switched-off sources), checked for the
  first address and for every redirect target.

``open_public_url`` is the single place for this check. The image proxy uses
it as well. Host names are read with ``yarl``, exactly as aiohttp reads them.

The check resolves a name before aiohttp connects, and aiohttp resolves it
again. ``PublicOnlyResolver`` closes that gap (DNS rebinding): a session whose
connector uses it refuses to connect to a name that now resolves to a
non-public address.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping
from contextlib import asynccontextmanager
import ipaddress
import json
import logging
import re
import socket
import time
from typing import Any
from urllib.parse import urljoin

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult
from aiohttp.resolver import ThreadedResolver
from yarl import URL

from .errors import RecipeNotFound, SourceBlocked, SourceError

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15.0
# Recipe pages are parsed in the event loop (html.parser); 3 MB take about
# half a second at most. Real recipe pages are far smaller.
MAX_BYTES = 3 * 1024 * 1024
# Captcha and bot-check pages are short; real recipe pages are long and may
# merely embed a captcha script (comment forms), so only short bodies count.
_CAPTCHA_MAX_BODY = 40_000
_CAPTCHA_RE = re.compile(
    r"just a moment\.\.\.|attention required|g-recaptcha|h-captcha|hcaptcha"
    r"|cf-challenge|cf_chl_|captcha-delivery|verify you are (?:a )?human",
    re.IGNORECASE,
)
_BLOCKED_STATUS = {403, 429}
_NOT_FOUND_STATUS = {404, 410}
_REDIRECT_STATUS = {301, 302, 303, 307, 308}
MAX_REDIRECTS = 3
_DEFAULT_PORTS = {"http": 80, "https": 443}
# IPv6 prefixes that carry an IPv4 address in their last 32 bits (NAT64).
_NAT64_NETWORKS = (
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
)

# Host names made only of numbers (``2130706433``, ``0177.0.0.1``, ``0x7f.1``)
# are read differently by different resolvers; they are never real names.
_NUMERIC_HOST_RE = re.compile(r"^(?:0x[0-9a-f]*|\d+)(?:\.(?:0x[0-9a-f]*|\d+))*$")

type Resolver = Callable[[str, int], Awaitable[list[str]]]
type HostCheck = Callable[[str], None]


class UnsafeAddress(RecipeNotFound):
    """The address is not http(s) or points into a non-public network."""


class HostBlocked(RecipeNotFound):
    """The address belongs to a recipe source that is switched off."""


def split_url(url: str) -> tuple[str, str, int]:
    """Return scheme, host and port of ``url`` as aiohttp sees them.

    The host is the lower-case ASCII form without a trailing dot (empty if
    there is none). Raises ``UnsafeAddress`` for addresses yarl cannot read.
    """
    try:
        parsed = URL(url.strip())
        scheme = (parsed.scheme or "").lower()
        host = (parsed.raw_host or "").lower().rstrip(".")
        port = parsed.port or _DEFAULT_PORTS.get(scheme, 0)
    except (ValueError, TypeError, UnicodeError) as err:
        raise UnsafeAddress("Not a valid web address") from err
    return scheme, host, port


def host_matches(host: str, domains: Iterable[str]) -> bool:
    """Return True if ``host`` is one of ``domains`` or below one of them."""
    host = host.lower().rstrip(".")
    return any(host == item or host.endswith(f".{item}") for item in domains)


def base_domain(host: str) -> str:
    """Return the host without a leading ``www.``."""
    host = host.lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


class PublicOnlyResolver(AbstractResolver):
    """DNS resolver for aiohttp that refuses names with non-public addresses.

    Used in the connector of the session for recipe pages and images, so the
    address aiohttp connects to has passed the same test as
    ``check_public_url``. IP literals do not reach a resolver; the check in
    ``open_public_url`` covers them.
    """

    def __init__(self, inner: AbstractResolver | None = None) -> None:
        """Wrap ``inner`` (default: the threaded getaddrinfo resolver)."""
        self._inner = inner or ThreadedResolver()

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        """Resolve ``host``; raise ``OSError`` unless all addresses are public."""
        results = await self._inner.resolve(host, port, family)
        if not results or not all(is_public_address(item["host"]) for item in results):
            raise OSError(f"{host} resolves to a non-public address")
        return results

    async def close(self) -> None:
        """Close the wrapped resolver."""
        await self._inner.close()


def create_public_session(**connector_args: Any) -> aiohttp.ClientSession:
    """Return a session that only connects to public addresses.

    The caller must close it. ``connector_args`` go to ``TCPConnector``
    (for example ``ssl``).
    """
    connector = aiohttp.TCPConnector(resolver=PublicOnlyResolver(), **connector_args)
    return aiohttp.ClientSession(connector=connector)


async def resolve_host(host: str, port: int) -> list[str]:
    """Return all IP addresses a host name resolves to."""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as err:
        raise SourceError(f"Cannot resolve {host}") from err
    return [str(info[4][0]) for info in infos]


def is_public_address(value: str) -> bool:
    """Return True only for globally reachable unicast addresses.

    Private, loopback, link-local, shared (CGNAT), reserved, documentation,
    multicast and unspecified addresses are not public. IPv6 addresses that
    embed an IPv4 address (mapped, 6to4, Teredo, NAT64) are judged by that
    IPv4 address as well.
    """
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    if address.is_multicast or not address.is_global:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        embedded: list[ipaddress.IPv4Address] = []
        if address.ipv4_mapped is not None:
            embedded.append(address.ipv4_mapped)
        if address.sixtofour is not None:
            embedded.append(address.sixtofour)
        if address.teredo is not None:
            embedded.extend(address.teredo)
        if any(address in network for network in _NAT64_NETWORKS):
            embedded.append(ipaddress.IPv4Address(int(address) & 0xFFFFFFFF))
        return all(is_public_address(str(item)) for item in embedded)
    return True


async def check_public_url(url: str, resolver: Resolver | None = None) -> None:
    """Raise ``UnsafeAddress`` unless ``url`` is http(s) on a public host.

    Host names are resolved and every resulting address must be public.
    """
    scheme, host, port = split_url(url)
    if scheme not in _DEFAULT_PORTS or not host:
        raise UnsafeAddress("Only http and https addresses are supported")
    try:
        ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        if _NUMERIC_HOST_RE.match(host):
            raise UnsafeAddress("Unusual numeric addresses are not allowed") from None
        addresses = await (resolver or resolve_host)(host, port)
    else:
        addresses = [host]
    if not addresses or not all(is_public_address(item) for item in addresses):
        raise UnsafeAddress("Addresses in private networks are not allowed")


@asynccontextmanager
async def open_public_url(
    session: aiohttp.ClientSession,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: aiohttp.ClientTimeout | None = None,
    resolver: Resolver | None = None,
    max_redirects: int = MAX_REDIRECTS,
    check_host: HostCheck | None = None,
) -> AsyncIterator[aiohttp.ClientResponse]:
    """GET a public address and yield the final response.

    Redirects are not left to aiohttp: each target is checked again with
    ``check_host`` (if given, it raises to refuse a host) and
    ``check_public_url``, and at most ``max_redirects`` are followed.
    Raises ``UnsafeAddress``, the error of ``check_host`` or ``SourceError``
    (too many redirects).
    """
    current = url
    for hop in range(max_redirects + 1):
        if check_host is not None:
            check_host(split_url(current)[1])
        await check_public_url(current, resolver)
        response = await session.get(
            current,
            params=params if hop == 0 else None,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
        )
        location = response.headers.get("Location")
        if response.status in _REDIRECT_STATUS and location:
            response.release()
            current = urljoin(str(response.url), location)
            continue
        try:
            yield response
        finally:
            response.release()
        return
    raise SourceError(f"Too many redirects from {_host_of(url)}")


class HttpClient:
    """Rate-limited GET client shared by all recipe sources."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        user_agent: str,
        min_interval: float = 1.5,
        resolver: Resolver | None = None,
        blocked_hosts: Iterable[str] = (),
    ) -> None:
        """Store the session, the User-Agent and the pause between requests.

        ``resolver`` replaces the DNS lookup of the address check (tests).
        ``blocked_hosts`` are domains (and their sub-domains) that are never
        fetched, not even as a redirect target.
        """
        self._session = session
        self._resolver = resolver
        self._blocked = frozenset(base_domain(host) for host in blocked_hosts)
        self._user_agent = user_agent
        self._min_interval = max(0.0, float(min_interval))
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_done: dict[str, float] = {}

    def is_blocked(self, host: str) -> bool:
        """Return True if ``host`` belongs to a blocked domain."""
        return host_matches(host, self._blocked)

    def _check_host(self, host: str) -> None:
        if self.is_blocked(host):
            raise HostBlocked("The source of this address is switched off")

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET ``url`` and return the decoded JSON body."""
        text = await self._request(
            url,
            params,
            accept="application/json, text/plain;q=0.8, */*;q=0.5",
            check_captcha=False,
        )
        try:
            return json.loads(text)
        except ValueError as err:
            if _looks_like_captcha(text):
                raise SourceBlocked(f"{_host_of(url)} asks for a bot check") from err
            raise SourceError(f"Invalid JSON from {_host_of(url)}") from err

    async def get_text(self, url: str, params: dict[str, Any] | None = None) -> str:
        """GET ``url`` and return the body as text."""
        return await self._request(
            url, params, accept="text/html,application/xhtml+xml,*/*;q=0.8"
        )

    async def _request(
        self,
        url: str,
        params: dict[str, Any] | None,
        *,
        accept: str,
        check_captcha: bool = True,
    ) -> str:
        try:
            scheme, host, _port = split_url(url)
        except UnsafeAddress as err:
            raise SourceError("Not a valid web address") from err
        if scheme not in _DEFAULT_PORTS or not host:
            raise SourceError("Only http and https addresses are supported")
        self._check_host(host)
        lock = self._locks.setdefault(host, asyncio.Lock())
        headers = {
            "User-Agent": self._user_agent,
            "Accept": accept,
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
        }
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

        async with lock:
            await self._wait_turn(host)
            try:
                async with open_public_url(
                    self._session,
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                    resolver=self._resolver,
                    check_host=self._check_host,
                ) as response:
                    return await self._read(response, host, check_captcha)
            except (SourceError, asyncio.CancelledError):
                raise
            except TimeoutError as err:
                raise SourceError(f"Timeout while reading {host}") from err
            except aiohttp.ClientError as err:
                raise SourceError(f"Request to {host} failed: {err}") from err
            finally:
                self._last_done[host] = time.monotonic()

    async def _wait_turn(self, host: str) -> None:
        last = self._last_done.get(host)
        if last is None:
            return
        wait = self._min_interval - (time.monotonic() - last)
        if wait > 0:
            await asyncio.sleep(wait)

    async def _read(
        self, response: aiohttp.ClientResponse, host: str, check_captcha: bool
    ) -> str:
        status = response.status
        if status in _BLOCKED_STATUS:
            raise SourceBlocked(f"{host} refused the request (HTTP {status})")
        if response.headers.get("cf-mitigated", "").lower() == "challenge":
            raise SourceBlocked(f"{host} asks for a bot check")
        if status in _NOT_FOUND_STATUS:
            raise RecipeNotFound(f"{host} has no such page (HTTP {status})")

        length = response.content_length
        if length is not None and length > MAX_BYTES:
            raise SourceError(f"Answer of {host} is too large")
        # StreamReader.read(n) returns whatever has arrived so far, so read
        # chunk by chunk until the end of the body.
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.content.iter_chunked(65536):
            size += len(chunk)
            if size > MAX_BYTES:
                raise SourceError(f"Answer of {host} is too large")
            chunks.append(chunk)
        body = b"".join(chunks)
        try:
            text = body.decode(response.charset or "utf-8", errors="replace")
        except LookupError:
            text = body.decode("utf-8", errors="replace")

        if status >= 400:
            if check_captcha and _looks_like_captcha(text):
                raise SourceBlocked(f"{host} asks for a bot check")
            raise SourceError(f"{host} answered with HTTP {status}")
        if check_captcha and _looks_like_captcha(text):
            raise SourceBlocked(f"{host} asks for a bot check")
        return text


def _looks_like_captcha(text: str) -> bool:
    return len(text) < _CAPTCHA_MAX_BODY and _CAPTCHA_RE.search(text) is not None


def _host_of(url: str) -> str:
    try:
        return split_url(url)[1] or "host"
    except UnsafeAddress:
        return "host"
