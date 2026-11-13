#
# Copyright (c) 2026, SpecStream SAS
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""The SpecStream REST calls the Pipecat tools share, over aiohttp.

Search the live web, read pages, price a Deep Search list, start it within a
maximum and read its rows, start a research report and read it.
"""

from __future__ import annotations

import hashlib
import time
import urllib.parse
from typing import Any

import aiohttp

DEFAULT_BASE_URL = "https://api.specstream.ai"
USER_AGENT = "pipecat-specstream/0.2.0"
FINISHED = frozenset({"completed", "partial"})
STOPPED = frozenset({"failed", "cancelled", "canceled", "expired"})
# Fields every row carries; a column with the same name is renamed so it can't overwrite them.
RESERVED = frozenset({"position", "source_url", "checked_at"})
KEY_HELP = (
    "Pass api_key or set SPECSTREAM_API_KEY. Create a key under Agents & API "
    "in your SpecStream workspace."
)


class SpecStreamError(RuntimeError):
    """SpecStream refused a call or answered with something this package can't read."""

    def __init__(self, message: str, status: int | None = None) -> None:
        """Initialize the error.

        Args:
            message: What went wrong, safe to show to the model.
            status: The HTTP status SpecStream answered, when there was one.
        """
        super().__init__(message)
        self.status = status


def dollars(cents: int) -> str:
    """Format cents as dollars, like ``$4.25``."""
    return f"${cents / 100:.2f}"


def list_link(find_id: str) -> str:
    """The workspace page of a list."""
    return f"https://specstream.ai/workspace/collections/{urllib.parse.quote(find_id, safe='')}"


def flatten_row(record: dict[str, Any], flat: dict[str, Any] | None = None) -> dict[str, Any]:
    """One row as flat fields: each column's label holds what the list shows.

    The page of each value (``<field>_source``) and of the fact that put the row in
    the list (``source_url``, ``checked_at``) come from the API's flat row.
    """
    flat = flat or {}
    sources = {
        key: value
        for key, value in flat.items()
        if key.endswith("_source") and key[: -len("_source")] in flat
    }
    row: dict[str, Any] = {"position": record.get("ordinal")}
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
    return row


def request_key(request: str, max_results: int, max_cents: int, at: float) -> str:
    """An idempotency key for one list: the same request and limits in the same hour."""
    hour = time.strftime("%Y-%m-%dT%H", time.gmtime(at))
    digest = hashlib.sha256(f"{request}|{max_results}|{max_cents}|{hour}".encode()).hexdigest()
    return "pipecat-" + digest[:32]


class SpecStreamClient:
    """A small async client for the SpecStream API.

    Uses the given ``aiohttp.ClientSession`` or opens its own on first use;
    :meth:`close` closes only a session it opened.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        session: aiohttp.ClientSession | None = None,
        timeout_secs: float = 60.0,
    ) -> None:
        """Initialize the client.

        Args:
            api_key: A SpecStream API key.
            base_url: The API root.
            session: An aiohttp session to reuse. When unset, one is opened on first use.
            timeout_secs: Timeout of one HTTP call.
        """
        self._api_key = (api_key or "").strip()
        self._base_url = base_url.rstrip("/")
        self._session = session
        self._owns_session = session is None
        self._timeout_secs = timeout_secs

    async def close(self) -> None:
        """Close the session this client opened. Safe to call more than once."""
        if self._owns_session and self._session is not None:
            session, self._session = self._session, None
            await session.close()

    async def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        allow_404: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Call the API and return the ``data`` object of its answer."""
        if not self._api_key:
            raise SpecStreamError(KEY_HELP)
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        key = self._api_key
        headers = {
            "Authorization": key if key.lower().startswith("bearer ") else f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            **(extra_headers or {}),
        }
        try:
            async with self._session.request(
                method,
                self._base_url + path,
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._timeout_secs),
            ) as response:
                status = response.status
                try:
                    payload = await response.json(content_type=None)
                except ValueError:
                    payload = None
        except (aiohttp.ClientError, TimeoutError) as error:
            raise SpecStreamError(f"Couldn't reach SpecStream: {error}") from None
        if status == 404 and allow_404:
            return None
        if status >= 400:
            raise SpecStreamError(f"SpecStream answered {status}: {_message(payload)}", status)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise SpecStreamError("SpecStream returned a response this package couldn't read.")
        return payload["data"]

    async def web_search(
        self, q: str, *, speed: str = "fast", passages: bool = False
    ) -> dict[str, Any]:
        """Search the live web with ``GET /v1/web-search``."""
        query = (q or "").strip()
        if not query or len(query) > 2000:
            raise SpecStreamError("q must be between 1 and 2,000 characters.")
        params = {"q": query, "speed": "fast" if speed == "fast" else "default"}
        if passages:
            params["passages"] = "true"
        return await self.request("GET", f"/v1/web-search?{urllib.parse.urlencode(params)}") or {}

    async def extract(self, urls: list[str], *, format: str = "text") -> dict[str, Any]:
        """Read the main text of 1 to 20 URLs with ``POST /v1/extract``."""
        cleaned = [str(u or "").strip() for u in (urls or []) if str(u or "").strip()]
        if not 1 <= len(cleaned) <= 20:
            raise SpecStreamError("Give 1 to 20 http or https URLs.")
        body = {"urls": cleaned, "format": "markdown" if format == "markdown" else "text"}
        return await self.request("POST", "/v1/extract", body) or {}

    async def price(self, request: str, max_results: int, *, locale: str = "en-US") -> dict[str, Any]:
        """Read a request and price it. Nothing runs and nothing is charged.

        Returns the reading (``status``, ``canonical_sentence``) and, when the request
        is runnable, the quote (``quote_id``, ``quote_hash``, ``maximum_cents``).
        """
        reading = await self.request("POST", "/v1/parse", {"q": request, "locale": locale}) or {}
        if reading.get("status") != "runnable":
            return {"runnable": False, "read_as": reading.get("canonical_sentence") or request}
        quote = await self.request(
            "POST",
            "/v1/capacity/quotes",
            {"ast_hash": reading["ast_hash"], "operation": "find", "requested_units": max_results},
        ) or {}
        return {
            "runnable": True,
            "read_as": reading.get("canonical_sentence") or request,
            "quote_id": quote.get("quote_id"),
            "quote_hash": quote.get("quote_hash"),
            "maximum_cents": int(quote.get("maximum_cents") or 0),
        }

    async def existing_run(self, key: str) -> dict[str, Any] | None:
        """The run already started with this idempotency key, if any."""
        found = await self.request(
            "GET", f"/v1/capacity/requests/{urllib.parse.quote(key, safe='')}", allow_404=True
        )
        return found if found and found.get("find_id") else None

    async def start(self, quote: dict[str, Any], *, confirm_max_cents: int, key: str) -> str:
        """Start a priced list within ``confirm_max_cents``. Returns its find id."""
        run = await self.request(
            "POST",
            "/v1/capacity/executions",
            {
                "quote_id": quote["quote_id"],
                "quote_hash": quote["quote_hash"],
                "confirm_max_cents": confirm_max_cents,
                "idempotency_key": key,
            },
        ) or {}
        if not run.get("find_id"):
            raise SpecStreamError("SpecStream started no list.")
        return run["find_id"]

    async def rows(self, find_id: str) -> dict[str, Any]:
        """Every row found so far for a list, following the pages. Reading is free."""
        rows: list[dict[str, Any]] = []
        cursor: str | None = None
        status = "running"
        quoted = urllib.parse.quote(find_id, safe="")
        while True:
            query = {"limit": "100", **({"cursor": cursor} if cursor else {})}
            page = await self.request(
                "GET", f"/v1/finds/{quoted}/rows?{urllib.parse.urlencode(query)}"
            ) or {}
            status = page.get("status") or status
            flat = {str(item.get("id")): item for item in page.get("flat_rows") or []}
            rows.extend(
                flatten_row(record, flat.get(f"{find_id}:{record.get('entity_id')}"))
                for record in page.get("rows") or []
            )
            cursor = page.get("next_cursor")
            if not cursor:
                break
        return {"list_id": find_id, "status": status, "rows": rows}

    async def start_research(self, body: dict[str, Any], *, key: str) -> dict[str, Any]:
        """Start a research report with ``POST /v1/research``.

        The same ``key`` with the same body returns the report it already started.
        """
        headers = {"Idempotency-Key": key}
        return await self.request("POST", "/v1/research", body, extra_headers=headers) or {}

    async def research(self, research_id: str) -> dict[str, Any]:
        """Read a research report with ``GET /v1/research/{id}``. Reading is free."""
        quoted = urllib.parse.quote(research_id, safe="")
        return await self.request("GET", f"/v1/research/{quoted}") or {}

    async def cancel_research(self, research_id: str) -> None:
        """Stop a running report with ``POST /v1/research/{id}/cancel``. It is not charged."""
        quoted = urllib.parse.quote(research_id, safe="")
        await self.request("POST", f"/v1/research/{quoted}/cancel")


def _message(payload: Any) -> str:
    detail = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(detail, dict):
        return str(detail.get("message") or "request refused")
    if isinstance(detail, str):
        return detail
    return "request refused"
