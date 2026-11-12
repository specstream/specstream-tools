from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.client import MONITORS_URL, SpecStreamClient, error_message, list_link


class GetMonitorRunsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        monitor_id = str(tool_parameters.get("monitor_id") or "").strip()
        limit = max(1, min(100, int(tool_parameters.get("limit") or 10)))
        if not monitor_id.startswith("csc_"):
            yield self.create_text_message(
                "Pass the monitor ID from Create a Monitor. It starts with csc_."
            )
            return
        client = SpecStreamClient(self.runtime.credentials["specstream_api_key"])
        try:
            page = client.get(f"/v1/capacity/schedules/{monitor_id}/occurrences?limit={limit}")
        except requests.HTTPError as error:
            yield self.create_text_message(
                "SpecStream could not read this monitor: " + error_message(error)
            )
            return
        runs = []
        for run in page.get("occurrences") or []:
            find_id = run.get("find_id")
            runs.append(
                {
                    "due_at": run.get("due_at"),
                    "status": run.get("status"),
                    "reason": run.get("reason"),
                    "list_id": find_id,
                    "list_link": list_link(find_id) if find_id else None,
                }
            )
        yield self.create_json_message(
            {"monitor_id": monitor_id, "runs": runs, "manage_link": MONITORS_URL}
        )
