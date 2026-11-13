"""LangChain tools that ask SpecStream for a research report: a written answer from the live web,
with the page behind each cited sentence (POST /v1/research)."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
from typing import Any, Literal, Optional

from langchain_core.callbacks import CallbackManagerForToolRun
from pydantic import BaseModel, Field

from langchain_specstream._api import SpecStreamAPI
from langchain_specstream.tools import _SpecStreamTool

Depth = Literal["quick", "standard", "deep"]
# What one report costs at each depth, in US dollars. The API's reply (price_usd) is what counts.
PRICES_USD: dict[str, float] = {"quick": 0.10, "standard": 0.30, "deep": 1.00}
# A run in one of these has ended.
ENDED = {"completed", "failed", "cancelled", "payment_required"}
# A deep report takes about five minutes, so the tool waits a little longer than that by default.
DEFAULT_RESEARCH_WAIT_SECONDS = 420.0
INPUT_MOST_CHARS = 15_000


def research_link(run_id: str) -> str:
    return f"/v1/research/{urllib.parse.quote(run_id, safe='')}"


def shown(run: dict[str, Any]) -> dict[str, Any]:
    """A research run as the model reads it: its state, and the report with its pages when it is completed."""
    out: dict[str, Any] = {"research_id": run.get("id"), "status": run.get("status"), "depth": run.get("depth")}
    if run.get("price_usd") is not None:
        out["price_usd"] = run["price_usd"]
    report = run.get("report")
    if isinstance(report, dict):
        out["title"] = report.get("title") or ""
        out["content"] = report.get("content") or ""
        if report.get("structured") is not None:
            out["structured"] = report["structured"]
        out["citations"] = [
            {key: item.get(key) for key in ("n", "url", "title", "read_at", "excerpt", "supported")}
            for item in report.get("citations") or []
        ]
        out["sources"] = [
            {key: item.get(key) for key in ("n", "url", "title", "read_at", "cited")} for item in report.get("sources") or []
        ]
    for key in ("progress", "usage", "error"):
        if run.get(key):
            out[key] = run[key]
    return out


def get_research(api: SpecStreamAPI, research_id: str) -> dict[str, Any]:
    """Read a research run with GET /v1/research/{id}. Costs nothing."""
    run_id = (research_id or "").strip()
    if not run_id:
        raise ValueError("Pass the research_id that specstream_research returned.")
    return shown(api.request("GET", research_link(run_id)) or {})


def start_research(
    api: SpecStreamAPI,
    question: str,
    *,
    depth: str = "standard",
    wait_seconds: float = DEFAULT_RESEARCH_WAIT_SECONDS,
    poll_interval: float = 5.0,
    options: dict[str, Any] | None = None,
    key_prefix: str = "langchain",
) -> dict[str, Any]:
    """Start a report with POST /v1/research, then read it until it ends or wait_seconds pass."""
    q = (question or "").strip()
    if not q or len(q) > INPUT_MOST_CHARS:
        raise ValueError("input must be between 1 and 15,000 characters.")
    if depth not in PRICES_USD:
        raise ValueError('depth must be "quick", "standard" or "deep".')
    body: dict[str, Any] = {"input": q, "depth": depth, **{k: v for k, v in (options or {}).items() if v not in (None, [], {})}}
    # The same question with the same settings in the same hour gets the report it already started,
    # so a retried agent step never buys the report twice.
    hour = time.strftime("%Y-%m-%dT%H", time.gmtime())
    key = f"{key_prefix}-research-" + hashlib.sha256(f"{json.dumps(body, sort_keys=True)}|{hour}".encode()).hexdigest()[:32]
    created = api.request("POST", "/v1/research", body, headers={"Idempotency-Key": key}) or {}
    run_id = created.get("id")
    if not run_id:
        return shown(created)
    price = created.get("price_usd")
    deadline = api.clock() + max(0.0, wait_seconds)
    while True:
        result = get_research(api, str(run_id))
        if result.get("status") in ENDED or api.clock() >= deadline:
            break
        api.sleep(poll_interval)
    result.setdefault("research_id", run_id)
    if price is not None:
        result.setdefault("price_usd", price)
    result["input"] = q
    if result.get("status") == "payment_required":
        result["message"] = "The balance does not hold this report's price. Add credit at https://specstream.ai/workspace, then ask again."
    elif result.get("status") not in ENDED:
        result["message"] = "Still running. Call specstream_get_research with this research_id for the report."
    return result


class ResearchInput(BaseModel):
    """What the model fills in. The depth, and so the price, is not here: the developer sets it on the tool."""

    input: str = Field(
        min_length=1,
        max_length=INPUT_MOST_CHARS,
        description=(
            "The question to research, in plain words, with what the report must cover. "
            "Example: 'How do the EU and the US regulate stablecoin reserves in 2026?'"
        ),
    )


class GetResearchInput(BaseModel):
    research_id: str = Field(description="The research_id returned by specstream_research.")


class SpecStreamResearch(_SpecStreamTool):
    """Ask a question in plain words and get a written report from the live web, with the page behind each cited sentence.

    A report costs $0.10 (``quick``), $0.30 (``standard``) or $1.00 (``deep``), charged once, when it is delivered.
    You set ``depth`` here, in code. The model writes the question; it can't choose a higher price.

    Example:
        .. code-block:: python

            from langchain_specstream import SpecStreamResearch

            tool = SpecStreamResearch(depth="quick")
            tool.invoke({"input": "How do the EU and the US regulate stablecoin reserves in 2026?"})
    """

    name: str = "specstream_research"
    description: str = (
        "Research a question on the live web and get back a written report in Markdown with numbered citations, "
        "each cited sentence with the page it was read from and when. Use it when the answer needs many pages "
        "read and compared (a market, a comparison, a state of the art, a due-diligence question), not a single "
        "fact or a table of rows. It takes one to five minutes and costs money per report at the depth the "
        "developer set. If the reply says it is still running, call specstream_get_research with its research_id."
    )
    args_schema: type[BaseModel] = ResearchInput

    depth: Depth = "standard"
    """How far the report goes: quick ($0.10), standard ($0.30) or deep ($1.00) a report."""
    length: Optional[Literal["short", "standard", "long"]] = None
    include_domains: Optional[list[str]] = None
    """Read only these sites."""
    exclude_domains: Optional[list[str]] = None
    """Never read these sites."""
    json_schema: Optional[dict[str, Any]] = None
    """A JSON Schema: the report also comes back as JSON that matches it, under ``structured``."""
    wait_seconds: float = DEFAULT_RESEARCH_WAIT_SECONDS
    """How long to wait for the report before returning its research_id to read later."""
    poll_interval: float = 5.0

    def _run(self, input: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        options: dict[str, Any] = {
            "length": self.length,
            "include_domains": self.include_domains,
            "exclude_domains": self.exclude_domains,
            "output": {"type": "json", "schema": self.json_schema} if self.json_schema else None,
        }
        result = start_research(
            self._api(), input, depth=self.depth, wait_seconds=self.wait_seconds, poll_interval=self.poll_interval, options=options
        )
        return json.dumps(result, ensure_ascii=False, default=str)


class SpecStreamGetResearch(_SpecStreamTool):
    """Read a research report by its id: its state while it runs, the report when it is completed. Costs nothing."""

    name: str = "specstream_get_research"
    description: str = (
        "Read a SpecStream research report by the research_id that specstream_research returned: its status and "
        "progress while it runs, and the report with its cited pages when it is completed. Costs nothing."
    )
    args_schema: type[BaseModel] = GetResearchInput

    def _run(self, research_id: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        return json.dumps(get_research(self._api(), research_id), ensure_ascii=False, default=str)
