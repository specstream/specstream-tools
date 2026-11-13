"""Monitors: a saved list checked again on the live web on a schedule.

The API calls them schedules (/v1/capacity/schedules). Each check stays within a
limit per check and a limit per period that a person approved. The monitor calls
here build the API's fields for one list and return a flat view of the result.
Client includes MonitorsMixin, so these are methods of Client.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote as quote_path

CADENCE_SECONDS: dict[str, int] = {
    "hour": 3_600,
    "day": 86_400,
    "week": 604_800,
    "month": 2_592_000,
}
MONITOR_STATES = ("active", "paused", "deleted")
WEBHOOK_TOLERANCE_SECONDS = 300


class MonitorsMixin:
    """Monitor calls of Client. They need Client's request, get_find and schedule calls."""

    # Tests set this to a fixed clock; None means the system clock.
    clock: Callable[[], datetime] | None = None

    # The generated schedule calls of Client (create_capacity_schedule,
    # list_capacity_schedules, ...) and _request, get_find and
    # quote_capacity_work are found on Client at run time.
    _request: Callable[..., dict[str, Any]]
    get_find: Callable[..., dict[str, Any]]
    quote_capacity_work: Callable[..., dict[str, Any]]
    create_capacity_schedule: Callable[..., dict[str, Any]]
    list_capacity_schedules: Callable[..., dict[str, Any]]
    update_capacity_schedule: Callable[..., dict[str, Any]]
    list_capacity_occurrences: Callable[..., dict[str, Any]]
    run_capacity_schedule_now: Callable[..., dict[str, Any]]

    def set_schedule_delivery(self, schedule_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """PATCH /v1/workspace/schedules/{id}/delivery: where a schedule's results go.

        Needs the schedule's expected_version. Nothing runs. A new webhook answers
        with webhook_secret once: store it, never log it.
        """
        path = f"/v1/workspace/schedules/{quote_path(_require_id(schedule_id), safe='')}/delivery"
        return self._request("PATCH", path, request)

    def monitor_list(
        self,
        list_id: str,
        *,
        max_price_per_run_usd: float,
        every: str = "day",
        max_price_per_month_usd: float | None = None,
        first_run_at: datetime | str | None = None,
        ends_at: datetime | str | None = None,
    ) -> dict[str, Any]:
        """Price one check of a list you own and save a schedule that checks it again.

        every is "hour", "day", "week" or "month" ("month" is every 30 days).
        Returns the monitor with status "saved", or status "over_maximum" with
        nothing saved when one check can cost more than max_price_per_run_usd.
        max_price_per_month_usd defaults to the per-check maximum times the checks
        in 31 days. The first check is one interval after the current hour began,
        and the monitor ends a year later, unless first_run_at and ends_at say
        otherwise. A retry with the same arguments in the same hour returns the
        monitor already saved.
        """
        find_id = _require_id(list_id, "Give the list_id of the list to monitor")
        cadence = CADENCE_SECONDS.get(str(every))
        if cadence is None:
            raise ValueError('every must be "hour", "day", "week" or "month"')
        per_run = _usd_to_cents(max_price_per_run_usd)
        if per_run <= 0:
            raise ValueError("max_price_per_run_usd must be greater than 0")
        if max_price_per_month_usd is None:
            period = per_run * math.ceil(31 * 86_400 / cadence)
        else:
            period = _usd_to_cents(max_price_per_month_usd)
        if period < per_run:
            raise ValueError("max_price_per_month_usd must cover at least one check")

        now = self._now()
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        first = (
            hour_start + timedelta(seconds=cadence)
            if first_run_at is None
            else _to_time(first_run_at, "first_run_at")
        )
        ends = first + timedelta(days=365) if ends_at is None else _to_time(ends_at, "ends_at")
        if ends <= first:
            raise ValueError("ends_at must come after the first check")

        listed = self.get_find(find_id)
        ast_hash = listed.get("ast_hash")
        if not isinstance(ast_hash, str) or not ast_hash:
            from specstream_client.client import SpecstreamError

            raise SpecstreamError(f"GET /v1/finds/{find_id} returned no ast_hash", body=listed)
        units = _as_int(listed.get("requested_count"), 25) or 25
        scope: dict[str, Any] = {
            "ast_hash": ast_hash,
            "operation": "refresh",
            "parent_find_id": find_id,
            "requested_units": min(max(units, 1), 10_000),
        }
        # A list in a project is checked in that project; the API refuses any other.
        project = listed.get("project_id")
        if isinstance(project, str) and project:
            scope["project_id"] = project

        quote = self.quote_capacity_work(scope)
        maximum = _as_int(quote.get("maximum_cents"), 0)
        if maximum > per_run:
            return {
                "status": "over_maximum",
                "list_id": find_id,
                "maximum_price_usd": maximum / 100,
                "message": (
                    f"Nothing was saved: one check of this list can cost up to "
                    f"{_dollars(maximum)}, above the maximum of {_dollars(per_run)} per check. "
                    "Raise max_price_per_run_usd."
                ),
            }

        first_due = _iso(first)
        valid_until = _iso(ends)
        digest = hashlib.sha256(
            "|".join(
                str(part) for part in (find_id, cadence, per_run, period, first_due, valid_until)
            ).encode()
        ).hexdigest()
        saved = self.create_capacity_schedule(
            {
                "idempotency_key": f"python-monitor-{digest[:32]}",
                "scope": scope,
                "cadence_seconds": cadence,
                "first_due_at": first_due,
                "per_run_cents": per_run,
                "period_cents": period,
                "valid_until": valid_until,
            }
        )
        return _monitor_view(saved)

    def monitors(self, *, project_id: str | None = None) -> list[dict[str, Any]]:
        """Every monitor of the account, running, paused or ended, page after page. Free."""
        found: list[dict[str, Any]] = []
        after: str | None = None
        while True:
            page = self.list_capacity_schedules(project_id=project_id, after=after, limit=100)
            for item in page.get("schedules") or []:
                if isinstance(item, dict):
                    found.append(_monitor_view(item))
            following = page.get("next_after")
            if not isinstance(following, str) or not following or following == after:
                return found
            after = following

    def monitor_runs(self, monitor_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        """A monitor's recent checks, newest first. Free.

        Each has when it was due, the outcome, the reason and the list it made.
        """
        size = min(max(_as_int(limit, 50), 1), 100)
        page = self.list_capacity_occurrences(_require_id(monitor_id), limit=size)
        return [
            {
                "due_at": str(item.get("due_at") or ""),
                "status": str(item.get("status") or ""),
                "reason": _optional_text(item.get("reason")),
                "list_id": _optional_text(item.get("find_id")),
            }
            for item in page.get("occurrences") or []
            if isinstance(item, dict)
        ]

    def run_monitor_now(self, monitor_id: str) -> dict[str, Any]:
        """One check now, inside the monitor's limits. Its regular times stay as they are."""
        schedule_id = _require_id(monitor_id)
        run = self.run_capacity_schedule_now(schedule_id)
        if run.get("find_id") is None:
            from specstream_client.client import SpecstreamError

            raise SpecstreamError(
                f"POST /v1/capacity/schedules/{schedule_id}/run returned no find_id", body=run
            )
        return {
            "monitor_id": schedule_id,
            "list_id": str(run["find_id"]),
            "started_at": str(run.get("started_at") or ""),
        }

    def pause_monitor(self, monitor_id: str) -> dict[str, Any]:
        """Stop the checks until resume_monitor. A missed check is never bought later."""
        return self._set_monitor_state(monitor_id, "paused")

    def resume_monitor(self, monitor_id: str) -> dict[str, Any]:
        """Start the checks again from the next time due."""
        return self._set_monitor_state(monitor_id, "active")

    def delete_monitor(self, monitor_id: str) -> dict[str, Any]:
        """End the monitor for good. The lists it made stay yours."""
        return self._set_monitor_state(monitor_id, "deleted")

    def set_monitor_delivery(
        self,
        monitor_id: str,
        *,
        webhook: str | None = None,
        slack: str | None = None,
        send_to: str | None = None,
        notify: bool = True,
    ) -> dict[str, Any]:
        """Where each check's new and changed records go. Nothing runs.

        webhook: an https URL; slack: a channel of the connected Slack workspace;
        send_to: a connected tool; notify: SpecStream notifications. A new webhook
        comes back with "webhook_secret" once: keep it for verify_webhook.
        """
        schedule_id = _require_id(monitor_id)
        body: dict[str, Any] = {
            "expected_version": self._current_monitor(schedule_id)["version"],
            "notify": bool(notify),
        }
        if webhook is not None:
            body["webhook"] = webhook
        if slack is not None:
            body["slack"] = slack
        if send_to is not None:
            body["sendTo"] = send_to
        return self.set_schedule_delivery(schedule_id, body)

    def _set_monitor_state(self, monitor_id: str, state: str) -> dict[str, Any]:
        if state not in MONITOR_STATES:
            raise ValueError(f"state must be one of {', '.join(MONITOR_STATES)}")
        schedule_id = _require_id(monitor_id)
        current = self._current_monitor(schedule_id)
        return _monitor_view(
            self.update_capacity_schedule(
                schedule_id, {"expected_version": current["version"], "state": state}
            )
        )

    def _current_monitor(self, schedule_id: str) -> dict[str, Any]:
        for monitor in self.monitors():
            if monitor["monitor_id"] == schedule_id:
                return monitor
        from specstream_client.client import SpecstreamError

        raise SpecstreamError(f"No monitor {schedule_id} on this account")

    def _now(self) -> datetime:
        moment = self.clock() if self.clock is not None else datetime.now(UTC)
        return moment.astimezone(UTC)


def verify_webhook(
    *,
    secret: str,
    signature: str,
    body: bytes | str,
    tolerance: int = WEBHOOK_TOLERANCE_SECONDS,
    now: float | None = None,
) -> bool:
    """Check a monitor delivery before your app trusts its body.

    Each delivery is a JSON POST with Specstream-Event-Id and
    Specstream-Signature: t=<unix time>,v1=<hex>, where v1 is the HMAC-SHA256 of
    "<t>.<raw body>" with the webhook's signing secret. Pass the raw body as
    received. Returns True, or raises SpecstreamError.
    """
    from specstream_client.client import SpecstreamError

    if not secret:
        raise SpecstreamError("The webhook signing secret is required")
    stamp: str | None = None
    signed: list[str] = []
    for part in str(signature or "").split(","):
        key, sep, value = part.strip().partition("=")
        if not sep:
            continue
        if key == "t":
            stamp = value
        elif key == "v1":
            signed.append(value)
    if stamp is None or not stamp.isdigit() or not signed:
        raise SpecstreamError("Specstream-Signature has no t= or v1=")
    current = time.time() if now is None else now
    if abs(int(current) - int(stamp)) > tolerance:
        raise SpecstreamError("Specstream-Signature is too old or from the future")
    raw = body.encode("utf-8") if isinstance(body, str) else bytes(body)
    expected = hmac.new(
        secret.encode("utf-8"), stamp.encode() + b"." + raw, hashlib.sha256
    ).hexdigest()
    if any(hmac.compare_digest(expected, value) for value in signed):
        return True
    raise SpecstreamError("Specstream-Signature does not match the body")


def _monitor_view(data: dict[str, Any]) -> dict[str, Any]:
    schedule_id = data.get("schedule_id")
    if not isinstance(schedule_id, str) or not schedule_id:
        from specstream_client.client import SpecstreamError

        raise SpecstreamError("The schedule answer carries no schedule_id", body=data)
    raw_scope = data.get("scope")
    scope: dict[str, Any] = raw_scope if isinstance(raw_scope, dict) else {}
    monthly = data.get("monthly_maximum_cents")
    return {
        "status": "saved",
        "monitor_id": schedule_id,
        "list_id": _optional_text(scope.get("parent_find_id")),
        "state": str(data.get("state") or ""),
        "every_seconds": _as_int(data.get("cadence_seconds"), 0),
        "next_run_at": _optional_text(data.get("next_due_at")),
        "last_run_at": _optional_text(data.get("last_occurrence_at")),
        "last_list_id": _optional_text(data.get("last_find_id")),
        "last_reason": _optional_text(data.get("last_reason")),
        "max_price_per_run_usd": _as_int(data.get("per_run_cents"), 0) / 100,
        "max_price_per_month_usd": _as_int(
            monthly if monthly is not None else data.get("period_cents"), 0
        )
        / 100,
        "valid_until": _optional_text(data.get("valid_until")),
        "version": _as_int(data.get("version"), 0),
    }


def _require_id(value: Any, message: str = "An identifier is required") -> str:
    text = str(value if value is not None else "").strip()
    if not text:
        raise ValueError(message)
    return text


def _optional_text(value: Any) -> str | None:
    return None if value is None or str(value) == "" else str(value)


def _as_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _usd_to_cents(value: Any) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = math.nan
    if isinstance(value, bool) or not math.isfinite(number):
        raise ValueError("Give a price in US dollars, for example 2 or 2.5")
    return round(number * 100)


def _dollars(cents: int) -> str:
    return f"${cents / 100:.2f}"


def _to_time(value: datetime | str, name: str) -> datetime:
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{name} must be a datetime or an ISO 8601 time") from exc
    if moment.tzinfo is None:
        raise ValueError(f"{name} must carry a time zone")
    return moment.astimezone(UTC)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
