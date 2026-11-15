"""Image proxy: serve recipe photos through Home Assistant with signed paths.

An <img> tag cannot send an auth header, so every image link handed to the
panel is a path signed with async_sign_path. The view only fetches from hosts
of the enabled recipe sources and photos of the configured KitchenOwl. Remote
addresses go through ``open_public_url``: names are resolved, private networks
are refused and every redirect is checked again, also against the allowed
hosts. At most ``MAX_PARALLEL_FETCHES`` remote images are fetched at a time,
because each one is buffered in memory.

A signed path is reused while it stays valid for at least
``IMAGE_SIGN_RENEW_BEFORE``. So the sensor attribute and the answers for the
panel keep the same address for the same photo (no new state every minute,
the browser cache keeps working), and a new one comes shortly before the old
one runs out.
"""

from __future__ import annotations

import asyncio
from http import HTTPStatus
import logging
import time

import aiohttp
from aiohttp import web
from homeassistant.components import websocket_api
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.components.http.auth import STORAGE_KEY, async_sign_path
from homeassistant.components.http.const import KEY_HASS_REFRESH_TOKEN_ID
from homeassistant.helpers.http import current_request
from homeassistant.util.hass_dict import HassKey
from homeassistant.core import HomeAssistant, callback
from yarl import URL

from .const import (
    IMAGE_FETCH_TIMEOUT,
    IMAGE_MAX_BYTES,
    IMAGE_PROXY_PATH,
    IMAGE_SIGN_EXPIRATION,
    IMAGE_SIGN_RENEW_BEFORE,
    USER_AGENT,
)
from .errors import EatFreshError
from .http import UnsafeAddress, open_public_url
from .runtime import EatFreshData, async_reauth_on_auth_error, get_runtime_data

_LOGGER = logging.getLogger(__name__)

MAX_PARALLEL_FETCHES = 6

ALLOWED_CONTENT_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}
)


# Signed paths by (signing token, path): (signed path, expiry as Unix time).
DATA_SIGNED: HassKey[dict[tuple[str, str], tuple[str, int]]] = HassKey(
    "eatfresh_signed_images"
)
# Upper bound for the reuse table; expired entries are dropped first.
MAX_SIGNED_PATHS = 2000


@callback
def sign_image_url(
    hass: HomeAssistant, url: str | None, *, content_user: bool = False
) -> str | None:
    """Return a signed proxy path for a remote image or None."""
    if not url:
        return None
    parsed = URL(url)
    if parsed.scheme not in ("http", "https") or not parsed.host:
        return None
    path = URL(IMAGE_PROXY_PATH).with_query(url=url)
    return _signed(hass, str(path), content_user)


@callback
def sign_photo(
    hass: HomeAssistant, filename: str | None, *, content_user: bool = False
) -> str | None:
    """Return a signed proxy path for a KitchenOwl photo or None.

    ``content_user`` signs for Home Assistant's content user instead of the
    caller. Entity attributes use it: they outlive a single connection.
    """
    if not filename or not _valid_photo_name(filename):
        return None
    path = URL(IMAGE_PROXY_PATH).with_query(photo=filename)
    return _signed(hass, str(path), content_user)


def _signing_token(hass: HomeAssistant, content_user: bool) -> str:
    """Return the refresh token id ``async_sign_path`` would sign for."""
    if not content_user:
        if (
            connection := websocket_api.current_connection.get()
        ) and connection.refresh_token_id:
            return connection.refresh_token_id
        if (request := current_request.get()) is not None and (
            KEY_HASS_REFRESH_TOKEN_ID in request
        ):
            return request[KEY_HASS_REFRESH_TOKEN_ID]
    return hass.data[STORAGE_KEY]


@callback
def _signed(hass: HomeAssistant, path: str, content_user: bool) -> str:
    """Return a signed path, reusing one that is still valid long enough."""
    token = _signing_token(hass, content_user)
    cache = hass.data.setdefault(DATA_SIGNED, {})
    now = time.time()
    key = (token, path)
    if (hit := cache.get(key)) is not None and (
        hit[1] - now > IMAGE_SIGN_RENEW_BEFORE.total_seconds()
    ):
        return hit[0]
    signed = async_sign_path(
        hass, path, IMAGE_SIGN_EXPIRATION, refresh_token_id=token
    )
    if len(cache) >= MAX_SIGNED_PATHS:
        for old in [k for k, (_s, exp) in cache.items() if exp <= now]:
            del cache[old]
        if len(cache) >= MAX_SIGNED_PATHS:
            cache.clear()
    cache[key] = (signed, int(now + IMAGE_SIGN_EXPIRATION.total_seconds()))
    return signed


def _valid_photo_name(filename: str) -> bool:
    """Return True for a plain file name without path parts."""
    return (
        "/" not in filename
        and "\\" not in filename
        and filename not in (".", "..")
        and len(filename) <= 255
    )


def _content_type(value: str | None) -> str | None:
    """Return the bare media type if it is an allowed image type."""
    if not value:
        return None
    media_type = value.split(";", 1)[0].strip().lower()
    return media_type if media_type in ALLOWED_CONTENT_TYPES else None


def _image_response(body: bytes, content_type: str) -> web.Response:
    """Return the image with safe headers."""
    return web.Response(
        body=body,
        content_type=content_type,
        headers={
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )


class EatFreshImageView(HomeAssistantView):
    """Fetch an image from an allowed host and pass it through."""

    url = IMAGE_PROXY_PATH
    name = "api:eatfresh:image"
    requires_auth = True

    def __init__(self) -> None:
        """Limit the number of remote images fetched at the same time."""
        self._fetch_limit = asyncio.Semaphore(MAX_PARALLEL_FETCHES)

    async def get(self, request: web.Request) -> web.StreamResponse:
        """Handle GET requests."""
        hass = request.app[KEY_HASS]
        data = get_runtime_data(hass)
        if data is None:
            return web.Response(status=HTTPStatus.NOT_FOUND)

        if (photo := request.query.get("photo")) is not None:
            if not _valid_photo_name(photo):
                return web.Response(status=HTTPStatus.BAD_REQUEST)
            try:
                body, raw_type = await data.client.fetch_photo(photo)
            except EatFreshError as err:
                _LOGGER.debug("KitchenOwl photo failed: %s", err)
                async_reauth_on_auth_error(hass, err)
                return web.Response(status=HTTPStatus.BAD_GATEWAY)
            if (content_type := _content_type(raw_type)) is None:
                return web.Response(status=HTTPStatus.BAD_GATEWAY)
            return _image_response(body, content_type)

        if (url := request.query.get("url")) is None:
            return web.Response(status=HTTPStatus.BAD_REQUEST)
        parsed = URL(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.host
            or parsed.host.lower() not in data.allowed_image_hosts()
        ):
            return web.Response(status=HTTPStatus.FORBIDDEN)
        if data.public_session is None:
            # Never fall back to the shared session of Home Assistant: only the
            # own session refuses non-public addresses.
            return web.Response(status=HTTPStatus.SERVICE_UNAVAILABLE)
        async with self._fetch_limit:
            return await self._fetch(data, data.public_session, url)

    async def _fetch(
        self, data: EatFreshData, session: aiohttp.ClientSession, url: str
    ) -> web.StreamResponse:
        """Download a remote image with a size and time limit."""
        allowed = data.allowed_image_hosts()

        def check_host(host: str) -> None:
            # Redirect targets must be allowed hosts as well.
            if host not in allowed:
                raise UnsafeAddress("Image host is not allowed")

        try:
            async with open_public_url(
                session,
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "image/*"},
                timeout=aiohttp.ClientTimeout(total=IMAGE_FETCH_TIMEOUT),
                check_host=check_host,
            ) as resp:
                if resp.status != HTTPStatus.OK:
                    return web.Response(status=HTTPStatus.BAD_GATEWAY)
                content_type = _content_type(resp.headers.get("Content-Type"))
                if content_type is None:
                    return web.Response(status=HTTPStatus.BAD_GATEWAY)
                length = resp.headers.get("Content-Length", "")
                if length.isdigit() and int(length) > IMAGE_MAX_BYTES:
                    return web.Response(status=HTTPStatus.BAD_GATEWAY)
                chunks: list[bytes] = []
                size = 0
                async for chunk in resp.content.iter_chunked(65536):
                    size += len(chunk)
                    if size > IMAGE_MAX_BYTES:
                        return web.Response(status=HTTPStatus.BAD_GATEWAY)
                    chunks.append(chunk)
        except UnsafeAddress as err:
            _LOGGER.debug("Image address refused for %s: %s", url, err)
            return web.Response(status=HTTPStatus.FORBIDDEN)
        except (EatFreshError, aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("Image fetch failed for %s: %s", url, err)
            return web.Response(status=HTTPStatus.BAD_GATEWAY)
        return _image_response(b"".join(chunks), content_type)
