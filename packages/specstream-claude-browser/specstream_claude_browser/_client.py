"""The three SpecStream browser-session calls the driver needs: open a session, send it one step, end it."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx2 as httpx

BASE_URL = "https://api.specstream.ai"
USER_AGENT = "specstream-claude-browser/0.1.0"
# Above the API's own wait for one step (120 s), so the API's answer arrives before this client gives up.
REQUEST_TIMEOUT_S = 150.0


class SpecStreamError(Exception):
    """SpecStream refused a call, or answered with something this driver cannot read."""


@dataclass(frozen=True)
class StepResult:
    """The answer to one step: the tool's text and image, the page after it, and the tool's own error."""

    text: str = ""
    image_data: str | None = None
    image_media_type: str | None = None
    url: str | None = None
    title: str | None = None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


class SessionClient:
    """Calls /v1/browser/sessions with an API key. `transport` replaces the network, for tests."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise SpecStreamError(
                "No SpecStream API key. Pass api_key=..., or set SPECSTREAM_API_KEY. "
                "Create a key under Agents & API at https://specstream.ai/workspace."
            )
        token = api_key.strip()
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=REQUEST_TIMEOUT_S,
            transport=transport,
            headers={
                "Authorization": token if token.lower().startswith("bearer ") else f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )

    def open(
        self,
        *,
        timeout_s: int,
        idle_timeout_s: int,
        allowed_domains: list[str] | None = None,
        block_media: bool = False,
    ) -> dict[str, Any]:
        """Opens a session. keep_alive is true because the driver sends one step at a time, with no
        client connected between steps: without it the session would end at once."""
        body: dict[str, Any] = {
            "timeout_s": timeout_s,
            "idle_timeout_s": idle_timeout_s,
            "keep_alive": True,
            "metadata": {"client": "claude-browser-toolset"},
        }
        if allowed_domains:
            body["allowed_domains"] = list(allowed_domains)
        if block_media:
            body["block_media"] = True
        return self._request("POST", "/v1/browser/sessions", body)

    def step(self, session_id: str, tool: str, arguments: dict[str, Any] | None = None) -> StepResult:
        """One step: a Playwright MCP tool name with its arguments, or browser_read for the page's text."""
        data = self._request("POST", f"{self._path(session_id)}/actions", {"tool": tool, "arguments": arguments or {}})
        texts: list[str] = []
        image_data = image_media_type = None
        for part in data.get("result") or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
            elif part.get("type") == "image" and isinstance(part.get("data"), str) and image_data is None:
                image_data, image_media_type = part["data"], part.get("mime_type")
        error = data.get("error")
        message = None
        if isinstance(error, dict):
            message = str(error.get("message") or error.get("code") or "The step failed.")
            if error.get("reason"):
                message = f"{message} ({error['reason']})"
        return StepResult(
            text="\n".join(texts),
            image_data=image_data,
            image_media_type=image_media_type,
            url=data.get("url") if isinstance(data.get("url"), str) else None,
            title=data.get("title") if isinstance(data.get("title"), str) else None,
            error=message,
            raw=data,
        )

    def release(self, session_id: str) -> dict[str, Any]:
        """Ends the session, so that its time stops being charged."""
        return self._request("POST", f"{self._path(session_id)}/release", {})

    def close(self) -> None:
        self._http.close()

    @staticmethod
    def _path(session_id: str) -> str:
        return f"/v1/browser/sessions/{quote(session_id, safe='')}"

    def _request(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._http.request(method, path, json=body)
        except httpx.HTTPError as exc:
            raise SpecStreamError(f"Could not reach SpecStream: {exc.__class__.__name__}") from exc
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if response.status_code >= 400:
            error = payload.get("error") if isinstance(payload, dict) else None
            message = error.get("message") if isinstance(error, dict) else error
            if not isinstance(message, str) or not message:
                message = response.text[:300] or response.reason_phrase
            raise SpecStreamError(f"SpecStream answered {response.status_code}: {message}")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise SpecStreamError("SpecStream answered without data.")
        return data
