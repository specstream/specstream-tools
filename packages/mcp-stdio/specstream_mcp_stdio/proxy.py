"""Stdio to Streamable HTTP proxy. Authorization is copied from env only.

Both MCP eras pass through. A request that carries its protocol version in
`params._meta` (2026-07-28 and later) is forwarded statelessly with the version, method
and name mirrored into headers. A client that starts with `initialize` gets the session
revision the server negotiates, and its session id is kept for later requests.

Without a key it still starts: it answers `initialize` and `tools/list` from the tool list
shipped with the package, so a client or a directory can see what the server offers, and
every tool call says how to get a key.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlsplit

DEFAULT_MCP_URL = "https://api.specstream.ai/mcp"
PROTOCOL_VERSION = "2025-11-25"
VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
NAMED_METHODS = {"tools/call": "name", "prompts/get": "name", "resources/read": "uri"}
MISSING_KEY = (
    "SPECSTREAM_API_KEY is not set, so SpecStream lists its tools but can't run them. "
    "Create a key under Agents & API at https://specstream.ai/workspace and set "
    "SPECSTREAM_API_KEY where this server starts."
)
KNOWN_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18", PROTOCOL_VERSION)
TOOLS_FILE = Path(__file__).with_name("tools.json")
SERVER_INFO = {
    "name": "specstream",
    "title": "SpecStream",
    "version": "1.2.3",
    "websiteUrl": "https://specstream.ai",
}


def authorization_from_env(env: Mapping[str, str]) -> str:
    for name in ("SPECSTREAM_API_KEY", "SPECSTREAM_AUTHORIZATION", "AUTHORIZATION"):
        value = (env.get(name) or "").strip()
        if value:
            if any(not 32 <= ord(char) < 127 for char in value):
                raise ValueError("The configured authorization header contains invalid characters")
            return value if value.lower().startswith("bearer ") else f"Bearer {value}"
    raise KeyError("SPECSTREAM_API_KEY")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def _mcp_url(env: Mapping[str, str]) -> str:
    value = (env.get("SPECSTREAM_MCP_URL") or DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
        try:
            loopback = host is not None and ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == "localhost"
        if (
            not host
            or parsed.scheme not in {"http", "https"}
            or parsed.scheme == "http"
            and not loopback
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or port == 0
            or any(ord(char) <= 32 or ord(char) == 127 for char in value)
        ):
            raise ValueError
    except ValueError:
        raise ValueError(
            "SPECSTREAM_MCP_URL must use HTTPS (or loopback HTTP), "
            "without credentials, query or fragment"
        ) from None
    return value


def _header_value(value: str) -> str:
    """Mcp-Name as the revision sends it: plain visible ASCII, or the Base64 sentinel form."""
    plain = (
        value == value.strip()
        and all(32 <= ord(char) < 127 for char in value)
        and not (value.startswith("=?base64?") and value.endswith("?="))
    )
    if plain:
        return value
    return "=?base64?" + base64.b64encode(value.encode("utf-8")).decode("ascii") + "?="


def _stateless_version(message: Mapping[str, Any]) -> str | None:
    params = message.get("params")
    meta = params.get("_meta") if isinstance(params, Mapping) else None
    version = meta.get(VERSION_KEY) if isinstance(meta, Mapping) else None
    return version if isinstance(version, str) and version else None


def _json_from_sse(text: str, request_id: Any) -> dict[str, Any]:
    for event in text.replace("\r\n", "\n").split("\n\n"):
        blob = "\n".join(
            line[5:].lstrip() for line in event.splitlines() if line.startswith("data:")
        )
        if not blob:
            continue
        payload = json.loads(blob)
        if isinstance(payload, dict) and "id" in payload and payload["id"] == request_id:
            return payload
    raise ValueError("mcp returned no response for the request")


def _post_json(
    url: str,
    message: dict[str, Any],
    *,
    authorization: str,
    session_id: str | None,
    session_version: str = PROTOCOL_VERSION,
) -> tuple[int, dict[str, str], dict[str, Any] | None]:
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    request.add_header("Authorization", authorization)
    request.add_header("Accept", "application/json, text/event-stream")
    request.add_header("Content-Type", "application/json")
    stateless = _stateless_version(message)
    if stateless:
        method = str(message.get("method", ""))
        request.add_header("MCP-Protocol-Version", stateless)
        request.add_header("Mcp-Method", method)
        params = message.get("params")
        field = NAMED_METHODS.get(method)
        name = params.get(field) if field and isinstance(params, Mapping) else None
        if isinstance(name, str):
            request.add_header("Mcp-Name", _header_value(name))
    else:
        request.add_header("MCP-Protocol-Version", session_version)
        if session_id:
            request.add_header("MCP-Session-Id", session_id)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        with opener.open(request, timeout=150) as response:
            status = int(response.status)
            headers = {key.lower(): value for key, value in response.headers.items()}
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        header_items = exc.headers.items() if exc.headers else []
        headers = {key.lower(): value for key, value in header_items}
        raw = exc.read().decode("utf-8") if exc.fp is not None else ""
    if not 200 <= status < 300:
        # The 2026-07-28 revision answers version, header and method problems with a JSON-RPC
        # error on a 4xx; the client needs it to pick another version or fall back.
        error = _error_body(raw, message.get("id"))
        if error is None:
            raise ValueError(f"mcp http {status}")
        return status, headers, error
    if status == 202:
        if "id" in message:
            raise ValueError("mcp returned no response for the request")
        return status, headers, None
    if not raw:
        raise ValueError("mcp returned an empty response")
    content_type = headers.get("content-type", "")
    if "text/event-stream" in content_type:
        loaded = _json_from_sse(raw, message.get("id"))
    else:
        loaded = json.loads(raw)
    if (
        not isinstance(loaded, dict)
        or loaded.get("jsonrpc") != "2.0"
        or "id" not in loaded
        or loaded["id"] != message.get("id")
        or not ({"result", "error"} & loaded.keys())
    ):
        raise ValueError("mcp returned an invalid response")
    return status, headers, loaded


def _error_body(raw: str, request_id: Any) -> dict[str, Any] | None:
    try:
        loaded = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        return None
    if (
        isinstance(loaded, dict)
        and loaded.get("jsonrpc") == "2.0"
        and "id" in loaded
        and loaded["id"] == request_id
        and isinstance(loaded.get("error"), dict)
    ):
        return loaded
    return None


def _keyless_reply(message: Mapping[str, Any]) -> dict[str, Any] | None:
    """Answer one message without a key. Notifications get no answer."""
    if "id" not in message:
        return None
    method = message.get("method")
    params = message.get("params")
    params = params if isinstance(params, Mapping) else {}
    result: dict[str, Any]
    if method == "initialize":
        requested = params.get("protocolVersion")
        result = {
            "protocolVersion": requested if requested in KNOWN_VERSIONS else PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": MISSING_KEY,
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": json.loads(TOOLS_FILE.read_text(encoding="utf-8"))}
    elif method == "resources/list":
        result = {"resources": []}
    elif method == "resources/templates/list":
        result = {"resourceTemplates": []}
    elif method == "prompts/list":
        result = {"prompts": []}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": MISSING_KEY}], "isError": True}
    else:
        return {
            "jsonrpc": "2.0",
            "id": message["id"],
            "error": {"code": -32601, "message": MISSING_KEY},
        }
    return {"jsonrpc": "2.0", "id": message["id"], "result": result}


def main(
    argv: list[str] | None = None,
    env: Mapping[str, str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    del argv
    environ = env if env is not None else os.environ
    in_stream = stdin if stdin is not None else sys.stdin
    out_stream = stdout if stdout is not None else sys.stdout
    err_stream = stderr if stderr is not None else sys.stderr
    authorization: str | None
    try:
        url = _mcp_url(environ)
        authorization = authorization_from_env(environ)
    except KeyError:
        authorization = None
        print(MISSING_KEY, file=err_stream)
    except ValueError as exc:
        print(str(exc), file=err_stream)
        return 2
    session_id: str | None = None
    session_version = PROTOCOL_VERSION
    for line in in_stream:
        text = line.strip()
        if not text:
            continue
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            print("invalid jsonrpc line", file=err_stream)
            return 1
        if not isinstance(message, dict):
            print("invalid jsonrpc line", file=err_stream)
            return 1
        if message.get("method") == "notifications/cancelled" and "id" not in message:
            # Each request is a blocking POST here, so there is nothing to cancel upstream.
            continue
        if authorization is None:
            reply = _keyless_reply(message)
            if reply is not None:
                out_stream.write(json.dumps(reply, separators=(",", ":")) + "\n")
                out_stream.flush()
            continue
        try:
            status, headers, body = _post_json(
                url,
                message,
                authorization=authorization,
                session_id=session_id,
                session_version=session_version,
            )
        except (ValueError, OSError) as exc:
            print(f"mcp transport failed: {exc}", file=err_stream)
            return 1
        header_session = headers.get("mcp-session-id")
        if header_session and not _stateless_version(message):
            session_id = header_session
        if message.get("method") == "initialize" and isinstance(body, dict):
            negotiated = (body.get("result") or {}).get("protocolVersion")
            if isinstance(negotiated, str) and negotiated:
                session_version = negotiated
        if body is None:
            if status >= 400:
                print(f"mcp http {status}", file=err_stream)
                return 1
            continue
        out_stream.write(json.dumps(body, separators=(",", ":")) + "\n")
        out_stream.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
