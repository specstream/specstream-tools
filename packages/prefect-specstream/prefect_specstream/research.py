"""Research reports as Prefect tasks and one flow: a written answer from the live web, with the
page behind each cited sentence (`POST /v1/research`)."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
from typing import Any, Literal

from prefect import flow, task

from prefect_specstream.credentials import SpecStreamCredentials, SpecStreamError

Depth = Literal["quick", "standard", "deep"]
# What one report costs at each depth, in US dollars. The API's reply (price_usd) is what counts.
PRICES_USD: dict[str, float] = {"quick": 0.10, "standard": 0.30, "deep": 1.00}
# A run in one of these states has ended.
ENDED = frozenset({"completed", "failed", "cancelled", "payment_required"})
MAX_INPUT_CHARS = 15_000
# A deep report takes about five minutes, so the default wait is a little longer than that.
DEFAULT_WAIT_SECONDS = 420.0
DEFAULT_POLL_SECONDS = 5.0
_sleep = time.sleep  # tests replace this one name, not time.sleep for the whole process


def _path(research_id: str) -> str:
    run_id = (research_id or "").strip()
    if not run_id:
        raise SpecStreamError("Pass the research_id that start_research returned.")
    return "/v1/research/" + urllib.parse.quote(run_id, safe="")


def _idempotency_key(body: dict[str, Any]) -> str:
    # The same question with the same settings in the same hour gets the report it already
    # started, so a retried task never buys the report twice.
    hour = time.strftime("%Y-%m-%dT%H", time.gmtime())
    digest = hashlib.sha256(f"{json.dumps(body, sort_keys=True)}|{hour}".encode()).hexdigest()[:32]
    return f"prefect-research-{digest}"


@task(name="specstream-start-research")
def start_research(
    question: str,
    specstream_credentials: SpecStreamCredentials,
    depth: Depth = "standard",
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Start a research report (`POST /v1/research`) and return the run, with its `id`.

    A report costs $0.10 (quick), $0.30 (standard) or $1.00 (deep), charged once, when it is
    delivered. A retry in the same hour with the same question and settings returns the same run.

    Args:
        question: The question to research, in plain words, 1 to 15,000 characters.
        specstream_credentials: The block that holds the API key.
        depth: "quick", "standard" or "deep".
        options: More fields of the request body, as the API reference names them.

    Returns:
        The run: `id`, `status`, `depth` and `price_usd`.
    """
    text = (question or "").strip()
    if not text or len(text) > MAX_INPUT_CHARS:
        raise SpecStreamError("Send the question, 1 to 15,000 characters.")
    if depth not in PRICES_USD:
        raise SpecStreamError('depth must be "quick", "standard" or "deep".')
    extra = {key: value for key, value in (options or {}).items() if value not in (None, [], {})}
    body: dict[str, Any] = {**extra, "input": text, "depth": depth}
    return specstream_credentials.get_client().call(
        "POST", "/v1/research", json=body, headers={"Idempotency-Key": _idempotency_key(body)}
    )


@task(name="specstream-get-research")
def get_research(research_id: str, specstream_credentials: SpecStreamCredentials) -> dict[str, Any]:
    """Read a research run (`GET /v1/research/{id}`). Costs nothing.

    Returns:
        The run: `status`, and when it is completed `report` with `title`, `content` (Markdown),
        `citations` and `sources`.
    """
    return specstream_credentials.get_client().call("GET", _path(research_id))


@task(name="specstream-wait-for-research")
def wait_for_research(
    research_id: str,
    specstream_credentials: SpecStreamCredentials,
    wait_seconds: float = DEFAULT_WAIT_SECONDS,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
) -> dict[str, Any]:
    """Read a research run until it ends, and return it. Reading costs nothing.

    Raises:
        SpecStreamError: the run failed, was cancelled, the balance does not hold its price, or
            it is still running after `wait_seconds`. The message carries the research_id, so
            `get_research` can read the run later.
    """
    client = specstream_credentials.get_client()
    path = _path(research_id)
    deadline = time.monotonic() + max(0.0, wait_seconds)
    while True:
        run = client.call("GET", path)
        status = run.get("status")
        if status in ENDED or time.monotonic() >= deadline:
            break
        _sleep(max(0.0, poll_seconds))
    if status == "completed":
        return run
    if status == "payment_required":
        raise SpecStreamError(
            f"The balance does not hold the price of research {research_id}. "
            "Add credit at https://specstream.ai/workspace, then start it again.",
            402,
        )
    if status in ENDED:
        error = run.get("error")
        detail = error.get("message") if isinstance(error, dict) else error
        raise SpecStreamError(f"Research {research_id} ended as {status}" + (f": {detail}" if detail else "."))
    raise SpecStreamError(
        f"Research {research_id} is still running after {wait_seconds:g} seconds. Read it later with get_research."
    )


@flow(name="specstream-research-report")
def research_report(
    question: str,
    specstream_credentials: SpecStreamCredentials,
    depth: Depth = "standard",
    wait_seconds: float = DEFAULT_WAIT_SECONDS,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Research a question on the live web and return the written report.

    Use it alone or as a subflow. It starts one report, waits until it is written and returns it.

    Returns:
        `research_id`, `depth`, `price_usd`, `title`, `content` (the report in Markdown with
        numbered citations), `citations` (each cited sentence's page, read time and excerpt)
        and `sources`.
    """
    started = start_research(question, specstream_credentials, depth=depth, options=options)
    research_id = str(started.get("id") or "")
    run = wait_for_research(research_id, specstream_credentials, wait_seconds=wait_seconds, poll_seconds=poll_seconds)
    report = run.get("report") if isinstance(run.get("report"), dict) else {}
    result: dict[str, Any] = {
        "research_id": research_id,
        "depth": run.get("depth") or depth,
        "price_usd": run.get("price_usd", started.get("price_usd")),
        "title": report.get("title") or "",
        "content": report.get("content") or "",
        "citations": report.get("citations") or [],
        "sources": report.get("sources") or [],
    }
    if report.get("structured") is not None:
        result["structured"] = report["structured"]
    return result
