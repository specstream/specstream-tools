"""The SpecStream REST calls the resource makes: search, extract, and a Deep Search list run within a maximum price."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

DEFAULT_BASE_URL = "https://api.specstream.ai"
USER_AGENT = "dagster-specstream/0.1.0"
# A list runs for up to about five minutes, so a task waits a little longer than that by default.
DEFAULT_WAIT_SECONDS = 420.0
FINISHED = {"completed", "partial"}
STOPPED = {"failed", "cancelled", "canceled", "expired"}
# Fields every row carries; a column with the same name is renamed so it can't overwrite them.
RESERVED = {"list_id", "list_link", "position", "source_url", "checked_at"}
SPEEDS = {"default", "fast"}

Opener = Callable[[urllib.request.Request, float], Any]


def _urlopen(request: urllib.request.Request, timeout: float) -> Any:
    return urllib.request.urlopen(request, timeout=timeout)


class SpecStreamError(RuntimeError):
    """SpecStream refused a call or answered with something this package can't read."""


def _dollars(cents: int) -> str:
    return f"${cents / 100:.2f}"


def list_link(find_id: str) -> str:
    return f"https://specstream.ai/workspace/collections/{urllib.parse.quote(find_id, safe='')}"


def flatten_row(find_id: str, record: dict[str, Any], flat: dict[str, Any] | None = None) -> dict[str, Any]:
    """One row as flat fields: each column's label holds what the list shows, and each value's page
    (<field>_source) plus the page that put the row in the list (source_url, checked_at)."""
    flat = flat or {}
    sources = {k: v for k, v in flat.items() if k.endswith("_source") and k[: -len("_source")] in flat}
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
            raise SpecStreamError(
                "The SpecStream connection has no API key. Put the key in the connection's API key (password) field; "
                "create one under Agents & API in your SpecStream workspace."
            )
        request = urllib.request.Request(
            (self.base_url or DEFAULT_BASE_URL).rstrip("/") + path,
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers={
                "Authorization": key if key.lower().startswith("bearer ") else f"Bearer {key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        open_ = self.opener or _urlopen
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

    def web_search(
        self,
        q: str,
        *,
        passages: bool = False,
        speed: str = "default",
        num: int | None = None,
        news: bool = False,
        country: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """GET /v1/web-search: $5 per 1,000 searches of up to 10 results, $1 per 1,000 with speed="fast"."""
        query = (q or "").strip()
        if not query or len(query) > 2000:
            raise ValueError("q must be between 1 and 2,000 characters.")
        if speed not in SPEEDS:
            raise ValueError('speed must be "default" or "fast".')
        params: dict[str, str] = {"q": query}
        if passages:
            params["passages"] = "true"
        if speed != "default":
            params["speed"] = speed
        if num is not None:
            if not 1 <= int(num) <= 200:
                raise ValueError("num must be between 1 and 200.")
            params["num"] = str(int(num))
        if news:
            params["news"] = "true"
        if country:
            params["country"] = country
        if language:
            params["language"] = language
        return self.request("GET", f"/v1/web-search?{urllib.parse.urlencode(params)}") or {}

    def extract_pages(self, urls: list[str], *, format: str = "markdown") -> dict[str, Any]:
        """POST /v1/extract: the main text of 1 to 20 URLs, $0.80 per 1,000 pages; a page with no text is free."""
        cleaned = [str(u or "").strip() for u in (urls or []) if str(u or "").strip()]
        if not 1 <= len(cleaned) <= 20:
            raise ValueError("Provide 1 to 20 http or https URLs.")
        fmt = "text" if format == "text" else "markdown"
        return self.request("POST", "/v1/extract", {"urls": cleaned, "format": fmt}) or {}

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
                flatten_row(find_id, record, flat.get(f"{find_id}:{record.get('entity_id')}")) for record in page.get("rows") or []
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
        idempotency_key: str,
        wait_seconds: float = DEFAULT_WAIT_SECONDS,
        poll_interval: float = 5.0,
        locale: str = "en-US",
    ) -> dict[str, Any]:
        """A Deep Search list. The same idempotency_key returns the run it already started, so a retried
        task never buys the list twice. Nothing runs when the quote is above max_price_usd."""
        q = (request or "").strip()
        if not q:
            raise ValueError("Describe the list to find.")
        if not isinstance(max_results, int) or max_results < 1:
            raise ValueError("max_results must be 1 or more.")
        max_cents = round(float(max_price_usd) * 100)
        if max_cents <= 0:
            raise ValueError("max_price_usd must be greater than 0.")
        if not idempotency_key:
            raise ValueError("idempotency_key is required.")

        existing = self.request("GET", f"/v1/capacity/requests/{urllib.parse.quote(idempotency_key, safe='')}", allow_404=True)
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
            quote = (
                self.request("POST", "/v1/capacity/quotes", {"ast_hash": reading["ast_hash"], "operation": "find", "requested_units": max_results})
                or {}
            )
            maximum_cents = int(quote.get("maximum_cents") or 0)
            if maximum_cents > max_cents:
                return {
                    "status": "over_maximum",
                    "request": q,
                    "maximum_price_usd": maximum_cents / 100,
                    "message": f"Nothing ran: this list can cost up to {_dollars(maximum_cents)}, above the maximum of {_dollars(max_cents)}. Ask for fewer results or raise max_price_usd.",
                }
            run = (
                self.request(
                    "POST",
                    "/v1/capacity/executions",
                    {
                        "quote_id": quote["quote_id"],
                        "quote_hash": quote["quote_hash"],
                        "confirm_max_cents": maximum_cents,
                        "idempotency_key": idempotency_key,
                    },
                )
                or {}
            )
            find_id = run["find_id"]

        deadline = self.clock() + max(0.0, wait_seconds)
        while True:
            result = self.results(find_id)
            if result["status"] in FINISHED | STOPPED or self.clock() >= deadline:
                break
            self.sleep(poll_interval)
        result.update({"request": q, "maximum_price_usd": maximum_cents / 100})
        if result["status"] not in FINISHED | STOPPED:
            result["message"] = "Still running. A retry of this task continues the same list; open list_link to see it."
        return result


def _error_message(error: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(error.read() or b"{}")
    except ValueError:
        payload = {}
    detail = payload.get("error") if isinstance(payload, dict) else None
    message = detail.get("message") if isinstance(detail, dict) else detail if isinstance(detail, str) else None
    return f"SpecStream answered {error.code}: {message or error.reason}"
