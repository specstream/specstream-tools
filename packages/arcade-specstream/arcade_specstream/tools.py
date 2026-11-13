"""Arcade tools for SpecStream: Deep Search lists, the Search API and the Extract API.

Every tool reads the key from the Arcade secret SPECSTREAM_API_KEY. FindList also reads the secret
SPECSTREAM_MAX_PRICE_USD: the most one list may cost. The developer sets it in Arcade; the model can't raise it.
"""

# No `from __future__ import annotations`: Arcade reads the parameter types at runtime to find the Context.
import asyncio
from typing import Annotated, Any

from arcade_mcp_server import Context, tool
from arcade_mcp_server.exceptions import RetryableToolError, ToolExecutionError
from arcade_mcp_server.metadata import Behavior, Classification, Operation, ServiceDomain, ToolMetadata

from arcade_specstream._api import DEFAULT_BASE_URL, DEFAULT_WAIT_SECONDS, SpecStreamAPI, SpecStreamError

KEY = "SPECSTREAM_API_KEY"
MAX_PRICE = "SPECSTREAM_MAX_PRICE_USD"
MAX_RESULTS = 1000
POLL_SECONDS = 3.0


def _metadata(operation: Operation, *, read_only: bool, idempotent: bool) -> ToolMetadata:
    return ToolMetadata(
        classification=Classification(service_domains=[ServiceDomain.WEB_SCRAPING]),
        behavior=Behavior(
            operations=[operation],
            read_only=read_only,
            destructive=False,
            idempotent=idempotent,
            open_world=True,
        ),
    )


def _api(context: Context) -> SpecStreamAPI:
    try:
        key = context.get_secret(KEY).strip()
    except ValueError:
        key = ""
    if not key:
        raise ToolExecutionError(
            "SpecStream needs an API key.",
            developer_message="Set the Arcade secret SPECSTREAM_API_KEY. Create a key under Agents & API in your SpecStream workspace.",
        )
    return SpecStreamAPI(key, DEFAULT_BASE_URL)


def _max_price_usd(context: Context) -> float:
    try:
        value = float(context.get_secret(MAX_PRICE).strip().lstrip("$"))
    except ValueError:
        value = 0.0
    if not value > 0:
        raise ToolExecutionError(
            "No price ceiling is set for SpecStream lists, so nothing ran.",
            developer_message="Set the Arcade secret SPECSTREAM_MAX_PRICE_USD to the most one list may cost, in US dollars (for example 5).",
        )
    return value


async def _call(func: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(func, *args, **kwargs)
    except ValueError as error:
        raise RetryableToolError(str(error), additional_prompt_content=str(error)) from None
    except SpecStreamError as error:
        raise ToolExecutionError(str(error)) from None


@tool(
    requires_secrets=[KEY, MAX_PRICE],
    metadata=_metadata(Operation.CREATE, read_only=False, idempotent=True),
)
async def find_list(
    context: Context,
    request: Annotated[
        str,
        "The list in plain words: what to find, where, what every row must meet, and the facts to bring back. "
        'Example: "Dental clinics in Lisbon with online booking, with their website and phone".',
    ],
    max_results: Annotated[int, "How many rows to find, from 1 to 1000. The price grows with the matches."] = 25,
) -> Annotated[dict[str, Any], "status, list_id, list_link and rows, each with its columns, source_url and checked_at"]:
    """Find a list of real things on the live web from a plain-English request, with the page each row was read from.

    Use it when the answer is many things that meet conditions: companies in a city, local businesses with a
    service, funding filings, open grants, tenders, clinical trials, repositories, people in a role. For one fact,
    use WebSearch. Rows that couldn't be confirmed are left out and aren't charged. status "over_maximum" means
    nothing ran because the price was above the ceiling: ask for fewer rows or tell the user. status "needs_edit"
    means the request was too vague to price: add the place or the conditions and call again. If the list is still
    running, call GetListResults with its list_id for the rest. The same request within the hour returns the same
    list and is not bought twice.
    """
    api = _api(context)
    ceiling = _max_price_usd(context)
    return await _call(
        api.find_list,
        request,
        max_results=max(1, min(int(max_results), MAX_RESULTS)),
        max_price_usd=ceiling,
        wait_seconds=DEFAULT_WAIT_SECONDS,
        poll_interval=POLL_SECONDS,
    )


@tool(
    requires_secrets=[KEY],
    metadata=_metadata(Operation.READ, read_only=True, idempotent=True),
)
async def get_list_results(
    context: Context,
    list_id: Annotated[str, 'The list_id that FindList returned, like "fnd_gk5y3d0r97bvyz0t08zzh75kr6".'],
) -> Annotated[dict[str, Any], "status, list_id, list_link and every row found so far"]:
    """Read every row found so far for a SpecStream list, such as one that was still running. Reading is free."""
    return await _call(_api(context).results, (list_id or "").strip())


@tool(
    requires_secrets=[KEY],
    metadata=_metadata(Operation.READ, read_only=True, idempotent=True),
)
async def web_search(
    context: Context,
    query: Annotated[str, "Search query or question in everyday words, up to 2,000 characters."],
    passages: Annotated[bool, "Include main text passages from the top matching pages."] = False,
) -> Annotated[dict[str, Any], "answer (value, page and seen_at), matching rows, ranked sources and optional passages"]:
    """Search the live web in seconds with the SpecStream Search API ($5 per 1,000 searches of up to 10 results)."""
    return await _call(_api(context).web_search, query, passages=passages)


@tool(
    requires_secrets=[KEY],
    metadata=_metadata(Operation.READ, read_only=True, idempotent=True),
)
async def extract_pages(
    context: Context,
    urls: Annotated[list[str], "1 to 20 http or https URLs to read live: web pages, PDF, Word or Excel files."],
    format: Annotated[str, 'Output format: "markdown" or "text".'] = "markdown",
) -> Annotated[dict[str, Any], "each page's main text, title and published date"]:
    """Read the main text, title and published date of 1 to 20 URLs live with the SpecStream Extract API ($0.80 per 1,000 pages, empty pages free)."""
    return await _call(_api(context).extract_pages, urls, format=format)
