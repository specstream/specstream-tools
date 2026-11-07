"""SpecStream Search API and Extract API as Pydantic AI tools and a toolset."""

from __future__ import annotations

import os
from typing import Any

import httpx
from pydantic_ai import FunctionToolset, Tool

__version__ = "0.1.0"

DEFAULT_BASE_URL = "https://api.specstream.ai"
MAX_EXTRACT_URLS = 20
TIMEOUT_SECONDS = 60.0
USER_AGENT = f"pydantic-ai-specstream/{__version__}"

__all__ = [
    "SpecStreamError",
    "specstream_extract_tool",
    "specstream_search_tool",
    "specstream_toolset",
]


class SpecStreamError(RuntimeError):
    """A SpecStream call failed. The message is the API error message or the HTTP status."""


class _Client:
    def __init__(self, api_key: str | None, base_url: str | None, client: httpx.AsyncClient | None) -> None:
        self._api_key = (api_key or os.environ.get("SPECSTREAM_API_KEY") or "").strip()
        self._base_url = (base_url or os.environ.get("SPECSTREAM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._client = client

    async def call(self, method: str, path: str, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._api_key:
            raise SpecStreamError("Set SPECSTREAM_API_KEY or pass api_key. Create a key under Agents & API in your SpecStream workspace.")
        headers = {"Authorization": f"Bearer {self._api_key}", "Accept": "application/json", "User-Agent": USER_AGENT}
        client = self._client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
        try:
            response = await client.request(method, self._base_url + path, params=params, json=json, headers=headers)
        finally:
            if self._client is None:
                await client.aclose()
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        data = payload.get("data") if isinstance(payload, dict) else None
        if response.is_error or not isinstance(data, dict):
            error = payload.get("error") if isinstance(payload, dict) else None
            message = error.get("message") if isinstance(error, dict) else None
            raise SpecStreamError(str(message or f"SpecStream HTTP {response.status_code}"))
        return data


def specstream_search_tool(
    api_key: str | None = None,
    *,
    base_url: str | None = None,
    client: httpx.AsyncClient | None = None,
    passages: bool = False,
) -> Tool[Any]:
    """A Pydantic AI tool for the Search API (`GET /v1/web-search`, $5 per 1,000 searches).

    `passages=True` adds the text of the top pages to every search. The reply holds `kind`, `answer`,
    `rows`, `sources` and, with passages, `passages`.
    """
    api = _Client(api_key, base_url, client)

    async def specstream_search(q: str) -> dict[str, Any]:
        """Search the live web with SpecStream and return the answer, matching rows and ranked sources.

        Args:
            q: The question or request in everyday words, 1 to 2,000 characters.
        """
        params: dict[str, Any] = {"q": q.strip()[:2000]}
        if passages:
            params["passages"] = "true"
        return await api.call("GET", "/v1/web-search", params=params)

    return Tool(specstream_search, name="specstream_search")


def specstream_extract_tool(
    api_key: str | None = None,
    *,
    base_url: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> Tool[Any]:
    """A Pydantic AI tool for the Extract API (`POST /v1/extract`, $0.80 per 1,000 pages, a page with no text is free)."""
    api = _Client(api_key, base_url, client)

    async def specstream_extract(urls: list[str], format: str = "markdown") -> dict[str, Any]:
        """Read the main text of web pages, PDF, Word and Excel files live with SpecStream.

        Args:
            urls: 1 to 20 http or https URLs to read.
            format: "markdown" (default) or "text".
        """
        cleaned = [url.strip() for url in urls if url and url.strip()][:MAX_EXTRACT_URLS]
        if not cleaned:
            raise SpecStreamError("Send 1 to 20 http or https URLs.")
        body = {"urls": cleaned, "format": "text" if format == "text" else "markdown"}
        return await api.call("POST", "/v1/extract", json=body)

    return Tool(specstream_extract, name="specstream_extract")


def specstream_toolset(
    api_key: str | None = None,
    *,
    base_url: str | None = None,
    client: httpx.AsyncClient | None = None,
    passages: bool = False,
) -> FunctionToolset[Any]:
    """A Pydantic AI toolset with `specstream_search` and `specstream_extract`."""
    return FunctionToolset(
        [
            specstream_search_tool(api_key, base_url=base_url, client=client, passages=passages),
            specstream_extract_tool(api_key, base_url=base_url, client=client),
        ]
    )
