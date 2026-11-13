"""Writes SpecStream research reports into a Pinecone index, one vector per chunk of a report.

A research report (POST /v1/research) answers a question with a written report from the live web; each cited
sentence carries a `[n]` marker and the page behind it. A chunk's metadata keeps the pages its markers name,
so an answer found in the index still shows where it came from.

A vector id is `research:<report id>#<chunk number>`, apart from the ids of lists, records and pages in the
same index. Writing a report again replaces its chunks. Starting a report is charged ($0.10 quick, $0.30
standard, $1.00 deep, once, when it is delivered); reading a report the account already has costs nothing.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from specstream_pinecone.api import RESEARCH_ENDED, SpecStreamAPI, SpecStreamError
from specstream_pinecone.load import DEFAULT_NAMESPACE, Embed, _ids
from specstream_pinecone.pages import DEFAULT_CHUNK_CHARS, DEFAULT_OVERLAP_CHARS, _write_page, split_text

DEFAULT_WAIT_SECONDS = 900  # A deep report takes about five minutes.
POLL_SECONDS = 5
QUESTION_KEPT_CHARS = 2000
_MARKER = re.compile(r"\[(\d+)\]")


def research_prefix(report_id: str) -> str:
    return f"research:{report_id.replace('#', '_')}#"


def research_chunk_id(report_id: str, chunk: int) -> str:
    return f"{research_prefix(report_id)}{chunk}"


def is_research_loaded(index: Any, report_id: str, namespace: str = DEFAULT_NAMESPACE) -> bool:
    page = index.list_paginated(prefix=research_prefix(report_id), limit=1, namespace=namespace)
    return bool(_ids(page))


def _pages_by_number(report: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """The page behind each `[n]` marker: the report's sources, then its citations for a number no source has."""
    found: dict[int, dict[str, Any]] = {}
    for entry in [*(report.get("sources") or []), *(report.get("citations") or [])]:
        if isinstance(entry.get("n"), int) and entry.get("url"):
            found.setdefault(entry["n"], entry)
    return found


def research_metadata(run: dict[str, Any], loaded_at: datetime, size: int = DEFAULT_CHUNK_CHARS,
                      overlap: int = DEFAULT_OVERLAP_CHARS, question: str | None = None) -> list[dict[str, Any]]:
    """One metadata dict per chunk of a completed report. Pinecone refuses a null metadata value, so a missing
    value is left out."""
    report = run.get("report") or {}
    pages = _pages_by_number(report)
    parts = split_text(report.get("content") or "", size, overlap)
    items = []
    for number, part in enumerate(parts):
        cited = {n: pages[n] for n in dict.fromkeys(int(m) for m in _MARKER.findall(part)) if n in pages}
        item = {
            "kind": "research",
            "report_id": run.get("id") or "",
            "title": report.get("title") or "",
            "question": (question or "")[:QUESTION_KEPT_CHARS] or None,
            "depth": run.get("depth"),
            "completed_at": run.get("completed_at"),
            "chunk": number,
            "chunks": len(parts),
            "text": part,
            "sources": json.dumps({str(n): p["url"] for n, p in cited.items()}, ensure_ascii=False),
            "source_urls": list(dict.fromkeys(p["url"] for p in cited.values())),
            "source_titles": [p.get("title") or "" for p in cited.values()],
            "loaded_at": loaded_at.isoformat(),
        }
        items.append({k: v for k, v in item.items() if v is not None})
    return items


@dataclass
class ResearchResult:
    reports: int = 0
    chunks: int = 0
    # What the reports started in this call cost. Reports only read cost nothing.
    price_usd: float = 0.0
    loaded: list[str] = field(default_factory=list)
    # (report id, status, reason) for each report that was not written.
    skipped: list[tuple[str, str, str | None]] = field(default_factory=list)


def wait_for_research(api: SpecStreamAPI, report_id: str, wait_seconds: float = DEFAULT_WAIT_SECONDS,
                      sleep: Callable[[float], None] = time.sleep,
                      clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    """Read the report until it has ended, or `wait_seconds` have passed. The report goes on at SpecStream
    after the wait ends: load it later by its id."""
    end = clock() + wait_seconds
    while True:
        run = api.research(report_id)
        if run.get("status") in RESEARCH_ENDED:
            return run
        if clock() >= end:
            raise SpecStreamError(f"Report {report_id} is still {run.get('status')} after {int(wait_seconds)} "
                                  f"seconds. It goes on at SpecStream: load it later with --id {report_id}.")
        sleep(POLL_SECONDS)


def load_research(
    api: SpecStreamAPI,
    embed: Embed,
    index: Any = None,
    questions: list[str] | None = None,
    report_ids: list[str] | None = None,
    every: bool = False,
    full: bool = False,
    depth: str = "standard",
    open: Callable[[int], Any] | None = None,
    namespace: str = DEFAULT_NAMESPACE,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    dimension: int | None = None,
    wait_seconds: float = DEFAULT_WAIT_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    **options: Any,
) -> ResearchResult:
    """Write research reports into a Pinecone index.

    `questions`: each starts a new report at `depth` and is charged when delivered ($0.10, $0.30 or $1.00).
    `report_ids`: reports the account already has; only read. `every`: each completed report of the account
    that is not yet in the namespace (with `full`, each completed report again); only read. `options` go to
    the new reports (`length`, `language`, `include_domains`, `exclude_domains`, `after_date`).

    Pass the `index`, or `open`: a function that gets the embedding's vector size and gives the index. A report
    that failed, was cancelled or has no text writes nothing and is reported in `skipped`."""
    split_text("", chunk_chars, overlap_chars)  # Refuse a bad size before anything is started or charged.
    if index is None and open is None:
        raise ValueError("Give the Pinecone index, or a function that opens it.")
    if every and index is None and not full:
        raise ValueError("Loading every report needs the index, to see the reports it already holds.")
    asked = [q.strip() for q in questions or [] if q and q.strip()]
    wanted = list(dict.fromkeys(i.strip() for i in report_ids or [] if i and i.strip()))
    if not (asked or wanted or every):
        raise ValueError("Give a question, a report's id, or every=True.")
    if asked and depth not in ("quick", "standard", "deep"):
        raise ValueError("The depth is quick, standard or deep.")

    def opened(size: int) -> Any:
        assert open is not None
        return open(size)

    result = ResearchResult()
    todo: list[tuple[dict[str, Any], str | None]] = []
    # Every question starts before the first wait, so SpecStream writes the reports side by side.
    started = []
    for question in asked:
        made = api.start_research(question, depth, idempotency_key=f"specstream-pinecone-{uuid.uuid4().hex}",
                                  **options)
        started.append((made["id"], question, float(made.get("price_usd") or 0)))
    for report_id, question, price in started:
        run = wait_for_research(api, report_id, wait_seconds, sleep)
        if run.get("status") == "completed":
            result.price_usd += float((run.get("usage") or {}).get("charged_usd") or price)
        todo.append((run, question))
    todo += [(api.research(report_id), None) for report_id in wanted]
    if every:
        seen = {run.get("id") for run, _ in todo}
        for listed in api.researches():
            if listed.get("status") != "completed" or listed.get("id") in seen:
                continue
            if not full and is_research_loaded(index, listed["id"], namespace):
                continue
            # The list may show a report without its text: then it is read by its id.
            whole = listed if (listed.get("report") or {}).get("content") else api.research(listed["id"])
            todo.append((whole, None))

    for run, question in todo:
        report_id = run.get("id") or ""
        if run.get("status") != "completed":
            reason = (run.get("error") or {}).get("message")
            result.skipped.append((report_id, run.get("status") or "failed", reason))
            continue
        items = research_metadata(run, datetime.now(timezone.utc), chunk_chars, overlap_chars, question)
        if not items:
            result.skipped.append((report_id, "empty", "The report has no text."))
            continue
        index, dimension = _write_page(index, embed, report_id, items, namespace, dimension, opened,
                                       prefix=research_prefix(report_id))
        result.reports += 1
        result.chunks += len(items)
        result.loaded.append(report_id)
    return result
