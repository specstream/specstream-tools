"""Browser sessions: a real Chromium on SpecStream that your code drives.

A session is charged for each second it runs and for each step, until it is
closed or its timeout_s passes. Drive it step by step with browser_step (the
tools of Playwright MCP by name, plus browser_read for the page's text), or
connect Playwright, Puppeteer, browser-use or Stagehand to its connect_url over
the Chrome DevTools Protocol.
Client includes BrowserMixin, so these are methods of Client.
"""

from __future__ import annotations

import copy
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import quote as quote_path
from urllib.parse import urlencode, urljoin

SESSIONS_PATH = "/v1/browser/sessions"
SESSION_STATES = ("starting", "running", "ended")
READ_FORMATS = ("markdown", "text")
IDEMPOTENCY_KEY_MAX = 128


class BrowserMixin:
    """Browser session calls of Client. They need Client's _request, _headers and _opener."""

    _request: Callable[..., dict[str, Any]]
    _headers: Callable[[], dict[str, str]]
    _opener: Callable[..., Any]
    base_url: str
    timeout: float

    def open_browser(
        self,
        *,
        timeout_s: int | None = None,
        idle_timeout_s: int | None = None,
        keep_alive: bool | None = None,
        headless: bool | None = None,
        viewport: dict[str, int] | None = None,
        allowed_domains: list[str] | None = None,
        block_media: bool | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """POST /v1/browser/sessions: open a browser and return the running session.

        The session holds its id, its connect_url (the Chrome DevTools Protocol
        address) and its price. Charges start now: call close_browser when you
        are done. timeout_s is the most seconds the session runs (60 to 3,600,
        default 300). allowed_domains limits the hosts the browser may open.
        A setting you leave out takes the API's default. With idempotency_key,
        the same call again answers with the same session and opens no second one.
        """
        settings = {
            "timeout_s": timeout_s,
            "idle_timeout_s": idle_timeout_s,
            "keep_alive": keep_alive,
            "headless": headless,
            "viewport": viewport,
            "allowed_domains": allowed_domains,
            "block_media": block_media,
            "metadata": metadata,
        }
        body = {name: value for name, value in settings.items() if value is not None}
        if idempotency_key is None:
            return self._request("POST", SESSIONS_PATH, body)
        key = str(idempotency_key).strip()
        if not key or len(key) > IDEMPOTENCY_KEY_MAX:
            raise ValueError(f"idempotency_key must hold 1 to {IDEMPOTENCY_KEY_MAX} characters")
        # A copy of the client whose requests carry the key: _request stays as it is,
        # with its errors and its one retry after Retry-After.
        keyed = copy.copy(self)
        send = self._opener

        def with_key(request: urllib.request.Request, timeout: float) -> Any:
            request.add_header("Idempotency-Key", key)
            return send(request, timeout)

        keyed._opener = with_key
        return keyed._request("POST", SESSIONS_PATH, body)

    def browser_sessions(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """GET /v1/browser/sessions: the account's sessions, newest first.

        Returns {"sessions": [...], "next_cursor": ...}. status is "starting",
        "running" or "ended". Pass next_cursor as cursor for the next page.
        """
        if status is not None and status not in SESSION_STATES:
            raise ValueError('status must be "starting", "running" or "ended"')
        query = {
            name: value
            for name, value in (("status", status), ("limit", limit), ("cursor", cursor))
            if value is not None
        }
        path = SESSIONS_PATH + (f"?{urlencode(query)}" if query else "")
        return self._request("GET", path, None)

    def browser_session(self, session_id: str) -> dict[str, Any]:
        """GET /v1/browser/sessions/{id}: status, why it ended, seconds, steps and charge."""
        return self._request("GET", _session_path(session_id), None)

    def close_browser(self, session_id: str) -> dict[str, Any]:
        """POST /v1/browser/sessions/{id}/release: end the session and settle its charge.

        Returns the ended session with charged_usd. A repeat call answers the same.
        """
        return self._request("POST", _session_path(session_id) + "/release", {})

    def browser_step(
        self, session_id: str, tool: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """POST /v1/browser/sessions/{id}/actions: run one step in the browser.

        tool is a Playwright MCP tool by its name (browser_navigate,
        browser_snapshot, browser_click, browser_type, browser_take_screenshot
        and the others) or browser_read. Returns the step's result, the page's
        url and title, and price_usd. A page the browser may not open does not
        raise: the answer's error holds code "blocked" and the reason.
        """
        name = str(tool or "").strip()
        if not name.startswith("browser_"):
            raise ValueError('tool is a step name that starts with "browser_"')
        body = {"tool": name, "arguments": dict(arguments or {})}
        return self._request("POST", _session_path(session_id) + "/actions", body)

    def browser_navigate(self, session_id: str, url: str) -> dict[str, Any]:
        """One step: open the address in the session's browser."""
        address = str(url or "").strip()
        if not address:
            raise ValueError("Give the url to open")
        return self.browser_step(session_id, "browser_navigate", {"url": address})

    def browser_snapshot(self, session_id: str) -> dict[str, Any]:
        """One step: the page's links, buttons and fields, each with a reference to act on."""
        return self.browser_step(session_id, "browser_snapshot")

    def browser_read(self, session_id: str, format: str = "markdown") -> str:
        """One step: the page's text as it stands after its JavaScript ran.

        format is "markdown" or "text". Raises SpecstreamError when the step
        answers with an error, for example a page the browser may not open.
        """
        if format not in READ_FORMATS:
            raise ValueError('format must be "markdown" or "text"')
        step = self.browser_step(session_id, "browser_read", {"format": format})
        failure = step.get("error")
        if failure:
            from specstream_client.client import SpecstreamError

            message = failure.get("message") if isinstance(failure, dict) else None
            raise SpecstreamError(f"browser_read failed: {message or failure}", body=step)
        return step_text(step)

    def browser_downloads(self, session_id: str) -> bytes:
        """GET /v1/browser/sessions/{id}/downloads: the files the browser downloaded, as one zip.

        They are kept until ten minutes after the session ends.
        """
        from specstream_client.client import SpecstreamError

        path = _session_path(session_id) + "/downloads"
        request = urllib.request.Request(
            urljoin(self.base_url, path.lstrip("/")), method="GET", headers=self._headers()
        )
        try:
            with self._opener(request, self.timeout) as response:
                status = getattr(response, "status", 200)
                content = response.read()
        except urllib.error.HTTPError as exc:
            raise SpecstreamError(
                f"GET {path} failed with HTTP {exc.code}", status=exc.code
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise SpecstreamError(f"GET {path} transport failed") from exc
        if not 200 <= status < 300:
            raise SpecstreamError(f"GET {path} failed with HTTP {status}", status=status)
        return bytes(content)

    @contextmanager
    def browser(self, **settings: Any) -> Iterator[dict[str, Any]]:
        """Open a browser for a with block and close it at the end, also after an error.

        Takes the arguments of open_browser and yields the session.
        """
        session = self.open_browser(**settings)
        try:
            yield session
        finally:
            self.close_browser(session["id"])


def step_text(step: dict[str, Any]) -> str:
    """The text parts of a step's result, joined."""
    parts = step.get("result")
    if not isinstance(parts, list):
        return ""
    return "\n".join(
        part["text"]
        for part in parts
        if isinstance(part, dict)
        and part.get("type") == "text"
        and isinstance(part.get("text"), str)
    )


def _session_path(session_id: str) -> str:
    value = str(session_id or "").strip()
    if not value:
        raise ValueError("Give the session's id, from open_browser")
    return f"{SESSIONS_PATH}/{quote_path(value, safe='')}"


__all__ = ["BrowserMixin", "step_text"]
