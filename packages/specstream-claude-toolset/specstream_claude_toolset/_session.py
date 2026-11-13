"""The SpecStream browser-session calls the driver makes: open a session and end it.

Two calls, so the standard library's HTTP client serves them and the package adds no HTTP dependency.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

BASE_URL = "https://api.specstream.ai"
USER_AGENT = "specstream-claude-toolset/0.1.0"
KEY_ENV = "SPECSTREAM_API_KEY"
# A session's create call waits for a browser to start.
REQUEST_TIMEOUT_S = 150.0

Send = Callable[[str, dict[str, Any], dict[str, str]], "tuple[int, bytes]"]
"""`(url, json body, headers) -> (status, body)`: one POST. Replace it to use your own HTTP client."""


class SpecStreamError(Exception):
    """SpecStream refused a call, or answered with something this driver cannot read."""


def _post(url: str, body: dict[str, Any], headers: dict[str, str]) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:  # noqa: S310 - https, checked below
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def _message(raw: bytes) -> str:
    text = raw.decode("utf-8", "replace")
    try:
        body = json.loads(text)
    except ValueError:
        return text[:300]
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:300]
        for field in ("message", "detail", "error"):
            if isinstance(body.get(field), str):
                return body[field][:300]
    return text[:300]


class SessionClient:
    """`POST /v1/browser/sessions` and `POST /v1/browser/sessions/{id}/release`, with an API key."""

    def __init__(self, api_key: str | None = None, *, base_url: str | None = None, send: Send | None = None) -> None:
        key = (api_key or os.environ.get(KEY_ENV, "")).strip()
        if not key:
            raise SpecStreamError(
                f"No SpecStream API key. Pass api_key, or set {KEY_ENV}. Keys: https://specstream.ai/workspace"
            )
        self._key = key if key.lower().startswith("bearer ") else f"Bearer {key}"
        self._base_url = (base_url or BASE_URL).rstrip("/")
        if urllib.parse.urlsplit(self._base_url).scheme not in ("http", "https"):
            raise SpecStreamError("base_url is an http or https address.")
        self._send = send or _post

    def _call(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": self._key,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
        try:
            status, raw = self._send(self._base_url + path, body, headers)
        except SpecStreamError:
            raise
        except Exception as error:
            raise SpecStreamError(f"SpecStream did not answer: {type(error).__name__}") from error
        if status >= 400:
            raise SpecStreamError(f"SpecStream answered {status}: {_message(raw)}")
        try:
            data = json.loads(raw)
        except ValueError as error:
            raise SpecStreamError("SpecStream answered with something that is not JSON.") from error
        if not isinstance(data, dict):
            raise SpecStreamError("SpecStream answered with something that is not a session.")
        return data

    def open(self, options: dict[str, Any]) -> dict[str, Any]:
        session = self._call("/v1/browser/sessions", options)
        if not session.get("id") or not session.get("connect_url"):
            raise SpecStreamError("SpecStream opened a session without an id or a connect_url.")
        return session

    def release(self, session_id: str) -> dict[str, Any]:
        return self._call(f"/v1/browser/sessions/{urllib.parse.quote(session_id, safe='')}/release", {})
