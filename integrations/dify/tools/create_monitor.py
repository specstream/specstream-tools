import hashlib
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.client import MONITORS_URL, SpecStreamClient, error_message, list_link

CADENCE_SECONDS = {"hourly": 3600, "daily": 86400, "weekly": 604800, "monthly": 2592000}
# The first run waits a few minutes, so the API never reads its due time as past.
FIRST_RUN_DELAY = timedelta(minutes=5)


def monitor_request(
    find_id: str,
    quote: dict[str, Any],
    scope: dict[str, Any],
    frequency: str,
    per_run_cents: int,
    month_cents: int,
    months: int,
    now: datetime,
) -> dict[str, Any]:
    """The schedule body for a quoted scope. A recheck covers the rows the quote counted."""
    scope = dict(scope)
    units = (quote.get("scope") or {}).get("requested_units") or (quote.get("terms") or {}).get(
        "maximum_units"
    )
    if units:
        scope["requested_units"] = int(units)
    first = (now + FIRST_RUN_DELAY).replace(microsecond=0)
    # The same monitor asked again within the hour gets the monitor it already made.
    key = "|".join(
        [
            find_id,
            scope["operation"],
            str(scope.get("requested_units")),
            frequency,
            str(per_run_cents),
            str(month_cents),
            str(months),
            now.strftime("%Y-%m-%dT%H"),
        ]
    )
    return {
        "idempotency_key": "dify-monitor-" + hashlib.sha256(key.encode()).hexdigest()[:32],
        "scope": scope,
        "cadence_seconds": CADENCE_SECONDS[frequency],
        "first_due_at": first.isoformat(),
        "per_run_cents": per_run_cents,
        "period_cents": month_cents,
        "valid_until": (first + timedelta(days=30 * months)).isoformat(),
    }


class CreateMonitorTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        list_id = str(tool_parameters.get("list_id") or "").strip()
        watch = str(tool_parameters.get("watch_for") or "changes")
        frequency = str(tool_parameters.get("frequency") or "daily")
        new_per_run = int(tool_parameters.get("new_results_per_run") or 25)
        per_run_cents = round(float(tool_parameters.get("max_price_per_run_usd") or 0) * 100)
        month_cents = round(float(tool_parameters.get("max_price_per_month_usd") or 0) * 100)
        months = max(1, min(24, int(tool_parameters.get("months") or 3)))
        if not list_id.startswith("fnd_"):
            yield self.create_text_message(
                "Pass the list ID from Find a List. It starts with fnd_."
            )
            return
        if watch not in ("changes", "new") or frequency not in CADENCE_SECONDS:
            yield self.create_text_message(
                "Watch for 'changes' or 'new', and run hourly, daily, weekly or monthly."
            )
            return
        if per_run_cents <= 0 or month_cents < per_run_cents:
            yield self.create_text_message(
                "Set a maximum price per run above 0 and a maximum per month at least as high."
            )
            return

        client = SpecStreamClient(self.runtime.credentials["specstream_api_key"])
        try:
            find = client.get(f"/v1/finds/{list_id}")
            scope: dict[str, Any] = {
                "ast_hash": find["ast_hash"],
                "operation": "refresh" if watch == "changes" else "extend",
                "parent_find_id": list_id,
                "project_id": find.get("project_id"),
            }
            if watch == "new":
                scope["requested_units"] = max(1, min(1000, new_per_run))
            quote = client.post("/v1/capacity/quotes", scope)
            if quote["maximum_cents"] > per_run_cents:
                yield self.create_text_message(
                    f"One run can cost up to ${quote['maximum_cents'] / 100:.2f}, above the maximum of "
                    f"${per_run_cents / 100:.2f} per run, so no monitor was made and nothing was charged."
                )
                return
            body = monitor_request(
                list_id,
                quote,
                scope,
                frequency,
                per_run_cents,
                month_cents,
                months,
                datetime.now(UTC),
            )
            monitor = client.post("/v1/capacity/schedules", body)
        except requests.HTTPError as error:
            yield self.create_text_message(
                "SpecStream did not make the monitor, and nothing was charged: "
                + error_message(error)
            )
            return

        yield self.create_json_message(
            {
                "monitor_id": monitor.get("schedule_id"),
                "state": monitor.get("state"),
                "watch_for": watch,
                "frequency": frequency,
                "next_run_at": monitor.get("next_due_at"),
                "runs_until": monitor.get("valid_until"),
                "max_price_per_run_usd": per_run_cents / 100,
                "max_price_per_month_usd": month_cents / 100,
                "price_of_one_run_now_usd": quote["maximum_cents"] / 100,
                "list_id": list_id,
                "list_link": list_link(list_id),
                "manage_link": MONITORS_URL,
            }
        )
