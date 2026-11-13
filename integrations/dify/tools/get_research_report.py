from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.client import SpecStreamClient, error_message
from tools.research import report_text, shown


class GetResearchReportTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        report_id = str(tool_parameters.get("report_id") or "").strip()
        if not report_id.startswith("rr_"):
            yield self.create_text_message(
                "Pass the report ID from Research Report. It starts with rr_."
            )
            return
        client = SpecStreamClient(self.runtime.credentials["specstream_api_key"])
        try:
            run = client.get(f"/v1/research/{report_id}")
        except requests.HTTPError as error:
            yield self.create_text_message(
                "SpecStream could not read this report: " + error_message(error)
            )
            return
        yield self.create_json_message(shown(run))
        yield self.create_text_message(report_text(run))
