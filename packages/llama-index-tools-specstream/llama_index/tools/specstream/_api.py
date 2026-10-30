"""The SpecStream REST calls the tools share: read a request, price it, start it within a maximum, read its rows."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

DEFAULT_BASE_URL = "https://api.specstream.ai"
USER_AGENT = "llama-index-tools-specstream/0.1.3"
# A list runs for up to about five minutes, so the tools wait a little longer than that by default.
DEFAULT_WAIT_SECONDS = 420.0
FINISHED = {"completed", "partial"}
STOPPED = {"failed", "cancelled", "canceled", "expired"}
# Fields every row carries; a column with the same name is renamed so it can't overwrite them.
RESERVED = {"list_id", "list_link", "position", "source_url", "checked_at"}

Opener = Callable[[urllib.request.Request, float], Any]


class SpecStreamError(RuntimeError):
    """SpecStream refused a call or answered with something this package can't read."""


def _dollars(cents: int) -> str:
    return f"${cents / 100:.2f}"


def list_link(find_id: str) -> str:
    return f"https://specstream.ai/workspace/collections/{urllib.parse.quote(find_id, safe='')}"


def _sources(flat: dict[str, Any]) -> dict[str, Any]:
    """Each value's page in the API's flat row: <field>_source beside the <field> it belongs to."""
    return {key: value for key, value in flat.items() if key.endswith("_source") and key[: -len("_source")] in flat}


def flatten_row(find_id: str, record: dict[str, Any], flat: dict[str, Any] | None = None) -> dict[str, Any]:
    """One row as flat fields: each column's label holds what the list shows. The page of each value
    (<field>_source) and of the fact that put the row in the list (source_url, checked_at) come from
    the API's flat row, so every tool shows the same pages."""
    flat = flat or {}
    sources = _sources(flat)
    row: dict[str, Any] = {"list_id": find_id, "position": record.get("ordinal")}
    for cell in record.get("details") or record.get("cells") or []:
        label = str(cell.get("label") or cell.get("column_id") or "").strip()
        if not label:
            continue
        if label in RESERVED or label in sources:
            label = f"{label} (column)"
        if cell.get("absence"):
            value: Any = ""
        elif cell.get("display") is not None:
            value = cell["display"]
        else:
            value = cell.get("value") if cell.get("value") is not None else ""
        row[label] = value
    row.update(sources)
    row["source_url"] = flat.get("source_url") or ""
    row["checked_at"] = flat.get("checked_at") or ""
    row["list_link"] = list_link(find_id)
    return row


@dataclass
class SpecStreamAPI:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    timeout: float = 150.0
    opener: Opener | None = None
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic

    def request(self, method: str, path: str, body: dict[str, Any] | None = None, *, allow_404: bool = False) -> dict[str, Any] | None:
        key = (self.api_key or "").strip()
        if not key:
            raise SpecStreamError("Set SPECSTREAM_API_KEY or pass api_key. Create a key under Agents & API in your SpecStream workspace.")
        request = urllib.request.Request(
            self.base_url.rstrip("/") + path,
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers={
                "Authorization": key if key.lower().startswith("bearer ") else f"Bearer {key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        open_ = self.opener or (lambda req, timeout: urllib.request.urlopen(req, timeout=timeout))
        try:
            response = open_(request, self.timeout)
            try:
                raw = response.read()
            finally:
                response.close()
        except urllib.error.HTTPError as error:
            if allow_404 and error.code == 404:
                return None
            raise SpecStreamError(_error_message(error)) from None
        except urllib.error.URLError as error:
            raise SpecStreamError(f"Couldn't reach SpecStream: {error.reason}") from None
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            payload = None
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise SpecStreamError("SpecStream returned a response this package couldn't read.")
        return payload["data"]

    def results(self, find_id: str) -> dict[str, Any]:
        """Every row found so far for a list, following the pages."""
        rows: list[dict[str, Any]] = []
        cursor: str | None = None
        status = "running"
        while True:
            query = {"limit": "100", **({"cursor": cursor} if cursor else {})}
            page = self.request("GET", f"/v1/finds/{urllib.parse.quote(find_id, safe='')}/rows?{urllib.parse.urlencode(query)}") or {}
            status = page.get("status") or status
            flat = {str(item.get("id")): item for item in page.get("flat_rows") or []}
            rows.extend(
                flatten_row(find_id, record, flat.get(f"{find_id}:{record.get('entity_id')}"))
                for record in page.get("rows") or []
            )
            cursor = page.get("next_cursor")
            if not cursor:
                break
        return {"list_id": find_id, "status": status, "list_link": list_link(find_id), "row_count": len(rows), "rows": rows}

    def find_list(
        self,
        request: str,
        *,
        max_results: int,
        max_price_usd: float,
        wait_seconds: float = DEFAULT_WAIT_SECONDS,
        poll_interval: float = 3.0,
        locale: str = "en-US",
        key_prefix: str = "llamaindex",
    ) -> dict[str, Any]:
        q = (request or "").strip()
        if not q:
            raise ValueError("Describe the list to find.")
        if not isinstance(max_results, int) or max_results < 1:
            raise ValueError("max_results must be 1 or more.")
        max_cents = round(float(max_price_usd) * 100)
        if max_cents <= 0:
            raise ValueError("max_price_usd must be greater than 0.")

        # The same request with the same limits gets the run it already started in this hour or the one before,
        # so a retried agent step never buys the list twice, even across the turn of the hour.
        def key_for(at: float) -> str:
            hour = time.strftime("%Y-%m-%dT%H", time.gmtime(at))
            return f"{key_prefix}-" + hashlib.sha256(f"{q}|{max_results}|{max_cents}|{hour}".encode()).hexdigest()[:32]

        now = time.time()
        request_key = key_for(now)
        existing = None
        for candidate in (request_key, key_for(now - 3600)):
            existing = self.request("GET", f"/v1/capacity/requests/{urllib.parse.quote(candidate, safe='')}", allow_404=True)
            if existing and existing.get("find_id"):
                break
        if existing and existing.get("find_id"):
            find_id = existing["find_id"]
            maximum_cents = int(existing.get("maximum_cents") or max_cents)
        else:
            reading = self.request("POST", "/v1/parse", {"q": q, "locale": locale}) or {}
            if reading.get("status") != "runnable":
                read_as = reading.get("canonical_sentence") or q
                return {
                    "status": "needs_edit",
                    "request": q,
                    "message": f'SpecStream needs a clearer request before it can price it. It read: "{read_as}". Add the place or what every row must meet.',
                }
            quote = self.request(
                "POST", "/v1/capacity/quotes", {"ast_hash": reading["ast_hash"], "operation": "find", "requested_units": max_results}
            ) or {}
            maximum_cents = int(quote.get("maximum_cents") or 0)
            if maximum_cents > max_cents:
                return {
                    "status": "over_maximum",
                    "request": q,
                    "maximum_price_usd": maximum_cents / 100,
                    "message": f"Nothing ran: this list can cost up to {_dollars(maximum_cents)}, above the maximum of {_dollars(max_cents)}. Ask for fewer results or raise max_price_usd.",
                }
            run = self.request(
                "POST",
                "/v1/capacity/executions",
                {"quote_id": quote["quote_id"], "quote_hash": quote["quote_hash"], "confirm_max_cents": maximum_cents, "idempotency_key": request_key},
            ) or {}
            find_id = run["find_id"]

        deadline = self.clock() + max(0.0, wait_seconds)
        while True:
            result = self.results(find_id)
            if result["status"] in FINISHED | STOPPED or self.clock() >= deadline:
                break
            self.sleep(poll_interval)
        result.update({"request": q, "maximum_price_usd": maximum_cents / 100})
        if result["status"] not in FINISHED | STOPPED:
            result["message"] = "Still running. Call specstream_get_list_results with this list_id for the rest."
        return result


def _error_message(error: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(error.read() or b"{}")
    except ValueError:
        payload = {}
    detail = payload.get("error") if isinstance(payload, dict) else None
    message = detail.get("message") if isinstance(detail, dict) else detail if isinstance(detail, str) else None
    return f"SpecStream answered {error.code}: {message or error.reason}"
