#
# Copyright (c) 2026, SpecStream SAS
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Live web search, page reading, Deep Search lists and research reports for Pipecat agents.

Pass :meth:`SpecStreamDeepSearch.tools` to an
:class:`~pipecat.processors.aggregators.llm_context.LLMContext` and the LLM
auto-registers the handlers:

Example::

    from pipecat_specstream import SpecStreamDeepSearch

    specstream = SpecStreamDeepSearch(api_key=os.getenv("SPECSTREAM_API_KEY"), max_price_usd=5)
    context = LLMContext(messages=[...], tools=specstream.tools())

A Deep Search list takes from a few seconds to a few minutes, so
``specstream_find_list`` runs as an async function call: the bot keeps talking,
and the rows reach the model when the list is done. Nothing is bought above
``max_price_usd``, which only the developer sets; with ``ask_before_buying``
(the default) the model must first tell the user the price and hear a yes.

:class:`SpecStreamResearch` adds written research reports, with the page behind
each cited sentence; merge its ``function_schemas()`` with the ones above, or
pass its ``tools()`` alone.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
from loguru import logger
from pipecat.adapters.llm.schemas.direct_function import tool_options
from pipecat.adapters.llm.schemas.function_schema import FunctionSchema
from pipecat.adapters.llm.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import FunctionCallResultProperties
from pipecat.services.llm_service import FunctionCallParams

from pipecat_specstream._api import (
    DEFAULT_BASE_URL,
    FINISHED,
    STOPPED,
    SpecStreamClient,
    SpecStreamError,
    dollars,
    list_link,
    request_key,
)

MAX_RESULTS = 1000

FIND_LIST = "specstream_find_list"
PRICE_LIST = "specstream_price_list"
LIST_RESULTS = "specstream_get_list_results"
WEB_SEARCH = "specstream_web_search"
READ_PAGES = "specstream_read_pages"
RESEARCH_PRICE = "specstream_research_price"
START_RESEARCH = "specstream_start_research"
GET_RESEARCH = "specstream_get_research"

# What one report costs at each depth, in cents. The price the API answers is what is charged.
RESEARCH_CENTS = {"quick": 10, "standard": 30, "deep": 100}
RESEARCH_PARTS = {
    "quick": "the question as one part",
    "standard": "the question in 3 to 5 parts",
    "deep": "the question in 6 to 10 parts",
}
RESEARCH_ENDED = frozenset({"completed", "failed", "cancelled", "payment_required"})
QUESTION_MOST_CHARS = 15_000


class SpecStreamDeepSearch:
    """SpecStream tools for a Pipecat voice or multimodal agent.

    :meth:`tools` returns function schemas with their handlers attached:

    - ``specstream_web_search``: one fact or a quick answer from the live web.
    - ``specstream_read_pages``: the text of 1 to 20 known pages.
    - ``specstream_price_list`` (only with ``ask_before_buying``): the most a
      Deep Search list can cost. Nothing runs.
    - ``specstream_find_list``: a Deep Search list of every match, each row with
      the page it was read from. Runs in the background.
    - ``specstream_get_list_results``: the rows of a list again. Free.

    The HTTP session is opened on first use; call :meth:`close` at teardown,
    or use the object as an async context manager.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        max_price_usd: float,
        ask_before_buying: bool = True,
        search_speed: str = "fast",
        rows_in_answer: int = 10,
        wait_secs: float = 420.0,
        poll_secs: float = 3.0,
        locale: str = "en-US",
        base_url: str = DEFAULT_BASE_URL,
        session: aiohttp.ClientSession | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize the tools.

        Args:
            api_key: A SpecStream API key. Read from ``SPECSTREAM_API_KEY`` when unset.
            max_price_usd: The most one Deep Search list may cost, in US dollars.
                The model can't raise it; a list priced above it never starts.
            ask_before_buying: When True, the model must price a list, tell the
                user the price and pass the price the user accepted as
                ``approved_max_usd``. When False, every list within
                ``max_price_usd`` starts without asking.
            search_speed: ``"fast"`` (lowest latency, a good fit for voice) or
                ``"default"`` (the most accurate answer) for ``specstream_web_search``.
            rows_in_answer: How many rows of a list go back to the model; the
                rest stay in the workspace at the list's link.
            wait_secs: How long ``specstream_find_list`` waits for a list to finish
                before it returns the rows found so far.
            poll_secs: How often a running list is read.
            locale: The locale the request is read in.
            base_url: The API root.
            session: An aiohttp session to reuse.
            sleep: Awaitable sleep, replaceable in tests.
            clock: Monotonic clock, replaceable in tests.
        """
        if max_price_usd is None or float(max_price_usd) <= 0:
            raise ValueError("max_price_usd must be greater than 0.")
        self._max_cents = round(float(max_price_usd) * 100)
        self._ask = ask_before_buying
        self._speed = "fast" if search_speed == "fast" else "default"
        self._rows_in_answer = max(1, int(rows_in_answer))
        self._wait_secs = max(0.0, float(wait_secs))
        self._poll_secs = max(0.0, float(poll_secs))
        self._locale = locale
        self._sleep = sleep
        self._clock = clock
        key = api_key if api_key is not None else os.environ.get("SPECSTREAM_API_KEY", "")
        self._client = SpecStreamClient(key, base_url=base_url, session=session)

    async def close(self) -> None:
        """Close the HTTP session this object opened. Safe to call more than once."""
        await self._client.close()

    async def __aenter__(self) -> SpecStreamDeepSearch:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    def tools(self) -> ToolsSchema:
        """The SpecStream tool schemas, handlers attached.

        Returns:
            A ToolsSchema to pass to an ``LLMContext``.
        """
        return ToolsSchema(standard_tools=self.function_schemas())

    def function_schemas(self) -> list[FunctionSchema]:
        """The SpecStream function schemas, to merge with other tools."""
        schemas = [self._web_search_schema(), self._read_pages_schema()]
        if self._ask:
            schemas.append(self._price_list_schema())
        schemas += [self._find_list_schema(), self._list_results_schema()]
        return schemas

    # Schemas

    def _web_search_schema(self) -> FunctionSchema:
        async def handler(params: FunctionCallParams) -> None:
            await self._answer(params, self.web_search(**_args(params, "q", "passages")))

        return FunctionSchema(
            name=WEB_SEARCH,
            description=(
                "Search the live web for one fact or a quick answer: news, prices, opening hours, "
                "who holds a role, anything current or beyond your training. Returns the answer with "
                "the page it came from, matching rows and ranked sources."
            ),
            properties={
                "q": {"type": "string", "description": "The question or search words."},
                "passages": {
                    "type": "boolean",
                    "description": "Also return text passages from the top pages.",
                },
            },
            required=["q"],
            handler=handler,
        )

    def _read_pages_schema(self) -> FunctionSchema:
        async def handler(params: FunctionCallParams) -> None:
            await self._answer(params, self.read_pages(**_args(params, "urls")))

        return FunctionSchema(
            name=READ_PAGES,
            description=(
                "Read the main text, title and published date of 1 to 20 known pages "
                "(web pages, PDF, Word, Excel). Use it when the user gives a link."
            ),
            properties={
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "1 to 20 http or https URLs.",
                }
            },
            required=["urls"],
            handler=handler,
        )

    def _price_list_schema(self) -> FunctionSchema:
        async def handler(params: FunctionCallParams) -> None:
            await self._answer(params, self.price_list(**_args(params, "request", "max_results")))

        return FunctionSchema(
            name=PRICE_LIST,
            description=(
                f"Price a Deep Search list before {FIND_LIST}. Nothing runs and nothing is charged. "
                "Tell the user the maximum price in dollars and ask whether to go ahead; only when "
                f"they say yes, call {FIND_LIST} with the same request and max_results and the "
                "accepted price as approved_max_usd."
            ),
            properties=_list_properties(),
            required=["request"],
            handler=handler,
        )

    def _find_list_schema(self) -> FunctionSchema:
        @tool_options(
            cancel_on_interruption=False,
            timeout_secs=self._wait_secs + 120,
            cancellable_by_llm=True,
        )
        async def handler(params: FunctionCallParams) -> None:
            names = ("request", "max_results", "approved_max_usd")
            await self._answer(params, self.find_list(**_args(params, *names), params=params))

        properties = _list_properties()
        required = ["request"]
        if self._ask:
            properties["approved_max_usd"] = {
                "type": "number",
                "description": (
                    f"The maximum price in dollars from {PRICE_LIST} that the user said yes to."
                ),
            }
            required.append("approved_max_usd")
        return FunctionSchema(
            name=FIND_LIST,
            description=(
                "Find a list of real things on the live web and get every match as a row, each with "
                "the page it was read from: companies in a city, local businesses with a service, "
                "events, grants, tenders, people in a role. Use it when the answer is many things that "
                "meet conditions; for one fact use "
                f"{WEB_SEARCH}. The list runs in the background for up to a few minutes: tell the user "
                "it has started and keep talking; the rows arrive when it is done. Only delivered rows "
                "are charged."
            ),
            properties=properties,
            required=required,
            handler=handler,
        )

    def _list_results_schema(self) -> FunctionSchema:
        async def handler(params: FunctionCallParams) -> None:
            await self._answer(params, self.list_results(**_args(params, "list_id", "start")))

        return FunctionSchema(
            name=LIST_RESULTS,
            description=(
                f"Read the rows of a list from {FIND_LIST} again, for example the next rows after the "
                "first ones. Free."
            ),
            properties={
                "list_id": {"type": "string", "description": f"The list_id from {FIND_LIST}."},
                "start": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "The first row to return, from 0.",
                },
            },
            required=["list_id"],
            handler=handler,
        )

    # Calls, usable without a pipeline

    async def web_search(self, q: str, passages: bool = False) -> dict[str, Any]:
        """Search the live web."""
        return await self._client.web_search(q, speed=self._speed, passages=bool(passages))

    async def read_pages(self, urls: list[str]) -> dict[str, Any]:
        """Read the text of 1 to 20 pages."""
        if isinstance(urls, str):
            urls = [urls]
        return await self._client.extract(list(urls or []), format="text")

    async def price_list(self, request: str, max_results: int = 25) -> dict[str, Any]:
        """Price a list. Nothing runs and nothing is charged."""
        q, count = _clean_request(request), _clean_count(max_results)
        priced = await self._client.price(q, count, locale=self._locale)
        if not priced["runnable"]:
            return _needs_edit(q, priced["read_as"])
        cents = priced["maximum_cents"]
        if cents > self._max_cents:
            return self._over_maximum(q, cents)
        return {
            "status": "priced",
            "request": q,
            "read_as": priced["read_as"],
            "max_results": count,
            "maximum_price_usd": cents / 100,
            "message": (
                f"This list can cost up to {dollars(cents)}; only delivered rows are charged. "
                "Ask the user whether to go ahead."
            ),
        }

    async def find_list(
        self,
        request: str,
        max_results: int = 25,
        approved_max_usd: float | None = None,
        *,
        params: FunctionCallParams | None = None,
    ) -> dict[str, Any]:
        """Start a list within the price ceiling and wait for its rows."""
        q, count = _clean_request(request), _clean_count(max_results)
        if self._ask and approved_max_usd is None:
            return {
                "status": "needs_approval",
                "request": q,
                "message": f"Call {PRICE_LIST} first and ask the user to accept the price.",
            }
        now = time.time()
        found = None
        for at in (now, now - 3600):
            # The same request in this hour or the one before gets the run it already has,
            # so a repeated call never buys the list twice.
            found = await self._client.existing_run(request_key(q, count, self._max_cents, at))
            if found:
                break
        if found:
            find_id = found["find_id"]
            cents = int(found.get("maximum_cents") or 0)
        else:
            priced = await self._client.price(q, count, locale=self._locale)
            if not priced["runnable"]:
                return _needs_edit(q, priced["read_as"])
            cents = priced["maximum_cents"]
            if cents > self._max_cents:
                return self._over_maximum(q, cents)
            if self._ask and cents > round(float(approved_max_usd or 0) * 100):
                return {
                    "status": "price_changed",
                    "request": q,
                    "maximum_price_usd": cents / 100,
                    "message": (
                        f"Nothing ran: the list now costs up to {dollars(cents)}, more than the "
                        f"user accepted. Ask again with the new price."
                    ),
                }
            key = request_key(q, count, self._max_cents, now)
            find_id = await self._client.start(priced, confirm_max_cents=cents, key=key)
        logger.debug(f"SpecStream list {find_id} started for {q!r}")
        if params is not None:
            await params.result_callback(
                {
                    "status": "running",
                    "list_id": find_id,
                    "message": "The list has started. Tell the user the rows will come shortly.",
                },
                properties=FunctionCallResultProperties(is_final=False, run_llm=False),
            )
        deadline = self._clock() + self._wait_secs
        while True:
            result = await self._client.rows(find_id)
            if result["status"] in FINISHED | STOPPED or self._clock() >= deadline:
                break
            await self._sleep(self._poll_secs)
        answer = self._summary(result, 0)
        answer.update({"request": q, "maximum_price_usd": cents / 100})
        if result["status"] not in FINISHED | STOPPED:
            answer["message"] = (
                f"Still running. Call {LIST_RESULTS} with this list_id later for the rest."
            )
        return answer

    async def list_results(self, list_id: str, start: int = 0) -> dict[str, Any]:
        """Read the rows of a list. Free."""
        result = await self._client.rows(str(list_id or "").strip())
        return self._summary(result, max(0, int(start or 0)))

    # Helpers

    def _summary(self, result: dict[str, Any], start: int) -> dict[str, Any]:
        rows = result["rows"]
        shown = rows[start : start + self._rows_in_answer]
        answer = {
            "status": result["status"],
            "list_id": result["list_id"],
            "list_link": list_link(result["list_id"]),
            "row_count": len(rows),
            "rows": shown,
        }
        if start + len(shown) < len(rows):
            answer["more"] = (
                f"{len(rows) - start - len(shown)} more rows: call {LIST_RESULTS} with "
                f"start={start + len(shown)}, or open list_link."
            )
        return answer

    def _over_maximum(self, request: str, cents: int) -> dict[str, Any]:
        return {
            "status": "over_maximum",
            "request": request,
            "maximum_price_usd": cents / 100,
            "message": (
                f"Nothing ran: this list can cost up to {dollars(cents)}, above this agent's limit "
                f"of {dollars(self._max_cents)}. Ask for fewer rows."
            ),
        }

    async def _answer(self, params: FunctionCallParams, call: Awaitable[dict[str, Any]]) -> None:
        await _answer(params, call)


async def _answer(params: FunctionCallParams, call: Awaitable[dict[str, Any]]) -> None:
    """Run a call and hand its result to the model; a failure goes to the model as text."""
    try:
        result: Any = await call
    except (SpecStreamError, ValueError, TypeError) as error:
        logger.warning(f"SpecStream {params.function_name} failed: {error}")
        result = {"status": "error", "error": str(error)}
    await params.result_callback(json.dumps(result, ensure_ascii=False, default=str))


def _list_properties() -> dict[str, Any]:
    return {
        "request": {
            "type": "string",
            "description": (
                "The list in plain words: what to find, where, what every row must meet and the facts "
                'to bring back. Example: "Dental clinics in Lisbon with online booking, with their '
                'website and phone".'
            ),
        },
        "max_results": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_RESULTS,
            "description": "How many rows to find. The price grows with the rows.",
        },
    }


def _args(params: FunctionCallParams, *names: str) -> dict[str, Any]:
    arguments = params.arguments or {}
    return {name: arguments[name] for name in names if arguments.get(name) is not None}


def _clean_request(request: str) -> str:
    q = str(request or "").strip()
    if not q:
        raise ValueError("Describe the list to find.")
    return q


def _clean_count(max_results: Any) -> int:
    return max(1, min(int(max_results or 25), MAX_RESULTS))


def _needs_edit(request: str, read_as: str) -> dict[str, Any]:
    return {
        "status": "needs_edit",
        "request": request,
        "message": (
            f'SpecStream needs a clearer request before it can price it. It read: "{read_as}". '
            "Add the place or what every row must meet."
        ),
    }


class SpecStreamResearch:
    """SpecStream research reports for a Pipecat voice or multimodal agent.

    A report is a written answer from the live web, with the page behind each
    cited sentence. It costs $0.10 (``quick``), $0.30 (``standard``) or $1.00
    (``deep``), charged once, when it is delivered. :meth:`tools` returns:

    - ``specstream_research_price`` (only with ``ask_before_buying``): the price
      of a report at each depth this agent may buy. Nothing runs.
    - ``specstream_start_research``: starts the report and waits for it. Runs in
      the background, so the bot keeps talking.
    - ``specstream_get_research``: a report by its id. Free.

    Example::

        search = SpecStreamDeepSearch(max_price_usd=5)
        research = SpecStreamResearch(max_price_usd=0.30)
        tools = ToolsSchema(standard_tools=search.function_schemas() + research.function_schemas())
        context = LLMContext(tools=tools)
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        max_price_usd: float,
        ask_before_buying: bool = True,
        length: str = "short",
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        sources_in_answer: int = 5,
        wait_secs: float = 900.0,
        poll_secs: float = 5.0,
        base_url: str = DEFAULT_BASE_URL,
        session: aiohttp.ClientSession | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize the tools.

        Args:
            api_key: A SpecStream API key. Read from ``SPECSTREAM_API_KEY`` when unset.
            max_price_usd: The most one report may cost, in US dollars: 0.10 allows
                quick reports, 0.30 also standard ones, 1.00 every depth. The model
                can't raise it.
            ask_before_buying: When True, the model must tell the user the price and
                pass the price the user accepted as ``approved_max_usd``. When False,
                every report within ``max_price_usd`` starts without asking.
            length: ``"short"`` (the default, a good fit for a spoken answer),
                ``"standard"`` or ``"long"``: the length of the text, not of the research.
            include_domains: Read only these sites.
            exclude_domains: Never read these sites.
            sources_in_answer: How many cited pages go back to the model.
            wait_secs: How long ``specstream_start_research`` waits for the report
                before it returns the id to read later.
            poll_secs: How often a running report is read.
            base_url: The API root.
            session: An aiohttp session to reuse.
            sleep: Awaitable sleep, replaceable in tests.
            clock: Monotonic clock, replaceable in tests.
        """
        self._max_cents = round(float(max_price_usd or 0) * 100)
        self._depths = [depth for depth, cents in RESEARCH_CENTS.items() if cents <= self._max_cents]
        if not self._depths:
            raise ValueError("max_price_usd must be at least 0.10, the price of a quick report.")
        if length not in ("short", "standard", "long"):
            raise ValueError('length must be "short", "standard" or "long".')
        self._ask = ask_before_buying
        self._options: dict[str, Any] = {"length": length}
        if include_domains:
            self._options["include_domains"] = list(include_domains)
        if exclude_domains:
            self._options["exclude_domains"] = list(exclude_domains)
        self._sources_in_answer = max(0, int(sources_in_answer))
        self._wait_secs = max(0.0, float(wait_secs))
        self._poll_secs = max(0.0, float(poll_secs))
        self._sleep = sleep
        self._clock = clock
        key = api_key if api_key is not None else os.environ.get("SPECSTREAM_API_KEY", "")
        self._client = SpecStreamClient(key, base_url=base_url, session=session)

    async def close(self) -> None:
        """Close the HTTP session this object opened. Safe to call more than once."""
        await self._client.close()

    async def __aenter__(self) -> SpecStreamResearch:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    def tools(self) -> ToolsSchema:
        """The research tool schemas, handlers attached.

        Returns:
            A ToolsSchema to pass to an ``LLMContext``.
        """
        return ToolsSchema(standard_tools=self.function_schemas())

    def function_schemas(self) -> list[FunctionSchema]:
        """The research function schemas, to merge with other tools."""
        schemas = [self._research_price_schema()] if self._ask else []
        return schemas + [self._start_research_schema(), self._get_research_schema()]

    # Schemas

    def _depth_property(self, description: str) -> dict[str, Any]:
        return {"type": "string", "enum": list(self._depths), "description": description}

    def _research_price_schema(self) -> FunctionSchema:
        async def handler(params: FunctionCallParams) -> None:
            await _answer(params, self.research_price(**_args(params, "depth")))

        return FunctionSchema(
            name=RESEARCH_PRICE,
            description=(
                f"Price a research report before {START_RESEARCH}. Nothing runs and nothing is "
                "charged. Tell the user the price in dollars and ask whether to go ahead; only "
                f"when they say yes, call {START_RESEARCH} with the accepted price as approved_max_usd."
            ),
            properties={"depth": self._depth_property("Without it, the price of each depth.")},
            required=[],
            handler=handler,
        )

    def _start_research_schema(self) -> FunctionSchema:
        @tool_options(
            cancel_on_interruption=False,
            timeout_secs=self._wait_secs + 120,
            cancellable_by_llm=True,
        )
        async def handler(params: FunctionCallParams) -> None:
            names = ("question", "depth", "approved_max_usd")
            await _answer(params, self.start_research(**_args(params, *names), params=params))

        properties: dict[str, Any] = {
            "question": {
                "type": "string",
                "description": (
                    "The question to research, in plain words, with what the report must cover. "
                    'Example: "How do the EU and the US regulate stablecoin reserves?"'
                ),
            },
            "depth": self._depth_property(
                f"How far the report searches and reads, and its price. Default: {self._depths[0]}."
            ),
        }
        required = ["question"]
        if self._ask:
            properties["approved_max_usd"] = {
                "type": "number",
                "description": f"The price in dollars from {RESEARCH_PRICE} that the user said yes to.",
            }
            required.append("approved_max_usd")
        return FunctionSchema(
            name=START_RESEARCH,
            description=(
                "Research a question on the live web and get a written report, with the page behind "
                "each cited sentence. Use it when the answer needs many pages read and compared (a "
                "market, a comparison, a state of the art), not one fact or a list of rows. The "
                "report runs in the background, about a minute for a quick one and up to about "
                "fifteen for a deep one: tell the user it has started and keep talking; the report "
                "arrives when it is done. It is charged once, when it is delivered."
            ),
            properties=properties,
            required=required,
            handler=handler,
        )

    def _get_research_schema(self) -> FunctionSchema:
        async def handler(params: FunctionCallParams) -> None:
            await _answer(params, self.get_research(**_args(params, "research_id")))

        return FunctionSchema(
            name=GET_RESEARCH,
            description=(
                f"Read a research report by the research_id from {START_RESEARCH}: its status while "
                "it runs, the report with its cited pages when it is completed. Free."
            ),
            properties={
                "research_id": {
                    "type": "string",
                    "description": f"The research_id from {START_RESEARCH}.",
                }
            },
            required=["research_id"],
            handler=handler,
        )

    # Calls, usable without a pipeline

    async def research_price(self, depth: str | None = None) -> dict[str, Any]:
        """The price of a report at one depth, or at each depth this agent may buy. Nothing runs."""
        if depth is not None and depth not in RESEARCH_CENTS:
            raise ValueError('depth must be "quick", "standard" or "deep".')
        if depth is not None and depth not in self._depths:
            return self._over_maximum(depth)
        prices = [
            {"depth": name, "price_usd": RESEARCH_CENTS[name] / 100, "researches": RESEARCH_PARTS[name]}
            for name in ([depth] if depth else self._depths)
        ]
        return {
            "status": "priced",
            "prices": prices,
            "message": (
                "A report is charged once, when it is delivered; a failed or cancelled report is "
                "not charged. Ask the user whether to go ahead."
            ),
        }

    async def start_research(
        self,
        question: str,
        depth: str | None = None,
        approved_max_usd: float | None = None,
        *,
        params: FunctionCallParams | None = None,
    ) -> dict[str, Any]:
        """Start a report within the price ceiling and wait for it."""
        q = str(question or "").strip()
        if not q or len(q) > QUESTION_MOST_CHARS:
            raise ValueError("question must be between 1 and 15,000 characters.")
        depth = depth or self._depths[0]
        if depth not in RESEARCH_CENTS:
            raise ValueError('depth must be "quick", "standard" or "deep".')
        if depth not in self._depths:
            return self._over_maximum(depth)
        cents = RESEARCH_CENTS[depth]
        if self._ask and (approved_max_usd is None or cents > round(float(approved_max_usd) * 100)):
            return {
                "status": "needs_approval",
                "question": q,
                "depth": depth,
                "price_usd": cents / 100,
                "message": (
                    f"Nothing ran: a {depth} report costs {dollars(cents)}. Tell the user this "
                    "price and call again with it as approved_max_usd once they accept."
                ),
            }
        body: dict[str, Any] = {"input": q, "depth": depth, **self._options}
        # The same question with the same settings in the same hour gets the report it already
        # started, so a repeated call never buys the report twice.
        hour = time.strftime("%Y-%m-%dT%H", time.gmtime())
        digest = hashlib.sha256(f"{json.dumps(body, sort_keys=True)}|{hour}".encode()).hexdigest()
        run = await self._client.start_research(body, key="pipecat-research-" + digest[:32])
        run_id = str(run.get("id") or "")
        if not run_id:
            raise SpecStreamError("SpecStream started no report.")
        price = run.get("price_usd")
        if price is not None and round(float(price) * 100) > self._max_cents:
            # The API's price is above the one this package knows: stop before a report is delivered.
            await self._client.cancel_research(run_id)
            return self._over_maximum(depth, round(float(price) * 100))
        logger.debug(f"SpecStream research {run_id} started for {q!r}")
        if params is not None:
            await params.result_callback(
                {
                    "status": "running",
                    "research_id": run_id,
                    "message": "The report has started. Tell the user it will come shortly.",
                },
                properties=FunctionCallResultProperties(is_final=False, run_llm=False),
            )
        deadline = self._clock() + self._wait_secs
        while run.get("status") not in RESEARCH_ENDED and self._clock() < deadline:
            await self._sleep(self._poll_secs)
            run = await self._client.research(run_id)
        answer = self._shown(run)
        answer["research_id"] = run_id
        answer.setdefault("price_usd", price if price is not None else cents / 100)
        answer["question"] = q
        if answer["status"] not in RESEARCH_ENDED:
            answer["message"] = f"Still running. Call {GET_RESEARCH} with this research_id later."
        return answer

    async def get_research(self, research_id: str) -> dict[str, Any]:
        """Read a report by its id. Free."""
        run_id = str(research_id or "").strip()
        if not run_id:
            raise ValueError(f"Pass the research_id that {START_RESEARCH} returned.")
        return self._shown(await self._client.research(run_id))

    # Helpers

    def _shown(self, run: dict[str, Any]) -> dict[str, Any]:
        """A report as the model reads it: its state, and the text with its pages when completed."""
        answer: dict[str, Any] = {
            "status": run.get("status"),
            "research_id": run.get("id"),
            "depth": run.get("depth"),
        }
        if run.get("price_usd") is not None:
            answer["price_usd"] = run["price_usd"]
        report = run.get("report")
        if isinstance(report, dict):
            answer["title"] = report.get("title") or ""
            answer["content"] = report.get("content") or ""
            cited = report.get("citations") or []
            answer["citations"] = [
                {key: item.get(key) for key in ("n", "url", "title", "read_at")}
                for item in cited[: self._sources_in_answer]
            ]
            answer["citation_count"] = len(cited)
        for key in ("progress", "error"):
            if run.get(key):
                answer[key] = run[key]
        if run.get("status") == "payment_required":
            answer["message"] = (
                "The balance does not hold this report's price. Add credit at "
                "https://specstream.ai/workspace, then ask again."
            )
        return answer

    def _over_maximum(self, depth: str, cents: int | None = None) -> dict[str, Any]:
        cents = RESEARCH_CENTS[depth] if cents is None else cents
        return {
            "status": "over_maximum",
            "depth": depth,
            "price_usd": cents / 100,
            "message": (
                f"Nothing ran: a {depth} report costs {dollars(cents)}, above this agent's limit of "
                f"{dollars(self._max_cents)}. This agent may buy: {', '.join(self._depths)}."
            ),
        }
