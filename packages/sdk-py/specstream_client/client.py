"""OpenAPI-aligned SPECSTREAM client: one product, explicit quotes and shared dollar balance."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, cast
from urllib.parse import quote as quote_path
from urllib.parse import urlencode, urljoin, urlsplit

from specstream_client.authorization import require_work_authorization
from specstream_client.families import FAMILIES

DEFAULT_BASE_URL = "https://api.specstream.ai"
USER_AGENT = "specstream-python/1.3.2"

OpenFn = Callable[[urllib.request.Request, float], Any]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


RETRY_AFTER_MAX_S = 10.0


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    """Seconds to wait before the one retry of a 503 that names its Retry-After, or None."""
    if exc.code != 503 or exc.headers is None:
        return None
    value = (exc.headers.get("Retry-After") or "").strip()
    try:
        seconds = float(value)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if when.tzinfo is None:
            return None
        seconds = (when - datetime.now(UTC)).total_seconds()
    if not 0 <= seconds <= RETRY_AFTER_MAX_S:
        return None
    return seconds


class SpecstreamError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.body = body
        self.code: str | None = None
        self.details: dict[str, Any] = {}
        parsed = body
        if isinstance(parsed, (str, bytes)):
            try:
                parsed = json.loads(parsed)
            except (ValueError, UnicodeError):
                parsed = None
        if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
            error = parsed["error"]
            self.code = error.get("code") if isinstance(error.get("code"), str) else None
            if isinstance(error.get("details"), dict):
                self.details = dict(error["details"])


class Client:
    """Typed HTTP client for finder.cross-source.v1 public operations."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        opener: OpenFn | None = None,
        timeout: float = 150.0,
        *,
        export_origin: str | None = None,
    ) -> None:
        key = (api_key or "").strip()
        if not key:
            raise SpecstreamError("SPECSTREAM_API_KEY is required")
        self.api_key = key
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/") + "/"
        self.timeout = timeout
        self.export_origin = export_origin
        self._opener: OpenFn
        if opener is None:
            transport = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
            self._opener = lambda request, timeout: transport.open(request, timeout=timeout)
        else:
            self._opener = opener

    def compile(self, q: str, locale: str = "en-US") -> dict[str, Any]:
        """POST /v1/parse (operationId parseQuery) — compile language into query_ast.v1."""
        data = self._request("POST", "/v1/parse", {"q": q, "locale": locale})
        return data

    def edit_spec(
        self, ast: dict[str, Any], operations: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Validate an edited Spec, retaining required facts and exact target scope."""
        return self._request(
            "POST",
            "/v1/parse/from-chips",
            {"ast": ast, "operations": operations if operations is not None else []},
        )

    def spec_options(self, target: str) -> dict[str, Any]:
        """Read supported conditions and return facts for a target."""
        return self._request("GET", f"/v1/spec-options/{quote_path(target, safe='')}", None)

    def revisit(self, find_id: str, *, after: str = "", limit: int = 100) -> dict[str, Any]:
        """Read exact-target outcomes, including unknown and not-reached records."""
        query = urlencode({"after": after, "limit": limit})
        return self._request(
            "GET", f"/v1/finds/{quote_path(find_id, safe='')}/revisit?{query}", None
        )

    def rows(self, find_id: str, *, cursor: str | None = None, limit: int = 100) -> dict[str, Any]:
        """Read accepted rows and separate unbilled possible candidates.

        Follow next_cursor for accepted rows. Possible candidates have open
        conditions, identity-only cells and billable=False; do not count them as Matches.
        """
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Row page limit must be an integer from 1 to 100")
        if cursor is not None and (not isinstance(cursor, str) or not cursor or len(cursor) > 2048):
            raise ValueError("Use the opaque next_cursor returned by this Delivery")
        query = {"limit": str(limit)}
        if cursor is not None:
            query["cursor"] = cursor
        path = f"/v1/finds/{quote_path(find_id, safe='')}/rows?" + urlencode(query)
        return self._request("GET", path, None)

    def export(self, find_id: str, format: str = "csv") -> dict[str, Any]:
        """POST /v1/finds/{id}/export (operationId exportFind)."""
        return self._request(
            "POST", f"/v1/finds/{quote_path(find_id, safe='')}/export", {"format": format}
        )

    def download_export(
        self, find_id: str, format: str = "xlsx", *, max_bytes: int = 64 * 1024 * 1024
    ) -> bytes:
        """Fetch a fresh one-use export without forwarding the account bearer.

        Custom deployments with a separate website origin must set export_origin.
        A failed download is not automatically retried: request a fresh capability.
        """
        if type(max_bytes) is not int or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        data = self.export(find_id, format)
        url = data.get("download_url")
        if not isinstance(url, str) or any(ord(c) <= 32 or c == "\\" for c in url):
            raise SpecstreamError("Export returned an invalid download location")
        try:
            parsed = urlsplit(url)
            base = urlsplit(self.base_url)

            def origin_of(value: Any) -> tuple[str, str | None, int | None]:
                default = {"https": 443, "http": 80}.get(value.scheme)
                port = value.port if value.port is not None else default
                return value.scheme, value.hostname, port

            origin = origin_of(parsed)
            allowed = {origin_of(base)}
            if self.export_origin is not None:
                declared = urlsplit(self.export_origin)
                if (
                    declared.scheme not in {"http", "https"}
                    or not declared.hostname
                    or declared.username is not None
                    or declared.password is not None
                    or declared.query
                    or declared.fragment
                    or declared.path not in {"", "/"}
                ):
                    raise ValueError("invalid export origin")
                allowed.add(origin_of(declared))
            elif (
                base.scheme == "https"
                and base.hostname == "api.specstream.ai"
                and base.port in {None, 443}
            ):
                allowed.add(("https", "specstream.ai", 443))
            if (
                origin not in allowed
                or parsed.scheme not in {"http", "https"}
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or not re.fullmatch(r"/export/[A-Za-z0-9_-]+", parsed.path)
            ):
                raise ValueError("untrusted download location")
        except ValueError as exc:
            raise SpecstreamError("Export returned an untrusted download location") from exc
        req = urllib.request.Request(
            url,
            method="GET",
            headers={"Accept": "*/*", "Accept-Encoding": "identity", "User-Agent": USER_AGENT},
        )
        try:
            with self._opener(req, self.timeout) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    raise SpecstreamError("Export download failed", status=status)
                payload = response.read(max_bytes + 1)
                if not payload:
                    raise SpecstreamError("Export download returned no body", status=status)
                if len(payload) > max_bytes:
                    raise SpecstreamError("Export exceeds max_bytes", status=status)
                return bytes(payload)
        except urllib.error.HTTPError as exc:
            # The capability URL and any response body are deliberately omitted.
            raise SpecstreamError("Export download failed", status=exc.code) from None
        except (urllib.error.URLError, OSError):
            raise SpecstreamError("Export download transport failed") from None

    def get_find(self, find_id: str) -> dict[str, Any]:
        """GET /v1/finds/{id} (operationId getFind)."""
        return self._request("GET", f"/v1/finds/{quote_path(find_id, safe='')}", None)

    # BEGIN GENERATED LIFECYCLE
    def get_vocabulary(self) -> dict[str, Any]:
        """Read the public bar vocabulary and ready-made details."""
        path = "/v1/vocabulary"
        return self._request("GET", path, None)

    def workspace_list_audit_events(
        self,
        *,
        project_id: str | None = None,
        actor_account_id: str | None = None,
        cursor: str | None = None,
        kind: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Read immutable twelve-month activity with current owner permissions."""
        path = "/v1/workspace/audit"
        query: dict[str, Any] = {
            "project_id": project_id,
            "actor_account_id": actor_account_id,
            "cursor": cursor,
            "kind": kind,
            "limit": limit,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def understand_live(self, request: dict[str, Any]) -> dict[str, Any]:
        """Read an exact editor snapshot without saving or authorizing work."""
        path = "/v1/understand"
        return self._request("POST", path, request)

    def workspace_search(
        self,
        *,
        q: str,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Search the requests, lists and sources you can open."""
        path = "/v1/search"
        query: dict[str, Any] = {
            "q": q,
            "limit": limit,
            "cursor": cursor,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def web_search(self, *, q: str, passages: bool | None = None) -> dict[str, Any]:
        """
        Fast search: answer a question from the live web in seconds, each value with its source.
        """
        path = "/v1/web-search"
        query: dict[str, Any] = {
            "q": q,
            "passages": passages,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def extract_pages(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Read up to 20 pages live: each page's main text as Markdown or plain text, its title and
        its published date. Only a page read is charged.
        """
        path = "/v1/extract"
        return self._request("POST", path, request)

    def web_search_answers(
        self,
        *,
        q: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List your web search history: each question, its answer and its sources, newest first."""
        path = "/v1/web-search/answers"
        query: dict[str, Any] = {
            "q": q,
            "limit": limit,
            "cursor": cursor,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def web_search_answer(self, answer_id: str) -> dict[str, Any]:
        """Open one kept web search answer as it was given."""
        path = f"/v1/web-search/answers/{quote_path(answer_id, safe='')}"
        return self._request("GET", path, None)

    def workspace_list_notifications(
        self,
        *,
        tab: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Read your inbox with current resource authorization."""
        path = "/v1/workspace/notifications"
        query: dict[str, Any] = {
            "tab": tab,
            "limit": limit,
            "cursor": cursor,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def workspace_update_notification(
        self,
        identifier: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist read or archive state from your signed-in browser."""
        path = f"/v1/workspace/notifications/{quote_path(identifier, safe='')}"
        return self._request("PATCH", path, request)

    def workspace_read_notifications(self, request: dict[str, Any]) -> dict[str, Any]:
        """Mark the supplied authorized notifications read atomically."""
        path = "/v1/workspace/notifications/read"
        return self._request("POST", path, request)

    def get_me(self) -> dict[str, Any]:
        """Spend ceiling and remaining_spend authorization state."""
        path = "/v1/me"
        return self._request("GET", path, None)

    def get_account(self) -> dict[str, Any]:
        """Paid history."""
        path = "/v1/account"
        return self._request("GET", path, None)

    def list_account_keys(self) -> dict[str, Any]:
        """List API keys."""
        path = "/v1/account/keys"
        return self._request("GET", path, None)

    def create_account_key(self, request: dict[str, Any]) -> dict[str, Any]:
        """Create ss_live_ or ss_test_ key."""
        path = "/v1/account/keys"
        return self._request("POST", path, request)

    def update_account_spend(self, request: dict[str, Any]) -> dict[str, Any]:
        """Set an explicit owner authorization ceiling without funding or spending."""
        path = "/v1/account/spend"
        return self._request("PATCH", path, request)

    def revoke_account_key(self, key_id: str) -> dict[str, Any]:
        """Revoke an API key."""
        path = f"/v1/account/keys/{quote_path(key_id, safe='')}"
        return self._request("DELETE", path, None)

    def get_find_commerce(self, find_id: str) -> dict[str, Any]:
        """Read payment, fulfillment and access truth."""
        path = f"/v1/finds/{quote_path(find_id, safe='')}/commerce"
        return self._request("GET", path, None)

    def reconcile_find_commerce(self, find_id: str) -> dict[str, Any]:
        """Recover the existing purchase without rerunning work."""
        path = f"/v1/finds/{quote_path(find_id, safe='')}/reconcile"
        return self._request("POST", path, None)

    def cancel_find(self, find_id: str) -> dict[str, Any]:
        """Request cancel."""
        path = f"/v1/finds/{quote_path(find_id, safe='')}/cancel"
        return self._request("POST", path, None)

    def share_find(self, find_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Snapshot share token."""
        path = f"/v1/finds/{quote_path(find_id, safe='')}/share"
        return self._request("POST", path, request)

    def revoke_share(self, share_id: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
        """Revoke snapshot."""
        path = f"/v1/share/{quote_path(share_id, safe='')}/revoke"
        return self._request("POST", path, request)

    def create_spec(self, request: dict[str, Any]) -> dict[str, Any]:
        """Save a request as its first revision."""
        path = "/v1/specs"
        return self._request("POST", path, request)

    def list_specs(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        project_id: str | None = None,
        archived: bool | None = None,
    ) -> dict[str, Any]:
        """List the saved requests you can open."""
        path = "/v1/specs"
        query: dict[str, Any] = {
            "limit": limit,
            "cursor": cursor,
            "project_id": project_id,
            "archived": archived,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def get_spec(self, spec_id: str) -> dict[str, Any]:
        """Read a saved request and its current revision."""
        path = f"/v1/specs/{quote_path(spec_id, safe='')}"
        return self._request("GET", path, None)

    def revise_spec(self, spec_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Create an immutable revision only if the expected head still matches."""
        path = f"/v1/specs/{quote_path(spec_id, safe='')}/revisions"
        return self._request("POST", path, request)

    def list_spec_revisions(
        self,
        spec_id: str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Read a saved request's revision history."""
        path = f"/v1/specs/{quote_path(spec_id, safe='')}/revisions"
        query: dict[str, Any] = {
            "limit": limit,
            "cursor": cursor,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def get_spec_revision(self, spec_id: str, revision_id: str) -> dict[str, Any]:
        """Read one revision of a saved request."""
        path = (
            "/v1/specs/"
            f"{quote_path(spec_id, safe='')}"
            "/revisions/"
            f"{quote_path(revision_id, safe='')}"
        )
        return self._request("GET", path, None)

    def archive_spec(self, spec_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Archive or restore a saved request."""
        path = f"/v1/specs/{quote_path(spec_id, safe='')}"
        return self._request("PATCH", path, request)

    def list_spec_finds(
        self,
        spec_id: str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Read the finds a saved request has run."""
        path = f"/v1/specs/{quote_path(spec_id, safe='')}/finds"
        query: dict[str, Any] = {
            "limit": limit,
            "cursor": cursor,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def get_find_lineage(self, find_id: str) -> dict[str, Any]:
        """Read which request revision a find ran, and the find it continued."""
        path = f"/v1/finds/{quote_path(find_id, safe='')}/lineage"
        return self._request("GET", path, None)

    def get_delivery(self, find_id: str) -> dict[str, Any]:
        """Read your finished results with the request revision and sources behind them."""
        path = f"/v1/finds/{quote_path(find_id, safe='')}/delivery"
        return self._request("GET", path, None)

    def get_find_decisions(
        self,
        find_id: str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Read currently authorized Match decisions."""
        path = f"/v1/finds/{quote_path(find_id, safe='')}/decisions"
        query: dict[str, Any] = {
            "limit": limit,
            "cursor": cursor,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def create_project(self, request: dict[str, Any]) -> dict[str, Any]:
        """Create a project with an explicit bounded authorization ceiling."""
        path = "/v1/projects"
        return self._request("POST", path, request)

    def list_projects(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List currently authorized projects."""
        path = "/v1/projects"
        query: dict[str, Any] = {
            "limit": limit,
            "cursor": cursor,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def get_project(self, project_id: str) -> dict[str, Any]:
        """Read current project membership and authorization."""
        path = f"/v1/projects/{quote_path(project_id, safe='')}"
        return self._request("GET", path, None)

    def update_project(self, project_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Update a project only if the expected version matches."""
        path = f"/v1/projects/{quote_path(project_id, safe='')}"
        return self._request("PATCH", path, request)

    def put_project_member(self, project_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Set a current project member role and bounded spending ceiling."""
        path = f"/v1/projects/{quote_path(project_id, safe='')}/members"
        return self._request("POST", path, request)

    def list_project_members(
        self,
        project_id: str,
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List current project membership."""
        path = f"/v1/projects/{quote_path(project_id, safe='')}/members"
        query: dict[str, Any] = {
            "limit": limit,
            "cursor": cursor,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def revoke_project_member(self, project_id: str, account_id: str) -> dict[str, Any]:
        """Revoke project membership without deleting owned work."""
        path = (
            "/v1/projects/"
            f"{quote_path(project_id, safe='')}"
            "/members/"
            f"{quote_path(account_id, safe='')}"
        )
        return self._request("DELETE", path, None)

    def list_customer_webhooks(self) -> dict[str, Any]:
        """List owned callback destinations without secrets."""
        path = "/v1/account/webhooks"
        return self._request("GET", path, None)

    def create_customer_webhook(self, request: dict[str, Any]) -> dict[str, Any]:
        """Register find.completed webhook."""
        path = "/v1/account/webhooks"
        return self._request("POST", path, request)

    def revoke_customer_webhook(self, hook_id: str) -> dict[str, Any]:
        """Revoke an owned callback and cancel queued deliveries."""
        path = f"/v1/account/webhooks/{quote_path(hook_id, safe='')}"
        return self._request("DELETE", path, None)

    def get_capacity_catalog(self) -> dict[str, Any]:
        """Read the current dollar balance and membership offer."""
        path = "/v1/capacity/catalog"
        return self._request("GET", path, None)

    def get_capacity_balance(self, *, project_id: str | None = None) -> dict[str, Any]:
        """Read the available balance without approving new work."""
        path = "/v1/capacity/balance"
        query: dict[str, Any] = {
            "project_id": project_id,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def get_capacity_entitlements(self, *, project_id: str | None = None) -> dict[str, Any]:
        """Read what the account's plan includes and how many members it uses."""
        path = "/v1/capacity/entitlements"
        query: dict[str, Any] = {
            "project_id": project_id,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def get_capacity_referral(self) -> dict[str, Any]:
        """Read the verified account's stable referral link and rewards."""
        path = "/v1/capacity/referral"
        return self._request("GET", path, None)

    def capture_capacity_referral(self, request: dict[str, Any]) -> dict[str, Any]:
        """Remember the first referral visit for sign-up within thirty days."""
        path = "/v1/capacity/referral/visit"
        return self._request("POST", path, request)

    def get_capacity_history(self) -> dict[str, Any]:
        """Read account balance events including the reason for each bonus grant."""
        path = "/v1/capacity/history"
        return self._request("GET", path, None)

    def claim_free_capacity(self) -> dict[str, Any]:
        """Claim the one-time free balance for a verified eligible account."""
        path = "/v1/capacity/free"
        return self._request("POST", path, None)

    def set_capacity_budget(self, request: dict[str, Any]) -> dict[str, Any]:
        """Set an owner-approved monthly account spending maximum."""
        path = "/v1/capacity/budget"
        return self._request("PATCH", path, request)

    def quote_capacity_work(self, request: dict[str, Any]) -> dict[str, Any]:
        """Get a quote for a request before anything runs."""
        path = "/v1/capacity/quotes"
        return self._request("POST", path, request)

    def get_capacity_quote(self, quote_id: str) -> dict[str, Any]:
        """Recover your signed quote and any find already approved from it."""
        path = f"/v1/capacity/quotes/{quote_path(quote_id, safe='')}"
        return self._request("GET", path, None)

    def authorize_capacity_work(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Approve the exact quote to start one find and reserve its maximum from your balance.
        Needs the specs:write, finds:write and finds:spend scopes.
        """
        path = "/v1/capacity/executions"
        require_work_authorization(request)
        return self._request("POST", path, request)

    def start_capacity_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Ask for a list in plain words and run it within a maximum price, answering at once."""
        path = "/v1/capacity/requests"
        return self._request("POST", path, request)

    def get_capacity_request(
        self,
        request_key: str,
        *,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Recover the find already started with this request key."""
        path = f"/v1/capacity/requests/{quote_path(request_key, safe='')}"
        query: dict[str, Any] = {
            "project_id": project_id,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def get_capacity_request_rows(
        self,
        request_key: str,
        *,
        project_id: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
        format: str | None = None,
    ) -> dict[str, Any]:
        """Read where the request asked with this key stands and the rows it found so far."""
        path = f"/v1/capacity/requests/{quote_path(request_key, safe='')}/rows"
        query: dict[str, Any] = {
            "project_id": project_id,
            "cursor": cursor,
            "limit": limit,
            "format": format,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def get_capacity_execution(self, find_id: str) -> dict[str, Any]:
        """Read a find's approved work, final charge and your access to its results."""
        path = f"/v1/capacity/executions/{quote_path(find_id, safe='')}"
        return self._request("GET", path, None)

    def create_capacity_funding(self, request: dict[str, Any]) -> dict[str, Any]:
        """Prepare owner-authorized balance or membership checkout without starting work."""
        path = "/v1/capacity/funding"
        return self._request("POST", path, request)

    def get_capacity_funding(self, funding_id: str) -> dict[str, Any]:
        """Recover the original funding request from verified provider facts."""
        path = f"/v1/capacity/funding/{quote_path(funding_id, safe='')}"
        return self._request("GET", path, None)

    def cancel_capacity_funding(self, funding_id: str) -> dict[str, Any]:
        """Close an unpaid funding request without duplicating payment."""
        path = f"/v1/capacity/funding/{quote_path(funding_id, safe='')}"
        return self._request("DELETE", path, None)

    def get_capacity_membership(self) -> dict[str, Any]:
        """Read the current paid period and next-renewal choice."""
        path = "/v1/capacity/membership"
        return self._request("GET", path, None)

    def change_capacity_membership(self, request: dict[str, Any]) -> dict[str, Any]:
        """Change, cancel, or resume the membership for its next renewal."""
        path = "/v1/capacity/membership"
        return self._request("POST", path, request)

    def create_capacity_authority(self, request: dict[str, Any]) -> dict[str, Any]:
        """Approve a spending limit for one agent or member in a project."""
        path = "/v1/capacity/authorities"
        return self._request("POST", path, request)

    def revoke_capacity_authority(self, authority_id: str) -> dict[str, Any]:
        """Revoke a delegated spending limit without removing saved results."""
        path = f"/v1/capacity/authorities/{quote_path(authority_id, safe='')}"
        return self._request("DELETE", path, None)

    def create_capacity_schedule(self, request: dict[str, Any]) -> dict[str, Any]:
        """Approve future runs of an exact request within set spending limits."""
        path = "/v1/capacity/schedules"
        return self._request("POST", path, request)

    def list_capacity_schedules(
        self,
        *,
        project_id: str | None = None,
        after: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Read authorized recurring work and its current state."""
        path = "/v1/capacity/schedules"
        query: dict[str, Any] = {
            "project_id": project_id,
            "after": after,
            "limit": limit,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def update_capacity_schedule(self, schedule_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Pause, resume, or delete recurring work without buying missed occurrences."""
        path = f"/v1/capacity/schedules/{quote_path(schedule_id, safe='')}"
        return self._request("PATCH", path, request)

    def list_capacity_occurrences(
        self,
        schedule_id: str,
        *,
        before: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Read completed, blocked, and missed occurrences."""
        path = f"/v1/capacity/schedules/{quote_path(schedule_id, safe='')}/occurrences"
        query: dict[str, Any] = {
            "before": before,
            "limit": limit,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def run_capacity_schedule_now(self, schedule_id: str) -> dict[str, Any]:
        """
        Run active recurring work once now, inside its own limits, without moving its schedule.
        """
        path = f"/v1/capacity/schedules/{quote_path(schedule_id, safe='')}/run"
        return self._request("POST", path, None)

    def create_capacity_refund_claim(self, request: dict[str, Any]) -> dict[str, Any]:
        """Report a wrong result for review against its sources."""
        path = "/v1/capacity/refund-claims"
        return self._request("POST", path, request)

    def list_capacity_refund_claims(self) -> dict[str, Any]:
        """Read the account's correction claims, newest first."""
        path = "/v1/capacity/refund-claims"
        return self._request("GET", path, None)

    def get_capacity_refund_claim(self, claim_id: str) -> dict[str, Any]:
        """Read the status of an owned correction claim."""
        path = f"/v1/capacity/refund-claims/{quote_path(claim_id, safe='')}"
        return self._request("GET", path, None)

    def request_capacity_custom_plan(self, request: dict[str, Any]) -> dict[str, Any]:
        """Request an Enterprise conversation without granting an entitlement."""
        path = "/v1/capacity/enterprise"
        return self._request("POST", path, request)

    def get_capacity_store_config(self) -> dict[str, Any]:
        """Read the app store products and this account's store purchases."""
        path = "/v1/capacity/stores/config"
        return self._request("GET", path, None)

    def verify_capacity_store_purchase(self, request: dict[str, Any]) -> dict[str, Any]:
        """Confirm an app store purchase before adding its balance."""
        path = "/v1/capacity/stores/purchases"
        return self._request("POST", path, request)

    def restore_capacity_store_purchases(self, request: dict[str, Any]) -> dict[str, Any]:
        """Recover verified purchases without duplicate balance grants."""
        path = "/v1/capacity/stores/restore"
        return self._request("POST", path, request)

    def transfer_capacity_store_to_card(self, request: dict[str, Any]) -> dict[str, Any]:
        """Authorize a recoverable Google Play to card billing transfer."""
        path = "/v1/capacity/stores/card-transfer"
        return self._request("POST", path, request)

    def create_spec_link(self, spec_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Share a saved request revision as a link, without its results or permission to spend."""
        path = f"/v1/specs/{quote_path(spec_id, safe='')}/links"
        return self._request("POST", path, request)

    def get_shared_spec(self, token: str) -> dict[str, Any]:
        """Read a public request snapshot while its issuer, access and link remain valid."""
        path = f"/v1/shared-specs/{quote_path(token, safe='')}"
        return self._request("GET", path, None)

    def revoke_spec_link(self, spec_id: str, link_id: str) -> dict[str, Any]:
        """Turn off a saved-request link without changing the request or its results."""
        path = (
            "/v1/specs/"
            f"{quote_path(spec_id, safe='')}"
            "/links/"
            f"{quote_path(link_id, safe='')}"
            "/revoke"
        )
        return self._request("POST", path, None)

    def workspace_research_input(self, find_id: str) -> dict[str, Any]:
        """
        Review each imported row: which business it matched and why, other possible matches, and
        its result.
        """
        path = f"/v1/workspace/collections/{quote_path(find_id, safe='')}/input"
        return self._request("GET", path, None)

    def workspace_set_schedule_delivery(
        self,
        schedule_id: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Set versioned monitor delivery settings without starting work."""
        path = f"/v1/workspace/schedules/{quote_path(schedule_id, safe='')}/delivery"
        return self._request("PATCH", path, request)

    def workspace_list_collections(
        self,
        *,
        project_id: str | None = None,
        after: str | None = None,
        limit: int | None = None,
        sort: str | None = None,
    ) -> dict[str, Any]:
        """Read the lists you can open, from your finds and imports."""
        path = "/v1/workspace/collections"
        query: dict[str, Any] = {
            "project_id": project_id,
            "after": after,
            "limit": limit,
            "sort": sort,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def workspace_read_collection(self, collection_id: str) -> dict[str, Any]:
        """Read one list, without rows removed by an opt-out."""
        path = f"/v1/workspace/collections/{quote_path(collection_id, safe='')}"
        return self._request("GET", path, None)

    def workspace_combine_collections(self, request: dict[str, Any]) -> dict[str, Any]:
        """Combine your lists into one and keep each row's sources."""
        path = "/v1/workspace/collections/combine"
        return self._request("POST", path, request)

    def workspace_copy_collection(
        self,
        collection_id: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Copy rows from a list you can open into a separate list you own."""
        path = f"/v1/workspace/collections/{quote_path(collection_id, safe='')}/copy"
        return self._request("POST", path, request)

    def workspace_filter_collection(
        self,
        collection_id: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Filter a list's rows by IDs, sources or a map area."""
        path = f"/v1/workspace/collections/{quote_path(collection_id, safe='')}/filter"
        return self._request("POST", path, request)

    def workspace_list_views(self, collection_id: str) -> dict[str, Any]:
        """List your saved views of a list."""
        path = f"/v1/workspace/views/{quote_path(collection_id, safe='')}"
        return self._request("GET", path, None)

    def workspace_save_view(self, collection_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Save a versioned personal view without changing source records."""
        path = f"/v1/workspace/views/{quote_path(collection_id, safe='')}"
        return self._request("PUT", path, request)

    def workspace_list_stars(self) -> dict[str, Any]:
        """List starred work that remains currently authorized."""
        path = "/v1/workspace/stars"
        return self._request("GET", path, None)

    def workspace_star_item(self, request: dict[str, Any]) -> dict[str, Any]:
        """Star or unstar currently authorized work with an expected version."""
        path = "/v1/workspace/stars"
        return self._request("PUT", path, request)

    def workspace_list_notes(
        self,
        *,
        project_id: str | None = None,
        collection_id: str | None = None,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        """Read authorized project or collection-record notes."""
        path = "/v1/workspace/notes"
        query: dict[str, Any] = {
            "project_id": project_id,
            "collection_id": collection_id,
            "record_id": record_id,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def workspace_add_note(self, request: dict[str, Any]) -> dict[str, Any]:
        """Add a versioned note to an authorized project or collection record."""
        path = "/v1/workspace/notes"
        return self._request("POST", path, request)

    def workspace_resolve_note(self, note_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Resolve or reopen an authorized note with an expected version."""
        path = f"/v1/workspace/notes/{quote_path(note_id, safe='')}"
        return self._request("PATCH", path, request)

    def workspace_edit_note(self, note_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Edit a note you wrote with an expected version."""
        path = f"/v1/workspace/notes/{quote_path(note_id, safe='')}"
        return self._request("PUT", path, request)

    def workspace_delete_note(self, note_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Remove an authorized note with an expected version."""
        path = f"/v1/workspace/notes/{quote_path(note_id, safe='')}"
        return self._request("DELETE", path, request)

    def workspace_register_web_push_subscription(self, request: dict[str, Any]) -> dict[str, Any]:
        """Register an encrypted browser push subscription for this signed-in account."""
        path = "/v1/workspace/push/subscriptions"
        return self._request("POST", path, request)

    def workspace_push_capabilities(self) -> dict[str, Any]:
        """Read configured notification transports, never credentials."""
        path = "/v1/workspace/push/capabilities"
        return self._request("GET", path, None)

    def workspace_list_push_devices(self) -> dict[str, Any]:
        """List your registered notification devices."""
        path = "/v1/workspace/push/devices"
        return self._request("GET", path, None)

    def workspace_register_push_device(self, request: dict[str, Any]) -> dict[str, Any]:
        """Register the current signed-in device for native notifications."""
        path = "/v1/workspace/push/devices"
        return self._request("POST", path, request)

    def workspace_revoke_push_device(self, device_id: str) -> dict[str, Any]:
        """Stop notifications to a registered device."""
        path = f"/v1/workspace/push/devices/{quote_path(device_id, safe='')}"
        return self._request("DELETE", path, None)

    def workspace_list_your_fields(self, collection_id: str) -> dict[str, Any]:
        """Read the fields you added to a collection and their values."""
        path = f"/v1/workspace/collections/{quote_path(collection_id, safe='')}/fields"
        return self._request("GET", path, None)

    def workspace_save_your_fields(
        self,
        collection_id: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Add, rename or remove your own fields on a collection."""
        path = f"/v1/workspace/collections/{quote_path(collection_id, safe='')}/fields"
        return self._request("PUT", path, request)

    def workspace_set_your_field_value(
        self,
        collection_id: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Set or clear one of your fields on selected records."""
        path = f"/v1/workspace/collections/{quote_path(collection_id, safe='')}/fields/values"
        return self._request("PUT", path, request)

    def begin_connection_authorization(self, provider: str) -> dict[str, Any]:
        """Begin account-bound provider authorization."""
        path = f"/v1/connections/{quote_path(provider, safe='')}/authorize"
        return self._request("POST", path, None)

    def disconnect_connection(self, connection_id: str) -> dict[str, Any]:
        """Revoke a connected provider."""
        path = f"/v1/connections/{quote_path(connection_id, safe='')}"
        return self._request("DELETE", path, None)

    def list_cloud_imports(self) -> dict[str, Any]:
        """List daily source checks and import status."""
        path = "/v1/imports/cloud"
        return self._request("GET", path, None)

    def list_connected_tools(self) -> dict[str, Any]:
        """List supported tables, CRM, automation and chat tools."""
        path = "/v1/connections/catalog"
        return self._request("GET", path, None)

    def list_connections(self) -> dict[str, Any]:
        """List this account's connected providers."""
        path = "/v1/connections"
        return self._request("GET", path, None)

    def list_connection_destinations(
        self,
        connection_id: str,
        *,
        base_id: str | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List provider-authorized destinations."""
        path = f"/v1/connections/{quote_path(connection_id, safe='')}/destinations"
        query: dict[str, Any] = {
            "base_id": base_id,
            "cursor": cursor,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def get_connection_columns(self, connection_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Read destination columns before mapping fields."""
        path = f"/v1/connections/{quote_path(connection_id, safe='')}/columns"
        return self._request("POST", path, request)

    def save_connection_destination(
        self,
        connection_id: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Save a provider-verified destination and field mapping."""
        path = f"/v1/connections/{quote_path(connection_id, safe='')}/destination"
        return self._request("POST", path, request)

    def send_to_destination(self, connection_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Send selected owned results with durable delivery identities."""
        path = f"/v1/connections/{quote_path(connection_id, safe='')}/send"
        return self._request("POST", path, request)

    def reconcile_destination_export(self, connection_id: str, export_id: str) -> dict[str, Any]:
        """Check an uncertain delivery without sending it again."""
        path = (
            "/v1/connections/"
            f"{quote_path(connection_id, safe='')}"
            "/exports/"
            f"{quote_path(export_id, safe='')}"
            "/reconcile"
        )
        return self._request("POST", path, None)

    def list_destination_exports(self) -> dict[str, Any]:
        """List delivery receipts for connected tools."""
        path = "/v1/connections/exports"
        return self._request("GET", path, None)

    def create_destination_sync(self, request: dict[str, Any]) -> dict[str, Any]:
        """Keep sending new and changed records to this destination."""
        path = "/v1/destination-syncs"
        return self._request("POST", path, request)

    def update_destination_sync(self, sync_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Start or stop continuous destination delivery."""
        path = f"/v1/destination-syncs/{quote_path(sync_id, safe='')}"
        return self._request("PATCH", path, request)

    def list_destination_syncs(self) -> dict[str, Any]:
        """List continuous destination deliveries."""
        path = "/v1/destination-syncs"
        return self._request("GET", path, None)

    def preview_cloud_list(self, request: dict[str, Any]) -> dict[str, Any]:
        """Read a provider-authorized list before importing."""
        path = "/v1/imports/cloud/preview"
        return self._request("POST", path, request)

    def import_cloud_list(self, request: dict[str, Any]) -> dict[str, Any]:
        """Import supplied records from a connected table or workbook."""
        path = "/v1/imports/cloud"
        return self._request("POST", path, request)

    def update_cloud_import(self, import_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Start or stop daily source checks."""
        path = f"/v1/imports/cloud/{quote_path(import_id, safe='')}"
        return self._request("PATCH", path, request)

    def workspace_invite_member(self, request: dict[str, Any]) -> dict[str, Any]:
        """Invite a project member under current project management authority."""
        path = "/v1/workspace/invitations"
        return self._request("POST", path, request)

    def import_file_command(self, request: dict[str, Any]) -> dict[str, Any]:
        """Import supplied CSV or XLSX values without starting research."""
        path = "/v1/imports/file"
        return self._request("POST", path, request)

    def workspace_activity(
        self,
        *,
        project_id: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Read activity through current account and project permissions."""
        path = "/v1/activity"
        query: dict[str, Any] = {
            "project_id": project_id,
            "cursor": cursor,
            "limit": limit,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def workspace_relationships(
        self,
        collection_id: str,
        *,
        field_id: str | None = None,
    ) -> dict[str, Any]:
        """Group accessible records by actual shared column values."""
        path = f"/v1/workspace/collections/{quote_path(collection_id, safe='')}/relationships"
        query: dict[str, Any] = {
            "field_id": field_id,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def workspace_save_relationships(
        self,
        collection_id: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Save a personal relationship column with an expected version."""
        path = f"/v1/workspace/collections/{quote_path(collection_id, safe='')}/relationships"
        return self._request("PUT", path, request)

    def workspace_share_collection(
        self,
        collection_id: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Share a fixed copy of every record in a list through a link."""
        path = f"/v1/workspace/collections/{quote_path(collection_id, safe='')}/share"
        return self._request("POST", path, request)

    def workspace_report_result(
        self,
        collection_id: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Report a billed result for review within its guarantee period."""
        path = f"/v1/workspace/collections/{quote_path(collection_id, safe='')}/reports"
        return self._request("POST", path, request)

    def list_request_templates(self, *, record_type: str | None = None) -> dict[str, Any]:
        """List request examples; compile and quote before work."""
        path = "/v1/request-templates"
        query: dict[str, Any] = {
            "record_type": record_type,
        }
        encoded = urlencode(
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in query.items()
                if value is not None
            }
        )
        if encoded:
            path += "?" + encoded
        return self._request("GET", path, None)

    def workspace_collection_changes(self, collection_id: str) -> dict[str, Any]:
        """Read source-backed changes against immutable prior results."""
        path = f"/v1/workspace/collections/{quote_path(collection_id, safe='')}/changes"
        return self._request("GET", path, None)

    def workspace_list_passkeys(self) -> dict[str, Any]:
        """List the current account's registered passkeys."""
        path = "/v1/workspace/security/passkeys"
        return self._request("GET", path, None)

    def workspace_register_passkey_options(self) -> dict[str, Any]:
        """Start a browser-bound passkey registration ceremony."""
        path = "/v1/workspace/security/passkeys/options"
        return self._request("POST", path, None)

    def workspace_register_passkey(self, request: dict[str, Any]) -> dict[str, Any]:
        """Verify and register a passkey for the current account."""
        path = "/v1/workspace/security/passkeys"
        return self._request("POST", path, request)

    def workspace_name_passkey(self, credential_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Name an account-owned passkey."""
        path = f"/v1/workspace/security/passkeys/{quote_path(credential_id, safe='')}"
        return self._request("PATCH", path, request)

    def workspace_delete_passkey(self, credential_id: str) -> dict[str, Any]:
        """Revoke an account-owned passkey."""
        path = f"/v1/workspace/security/passkeys/{quote_path(credential_id, safe='')}"
        return self._request("DELETE", path, None)

    def workspace_passkey_sign_in_options(self) -> dict[str, Any]:
        """Start a browser-bound passkey sign-in ceremony."""
        path = "/v1/workspace/auth/passkey/options"
        return self._request("POST", path, None)

    def workspace_passkey_sign_in(self, request: dict[str, Any]) -> dict[str, Any]:
        """Verify a passkey assertion and establish a session."""
        path = "/v1/workspace/auth/passkey/verify"
        return self._request("POST", path, request)

    def workspace_list_s_s_o_domains(self) -> dict[str, Any]:
        """List account-owned verified SSO domains."""
        path = "/v1/workspace/security/sso"
        return self._request("GET", path, None)

    def workspace_add_s_s_o_domain(self, request: dict[str, Any]) -> dict[str, Any]:
        """Create an account-owned domain verification challenge."""
        path = "/v1/workspace/security/sso"
        return self._request("POST", path, request)

    def workspace_verify_s_s_o_domain(self, domain_id: str) -> dict[str, Any]:
        """Verify the account's domain through its DNS TXT record."""
        path = f"/v1/workspace/security/sso/{quote_path(domain_id, safe='')}/verify"
        return self._request("POST", path, None)

    def workspace_configure_s_s_o(self, domain_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Configure verified SAML metadata for an owned domain."""
        path = f"/v1/workspace/security/sso/{quote_path(domain_id, safe='')}/provider"
        return self._request("PUT", path, request)

    def workspace_set_s_s_o_policy(self, domain_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Set SSO enforcement after a successful provider test."""
        path = f"/v1/workspace/security/sso/{quote_path(domain_id, safe='')}"
        return self._request("PATCH", path, request)

    def workspace_start_s_s_o(self, request: dict[str, Any]) -> dict[str, Any]:
        """Start a single-use browser-bound SAML sign-in."""
        path = "/v1/workspace/auth/sso/start"
        return self._request("POST", path, request)

    def workspace_rotate_s_c_i_m_token(self, domain_id: str) -> dict[str, Any]:
        """Rotate a verified domain's provisioning credential."""
        path = f"/v1/workspace/security/sso/{quote_path(domain_id, safe='')}/scim/token"
        return self._request("POST", path, None)

    def workspace_revoke_s_c_i_m_token(self, domain_id: str) -> dict[str, Any]:
        """Revoke a domain's provisioning credential."""
        path = f"/v1/workspace/security/sso/{quote_path(domain_id, safe='')}/scim/token"
        return self._request("DELETE", path, None)

    def workspace_read_s_c_i_m_mappings(self, domain_id: str) -> dict[str, Any]:
        """Read provisioning mappings, provider groups and token state."""
        path = f"/v1/workspace/security/sso/{quote_path(domain_id, safe='')}/scim/mappings"
        return self._request("GET", path, None)

    def workspace_set_s_c_i_m_mappings(
        self,
        domain_id: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Set domain-to-project mappings under current owner authority."""
        path = f"/v1/workspace/security/sso/{quote_path(domain_id, safe='')}/scim/mappings"
        return self._request("PUT", path, request)

    def workspace_read_photo(self) -> dict[str, Any]:
        """Read the account-owned photo version and private URL."""
        path = "/v1/workspace/profile/photo"
        return self._request("GET", path, None)

    def workspace_delete_photo(self) -> dict[str, Any]:
        """Remove the current account's private profile photo."""
        path = "/v1/workspace/profile/photo"
        return self._request("DELETE", path, None)

    def workspace_start_native_provider(self, request: dict[str, Any]) -> dict[str, Any]:
        """Begin native provider authorization bound to an app-held PKCE secret."""
        path = "/v1/workspace/auth/native/start"
        return self._request("POST", path, request)

    def workspace_redeem_native_provider(self, request: dict[str, Any]) -> dict[str, Any]:
        """Redeem verified provider proof for an app session or connection."""
        path = "/v1/workspace/auth/native/redeem"
        return self._request("POST", path, request)

    def workspace_placement_allowance(self) -> dict[str, Any]:
        """Read this billing account's UTC monthly free placement allowance."""
        path = "/v1/workspace/placement/allowance"
        return self._request("GET", path, None)

    def workspace_quote_placement(self, import_id: str) -> dict[str, Any]:
        """Quote the maximum cost of placing imported addresses on the map."""
        path = f"/v1/workspace/imports/{quote_path(import_id, safe='')}/placement/quote"
        return self._request("POST", path, None)

    def workspace_start_placement(self, import_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Approve the placement quote and enqueue durable background placement."""
        path = f"/v1/workspace/imports/{quote_path(import_id, safe='')}/placement"
        return self._request("POST", path, request)

    def workspace_placement_status(self, import_id: str, placement_id: str) -> dict[str, Any]:
        """Read placement progress and per-row geocoding outcomes."""
        path = (
            "/v1/workspace/imports/"
            f"{quote_path(import_id, safe='')}"
            "/placement/"
            f"{quote_path(placement_id, safe='')}"
        )
        return self._request("GET", path, None)

    def teach_web_source(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Read one public page and learn its records and fields from 3 to 8 example rows. The
        preview explains how each field was inferred and marks the example rows. Nothing becomes
        a list until you save it..
        """
        path = "/v1/imports/web/sources"
        return self._request("POST", path, request)

    def list_web_sources(self) -> dict[str, Any]:
        """List up to 100 saved website sources in a project. No page is read.."""
        path = "/v1/imports/web/sources"
        return self._request("GET", path, None)

    def get_web_source(self, source_id: str) -> dict[str, Any]:
        """Read a saved website source and how each of its columns is read.."""
        path = f"/v1/imports/web/sources/{quote_path(source_id, safe='')}"
        return self._request("GET", path, None)

    def preview_web_source(self, source_id: str) -> dict[str, Any]:
        """
        Read the saved page again and preview its rows. Earlier lists stay unchanged. Columns
        paired by position need fresh examples once the page changes..
        """
        path = f"/v1/imports/web/sources/{quote_path(source_id, safe='')}/previews"
        return self._request("POST", path, None)

    def get_web_source_preview(self, preview_id: str) -> dict[str, Any]:
        """Read one source preview with its page hash, cell locations and field explanations.."""
        path = f"/v1/imports/web/previews/{quote_path(preview_id, safe='')}"
        return self._request("GET", path, None)

    def save_web_source_list(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Save a reviewed preview as an imported list, using its preview hash. Saving does not
        research or spend; quote and approve research on the list afterward..
        """
        path = "/v1/imports/web/lists"
        return self._request("POST", path, request)

    def get_reconciliation_fields(self, collection_id: str) -> dict[str, Any]:
        """
        Read the fields of a list you can open that can be used to match it against another
        list.
        """
        path = f"/v1/reconciliation/collections/{quote_path(collection_id, safe='')}/fields"
        return self._request("GET", path, None)

    def list_reconciliations(self, collection_id: str) -> dict[str, Any]:
        """List the recent comparisons that include this list (the latest 20, kept for 30 days)."""
        path = f"/v1/reconciliation/collections/{quote_path(collection_id, safe='')}/comparisons"
        return self._request("GET", path, None)

    def prepare_reconciliation(self, request: dict[str, Any]) -> dict[str, Any]:
        """
        Compare two of your lists with exact or close-spelling rules and conflict checks, and
        propose which rows correspond.
        """
        path = "/v1/reconciliation/comparisons"
        return self._request("POST", path, request)

    def get_reconciliation(self, comparison_id: str) -> dict[str, Any]:
        """
        Read a comparison: proposed pairs, alternatives, conflicts, missing values and sources.
        """
        path = f"/v1/reconciliation/comparisons/{quote_path(comparison_id, safe='')}"
        return self._request("GET", path, None)

    def apply_reconciliation(self, comparison_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """
        Fill empty cells in a new list from the pairs you chose. The original lists stay
        unchanged.
        """
        path = f"/v1/reconciliation/comparisons/{quote_path(comparison_id, safe='')}/apply"
        return self._request("POST", path, request)

    def get_reconciled_input(self, import_id: str) -> dict[str, Any]:
        """Read which chosen pair filled each cell of a list made by matching."""
        path = f"/v1/reconciliation/imports/{quote_path(import_id, safe='')}"
        return self._request("GET", path, None)
    # END GENERATED LIFECYCLE

    def families(self) -> tuple[str, ...]:
        return FAMILIES

    def _headers(self) -> dict[str, str]:
        token = self.api_key
        auth = token if token.lower().startswith("bearer ") else f"Bearer {token}"
        return {
            "Authorization": auth,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }

    def _request(self, method: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        url = urljoin(self.base_url, path.lstrip("/"))
        payload = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method=method, headers=self._headers())
        try:
            try:
                with self._opener(req, self.timeout) as resp:
                    status = getattr(resp, "status", 200)
                    text = resp.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as busy:
                wait = _retry_after(busy)
                if wait is None:
                    raise
                # The server did nothing and names when to ask again: ask once more.
                busy.close()
                time.sleep(wait)
                with self._opener(req, self.timeout) as resp:
                    status = getattr(resp, "status", 200)
                    text = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", "replace") if exc.fp else ""
            try:
                parsed: Any = json.loads(text)
            except ValueError:
                parsed = text
            raise SpecstreamError(
                f"{method} {path} failed with HTTP {exc.code}", status=exc.code, body=parsed
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise SpecstreamError(f"{method} {path} transport failed") from exc
        try:
            loaded = json.loads(text)
        except ValueError as exc:
            raise SpecstreamError(
                f"{method} {path} returned invalid JSON", status=status, body=text
            ) from exc
        if not 200 <= status < 300:
            raise SpecstreamError(
                f"{method} {path} failed with HTTP {status}", status=status, body=loaded
            )
        if not isinstance(loaded, dict):
            raise SpecstreamError(
                f"{method} {path} returned non-object JSON", status=status, body=loaded
            )
        if loaded.get("error") is not None or not isinstance(loaded.get("data"), dict):
            raise SpecstreamError(
                f"{method} {path} returned an invalid success envelope",
                status=status,
                body=loaded,
            )
        return cast(dict[str, Any], loaded["data"])


__all__ = [
    "Client",
    "DEFAULT_BASE_URL",
    "FAMILIES",
    "SpecstreamError",
]
