"""Tests for the polite HTTP client."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator

import aiohttp
import pytest
from aioresponses import CallbackResult, aioresponses

from custom_components.eatfresh.errors import RecipeNotFound, SourceBlocked, SourceError
from custom_components.eatfresh.http import (
    MAX_BYTES,
    HostBlocked,
    HttpClient,
    PublicOnlyResolver,
    UnsafeAddress,
    check_public_url,
    create_public_session,
    is_public_address,
    open_public_url,
)

URL = "https://recipes.example.com/api"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations() -> None:
    """These tests need no Home Assistant instance."""


@pytest.fixture(autouse=True)
def setup_dependencies() -> None:
    """These tests need no Home Assistant instance."""


@pytest.fixture
async def session() -> AsyncIterator[aiohttp.ClientSession]:
    async with aiohttp.ClientSession() as client_session:
        yield client_session


@pytest.fixture
def client(session: aiohttp.ClientSession) -> HttpClient:
    return HttpClient(session, "EatFresh-Test/0.1", min_interval=0)


def _last_call(mock: aioresponses):
    return list(mock.requests.values())[-1][-1]


async def test_get_json(client: HttpClient, mock: aioresponses) -> None:
    mock.get(URL, payload={"a": [1, 2]})
    assert await client.get_json(URL) == {"a": [1, 2]}


async def test_get_json_with_wrong_content_type(client: HttpClient, mock: aioresponses) -> None:
    mock.get(URL, body='{"a": 1}', content_type="text/html")
    assert await client.get_json(URL) == {"a": 1}


async def test_get_text(client: HttpClient, mock: aioresponses) -> None:
    mock.get(URL, body="<html>Grüße</html>")
    assert await client.get_text(URL) == "<html>Grüße</html>"


async def test_params_and_headers_are_sent(client: HttpClient, mock: aioresponses) -> None:
    mock.get(re.compile(r"^https://recipes\.example\.com/api\?.*$"), payload=[])
    await client.get_json(URL, {"search": "Suppe", "per_page": 5})
    call = _last_call(mock)
    assert call.kwargs["params"] == {"search": "Suppe", "per_page": 5}
    assert call.kwargs["headers"]["User-Agent"] == "EatFresh-Test/0.1"
    assert "application/json" in call.kwargs["headers"]["Accept"]
    assert call.kwargs["timeout"].total == 15


async def test_utf8_without_charset(client: HttpClient, mock: aioresponses) -> None:
    mock.get(URL, body="Käse".encode(), content_type="text/html")
    assert await client.get_text(URL) == "Käse"


@pytest.mark.parametrize("status", [403, 429])
async def test_blocked_status(client: HttpClient, mock: aioresponses, status: int) -> None:
    mock.get(URL, status=status, body="no")
    with pytest.raises(SourceBlocked):
        await client.get_text(URL)
    # No retry.
    assert sum(len(calls) for calls in mock.requests.values()) == 1


async def test_blocked_by_cloudflare_header(client: HttpClient, mock: aioresponses) -> None:
    mock.get(URL, status=200, body="x" * 100, headers={"cf-mitigated": "challenge"})
    with pytest.raises(SourceBlocked):
        await client.get_text(URL)


@pytest.mark.parametrize("status", [200, 503])
async def test_captcha_page(client: HttpClient, mock: aioresponses, status: int) -> None:
    mock.get(URL, status=status, body="<title>Just a moment...</title><div class='cf-challenge'>")
    with pytest.raises(SourceBlocked):
        await client.get_text(URL)


async def test_long_page_with_captcha_script_is_fine(client: HttpClient, mock: aioresponses) -> None:
    page = "<script src='https://www.google.com/recaptcha/g-recaptcha.js'></script>" + "a" * 50_000
    mock.get(URL, body=page)
    assert (await client.get_text(URL)).endswith("a")


async def test_json_with_captcha_word_is_fine(client: HttpClient, mock: aioresponses) -> None:
    mock.get(URL, payload={"text": "hcaptcha"})
    assert await client.get_json(URL) == {"text": "hcaptcha"}


async def test_captcha_html_for_json_request(client: HttpClient, mock: aioresponses) -> None:
    mock.get(URL, body="<html><title>Just a moment...</title></html>")
    with pytest.raises(SourceBlocked):
        await client.get_json(URL)


@pytest.mark.parametrize("status", [404, 410])
async def test_not_found(client: HttpClient, mock: aioresponses, status: int) -> None:
    mock.get(URL, status=status)
    with pytest.raises(RecipeNotFound):
        await client.get_text(URL)


@pytest.mark.parametrize("status", [400, 500, 502, 503])
async def test_other_errors(client: HttpClient, mock: aioresponses, status: int) -> None:
    mock.get(URL, status=status, body="oops")
    with pytest.raises(SourceError) as info:
        await client.get_text(URL)
    assert not isinstance(info.value, (SourceBlocked, RecipeNotFound))


async def test_invalid_json(client: HttpClient, mock: aioresponses) -> None:
    mock.get(URL, body="<html>kein json</html>")
    with pytest.raises(SourceError):
        await client.get_json(URL)


async def test_network_error(client: HttpClient, mock: aioresponses) -> None:
    mock.get(URL, exception=aiohttp.ClientConnectionError("down"))
    with pytest.raises(SourceError):
        await client.get_text(URL)


async def test_timeout(client: HttpClient, mock: aioresponses) -> None:
    mock.get(URL, exception=asyncio.TimeoutError())
    with pytest.raises(SourceError, match="Timeout"):
        await client.get_text(URL)


async def test_too_large_answer(
    client: HttpClient, mock: aioresponses, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("custom_components.eatfresh.http.MAX_BYTES", 1000)
    mock.get(URL, body="x" * 2000)
    with pytest.raises(SourceError, match="too large"):
        await client.get_text(URL)


@pytest.mark.parametrize("url", ["ftp://example.com/a", "file:///etc/passwd", "/relative", ""])
async def test_only_http_urls(client: HttpClient, mock: aioresponses, url: str) -> None:
    with pytest.raises(SourceError):
        await client.get_text(url)
    assert not mock.requests


async def test_minimum_interval_per_host(session: aiohttp.ClientSession, mock: aioresponses) -> None:
    client = HttpClient(session, "EatFresh-Test/0.1", min_interval=0.3)
    starts: list[float] = []

    def record(url, **kwargs) -> CallbackResult:
        starts.append(time.monotonic())
        return CallbackResult(body="ok")

    mock.get(URL, callback=record, repeat=True)
    await client.get_text(URL)
    await client.get_text(URL)
    assert starts[1] - starts[0] >= 0.28


async def test_one_request_at_a_time_per_host(session: aiohttp.ClientSession, mock: aioresponses) -> None:
    client = HttpClient(session, "EatFresh-Test/0.1", min_interval=0.2)
    starts: list[float] = []

    def record(url, **kwargs) -> CallbackResult:
        starts.append(time.monotonic())
        return CallbackResult(body="ok")

    mock.get(URL, callback=record, repeat=True)
    await asyncio.gather(*(client.get_text(URL) for _ in range(3)))
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert len(starts) == 3
    assert all(gap >= 0.18 for gap in gaps)


async def test_other_hosts_do_not_wait(session: aiohttp.ClientSession, mock: aioresponses) -> None:
    client = HttpClient(session, "EatFresh-Test/0.1", min_interval=1.0)
    mock.get("https://a.example.com/x", body="a")
    mock.get("https://b.example.com/x", body="b")
    started = time.monotonic()
    await asyncio.gather(client.get_text("https://a.example.com/x"), client.get_text("https://b.example.com/x"))
    assert time.monotonic() - started < 0.5


async def test_interval_also_after_an_error(session: aiohttp.ClientSession, mock: aioresponses) -> None:
    client = HttpClient(session, "EatFresh-Test/0.1", min_interval=0.3)
    mock.get(URL, status=500)
    mock.get(URL, body="ok")
    with pytest.raises(SourceError):
        await client.get_text(URL)
    started = time.monotonic()
    await client.get_text(URL)
    assert time.monotonic() - started >= 0.25


# ----- protection against requests into private networks ------------------


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.5.5",
        "172.31.255.254",
        "169.254.10.20",
        "100.64.0.1",
        "0.0.0.0",
        "192.0.2.10",
        "198.51.100.7",
        "203.0.113.9",
        "224.0.0.1",
        "255.255.255.255",
        "::1",
        "::",
        "fe80::1",
        "fe80::1%eth0",
        "fc00::1",
        "fd12:3456::1",
        "ff02::1",
        "2001:db8::1",
        "::ffff:10.0.0.1",
        "::ffff:127.0.0.1",
        "2002:0a00:0001::1",
        "64:ff9b::a00:1",
        "not-an-ip",
    ],
)
def test_non_public_addresses(address: str) -> None:
    assert not is_public_address(address)


@pytest.mark.parametrize(
    "address", ["93.184.215.14", "2606:4700:4700::1111", "::ffff:93.184.215.14"]
)
def test_public_addresses(address: str) -> None:
    assert is_public_address(address)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/x",
        "http://127.0.0.1:8123/x",
        "http://10.0.0.1/x",
        "http://172.16.5.5/x",
        "http://[::1]/x",
        "http://[fd00::5]/x",
        "http://169.254.169.254/latest/meta-data",
        "http://2130706433/x",
        "http://0177.0.0.1/x",
        "http://0x7f.1/x",
        "http://127.1/x",
        "ftp://recipes.example.com/x",
        "file:///etc/passwd",
        "not a url",
        "http://recipes.example.com:99999/x",
    ],
)
async def test_check_refuses(url: str, fake_dns: dict[str, list[str]]) -> None:
    fake_dns["localhost"] = ["127.0.0.1", "::1"]
    with pytest.raises(UnsafeAddress):
        await check_public_url(url)


async def test_check_refuses_name_with_one_private_address(
    fake_dns: dict[str, list[str]],
) -> None:
    fake_dns["mixed.example.com"] = ["93.184.215.14", "10.9.8.7"]
    with pytest.raises(UnsafeAddress):
        await check_public_url("https://mixed.example.com/rezept")


async def test_check_refuses_name_without_addresses(
    fake_dns: dict[str, list[str]],
) -> None:
    fake_dns["empty.example.com"] = []
    with pytest.raises(UnsafeAddress):
        await check_public_url("https://empty.example.com/rezept")


async def test_check_accepts_public(fake_dns: dict[str, list[str]]) -> None:
    fake_dns["v6.example.com"] = ["2606:4700:4700::1111"]
    await check_public_url("https://recipes.example.com/rezept")
    await check_public_url("https://v6.example.com/rezept")
    await check_public_url("http://93.184.215.14/rezept")


async def test_check_uses_given_resolver() -> None:
    seen: list[tuple[str, int]] = []

    async def resolver(host: str, port: int) -> list[str]:
        seen.append((host, port))
        return ["10.77.0.1"]

    with pytest.raises(UnsafeAddress):
        await check_public_url("https://recipes.example.com/x", resolver)
    assert seen == [("recipes.example.com", 443)]


async def test_private_name_makes_no_request(
    client: HttpClient, mock: aioresponses, fake_dns: dict[str, list[str]]
) -> None:
    fake_dns["router.example.net"] = ["10.0.0.1"]
    with pytest.raises(UnsafeAddress):
        await client.get_text("http://router.example.net/admin")
    assert not mock.requests


async def test_redirect_is_followed_and_checked(
    client: HttpClient, mock: aioresponses
) -> None:
    mock.get(URL, status=301, headers={"Location": "/api/v2"})
    mock.get(
        "https://recipes.example.com/api/v2",
        status=302,
        headers={"Location": "https://cdn.example.org/data"},
    )
    mock.get("https://cdn.example.org/data", body="final")
    assert await client.get_text(URL) == "final"
    assert len(mock.requests) == 3


async def test_redirect_into_private_network_is_refused(
    client: HttpClient, mock: aioresponses, fake_dns: dict[str, list[str]]
) -> None:
    fake_dns["intranet.example.net"] = ["172.20.1.2"]
    mock.get(URL, status=302, headers={"Location": "http://intranet.example.net/"})
    with pytest.raises(UnsafeAddress):
        await client.get_text(URL)
    assert len(mock.requests) == 1


async def test_redirect_to_literal_private_address_is_refused(
    client: HttpClient, mock: aioresponses
) -> None:
    mock.get(URL, status=307, headers={"Location": "http://127.0.0.1:8123/api"})
    with pytest.raises(UnsafeAddress):
        await client.get_text(URL)
    assert len(mock.requests) == 1


async def test_at_most_three_redirects(client: HttpClient, mock: aioresponses) -> None:
    for hop in range(4):
        mock.get(
            f"https://recipes.example.com/r{hop}",
            status=302,
            headers={"Location": f"/r{hop + 1}"},
        )
    mock.get("https://recipes.example.com/r4", body="too far")
    with pytest.raises(SourceError, match="redirects"):
        await client.get_text("https://recipes.example.com/r0")
    assert len(mock.requests) == 4


async def test_three_redirects_are_fine(client: HttpClient, mock: aioresponses) -> None:
    for hop in range(3):
        mock.get(
            f"https://recipes.example.com/r{hop}",
            status=302,
            headers={"Location": f"/r{hop + 1}"},
        )
    mock.get("https://recipes.example.com/r3", body="ok")
    assert await client.get_text("https://recipes.example.com/r0") == "ok"


async def test_params_only_on_first_request(client: HttpClient, mock: aioresponses) -> None:
    mock.get(re.compile(r"^https://recipes\.example\.com/api\?q=x$"), status=302,
             headers={"Location": "https://recipes.example.com/other"})
    mock.get("https://recipes.example.com/other", body="[]")
    assert await client.get_json(URL, {"q": "x"}) == []
    urls = [str(url) for (_method, url) in mock.requests]
    assert urls[-1] == "https://recipes.example.com/other"


async def test_open_public_url_on_private_literal(session: aiohttp.ClientSession) -> None:
    with pytest.raises(UnsafeAddress):
        async with open_public_url(session, "http://[::ffff:10.0.0.1]/x"):
            pass



async def test_body_arriving_in_pieces_is_read_completely(client: HttpClient) -> None:
    """A body that arrives in several network chunks is read to the end."""

    class _Content:
        async def read(self, n: int = -1) -> bytes:  # what arrived so far only
            return b'[{"a": '

        async def iter_chunked(self, n: int):
            for part in (b'[{"a": ', b"1}", b"]"):
                yield part

    class _Response:
        status = 200
        headers: dict[str, str] = {}
        content_length = None
        charset = "utf-8"
        content = _Content()

    text = await client._read(_Response(), "recipes.example.com", False)  # noqa: SLF001
    assert text == '[{"a": 1}]'


# ----- review fixes ---------------------------------------------------------


async def test_check_reads_host_like_aiohttp() -> None:
    """Unicode digits are an IP address for yarl (and aiohttp), not a name."""

    async def resolve(host: str, port: int) -> list[str]:
        return ["93.184.215.14"]

    with pytest.raises(UnsafeAddress):
        await check_public_url("http://\u2460\u2461\u2466.0.0.1/", resolve)


async def test_html_limit_is_small_enough_for_the_event_loop(client: HttpClient) -> None:
    """Pages over 3 MB are refused before they are parsed (in the event loop)."""
    assert MAX_BYTES <= 3 * 1024 * 1024

    class _Content:
        async def iter_chunked(self, n: int):
            for _ in range(50):
                yield b"x" * 65536  # 3.1 MB in total

    class _Response:
        status = 200
        headers: dict[str, str] = {}
        content_length = None
        charset = "utf-8"
        content = _Content()

    with pytest.raises(SourceError, match="too large"):
        await client._read(_Response(), "recipes.example.com", True)  # noqa: SLF001


@pytest.mark.parametrize(
    "url",
    [
        "https://www.chefkoch.de/rezepte/1/x.html",
        "https://chefkoch.de/x",
        "https://api.chefkoch.de/v2/recipes/1",
        "https://WWW.CHEFKOCH.DE./x",
    ],
)
async def test_blocked_host_is_never_fetched(
    session: aiohttp.ClientSession, mock: aioresponses, url: str
) -> None:
    client = HttpClient(
        session, "EatFresh-Test/0.1", min_interval=0, blocked_hosts=("www.chefkoch.de",)
    )
    with pytest.raises(HostBlocked):
        await client.get_text(url)
    assert not mock.requests


async def test_redirect_to_blocked_host_is_refused(
    session: aiohttp.ClientSession, mock: aioresponses
) -> None:
    client = HttpClient(
        session, "EatFresh-Test/0.1", min_interval=0, blocked_hosts=("chefkoch.de",)
    )
    mock.get(URL, status=302, headers={"Location": "https://www.chefkoch.de/r/1"})
    with pytest.raises(HostBlocked):
        await client.get_text(URL)
    assert len(mock.requests) == 1


async def test_other_hosts_are_not_blocked(
    session: aiohttp.ClientSession, mock: aioresponses
) -> None:
    client = HttpClient(
        session, "EatFresh-Test/0.1", min_interval=0, blocked_hosts=("chefkoch.de",)
    )
    mock.get("https://notchefkoch.de/a", body="ok")
    assert await client.get_text("https://notchefkoch.de/a") == "ok"


class _FakeResolver:
    def __init__(self, addresses: list[str]) -> None:
        self.addresses = addresses
        self.closed = False

    async def resolve(self, host: str, port: int = 0, family: int = 0) -> list[dict]:
        return [
            {"hostname": host, "host": item, "port": port, "family": family,
             "proto": 0, "flags": 0}
            for item in self.addresses
        ]

    async def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    "addresses", [["10.1.2.3"], ["93.184.215.14", "127.0.0.1"], ["fd12:3456::1"], []]
)
async def test_public_only_resolver_refuses(addresses: list[str]) -> None:
    resolver = PublicOnlyResolver(_FakeResolver(addresses))  # type: ignore[arg-type]
    with pytest.raises(OSError):
        await resolver.resolve("rebind.example.com", 443)


async def test_public_only_resolver_passes_public_and_closes() -> None:
    inner = _FakeResolver(["93.184.215.14"])
    resolver = PublicOnlyResolver(inner)  # type: ignore[arg-type]
    result = await resolver.resolve("recipes.example.com", 443)
    assert [item["host"] for item in result] == ["93.184.215.14"]
    await resolver.close()
    assert inner.closed


@pytest.mark.usefixtures("socket_enabled")
async def test_public_session_does_not_connect_to_local_name() -> None:
    """A name that resolves to loopback is refused when connecting.

    This is the second lookup by aiohttp (after the address check), so a
    DNS answer that changes in between cannot reach the local network.
    """
    from aiohttp import web
    from aiohttp.test_utils import TestServer

    async def handler(request: web.Request) -> web.Response:
        return web.Response(text="secret")

    app = web.Application()
    app.router.add_get("/", handler)
    async with TestServer(app, host="127.0.0.1") as server:
        async with create_public_session() as public:
            with pytest.raises(aiohttp.ClientConnectorError):
                await public.get(f"http://localhost:{server.port}/")
        # Control: a normal session reaches the same server.
        async with aiohttp.ClientSession() as normal:
            async with normal.get(f"http://127.0.0.1:{server.port}/") as resp:
                assert await resp.text() == "secret"
