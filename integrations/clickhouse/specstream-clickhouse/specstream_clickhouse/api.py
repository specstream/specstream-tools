"""Reads Deep Search lists from the SpecStream API. Read-only: it never starts a request or spends."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any

from specstream_clickhouse import __version__

DEFAULT_API_URL = "https://api.specstream.ai"

# Workspace buttons, not facts.
BUTTON_COLUMNS = {"matches", "open"}

# (method, url, headers) -> parsed JSON body. Tests pass a scripted one.
Fetch = Callable[[str, dict[str, str]], dict[str, Any]]


class SpecStreamError(RuntimeError):
    """The SpecStream API refused a call."""


def _urllib_fetch(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        if exc.code == 401:
            raise SpecStreamError("SpecStream refused the API key (401). Check SPECSTREAM_API_KEY.") from exc
        raise SpecStreamError(f"SpecStream answered {exc.code} for {url}: {detail}") from exc


class SpecStreamAPI:
    def __init__(self, api_key: str, api_url: str | None = None, fetch: Fetch | None = None) -> None:
        if not api_key:
            raise SpecStreamError("A SpecStream API key is required (SPECSTREAM_API_KEY).")
        self.api_url = (api_url or DEFAULT_API_URL).rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": f"specstream-clickhouse/{__version__}",
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
