"""SpecStream's MCP server in the shape Amazon Bedrock AgentCore Runtime runs.

AgentCore Runtime starts the container and sends MCP as stateless Streamable HTTP to
0.0.0.0:8000/mcp, with its own `Mcp-Session-Id` per runtime session. This server answers
there and forwards each JSON-RPC message to SpecStream's hosted MCP server
(https://api.specstream.ai/mcp), with the key from `SPECSTREAM_API_KEY` (set as an
environment variable of the agent runtime). It keeps one upstream session per runtime
session, and opens it itself when a client calls a tool without `initialize` first.

Without a key it still answers `initialize` and `tools/list`, so the AgentCore console and a
gateway can list the tools, and each tool call says how to get a key.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from specstream_mcp_stdio.proxy import (
    MISSING_KEY,
    PROTOCOL_VERSION,
    _keyless_reply,
    _mcp_url,
    _post_json,
    _stateless_version,
    authorization_from_env,
)

HOST = "0.0.0.0"
PORT = 8000
PATH = "/mcp"
MAX_BODY = 4 * 1024 * 1024
CLIENT_INFO = {"name": "specstream-agentcore", "version": "1.0.0"}


class Upstream:
    """One upstream MCP session per AgentCore runtime session id."""

    def __init__(self, url: str, authorization: str | None) -> None:
        self.url = url
        self.authorization = authorization
        self._sessions: dict[str, tuple[str | None, str]] = {}
        self._lock = threading.Lock()

    def forget(self, key: str) -> None:
        with self._lock:
            self._sessions.pop(key, None)

    def _open(self, key: str) -> tuple[str | None, str]:
        assert self.authorization is not None
        hello = {
            "jsonrpc": "2.0",
            "id": "agentcore-init",
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        }
        _, headers, body = _post_json(
            self.url, hello, authorization=self.authorization, session_id=None
        )
        version = ((body or {}).get("result") or {}).get("protocolVersion") or PROTOCOL_VERSION
        session_id = headers.get("mcp-session-id")
        _post_json(
            self.url,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            authorization=self.authorization,
            session_id=session_id,
            session_version=version,
        )
        state = (session_id, version)
        with self._lock:
            self._sessions[key] = state
        return state

    def handle(self, key: str, message: Mapping[str, Any]) -> tuple[int, dict[str, Any] | None]:
        """Answer one JSON-RPC message: (HTTP status, body or None for 202)."""
        if self.authorization is None:
            reply = _keyless_reply(message)
            return (200, reply) if reply is not None else (202, None)
        method = message.get("method")
        if method == "notifications/cancelled" and "id" not in message:
            return 202, None
        if _stateless_version(message):
            status, _, body = _post_json(
                self.url, dict(message), authorization=self.authorization, session_id=None
            )
            return (status, body) if body is not None else (202, None)
        if method == "initialize":
            status, headers, body = _post_json(
                self.url, dict(message), authorization=self.authorization, session_id=None
            )
            version = ((body or {}).get("result") or {}).get("protocolVersion") or PROTOCOL_VERSION
            with self._lock:
                self._sessions[key] = (headers.get("mcp-session-id"), version)
            return status, body
        with self._lock:
            state = self._sessions.get(key)
        if method == "notifications/initialized" and state is None:
            return 202, None
        if state is None:
            state = self._open(key)
        try:
            status, body = self._send(message, state)
        except ValueError as exc:
            if str(exc) != "mcp http 404" or "id" not in message:
                raise
            # The upstream session expired: open a new one and send the message again.
            status, body = self._send(message, self._open(key))
        return (status, body) if body is not None else (202, None)

    def _send(
        self, message: Mapping[str, Any], state: tuple[str | None, str]
    ) -> tuple[int, dict[str, Any] | None]:
        assert self.authorization is not None
        status, _, body = _post_json(
            self.url,
            dict(message),
            authorization=self.authorization,
            session_id=state[0],
            session_version=state[1],
        )
        return status, body


def _error(request_id: Any, code: int, text: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": text}}


def make_handler(upstream: Upstream) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "SpecStreamAgentCore/1.0"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            sys.stderr.write("%s %s\n" % (self.command, self.path.split("?", 1)[0]))

        def _send(self, status: int, body: Any = None) -> None:
            raw = b"" if body is None else json.dumps(body, separators=(",", ":")).encode()
            self.send_response(status)
            if body is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            if raw:
                self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            route = self.path.split("?", 1)[0]
            if route == "/ping":
                self._send(200, {"status": "Healthy"})
            elif route == PATH:
                # Stateless server: no server-to-client stream.
                self._send(405, {"error": "method not allowed"})
            else:
                self._send(404, {"error": "not found"})

        def do_DELETE(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0] != PATH:
                self._send(404, {"error": "not found"})
                return
            upstream.forget(self.headers.get("Mcp-Session-Id") or "")
            self._send(200)

        def do_POST(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0] != PATH:
                self._send(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                self._send(400, _error(None, -32600, "a JSON-RPC body is required"))
                return
            try:
                message = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send(400, _error(None, -32700, "parse error"))
                return
            if not isinstance(message, dict):
                self._send(400, _error(None, -32600, "send one JSON-RPC message per request"))
                return
            key = self.headers.get("Mcp-Session-Id") or ""
            try:
                status, body = upstream.handle(key, message)
            except (ValueError, OSError) as exc:
                if "id" not in message:
                    self._send(202)
                    return
                self._send(502, _error(message.get("id"), -32603, f"SpecStream MCP failed: {exc}"))
                return
            self._send(status, body)

    return Handler


def make_server(
    env: Mapping[str, str] | None = None, host: str = HOST, port: int = PORT
) -> ThreadingHTTPServer:
    environ = env if env is not None else os.environ
    url = _mcp_url(environ)
    try:
        authorization: str | None = authorization_from_env(environ)
    except KeyError:
        authorization = None
        print(MISSING_KEY, file=sys.stderr)
    return ThreadingHTTPServer((host, port), make_handler(Upstream(url, authorization)))


def main() -> int:
    try:
        server = make_server(port=int(os.environ.get("PORT") or PORT))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"SpecStream MCP for AgentCore on {HOST}:{server.server_address[1]}{PATH}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
