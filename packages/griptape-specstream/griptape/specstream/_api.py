"""The one SpecStream REST call both drivers make, with the key from the driver or SPECSTREAM_API_KEY."""

from __future__ import annotations

import os
from typing import Any, Optional

import requests

DEFAULT_BASE_URL = "https://api.specstream.ai"
TIMEOUT_SECONDS = 60.0
USER_AGENT = "griptape-specstream/0.1.0"


class SpecStreamError(RuntimeError):
    """A SpecStream call failed. The message is the API's error message or the HTTP status.

    `status_code` is the HTTP status, or None when no request was sent.
    """

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def call(
    path: str,
    body: dict[str, Any],
    *,
    api_key: Optional[str],
    base_url: Optional[str],
    session: Optional[requests.Session] = None,
    timeout: float = TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """POST a JSON body to SpecStream and return the reply's `data` object."""
    key = (api_key or os.environ.get("SPECSTREAM_API_KEY") or "").strip()
    if not key:
        raise SpecStreamError(
            "Set SPECSTREAM_API_KEY or pass api_key. Create a key under Agents & API in your SpecStream workspace."
        )
    base = (base_url or os.environ.get("SPECSTREAM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json", "User-Agent": USER_AGENT}
    response = (session or requests).post(base + path, json=body, headers=headers, timeout=timeout)
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    data = payload.get("data") if isinstance(payload, dict) else None
    error = payload.get("error") if isinstance(payload, dict) else None
    if not response.ok or error or not isinstance(data, dict):
        message = error.get("message") if isinstance(error, dict) else None
        raise SpecStreamError(str(message or f"SpecStream HTTP {response.status_code}"), response.status_code)
    return data
