"""The SpecStream tool spec: live web data for a LlamaIndex agent, within a price set in code."""

# No `from __future__ import annotations`: LlamaIndex reads these signatures at runtime to build the tool schema.
import json
import os
from typing import Annotated, Optional

from llama_index.core.tools.tool_spec.base import BaseToolSpec
from pydantic import Field

from llama_index.tools.specstream._api import DEFAULT_BASE_URL, DEFAULT_WAIT_SECONDS, SpecStreamAPI

MAX_RESULTS = 1000


def _api(api_key: Optional[str], base_url: str) -> SpecStreamAPI:
    return SpecStreamAPI(api_key=api_key or os.environ.get("SPECSTREAM_API_KEY", ""), base_url=base_url)


class SpecStreamToolSpec(BaseToolSpec):
    """Two tools that let an agent find a list on the live web and read its rows.

    The price cap is set here, in code, and is not a tool argument, so the model can't raise it.

    Example:
        .. code-block:: python

            from llama_index.core.agent.workflow import FunctionAgent
            from llama_index.tools.specstream import SpecStreamToolSpec

            tools = SpecStreamToolSpec(max_price_usd=5).to_tool_list()
            agent = FunctionAgent(tools=tools, llm=llm)
    """

    spec_functions = ["specstream_web_search", "specstream_extract_pages", "specstream_find_list", "specstream_get_list_results"]

    def __init__(
        self,
        *,
        max_price_usd: float,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        wait_seconds: float = DEFAULT_WAIT_SECONDS,
        poll_interval: float = 3.0,
        locale: str = "en-US",
    ) -> None:
        """
        Args:
            max_price_usd: The most one list may cost, in US dollars. Above it, nothing runs and the tool returns the price.
            api_key: A SpecStream API key. Defaults to the SPECSTREAM_API_KEY environment variable.
            base_url: The SpecStream API address.
            wait_seconds: How long find_list waits for the list before returning the rows found so far.
            poll_interval: Seconds between checks while a list is running.
            locale: The language and region the request is written in.
        """
        if not max_price_usd or float(max_price_usd) <= 0:
            raise ValueError("max_price_usd must be greater than 0.")
        self.max_price_usd = float(max_price_usd)
        self.wait_seconds = wait_seconds
        self.poll_interval = poll_interval
        self.locale = locale
        self._client = _api(api_key, base_url)
        if not self._client.api_key.strip():
            raise ValueError("Set SPECSTREAM_API_KEY or pass api_key. Create a key under Agents & API in your SpecStream workspace.")


    def specstream_web_search(
        self,
        q: Annotated[str, Field(description="Search query or question in everyday words (1 to 2,000 characters).")],
        passages: Annotated[bool, Field(description="Set True to include main text passages from the top matching pages.")] = False,
    ) -> str:
        """Search the live web in seconds with the SpecStream Search API (GET /v1/web-search, $5 per 1,000 searches of up to 10 results, or $1 on the fast tier, no quote needed)."""
        return json.dumps(self._client.web_search(q, passages=passages), ensure_ascii=False)

    def specstream_extract_pages(
        self,
        urls: Annotated[list[str], Field(description="1 to 20 http or https URLs (web pages, PDF, Word, Excel) to read live.")],
        format: Annotated[str, Field(description='Output format: "markdown" (default) or "text".')] = "markdown",
    ) -> str:
        """Read the main text, title and published date of 1 to 20 URLs live with the SpecStream Extract API (POST /v1/extract, $0.80 per 1,000 pages)."""
        return json.dumps(self._client.extract_pages(urls, format=format), ensure_ascii=False)
    def specstream_find_list(
        self,
        request: Annotated[
            str,
            Field(
                description=(
                    "The list in plain words: what to find, where, what every row must meet, and the facts to bring back. "
                    'Example: "Dental clinics in Lisbon with online booking, with their website and phone".'
                )
            ),
        ],
        max_results: Annotated[
            int,
            Field(description="How many rows to find, from 1 to 1000. Ask for what the task needs; the price grows with the matches."),
        ] = 25,
    ) -> str:
        """Find a list of real things on the live web and return every matching row, each with the page it was read from.

        Use it when the answer is many things that meet conditions: companies in a city, local businesses with a service,
        funding filings, open grants, tenders, clinical trials, repositories, people in a role. For one fact or a summary
        of one page, use a search tool instead. Rows that couldn't be confirmed are left out and aren't charged.

        Returns JSON with status, list_id, list_link and rows (one object per match: its columns, source_url and
        checked_at). status "over_maximum" means nothing ran because the price was above the cap: ask for fewer rows or
        tell the user. status "needs_edit" means the request was too vague to price: add the place or the conditions.
        If the list is still running, call specstream_get_list_results with its list_id for the rest.
        """
        count = max(1, min(int(max_results), MAX_RESULTS))
        result = self._client.find_list(
            request,
            max_results=count,
            max_price_usd=self.max_price_usd,
            wait_seconds=self.wait_seconds,
            poll_interval=self.poll_interval,
            locale=self.locale,
            key_prefix="llamaindex",
        )
        return json.dumps(result, ensure_ascii=False)

    def specstream_get_list_results(
        self,
        list_id: Annotated[
            str,
            Field(description='The list_id that specstream_find_list returned, like "fnd_gk5y3d0r97bvyz0t08zzh75kr6".'),
        ],
    ) -> str:
        """Read every row found so far for a SpecStream list, such as one that was still running. Reading is free.

        Returns JSON with status, list_id, list_link and rows, each with its columns, source_url and checked_at.
        """
        return json.dumps(self._client.results(list_id.strip()), ensure_ascii=False)
