"""SpecStream Search API and Extract API as a Pydantic AI capability, tools and a toolset."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic_ai import FunctionToolset, ModelRetry, Tool
from pydantic_ai.capabilities import AbstractCapability

__version__ = "0.2.0"

DEFAULT_BASE_URL = "https://api.specstream.ai"
MAX_EXTRACT_URLS = 20
TIMEOUT_SECONDS = 60.0
USER_AGENT = f"pydantic-ai-specstream/{__version__}"

DEFAULT_INSTRUCTIONS = (
    "You can read the live web with SpecStream. Call specstream_search with the question in everyday words "
    "to get an answer, matching rows and ranked sources. Call specstream_extract with 1 to 20 URLs to read "
    "the main text of web pages, PDF, Word and Excel files. Name the source URL of each fact you report."
)
DESCRIPTION = "Live web search and page extraction with SpecStream."
# Statuses that mean the model sent input the API refused, so the model can correct the call.
_BAD_INPUT_STATUSES = frozenset({400, 422})

__all__ = [
    "SpecStreamCapability",
    "SpecStreamError",
    "specstream_extract_tool",
    "specstream_search_tool",
    "specstream_toolset",
]


class SpecStreamError(RuntimeError):
    """A SpecStream call failed. The message is the API error message or the HTTP status.

    `status_code` is the HTTP status, or None when no request was sent.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


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
        error = payload.get("error") if isinstance(payload, dict) else None
        if response.is_error or error or not isinstance(data, dict):
            message = error.get("message") if isinstance(error, dict) else None
            raise SpecStreamError(str(message or f"SpecStream HTTP {response.status_code}"), response.status_code)
        return data


def _search_tool(api: _Client, passages: bool, retry_bad_input: bool) -> Tool[Any]:
    async def specstream_search(q: str) -> dict[str, Any]:
        """Search the live web with SpecStream and return the answer, matching rows and ranked sources.

        Args:
            q: The question or request in everyday words, 1 to 2,000 characters.
        """
        question = q.strip()[:2000]
        if retry_bad_input and not question:
            raise ModelRetry("Send the question in q, 1 to 2,000 characters.")
        params: dict[str, Any] = {"q": question}
        if passages:
            params["passages"] = "true"
        try:
            return await api.call("GET", "/v1/web-search", params=params)
        except SpecStreamError as error:
            if retry_bad_input and error.status_code in _BAD_INPUT_STATUSES:
                raise ModelRetry(str(error)) from error
            raise

    return Tool(specstream_search, name="specstream_search")


def _extract_tool(api: _Client, retry_bad_input: bool) -> Tool[Any]:
    async def specstream_extract(urls: list[str], format: str = "markdown") -> dict[str, Any]:
        """Read the main text of web pages, PDF, Word and Excel files live with SpecStream.

        Args:
            urls: 1 to 20 http or https URLs to read.
            format: "markdown" (default) or "text".
        """
        cleaned = [url.strip() for url in urls if url and url.strip()][:MAX_EXTRACT_URLS]
        if not cleaned:
            if retry_bad_input:
                raise ModelRetry("Send 1 to 20 http or https URLs.")
            raise SpecStreamError("Send 1 to 20 http or https URLs.")
        body = {"urls": cleaned, "format": "text" if format == "text" else "markdown"}
        try:
            return await api.call("POST", "/v1/extract", json=body)
        except SpecStreamError as error:
            if retry_bad_input and error.status_code in _BAD_INPUT_STATUSES:
                raise ModelRetry(str(error)) from error
            raise

    return Tool(specstream_extract, name="specstream_extract")


def specstream_search_tool(
    api_key: str | None = None,
    *,
    base_url: str | None = None,
    client: httpx.AsyncClient | None = None,
    passages: bool = False,
) -> Tool[Any]:
    """A Pydantic AI tool for the Search API (`GET /v1/web-search`, $5 per 1,000 searches of up to 10 results).

    `passages=True` adds the text of the top pages to every search. The reply holds `kind`, `answer`,
    `rows`, `sources` and, with passages, `passages`.
    """
    return _search_tool(_Client(api_key, base_url, client), passages, retry_bad_input=False)


def specstream_extract_tool(
    api_key: str | None = None,
    *,
    base_url: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> Tool[Any]:
    """A Pydantic AI tool for the Extract API (`POST /v1/extract`, $0.80 per 1,000 pages, a page with no text is free)."""
    return _extract_tool(_Client(api_key, base_url, client), retry_bad_input=False)


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


@dataclass
class SpecStreamCapability(AbstractCapability[Any]):
    """Live web search and page extraction for a Pydantic AI agent.

    Adds the `specstream_search` tool (Search API, `GET /v1/web-search`) and the `specstream_extract`
    tool (Extract API, `POST /v1/extract`, 1 to 20 URLs a call) with instructions for when to use each.
    A call the API refuses as bad input (HTTP 400 or 422) goes back to the model as a `ModelRetry`;
    every other failure raises `SpecStreamError`.

        from pydantic_ai import Agent
        from pydantic_ai_specstream import SpecStreamCapability

        agent = Agent('openai:gpt-5', capabilities=[SpecStreamCapability()])

    In an agent spec: `- SpecStreamCapability: {passages: true}` with
    `Agent.from_file('agent.yaml', custom_capability_types=[SpecStreamCapability])`.

    Args:
        api_key: The SpecStream API key. Default: the `SPECSTREAM_API_KEY` environment variable.
        base_url: The API address. Default: `SPECSTREAM_BASE_URL` or `https://api.specstream.ai`.
        search: Add the `specstream_search` tool.
        extract: Add the `specstream_extract` tool.
        passages: Add the text of the top pages to every search.
        instructions: The guidance added to the agent's instructions. `None` or `""` adds none.
        client: A shared `httpx.AsyncClient`. Not available in an agent spec.
        id, description, defer_loading: See `AbstractCapability`. `defer_loading=True` needs an `id`.
    """

    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None
    search: bool = True
    extract: bool = True
    passages: bool = False
    instructions: str | None = DEFAULT_INSTRUCTIONS
    client: httpx.AsyncClient | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not (self.search or self.extract):
            raise ValueError("SpecStreamCapability needs search, extract or both.")
        if self.description is None:
            self.description = DESCRIPTION

    @classmethod
    def from_spec(
        cls,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        search: bool = True,
        extract: bool = True,
        passages: bool = False,
        instructions: str | None = DEFAULT_INSTRUCTIONS,
        id: str | None = None,
        description: str | None = None,
        defer_loading: bool = False,
    ) -> SpecStreamCapability:
        """Build the capability from an agent spec. Leave `api_key` out to read `SPECSTREAM_API_KEY`."""
        return cls(
            api_key=api_key,
            base_url=base_url,
            search=search,
            extract=extract,
            passages=passages,
            instructions=instructions,
            id=id,
            description=description,
            defer_loading=defer_loading,
        )

    def get_instructions(self) -> str | None:
        return self.instructions or None

    def get_toolset(self) -> FunctionToolset[Any]:
        api = _Client(self.api_key, self.base_url, self.client)
        tools: list[Tool[Any]] = []
        if self.search:
            tools.append(_search_tool(api, self.passages, retry_bad_input=True))
        if self.extract:
            tools.append(_extract_tool(api, retry_bad_input=True))
        return FunctionToolset(tools)
