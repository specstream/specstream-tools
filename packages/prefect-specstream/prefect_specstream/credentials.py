"""The SpecStream credentials block and the small HTTP client the tasks share."""

from __future__ import annotations

import os
from typing import Any

import httpx
from prefect.blocks.abstract import CredentialsBlock
from pydantic import Field, SecretStr

from prefect_specstream._version import __version__

DEFAULT_BASE_URL = "https://api.specstream.ai"
TIMEOUT_SECONDS = 60.0
USER_AGENT = f"prefect-specstream/{__version__}"


class SpecStreamError(RuntimeError):
    """A SpecStream call failed. The message is the API error message or the HTTP status.

    `status_code` is the HTTP status, or None when no request was sent.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SpecStreamClient:
    """Calls the SpecStream API with one key. Pass `transport` to replace the network (tests)."""

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, transport: httpx.BaseTransport | None = None) -> None:
        self._api_key = (api_key or "").strip()
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._transport = transport

    def call(
        self, method: str, path: str, *, json: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        if not self._api_key:
            raise SpecStreamError("The SpecStream API key is empty. Create a key under Agents & API in your SpecStream workspace.")
        sent = {**(headers or {}), "Authorization": f"Bearer {self._api_key}", "Accept": "application/json", "User-Agent": USER_AGENT}
        with httpx.Client(timeout=TIMEOUT_SECONDS, transport=self._transport) as client:
            response = client.request(method, self._base_url + path, json=json, headers=sent)
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


class SpecStreamCredentials(CredentialsBlock):
    """Holds a SpecStream API key for the SpecStream tasks.

    Example:
        ```python
        from prefect_specstream import SpecStreamCredentials

        SpecStreamCredentials(api_key="ss_live_...").save("specstream")
        credentials = SpecStreamCredentials.load("specstream")
        ```
    """

    _block_type_name = "SpecStream Credentials"
    _block_type_slug = "specstream-credentials"
    _documentation_url = "https://specstream.ai/docs/api"

    api_key: SecretStr = Field(
        default_factory=lambda: SecretStr(os.environ.get("SPECSTREAM_API_KEY", "")),
        description="A SpecStream API key (Agents & API in your SpecStream workspace). Defaults to SPECSTREAM_API_KEY.",
    )
    base_url: str = Field(default=DEFAULT_BASE_URL, description="The SpecStream API address.")

    def get_client(self, transport: httpx.BaseTransport | None = None) -> SpecStreamClient:
        """A client that calls SpecStream with this key."""
        return SpecStreamClient(self.api_key.get_secret_value(), self.base_url, transport=transport)
