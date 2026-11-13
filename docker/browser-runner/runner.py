"""SpecStream browser runner: one local address that starts a hosted browser for each connection.

A CDP client (Puppeteer, Playwright, browser-use, Stagehand) connects to ws://<this container>:3000.
For each connection the runner opens a session with the SpecStream browser-sessions API
(POST /v1/browser/sessions), pipes the WebSocket to the session's connect_url, and releases the
session when either side leaves. The API key stays in the container: clients never hold it.

Settings, all from the environment:
  SPECSTREAM_API_KEY   required; the key the sessions are charged to
  SPECSTREAM_API_URL   default https://api.specstream.ai
  PORT                 default 3000
  RUNNER_TOKEN         optional; when set, a client must send ?token=<it> (or a Bearer header)
  SESSION_TIMEOUT_S    default 300; the most seconds one session runs (60 to 3600)
  HEADLESS             default true; false gives the browser a screen
  BLOCK_MEDIA          default false; true skips images, video, audio and fonts
  ALLOWED_DOMAINS      optional; hosts the browser may open, separated by commas
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import os
import sys
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from aiohttp import web

VERSION = "1.0.0"
TIMEOUT_MIN_S, TIMEOUT_MAX_S = 60, 3_600
# A create starts a browser; the API answers within this or the connection is refused.
CREATE_WAIT_S = 45.0
RELEASE_WAIT_S = 15.0


class SettingsError(ValueError):
    """A setting is absent or not in its range; the message names it."""


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise SettingsError(f"{name} must be true or false, not {raw!r}.")


def _number(env: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise SettingsError(f"{name} must be a whole number, not {raw!r}.") from None
    if not low <= value <= high:
        raise SettingsError(f"{name} must be from {low} to {high}, not {value}.")
    return value


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    api_url: str = "https://api.specstream.ai"
    port: int = 3000
    runner_token: str = field(default="", repr=False)
    timeout_s: int = 300
    headless: bool = True
    block_media: bool = False
    allowed_domains: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        key = env.get("SPECSTREAM_API_KEY", "").strip()
        if not key:
            raise SettingsError(
                "SPECSTREAM_API_KEY is not set. Start the container with "
                "-e SPECSTREAM_API_KEY=<your key>. Get a key at "
                "https://specstream.ai/workspace/agents?tab=keys"
            )
        url = (env.get("SPECSTREAM_API_URL", "").strip() or cls.api_url).rstrip("/")
        if not url.startswith(("https://", "http://")):
            raise SettingsError("SPECSTREAM_API_URL must start with https:// or http://.")
        domains = tuple(d.strip() for d in env.get("ALLOWED_DOMAINS", "").split(",") if d.strip())
        return cls(
            api_key=key,
            api_url=url,
            port=_number(env, "PORT", 3000, 1, 65_535),
            runner_token=env.get("RUNNER_TOKEN", "").strip(),
            timeout_s=_number(env, "SESSION_TIMEOUT_S", 300, TIMEOUT_MIN_S, TIMEOUT_MAX_S),
            headless=_flag(env, "HEADLESS", True),
            block_media=_flag(env, "BLOCK_MEDIA", False),
            allowed_domains=domains,
        )


def session_request(settings: Settings, query: Mapping[str, str]) -> dict[str, Any]:
    """The body of POST /v1/browser/sessions for one connection.

    A client may set `timeout` (milliseconds, as Browserless clients send it) and `headless` in
    the address it connects to; every other value is the container's setting.
    """
    timeout_s = settings.timeout_s
    raw = query.get("timeout", "")
    if raw:
        try:
            timeout_s = -(-int(raw) // 1000)
        except ValueError:
            raise SettingsError("timeout must be a whole number of milliseconds.") from None
        timeout_s = max(TIMEOUT_MIN_S, min(TIMEOUT_MAX_S, timeout_s))
    headless = settings.headless
    raw = query.get("headless", "").strip().lower()
    if raw in ("false", "0"):
        headless = False
    elif raw in ("true", "1", "new", "shell"):
        headless = True
    body: dict[str, Any] = {
        "timeout_s": timeout_s,
        "headless": headless,
        "metadata": {"client": f"docker-browser-runner/{VERSION}"},
    }
    if settings.block_media:
        body["block_media"] = True
    if settings.allowed_domains:
        body["allowed_domains"] = list(settings.allowed_domains)
    return body


SETTINGS = web.AppKey("settings", Settings)
HTTP = web.AppKey("http", aiohttp.ClientSession)


def _refusal(status: int, code: str, message: str) -> web.Response:
    return web.json_response({"error": {"code": code, "message": message}}, status=status)


def _allowed(request: web.Request, settings: Settings) -> bool:
    if not settings.runner_token:
        return True
    sent = request.query.get("token", "")
    header = request.headers.get("Authorization", "")
    if not sent and header.lower().startswith("bearer "):
        sent = header[7:].strip()
    return hmac.compare_digest(sent.encode(), settings.runner_token.encode())


def _public_ws(request: web.Request, settings: Settings) -> str:
    scheme = "wss" if request.headers.get("X-Forwarded-Proto", request.scheme) == "https" else "ws"
    token = f"?token={settings.runner_token}" if settings.runner_token else ""
    return f"{scheme}://{request.host}/{token}"


async def health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "version": VERSION})


async def json_version(request: web.Request) -> web.Response:
    """What a CDP client reads to find the WebSocket (Playwright connect_over_cdp("http://...")).

    It opens no session, so it costs nothing: the browser starts with the WebSocket connection.
    """
    settings = request.app[SETTINGS]
    if not _allowed(request, settings):
        return _refusal(401, "invalid_runner_token", "Send ?token=<RUNNER_TOKEN>.")
    return web.json_response(
        {
            "Browser": f"SpecStream-Browser-Runner/{VERSION}",
            "Protocol-Version": "1.3",
            "webSocketDebuggerUrl": _public_ws(request, settings),
        }
    )


async def _release(http: aiohttp.ClientSession, settings: Settings, session_id: str) -> None:
    with contextlib.suppress(aiohttp.ClientError, asyncio.TimeoutError):
        async with http.post(
            f"{settings.api_url}/v1/browser/sessions/{session_id}/release",
            headers={"Authorization": f"Bearer {settings.api_key}"},
            timeout=aiohttp.ClientTimeout(total=RELEASE_WAIT_S),
        ):
            pass


async def _pipe(source: Any, target: Any) -> None:
    async for message in source:
        if message.type == aiohttp.WSMsgType.TEXT:
            await target.send_str(message.data)
        elif message.type == aiohttp.WSMsgType.BINARY:
            await target.send_bytes(message.data)
        else:
            break


async def connect(request: web.Request) -> web.StreamResponse:
    """One client connection: create a session, pipe it, release it."""
    settings = request.app[SETTINGS]
    http = request.app[HTTP]
    if request.headers.get("Upgrade", "").lower() != "websocket":
        return _refusal(
            426,
            "websocket_required",
            "Connect a CDP client to this address over WebSocket, "
            "for example puppeteer.connect({browserWSEndpoint: 'ws://localhost:3000'}).",
        )
    if not _allowed(request, settings):
        return _refusal(401, "invalid_runner_token", "Send ?token=<RUNNER_TOKEN>.")
    try:
        body = session_request(settings, request.query)
    except SettingsError as error:
        return _refusal(400, "invalid_request", str(error))

    # The session is created before the upgrade, so a refusal of the API (a wrong key, an empty
    # balance, too many open sessions) reaches the client as that HTTP status and message.
    try:
        async with http.post(
            f"{settings.api_url}/v1/browser/sessions",
            json=body,
            headers={"Authorization": f"Bearer {settings.api_key}"},
            timeout=aiohttp.ClientTimeout(total=CREATE_WAIT_S),
        ) as created:
            status = created.status
            try:
                answer = await created.json(content_type=None)
            except ValueError:
                answer = None
    except (TimeoutError, aiohttp.ClientError) as error:
        return _refusal(
            502, "api_unreachable", f"SpecStream did not answer: {type(error).__name__}."
        )
    if status >= 400 or not isinstance(answer, dict):
        if isinstance(answer, dict) and isinstance(answer.get("error"), dict):
            return web.json_response({"error": answer["error"]}, status=status)
        return _refusal(502, "api_error", f"SpecStream answered {status}.")
    session = answer.get("data", answer)
    session_id, connect_url = session.get("id"), session.get("connect_url")
    if not session_id or not connect_url:
        return _refusal(502, "api_error", "SpecStream answered without a session to connect to.")

    try:
        try:
            upstream = await http.ws_connect(connect_url, max_msg_size=0, heartbeat=30)
        except (TimeoutError, aiohttp.ClientError) as error:
            return _refusal(
                502, "session_unreachable", f"The session did not connect: {type(error).__name__}."
            )
        client = web.WebSocketResponse(max_msg_size=0)
        await client.prepare(request)
        print(f"session {session_id} opened", flush=True)
        pipes = [
            asyncio.ensure_future(_pipe(client, upstream)),
            asyncio.ensure_future(_pipe(upstream, client)),
        ]
        try:
            await asyncio.wait(pipes, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for pipe in pipes:
                pipe.cancel()
            await asyncio.gather(*pipes, return_exceptions=True)
            with contextlib.suppress(Exception):
                await upstream.close()
            with contextlib.suppress(Exception):
                await client.close()
        return client
    finally:
        # Shielded: the session is released, and so stops being charged, even when the client's
        # connection is cut and this handler is cancelled.
        await asyncio.shield(_release(http, settings, session_id))
        print(f"session {session_id} released", flush=True)


async def _http(app: web.Application) -> AsyncIterator[None]:
    app[HTTP] = aiohttp.ClientSession()
    yield
    await app[HTTP].close()


def make_app(settings: Settings) -> web.Application:
    app = web.Application()
    app[SETTINGS] = settings
    app.cleanup_ctx.append(_http)
    app.router.add_get("/health", health)
    app.router.add_get("/json/version", json_version)
    app.router.add_get("/json/version/", json_version)
    app.router.add_get("/{path:.*}", connect)
    return app


def main() -> int:
    try:
        settings = Settings.from_env()
    except SettingsError as error:
        print(error, file=sys.stderr)
        return 2
    print(f"SpecStream browser runner {VERSION} on port {settings.port}", flush=True)
    web.run_app(make_app(settings), host="0.0.0.0", port=settings.port, print=None)  # noqa: S104
    return 0


if __name__ == "__main__":
    sys.exit(main())
