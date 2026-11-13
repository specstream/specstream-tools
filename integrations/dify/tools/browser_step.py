from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.browser import (
    NOT_A_STEP,
    STEP_NAME,
    arguments,
    shown_step,
    step_images,
    step_text,
)
from tools.client import SpecStreamClient, error_message


class BrowserStepTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        session_id = str(tool_parameters.get("session_id") or "").strip()
        step = str(tool_parameters.get("step") or "browser_read").strip()
        given = arguments(tool_parameters.get("arguments"))
        if not session_id.startswith("brs_"):
            yield self.create_text_message(
                "Pass the session ID from Open Browser. It starts with brs_."
            )
            return
        if step in NOT_A_STEP:
            yield self.create_text_message(
                "browser_close does not end the session. Call Close Browser with the session ID."
            )
            return
        if not STEP_NAME.match(step):
            yield self.create_text_message(
                "Set the step to a Playwright MCP tool name such as browser_navigate, "
                "browser_snapshot, browser_click or browser_type, or to browser_read."
            )
            return
        if given is None:
            yield self.create_text_message(
                'Pass the arguments as one JSON object, for example {"url": "https://example.com"}.'
            )
            return

        client = SpecStreamClient(self.runtime.credentials["specstream_api_key"])
        try:
            answer = client.post(
                f"/v1/browser/sessions/{session_id}/actions",
                {"tool": step, "arguments": given},
            )
        except requests.HTTPError as error:
            yield self.create_text_message(
                "SpecStream could not run this step: " + error_message(error)
            )
            return

        yield self.create_json_message(shown_step(step, answer))
        text = step_text(answer)
        if text:
            yield self.create_text_message(text)
        for data, mime_type in step_images(answer):
            yield self.create_blob_message(blob=data, meta={"mime_type": mime_type})
