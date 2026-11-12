"""CrewAI tools that ask SpecStream for a list on the live web and read its rows."""

import asyncio
import json
import os
from typing import Any, Type

from crewai.tools import BaseTool, EnvVar
from pydantic import BaseModel, Field, SecretStr, field_validator

from crewai_specstream._api import DEFAULT_BASE_URL, DEFAULT_WAIT_SECONDS, FINISHED, STOPPED, SpecStreamAPI

KEY_HELP = "Set SPECSTREAM_API_KEY or pass api_key. Create a key under Agents & API in your SpecStream workspace."
MAX_RESULTS = 1000


class FindListInput(BaseModel):
    """What the model fills in. The price ceiling is not here: the developer sets it on the tool."""

    request: str = Field(
        ...,
        description=(
            "The list in plain words: what to find, where, what every row must meet, and the facts to bring back. "
            'Example: "Dental clinics in Lisbon with online booking, with their website and phone".'
        ),
    )
    max_results: int = Field(
        default=25,
        ge=1,
        le=MAX_RESULTS,
        description="How many rows to find, from 1 to 1000. Ask for what the task needs; the price grows with the matches.",
    )


class GetListResultsInput(BaseModel):
    list_id: str = Field(
        ...,
        description='The list_id that specstream_find_list returned, like "fnd_gk5y3d0r97bvyz0t08zzh75kr6".',
    )


class WebSearchInput(BaseModel):
    q: str = Field(min_length=1, max_length=2000, description="Search query or question in everyday words.")
    passages: bool = Field(default=False, description="Include main text passages from the top matching pages.")


class ExtractPagesInput(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=20, description="1 to 20 http or https URLs to read live.")
    format: str = Field(default="markdown", description='Output format: "markdown" or "text".')

def _key_from_env() -> SecretStr:
    key = os.environ.get("SPECSTREAM_API_KEY", "").strip()
    if not key:
        raise ValueError(KEY_HELP)
    return SecretStr(key)


def _cache_finished(_args: Any = None, result: Any = None) -> bool:
    """Cache a list only once it is done; a running, vague or over-the-maximum answer should be asked again."""
    try:
        return json.loads(result).get("status") in FINISHED | STOPPED
    except (TypeError, ValueError, AttributeError):
        return False


def _never_cache(_args: Any = None, _result: Any = None) -> bool:
    return False


class _SpecStreamTool(BaseTool):
    api_key: SecretStr = Field(default_factory=_key_from_env, repr=False)
    """A SpecStream API key. Read from SPECSTREAM_API_KEY when not passed."""
    base_url: str = DEFAULT_BASE_URL
    env_vars: list[EnvVar] = Field(
        default_factory=lambda: [
            EnvVar(name="SPECSTREAM_API_KEY", description="SpecStream API key (Agents & API in your workspace)", required=True)
        ]
    )

    @field_validator("api_key", mode="after")
    @classmethod
    def _key_is_not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError(KEY_HELP)
        return value

    def _api(self) -> SpecStreamAPI:
        return SpecStreamAPI(self.api_key.get_secret_value(), self.base_url)


class SpecStreamFindListTool(_SpecStreamTool):
    """Ask for a list in plain words and get every matching row, each with the page it was read from.

    The list starts only if its price is within ``max_price_usd``, which you set here, in code. The model
    chooses the request and how many rows; it can't raise the price ceiling.

    Example:
        .. code-block:: python

            from crewai_specstream import SpecStreamFindListTool

            tool = SpecStreamFindListTool(max_price_usd=5)
    """

    name: str = "specstream_find_list"
    description: str = (
        "Find a list of real things on the live web from a plain-English request and get back every matching row, "
        "each with the page it was read from. Use it when the answer is many things that meet conditions: companies "
        "in a city, local businesses with a service, funding filings, open grants, tenders, clinical trials, "
        "repositories, people in a role. For one fact or a summary of one page, use a search tool instead. Rows that "
        "couldn't be confirmed are left out and aren't charged. "
        "Returns JSON with status, list_id, list_link and rows (one object per match: its columns, source_url and "
        'checked_at). status "over_maximum" means nothing ran because the price was above the cap: ask for fewer rows '
        'or tell the user. status "needs_edit" means the request was too vague to price: add the place or the '
        "conditions and call again. If the list is still running, call specstream_get_list_results with its list_id "
        "for the rest."
    )
    args_schema: type[BaseModel] = FindListInput

    max_price_usd: float = Field(gt=0)
    """The most one list may cost, in US dollars. If the price is higher, nothing runs."""
    wait_seconds: float = DEFAULT_WAIT_SECONDS
    """How long to wait for the list to finish before returning the rows found so far."""
    poll_interval: float = 3.0
    locale: str = "en-US"

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("cache_function", _cache_finished)
        super().__init__(**kwargs)

    def _run(self, request: str, max_results: int = 25) -> str:
        result = self._api().find_list(
            request,
            max_results=max(1, min(int(max_results), MAX_RESULTS)),
            max_price_usd=self.max_price_usd,
            wait_seconds=self.wait_seconds,
            poll_interval=self.poll_interval,
            locale=self.locale,
        )
        return json.dumps(result, ensure_ascii=False, default=str)

    async def _arun(self, request: str, max_results: int = 25) -> str:
        return await asyncio.to_thread(self._run, request, max_results)


class SpecStreamGetListResultsTool(_SpecStreamTool):
    """Read every row found so far for a list. Reading a list you already have costs nothing."""

    name: str = "specstream_get_list_results"
    description: str = (
        "Read every row found so far for a SpecStream list, such as one that was still running. Use it with the "
        "list_id from specstream_find_list. Reading is free. Returns JSON with status, list_id, list_link and rows, "
        "each with its columns, source_url and checked_at."
    )
    args_schema: type[BaseModel] = GetListResultsInput

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("cache_function", _never_cache)
        super().__init__(**kwargs)

    def _run(self, list_id: str) -> str:
        return json.dumps(self._api().results(list_id.strip()), ensure_ascii=False, default=str)

    async def _arun(self, list_id: str) -> str:
        return await asyncio.to_thread(self._run, list_id)


class SpecStreamWebSearchTool(_SpecStreamTool):
    """Search the live web in seconds with the SpecStream Search API (GET /v1/web-search, $5 per 1,000 searches of up to 10 results, or $1 on the fast tier)."""

    name: str = "specstream_web_search"
    description: str = (
        "Search the live web in seconds with the SpecStream Search API ($5 per 1,000 searches of up to 10 results, or $1 on the fast tier, no quote needed). "
        "Returns JSON with kind ('fact' or 'list'), answer (value, page and seen_at), matching rows, ranked sources and optional passages."
    )
    args_schema: Type[BaseModel] = WebSearchInput

    def _run(self, q: str, passages: bool = False) -> str:
        import json

        return json.dumps(self._api().web_search(q, passages=passages), ensure_ascii=False, default=str)

    async def _arun(self, q: str, passages: bool = False) -> str:
        return await asyncio.to_thread(self._run, q, passages)


class SpecStreamExtractPagesTool(_SpecStreamTool):
    """Read the main text, title and published date of 1 to 20 web pages, PDFs, Word or Excel files live ($0.80 per 1,000 pages)."""

    name: str = "specstream_extract_pages"
    description: str = (
        "Read the main text, title and published date of 1 to 20 URLs (web pages, PDF, Word, Excel) live with the SpecStream Extract API "
        "($0.80 per 1,000 pages, empty pages free, no quote needed)."
    )
    args_schema: Type[BaseModel] = ExtractPagesInput

    def _run(self, urls: list[str], format: str = "markdown") -> str:
        import json

        return json.dumps(self._api().extract_pages(urls, format=format), ensure_ascii=False, default=str)

    async def _arun(self, urls: list[str], format: str = "markdown") -> str:
        return await asyncio.to_thread(self._run, urls, format)

def specstream_tools(max_price_usd: float, **kwargs: Any) -> list[BaseTool]:
    """All four SpecStream tools (Search API, Extract API, Deep Search and row reader), sharing one key and base URL."""
    shared = {key: kwargs.pop(key) for key in ("api_key", "base_url") if key in kwargs}
    return [
        SpecStreamWebSearchTool(**shared),
        SpecStreamExtractPagesTool(**shared),
        SpecStreamFindListTool(max_price_usd=max_price_usd, **shared, **kwargs),
        SpecStreamGetListResultsTool(**shared),
    ]
