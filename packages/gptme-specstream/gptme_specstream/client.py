"""The two SpecStream calls the gptme tool makes: the Search API and the Extract API."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

__version__ = "0.1.0"

DEFAULT_BASE_URL = "https://api.specstream.ai"
MAX_EXTRACT_URLS = 20
MAX_QUERY_CHARS = 2000
TIMEOUT_SECONDS = 60.0
USER_AGENT = f"gptme-specstream/{__version__}"

# Set by the plugin's init() from gptme's own config ([env] and [plugin.specstream]).
# The process environment is read when init() has not run, as in a plain import.
_settings: dict[str, str] = {}
# A shared client, replaced in tests by one with a mock transport.
_client: httpx.Client | None = None


class SpecStreamError(RuntimeError):
    """A SpecStream call failed. The message is the API error message or the HTTP status.

    `status_code` is the HTTP status, or None when no request was sent.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def configure(api_key: str | None = None, base_url: str | None = None, client: httpx.Client | None = None) -> None:
    """Set the API key, the API address or an `httpx.Client` for every later call. None keeps the current one."""
    global _client
    if api_key is not None:
        _settings["api_key"] = api_key
    if base_url is not None:
        _settings["base_url"] = base_url
    if client is not None:
        _client = client


def reset() -> None:
    """Forget what configure() set."""
    global _client
    _settings.clear()
    _client = None


def _api_key() -> str:
    return (_settings.get("api_key") or os.environ.get("SPECSTREAM_API_KEY") or "").strip()


def _base_url() -> str:
    return (_settings.get("base_url") or os.environ.get("SPECSTREAM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def call(method: str, path: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Send one request and return the `data` object of the reply, or raise SpecStreamError."""
    key = _api_key()
    if not key:
        raise SpecStreamError(
            "Set SPECSTREAM_API_KEY in the environment or in the [env] table of ~/.config/gptme/config.toml. "
            "Create a key under Agents & API in your SpecStream workspace."
        )
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json", "User-Agent": USER_AGENT}
    client = _client or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        response = client.request(method, _base_url() + path, params=params, json=body, headers=headers)
    except httpx.HTTPError as error:
        raise SpecStreamError(f"SpecStream request failed: {error}") from error
    finally:
        if _client is None:
            client.close()
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    data = payload.get("data") if isinstance(payload, dict) else None
    error = payload.get("error") if isinstance(payload, dict) else None
    if response.is_error or error or not isinstance(data, dict):
        message = error.get("message") if isinstance(error, dict) else None
        raise SpecStreamError(str(message or f"SpecStream HTTP {response.status_code}"), response.status_code)
    return data


def as_text(data: dict[str, Any]) -> str:
    """The reply as indented JSON, which the model reads as is."""
    return json.dumps(data, ensure_ascii=False, indent=2)
