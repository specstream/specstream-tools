"""Calls the SpecStream API: Deep Search lists are only read (no spend); Extract reads pages ($0.80 per 1,000);
a research report is started ($0.10, $0.30 or $1.00 by depth) or only read (no spend)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any

from specstream_pinecone import __version__

DEFAULT_API_URL = "https://api.specstream.ai"

# Workspace buttons, not facts.
BUTTON_COLUMNS = {"matches", "open"}

# Most pages one Extract call takes.
EXTRACT_MAX_PAGES = 20

# What a research report costs, by depth, in dollars.
RESEARCH_PRICES = {"quick": 0.10, "standard": 0.30, "deep": 1.00}
# A report in one of these has ended.
RESEARCH_ENDED = {"completed", "failed", "cancelled", "payment_required"}

# (url, headers) -> parsed JSON body for a GET; (url, headers, body) for a POST. Tests pass a scripted one.
Fetch = Callable[..., dict[str, Any]]


class SpecStreamError(RuntimeError):
    """The SpecStream API refused a call."""


def _urllib_fetch(url: str, headers: dict[str, str], body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers = {**headers, "Content-Type": "application/json"}
    request = urllib.request.Request(url, data=data, headers=headers, method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        if exc.code == 401:
            raise SpecStreamError("SpecStream refused the API key (401). Check SPECSTREAM_API_KEY.") from exc
        if exc.code == 402:
            raise SpecStreamError("SpecStream answered 402: the balance or spending limit does not cover this call.") from exc
        raise SpecStreamError(f"SpecStream answered {exc.code} for {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SpecStreamError(f"Could not reach SpecStream: {exc.reason}") from exc


class SpecStreamAPI:
    def __init__(self, api_key: str, api_url: str | None = None, fetch: Fetch | None = None) -> None:
        if not api_key:
            raise SpecStreamError("A SpecStream API key is required (SPECSTREAM_API_KEY).")
        self.api_url = (api_url or DEFAULT_API_URL).rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": f"specstream-pinecone/{__version__}",
        }
        self._fetch = fetch or _urllib_fetch

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.api_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        body = self._fetch(url, self._headers)
        return body.get("data", body)

    def lists(self) -> Iterator[dict[str, Any]]:
        """Every list the key can open, newest first."""
        after: str | None = None
        while True:
            params: dict[str, Any] = {"limit": 100, "sort": "recent"}
            if after:
                params["after"] = after
            page = self._get("/v1/workspace/collections", params)
            yield from page.get("collections") or []
            after = page.get("next_after")
            if not after:
                return

    def list(self, list_id: str) -> dict[str, Any]:
        """One list with all its rows."""
        return self._get(f"/v1/workspace/collections/{urllib.parse.quote(list_id, safe='')}")

    def extract(self, urls: list[str], format: str = "markdown") -> dict[str, Any]:
        """The main text of 1 to 20 pages, read live with POST /v1/extract. Only a page with status "ok" is
        charged ($0.80 per 1,000 pages)."""
        if not 1 <= len(urls) <= EXTRACT_MAX_PAGES:
            raise ValueError(f"Send 1 to {EXTRACT_MAX_PAGES} URLs in one Extract call.")
        body = {"urls": list(urls), "format": "text" if format == "text" else "markdown"}
        answer = self._fetch(f"{self.api_url}/v1/extract", self._headers, body)
        return answer.get("data", answer)

    def start_research(self, question: str, depth: str = "standard", idempotency_key: str | None = None,
                       **options: Any) -> dict[str, Any]:
        """Start a research report with POST /v1/research. It answers at once with the report's `id` and
        `price_usd`; the price is taken once, when the report is delivered. `options` are the other fields of
        the request (`length`, `language`, `include_domains`, `exclude_domains`, `after_date`, `metadata`)."""
        if not question or not question.strip():
            raise ValueError("Give the question the report answers.")
        if depth not in RESEARCH_PRICES:
            raise ValueError("The depth is quick, standard or deep.")
        body = {"input": question, "depth": depth, **{k: v for k, v in options.items() if v not in (None, [], {})}}
        headers = {**self._headers, "Idempotency-Key": idempotency_key} if idempotency_key else self._headers
        return _data(self._fetch(f"{self.api_url}/v1/research", headers, body))

    def research(self, report_id: str) -> dict[str, Any]:
        """One research report with GET /v1/research/{id}. `report` is there once `status` is `completed`."""
        return _data(self._fetch(f"{self.api_url}/v1/research/{urllib.parse.quote(report_id, safe='')}",
                                 self._headers))

    def researches(self) -> Iterator[dict[str, Any]]:
        """Every research report of the account, newest first."""
        after: str | None = None
        while True:
            params: dict[str, Any] = {"limit": 100}
            if after:
                params["after"] = after
            page = _data(self._fetch(f"{self.api_url}/v1/research?{urllib.parse.urlencode(params)}", self._headers))
            yield from page.get("data") or []
            after = page.get("next_after")
            if not after or not page.get("has_more", True):
                return


def _data(body: dict[str, Any]) -> dict[str, Any]:
    """The answer with or without its `data` envelope (the list of reports has a `data` list of its own)."""
    inner = body.get("data")
    return inner if isinstance(inner, dict) else body


def _cell(cell: dict[str, Any]) -> dict[str, Any]:
    provenance = cell.get("provenance") or {}
    shown = cell.get("display")
    if shown is None and cell.get("value") is not None:
        shown = str(cell["value"])
    return {
        "column_id": cell.get("column_id") or "",
        "label": cell.get("label") or cell.get("column_id") or "",
        "value": None if cell.get("absence") else shown,
        "source_url": provenance.get("source_url"),
        "observed_at": provenance.get("observed_at"),
    }


def shape_record(row: dict[str, Any]) -> dict[str, Any]:
    """A list row as one record of plain values.

    Rows SpecStream found have an `ordinal` and `cells`; rows of an imported list have an `id` and the
    columns in `provided`; rows of a combined list have an `id` and each column's values in `field_values`.
    """
    if "provided" in row:
        cells = [
            {"column_id": key, "label": key, "value": None if value is None else str(value),
             "source_url": None, "observed_at": None}
            for key, value in (row.get("provided") or {}).items()
        ]
    elif "field_values" in row:
        cells = [
            _cell({"column_id": key, **entries[0]})
            for key, entries in (row.get("field_values") or {}).items()
            if entries and key not in BUTTON_COLUMNS
        ]
    else:
        cells = [
            _cell(cell)
            for cell in row.get("cells") or []
            if cell.get("column_id") and cell["column_id"] not in BUTTON_COLUMNS
        ]
    entity_id = row.get("entity_id") or next(
        (s["row"]["entity_id"] for s in row.get("sources") or [] if (s.get("row") or {}).get("entity_id")),
        None,
    )
    record_id = row["ordinal"] if row.get("ordinal") is not None else row["id"]
    return {
        "record_id": str(record_id),
        "entity_id": entity_id,
        "fields": {cell["label"]: cell["value"] for cell in cells},
        "cells": cells,
    }
