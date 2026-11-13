from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.browser import (
    IDLE_SECONDS,
    MAX_MINUTES,
    MIN_MINUTES,
    hosts,
    shown_session,
    shown_step,
    step_text,
    time_usd,
)
from tools.client import SpecStreamClient, error_message


class OpenBrowserTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        url = str(tool_parameters.get("url") or "").strip()
        try:
            minutes = int(float(tool_parameters.get("max_minutes") or 5))
        except (TypeError, ValueError):
            minutes = 0
        if not MIN_MINUTES <= minutes <= MAX_MINUTES:
            yield self.create_text_message(
                f"Set the maximum minutes from {MIN_MINUTES} to {MAX_MINUTES}. No browser was "
                "opened and nothing was charged."
            )
            return
        if url and not url.lower().startswith(("http://", "https://")):
            yield self.create_text_message(
                "Pass a full address that starts with https://. No browser was opened and "
                "nothing was charged."
            )
            return
        allowed, bad = hosts(str(tool_parameters.get("allowed_domains") or ""))
        if bad is not None:
            yield self.create_text_message(
                f"{bad[:80]!r} is not a host. List hosts such as example.com or *.example.com, "
                "with no scheme, path or port. No browser was opened and nothing was charged."
            )
            return

        client = SpecStreamClient(self.runtime.credentials["specstream_api_key"])
        # keep_alive: the steps come as separate calls with no client connected between them.
        body: dict[str, Any] = {
            "timeout_s": minutes * 60,
            "idle_timeout_s": IDLE_SECONDS,
            "keep_alive": True,
            "metadata": {"client": "dify"},
        }
        if allowed:
            body["allowed_domains"] = allowed
        try:
            session = client.post("/v1/browser/sessions", body)
        except requests.HTTPError as error:
            yield self.create_text_message(
                "SpecStream could not open a browser: " + error_message(error)
            )
            return

        session_id = str(session.get("id") or "")
        opened = shown_session(session)
        opened["max_time_usd"] = time_usd(minutes)
        lines = [
            f"The browser is open. Session ID: {session_id}. It closes on its own after "
            f"{minutes} minutes, or after {IDLE_SECONDS // 60} minutes without a step. Call "
            "Close Browser when the task is done, so the time stops being charged."
        ]
        if url:
            actions = f"/v1/browser/sessions/{session_id}/actions"
            try:
                went = client.post(actions, {"tool": "browser_navigate", "arguments": {"url": url}})
                opened["navigate"] = shown_step("browser_navigate", went)
                if went.get("error"):
                    lines.append(step_text(went))
                else:
                    read = client.post(
                        actions, {"tool": "browser_read", "arguments": {"format": "markdown"}}
                    )
                    opened["read"] = shown_step("browser_read", read)
                    lines.append(step_text(read))
            except requests.HTTPError as error:
                lines.append(
                    "The browser is open, but the page did not load: " + error_message(error)
                )
        yield self.create_json_message(opened)
        yield self.create_text_message("\n\n".join(line for line in lines if line))
