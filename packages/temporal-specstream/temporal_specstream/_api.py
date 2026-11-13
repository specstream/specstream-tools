"""The SpecStream REST calls behind the Activities, over httpx."""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.specstream.ai"
USER_AGENT = "temporal-specstream/0.1.0"
KEY_HELP = (
    "Pass api_key to SpecStreamPlugin or set SPECSTREAM_API_KEY on the Worker. "
    "Create a key under Agents & API in your SpecStream workspace."
)
# A later attempt can succeed: the request timed out or was rate limited.
RETRYABLE_STATUS = frozenset({408, 425, 429})


class SpecStreamError(RuntimeError):
    """SpecStream refused a call, or could not be reached.

    ``retryable`` says whether the same call can succeed later.
    """

    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable


def is_retryable(status: int) -> bool:
    """True for a status that a later attempt can turn into an answer."""
    return status in RETRYABLE_STATUS or status >= 500


class SpecStreamClient:
    """A small async client for the Search API and the Extract API.

    ``transport`` replaces the network in tests. Each call opens and closes its own
    connection, so one client is safe on any event loop a Worker runs.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport

    def _key(self) -> str:
        key = (self._api_key or os.environ.get("SPECSTREAM_API_KEY") or "").strip()
        if not key:
            raise SpecStreamError(KEY_HELP)
        return key if key.lower().startswith("bearer ") else f"Bearer {key}"

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """One call. Raises :class:`SpecStreamError`; the message never holds the key."""
        headers = {"Authorization": self._key(), "Accept": "application/json", "User-Agent": USER_AGENT}
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=self._timeout, transport=self._transport
            ) as http:
                response = await http.request(method, path, params=params, json=body, headers=headers)
        except httpx.HTTPError as error:
            raise SpecStreamError(f"Couldn't reach SpecStream: {type(error).__name__}", retryable=True) from None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        status = response.status_code
        if status >= 400:
            raise SpecStreamError(
                f"SpecStream answered {status}: {_message(payload)}", status=status, retryable=is_retryable(status)
            )
        if not isinstance(payload, dict):
            raise SpecStreamError("SpecStream returned a response this package couldn't read.", retryable=True)
        return payload

    async def web_search(self, q: str, *, speed: str = "default", passages: bool = False) -> dict[str, Any]:
        """Search the live web with ``GET /v1/web-search``."""
        query = (q or "").strip()
        if not 1 <= len(query) <= 2000:
            raise SpecStreamError("q must be between 1 and 2,000 characters.")
        params = {"q": query, "speed": "fast" if speed == "fast" else "default"}
        if passages:
            params["passages"] = "true"
        return await self.request("GET", "/v1/web-search", params=params)

    async def extract(self, urls: list[str], *, format: str = "text") -> dict[str, Any]:
        """Read the main text of 1 to 20 URLs with ``POST /v1/extract``."""
        cleaned = [str(u or "").strip() for u in (urls or []) if str(u or "").strip()]
        if not 1 <= len(cleaned) <= 20:
            raise SpecStreamError("Give 1 to 20 http or https URLs.")
        body = {"urls": cleaned, "format": "markdown" if format == "markdown" else "text"}
        return await self.request("POST", "/v1/extract", body=body)


def _message(payload: Any) -> str:
    detail = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(detail, dict):
        return str(detail.get("message") or "request refused")
    if isinstance(detail, str):
        return detail
    return "request refused"
