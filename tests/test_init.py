"""Tests for setup, unload, panel and image proxy of EatFresh."""

from __future__ import annotations

from http import HTTPStatus
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.frontend import DATA_PANELS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.eatfresh.const import (
    CONF_ACCEPT_CHEFKOCH,
    CONF_SOURCES,
    DOMAIN,
    PANEL_URL_PATH,
    VERSION,
)
from custom_components.eatfresh.errors import KitchenOwlAuthError, KitchenOwlError
from custom_components.eatfresh.image_proxy import sign_image_url, sign_photo

from .conftest import IMAGE_HOST, KITCHENOWL_URL, RECIPE_HOST, TOKEN

MANIFEST = Path(__file__).parent.parent / "custom_components" / "eatfresh" / "manifest.json"


def test_manifest_version_matches_const() -> None:
    """The version in manifest.json and const.py must be the same."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["version"] == VERSION
    assert manifest["requirements"] == []
    assert manifest["single_config_entry"] is True


async def test_setup_and_unload(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    patch_client: MagicMock,
    mock_sources: MagicMock,
) -> None:
    """Setup builds client, sources and panel; unload removes the panel."""
    entry = init_integration
    assert entry.state is ConfigEntryState.LOADED
    patch_client.assert_called_once()
    assert patch_client.call_args.args[1:] == (KITCHENOWL_URL, TOKEN)
    enabled = list(mock_sources.call_args.args[1])
    assert enabled == ["fakea", "fakeb"]  # chefkoch is off by default
    assert set(entry.runtime_data.sources) == {"fakea", "fakeb", "jsonld"}

    panel = hass.data[DATA_PANELS][PANEL_URL_PATH]
    assert panel.sidebar_title == "EatFresh"
    assert panel.sidebar_icon == "mdi:silverware-fork-knife"
    assert panel.require_admin is False
    custom = panel.config["_panel_custom"]
    assert custom["name"] == "eatfresh-panel"
    assert custom["module_url"] == f"/eatfresh_static/eatfresh-panel.js?v={VERSION}"

    assert hass.services.has_service(DOMAIN, "import_recipe")
    assert hass.services.has_service(DOMAIN, "add_recipe_to_shopping_list")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert PANEL_URL_PATH not in hass.data.get(DATA_PANELS, {})


async def test_reload_keeps_single_panel(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """A reload registers the panel again without errors."""
    assert await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.LOADED
    assert PANEL_URL_PATH in hass.data[DATA_PANELS]


async def test_missing_panel_file(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    patch_client: MagicMock,
    mock_sources: MagicMock,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Without the built panel the integration loads, but adds no sidebar entry."""
    config_entry.add_to_hass(hass)
    with patch("custom_components.eatfresh.panel.FRONTEND_DIR", tmp_path):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    assert PANEL_URL_PATH not in hass.data.get(DATA_PANELS, {})
    assert "Panel file eatfresh-panel.js is missing" in caplog.text
    assert await hass.config_entries.async_unload(config_entry.entry_id)


@pytest.mark.parametrize(
    ("error", "state"),
    [
        (KitchenOwlAuthError("401"), ConfigEntryState.SETUP_ERROR),
        (KitchenOwlError("down"), ConfigEntryState.SETUP_RETRY),
    ],
)
async def test_setup_errors(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    patch_client: MagicMock,
    mock_client: MagicMock,
    mock_sources: MagicMock,
    panel_dir: Path,
    error: Exception,
    state: ConfigEntryState,
) -> None:
    """KitchenOwl errors during setup lead to retry or reauth."""
    mock_client.get_user.side_effect = error
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is state
    if state is ConfigEntryState.SETUP_ERROR:
        flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        assert flows and flows[0]["context"]["source"] == "reauth"


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({CONF_SOURCES: ["fakeb", "chefkoch"]}, ["fakeb"]),
        (
            {CONF_SOURCES: ["fakeb", "chefkoch"], CONF_ACCEPT_CHEFKOCH: True},
            ["fakeb", "chefkoch"],
        ),
        ({CONF_SOURCES: ["unknown", "jsonld"]}, []),
    ],
)
async def test_enabled_sources_from_options(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    patch_client: MagicMock,
    mock_sources: MagicMock,
    panel_dir: Path,
    options: dict,
    expected: list[str],
) -> None:
    """Chefkoch is only used with accepted terms; unknown ids are dropped."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="1",
        data=dict(config_entry.data),
        options=options,
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    assert list(mock_sources.call_args.args[1]) == expected


async def test_image_proxy_remote(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_client,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Images from allowed hosts pass through, others are refused."""
    aioclient_mock.get(
        f"https://{IMAGE_HOST}/a.jpg",
        content=b"jpegdata",
        headers={"Content-Type": "image/jpeg"},
    )
    aioclient_mock.get(
        f"https://{IMAGE_HOST}/b.svg",
        content=b"<svg/>",
        headers={"Content-Type": "image/svg+xml"},
    )
    aioclient_mock.get(f"https://{IMAGE_HOST}/missing.jpg", status=404)
    client = await hass_client()

    resp = await client.get(
        "/api/eatfresh/image", params={"url": f"https://{IMAGE_HOST}/a.jpg"}
    )
    assert resp.status == HTTPStatus.OK
    assert await resp.read() == b"jpegdata"
    assert resp.headers["Content-Type"] == "image/jpeg"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"

    resp = await client.get(
        "/api/eatfresh/image", params={"url": f"https://{IMAGE_HOST}/b.svg"}
    )
    assert resp.status == HTTPStatus.BAD_GATEWAY

    resp = await client.get(
        "/api/eatfresh/image", params={"url": f"https://{IMAGE_HOST}/missing.jpg"}
    )
    assert resp.status == HTTPStatus.BAD_GATEWAY

    for url in ("https://evil.example.net/a.jpg", "file:///etc/passwd", "http://127.0.0.1/x"):
        resp = await client.get("/api/eatfresh/image", params={"url": url})
        assert resp.status == HTTPStatus.FORBIDDEN, url

    resp = await client.get("/api/eatfresh/image")
    assert resp.status == HTTPStatus.BAD_REQUEST
    assert aioclient_mock.call_count == 3


async def test_image_proxy_checks_addresses_and_redirects(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_client,
    aioclient_mock: AiohttpClientMocker,
    fake_dns: dict[str, list[str]],
) -> None:
    """Allowed hosts must resolve publicly; redirects are checked one by one."""
    aioclient_mock.get(
        f"https://{IMAGE_HOST}/moved.jpg",
        status=302,
        headers={"Location": f"https://{RECIPE_HOST}/real.jpg"},
    )
    aioclient_mock.get(
        f"https://{RECIPE_HOST}/real.jpg",
        content=b"jpegdata",
        headers={"Content-Type": "image/jpeg"},
    )
    aioclient_mock.get(
        f"https://{IMAGE_HOST}/inside.jpg",
        status=302,
        headers={"Location": "http://10.11.12.13/admin.jpg"},
    )
    client = await hass_client()

    resp = await client.get(
        "/api/eatfresh/image", params={"url": f"https://{IMAGE_HOST}/moved.jpg"}
    )
    assert resp.status == HTTPStatus.OK
    assert await resp.read() == b"jpegdata"

    resp = await client.get(
        "/api/eatfresh/image", params={"url": f"https://{IMAGE_HOST}/inside.jpg"}
    )
    assert resp.status == HTTPStatus.FORBIDDEN
    assert aioclient_mock.call_count == 3

    # An allowed host name that points into the local network.
    fake_dns[IMAGE_HOST] = ["192.0.2.1", "172.16.0.9"]
    resp = await client.get(
        "/api/eatfresh/image", params={"url": f"https://{IMAGE_HOST}/moved.jpg"}
    )
    assert resp.status == HTTPStatus.FORBIDDEN
    assert aioclient_mock.call_count == 3


async def test_image_proxy_photo(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_client,
    mock_client: MagicMock,
) -> None:
    """KitchenOwl photos come from the configured client only."""
    client = await hass_client()
    resp = await client.get("/api/eatfresh/image", params={"photo": "abc123.jpg"})
    assert resp.status == HTTPStatus.OK
    assert await resp.read() == b"\xff\xd8photo"
    mock_client.fetch_photo.assert_awaited_once_with("abc123.jpg")

    resp = await client.get("/api/eatfresh/image", params={"photo": "../secret"})
    assert resp.status == HTTPStatus.BAD_REQUEST

    mock_client.fetch_photo.side_effect = KitchenOwlError("gone")
    resp = await client.get("/api/eatfresh/image", params={"photo": "x.jpg"})
    assert resp.status == HTTPStatus.BAD_GATEWAY


async def test_image_proxy_signed_path(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_client_no_auth,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Signed paths work without a header; unsigned or changed paths do not."""
    aioclient_mock.get(
        f"https://{IMAGE_HOST}/a.jpg",
        content=b"jpegdata",
        headers={"Content-Type": "image/jpeg"},
    )
    client = await hass_client_no_auth()
    signed = sign_image_url(hass, f"https://{IMAGE_HOST}/a.jpg")
    assert signed is not None and "authSig=" in signed

    resp = await client.get(signed)
    assert resp.status == HTTPStatus.OK

    resp = await client.get(
        "/api/eatfresh/image", params={"url": f"https://{IMAGE_HOST}/a.jpg"}
    )
    assert resp.status == HTTPStatus.UNAUTHORIZED

    tampered = signed.replace("a.jpg", "b.jpg")
    resp = await client.get(tampered)
    assert resp.status == HTTPStatus.UNAUTHORIZED


async def test_sign_helpers(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Invalid inputs give no image link."""
    assert sign_image_url(hass, None) is None
    assert sign_image_url(hass, "data:image/png;base64,AAAA") is None
    assert sign_photo(hass, None) is None
    assert sign_photo(hass, "a/b.jpg") is None
    assert sign_photo(hass, "ok.jpg").startswith("/api/eatfresh/image?photo=ok.jpg")


async def test_not_loaded_image_proxy(
    hass: HomeAssistant, init_integration: MockConfigEntry, hass_client
) -> None:
    """The proxy answers 404 when the entry is unloaded."""
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    client = await hass_client()
    resp = await client.get("/api/eatfresh/image", params={"photo": "a.jpg"})
    assert resp.status == HTTPStatus.NOT_FOUND


# ----- review fixes ---------------------------------------------------------


async def test_image_proxy_redirect_to_foreign_host_is_refused(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_client,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A redirect may only lead to an allowed image host."""
    aioclient_mock.get(
        f"https://{IMAGE_HOST}/open-redirect.jpg",
        status=302,
        headers={"Location": "https://cdn.example.org/any.jpg"},
    )
    aioclient_mock.get(
        "https://cdn.example.org/any.jpg",
        content=b"jpegdata",
        headers={"Content-Type": "image/jpeg"},
    )
    client = await hass_client()
    resp = await client.get(
        "/api/eatfresh/image", params={"url": f"https://{IMAGE_HOST}/open-redirect.jpg"}
    )
    assert resp.status == HTTPStatus.FORBIDDEN
    assert aioclient_mock.call_count == 1


async def test_image_proxy_size_limit_while_streaming(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_client,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A body without Content-Length is cut off at the limit."""
    aioclient_mock.get(
        f"https://{IMAGE_HOST}/big.jpg",
        content=b"x" * 100,
        headers={"Content-Type": "image/jpeg"},
    )
    client = await hass_client()
    with patch("custom_components.eatfresh.image_proxy.IMAGE_MAX_BYTES", 99):
        resp = await client.get(
            "/api/eatfresh/image", params={"url": f"https://{IMAGE_HOST}/big.jpg"}
        )
    assert resp.status == HTTPStatus.BAD_GATEWAY
    with patch("custom_components.eatfresh.image_proxy.IMAGE_MAX_BYTES", 100):
        resp = await client.get(
            "/api/eatfresh/image", params={"url": f"https://{IMAGE_HOST}/big.jpg"}
        )
    assert resp.status == HTTPStatus.OK


@pytest.mark.parametrize("name", ["..", ".", "a/b.jpg", "a\\b.jpg", "x" * 256])
async def test_image_proxy_refuses_photo_paths(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_client,
    mock_client: MagicMock,
    name: str,
) -> None:
    """Photo names with path parts never reach KitchenOwl."""
    client = await hass_client()
    resp = await client.get("/api/eatfresh/image", params={"photo": name})
    assert resp.status == HTTPStatus.BAD_REQUEST
    mock_client.fetch_photo.assert_not_awaited()


async def test_image_proxy_limits_parallel_fetches(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_client,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """At most MAX_PARALLEL_FETCHES remote images are buffered at once."""
    import asyncio

    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMockResponse,
    )

    from custom_components.eatfresh.image_proxy import MAX_PARALLEL_FETCHES

    active = 0
    peak = 0
    release = asyncio.Event()

    async def slow(method, url, data):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await release.wait()
        active -= 1
        return AiohttpClientMockResponse(
            method, url, response=b"img", headers={"Content-Type": "image/jpeg"}
        )

    aioclient_mock.get(f"https://{IMAGE_HOST}/slow.jpg", side_effect=slow)
    client = await hass_client()
    tasks = [
        asyncio.create_task(
            client.get(
                "/api/eatfresh/image", params={"url": f"https://{IMAGE_HOST}/slow.jpg"}
            )
        )
        for _ in range(MAX_PARALLEL_FETCHES + 3)
    ]
    for _ in range(200):
        if active >= MAX_PARALLEL_FETCHES:
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)
    assert peak == MAX_PARALLEL_FETCHES
    release.set()
    responses = await asyncio.gather(*tasks)
    assert [resp.status for resp in responses] == [HTTPStatus.OK] * len(tasks)
    assert peak == MAX_PARALLEL_FETCHES


async def test_public_session_is_closed_on_unload(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    patch_client: MagicMock,
    mock_sources: MagicMock,
    panel_dir: Path,
) -> None:
    """The own session for recipe pages is closed when the entry unloads."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    session = config_entry.runtime_data.public_session
    assert session is not None and not session.closed
    # The HTTP client of the sources uses this session, not the shared one.
    client = mock_sources.call_args.args[0]
    assert client._session is session  # noqa: SLF001
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert session.closed


async def test_chefkoch_hosts_are_blocked_while_chefkoch_is_off(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    patch_client: MagicMock,
    panel_dir: Path,
) -> None:
    """With the real sources, the HTTP client refuses Chefkoch hosts."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    data = config_entry.runtime_data
    client = data.sources["jsonld"]._client  # noqa: SLF001
    assert client.is_blocked("www.chefkoch.de")
    assert client.is_blocked("img.chefkoch-cdn.de")
    assert not client.is_blocked("emmikochteinfach.de")
    assert "img.chefkoch-cdn.de" not in data.allowed_image_hosts()
    assert await hass.config_entries.async_unload(config_entry.entry_id)


class _SpySession:
    """Pass requests to a real session and count them."""

    def __init__(self, session) -> None:
        self._session = session
        self.calls = 0

    async def get(self, *args, **kwargs):
        self.calls += 1
        return await self._session.get(*args, **kwargs)


async def test_image_proxy_uses_the_own_session(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_client,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Remote images go through the own session, not the shared one of HA."""
    aioclient_mock.get(
        f"https://{IMAGE_HOST}/a.jpg",
        content=b"jpegdata",
        headers={"Content-Type": "image/jpeg"},
    )
    data = init_integration.runtime_data
    spy = _SpySession(data.public_session)
    data.public_session = spy
    client = await hass_client()
    resp = await client.get(
        "/api/eatfresh/image", params={"url": f"https://{IMAGE_HOST}/a.jpg"}
    )
    assert resp.status == HTTPStatus.OK
    assert spy.calls == 1


async def test_image_proxy_without_own_session_fails(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_client,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Without the own session there is an error, never the shared session."""
    aioclient_mock.get(
        f"https://{IMAGE_HOST}/a.jpg",
        content=b"jpegdata",
        headers={"Content-Type": "image/jpeg"},
    )
    init_integration.runtime_data.public_session = None
    client = await hass_client()
    resp = await client.get(
        "/api/eatfresh/image", params={"url": f"https://{IMAGE_HOST}/a.jpg"}
    )
    assert resp.status == HTTPStatus.SERVICE_UNAVAILABLE
    assert aioclient_mock.call_count == 0
