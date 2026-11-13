from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.browser import shown_session
from tools.client import SpecStreamClient, error_message


class CloseBrowserTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        session_id = str(tool_parameters.get("session_id") or "").strip()
        if not session_id.startswith("brs_"):
            yield self.create_text_message(
                "Pass the session ID from Open Browser. It starts with brs_."
            )
            return
        client = SpecStreamClient(self.runtime.credentials["specstream_api_key"])
        try:
            session = client.post(f"/v1/browser/sessions/{session_id}/release", {})
        except requests.HTTPError as error:
            yield self.create_text_message(
                "SpecStream could not close this browser: " + error_message(error)
            )
            return
        closed = shown_session(session)
        yield self.create_json_message(closed)
        yield self.create_text_message(
            f"The browser is closed. It ran {closed['seconds']} seconds and {closed['steps']} "
            f"steps, and cost ${float(closed['charged_usd'] or 0):.4f}."
        )
