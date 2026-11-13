"""LangChain tools that open a real browser at SpecStream and drive it: open a page, read it,
click, type, close (POST /v1/browser/sessions and its actions)."""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any, Literal, Optional

from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from langchain_specstream._api import SpecStreamAPI
from langchain_specstream.tools import _SpecStreamTool

# A step waits on the page for up to 120 seconds on the server, so the call waits a little longer.
STEP_TIMEOUT_SECONDS = 130.0
TOOL_NAME = re.compile(r"^browser_[a-z][a-z0-9_]{0,62}$")
SESSION_KEYS = ("status", "ended_reason", "live_url", "expires_at", "timeout_s", "seconds", "actions", "charged_usd", "price")


def _session_path(session_id: str) -> str:
    sid = (session_id or "").strip()
    if not sid:
        raise ValueError("Pass the session_id that specstream_open_browser returned.")
    return f"/v1/browser/sessions/{urllib.parse.quote(sid, safe='')}"


def shown_session(session: dict[str, Any]) -> dict[str, Any]:
    """A session as the model reads it. The connect address is left out: it carries the session's token."""
    out: dict[str, Any] = {"session_id": session.get("id")}
    out.update({key: session[key] for key in SESSION_KEYS if session.get(key) is not None})
    return out


def shown_step(session_id: str, step: dict[str, Any]) -> dict[str, Any]:
    """One step as the model reads it: the step's text, where the page is, and what the step cost."""
    out: dict[str, Any] = {"session_id": session_id}
    texts: list[str] = []
    images: list[dict[str, Any]] = []
    for part in step.get("result") or []:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text" and part.get("text"):
            texts.append(str(part["text"]))
        elif part.get("type") == "image":
            # An image's base64 is of no use to a model that reads text, and it is large.
            images.append({"mime_type": part.get("mime_type"), "base64_chars": len(part.get("data") or "")})
    if texts:
        out["text"] = "\n\n".join(texts)
    if images:
        out["images"] = images
    for key in ("url", "title", "read_at", "price_usd"):
        if step.get(key) is not None:
            out[key] = step[key]
    if step.get("error"):
        out["error"] = step["error"]
    return out


def open_session(api: SpecStreamAPI, **settings: Any) -> dict[str, Any]:
    """Open a browser with POST /v1/browser/sessions. Time is charged by the second while it is open."""
    body = {key: value for key, value in settings.items() if value not in (None, [], {})}
    return api.request("POST", "/v1/browser/sessions", body) or {}


def step(api: SpecStreamAPI, session_id: str, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run one step in the session's browser with POST /v1/browser/sessions/{id}/actions."""
    path = _session_path(session_id)
    if not TOOL_NAME.match(tool or ""):
        raise ValueError("tool must be a browser step name such as browser_navigate or browser_click.")
    arguments = {key: value for key, value in (arguments or {}).items() if value is not None}
    slow = SpecStreamAPI(api.api_key, api.base_url, timeout=max(api.timeout, STEP_TIMEOUT_SECONDS), opener=api.opener)
    answer = slow.request("POST", f"{path}/actions", {"tool": tool, "arguments": arguments}) or {}
    return shown_step(session_id.strip(), answer)


def close_session(api: SpecStreamAPI, session_id: str) -> dict[str, Any]:
    """End the session with POST /v1/browser/sessions/{id}/release, so its time stops being charged."""
    return shown_session(api.request("POST", f"{_session_path(session_id)}/release") or {})


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


SESSION_ID = Field(min_length=1, description="The session_id returned by specstream_open_browser.")
TARGET = "The element's reference from the last specstream_browser_snapshot (such as e12), or a unique selector."


class OpenBrowserInput(BaseModel):
    """What the model fills in. How long the browser may run, and so its highest price, is set on the tool."""

    url: Optional[str] = Field(default=None, description="A page to open first, as an http or https address.")


class SessionInput(BaseModel):
    session_id: str = SESSION_ID


class NavigateInput(BaseModel):
    session_id: str = SESSION_ID
    url: str = Field(min_length=1, description="The http or https address to open.")


class ReadInput(BaseModel):
    session_id: str = SESSION_ID
    format: Literal["markdown", "text"] = Field(default="markdown", description='"markdown" or "text".')


class ClickInput(BaseModel):
    session_id: str = SESSION_ID
    target: str = Field(min_length=1, description=TARGET)
    element: Optional[str] = Field(default=None, description="What the element is, in a few words.")


class TypeInput(BaseModel):
    session_id: str = SESSION_ID
    target: str = Field(min_length=1, description=TARGET)
    text: str = Field(description="The text to type into the element.")
    submit: bool = Field(default=False, description="Press Enter after the text.")


class ActionInput(BaseModel):
    session_id: str = SESSION_ID
    tool: str = Field(
        pattern=TOOL_NAME.pattern,
        description=(
            "The step's name: browser_press_key, browser_select_option, browser_fill_form, browser_hover, "
            "browser_wait_for, browser_navigate_back, browser_tabs, browser_handle_dialog, browser_take_screenshot "
            "or another Playwright MCP tool name."
        ),
    )
    arguments: dict[str, Any] = Field(default_factory=dict, description="The step's arguments, as Playwright MCP names them.")


class SpecStreamOpenBrowser(_SpecStreamTool):
    """Open a real browser that SpecStream runs, for pages that need clicks, typed text or JavaScript.

    Time costs $0.10 an hour, charged by the second, and each step costs $0.001 ($1 per 1,000). The browser
    ends by itself after ``timeout_s`` seconds, which you set here, in code: the model can't keep it open longer.

    Example:
        .. code-block:: python

            from langchain_specstream import specstream_browser_tools

            tools = specstream_browser_tools(timeout_s=300, allowed_domains=["example.com"])
    """

    name: str = "specstream_open_browser"
    description: str = (
        "Open a real browser in the cloud and get its session_id. Use it when a page needs clicks, typed text, "
        "a sign-in the user gave you, or JavaScript before its content shows; for the plain text of a known page, "
        "specstream_extract_pages is cheaper. The browser costs money while it is open, so call "
        "specstream_close_browser with the session_id as soon as the work is done."
    )
    args_schema: type[BaseModel] = OpenBrowserInput

    timeout_s: int = Field(default=300, ge=60, le=3600)
    """The most seconds the browser runs. At $0.10 an hour, 300 seconds is at most $0.0084 of time."""
    idle_timeout_s: int = Field(default=120, ge=10, le=600)
    """The browser ends after this many seconds with no step."""
    allowed_domains: Optional[list[str]] = None
    """Hosts the browser may open, such as example.com or *.example.com. None allows every public host."""
    block_media: bool = False
    """True skips images, video, audio and fonts, so pages load faster."""
    headless: bool = True
    metadata: Optional[dict[str, Any]] = None
    """Your own labels for the session."""

    def _run(self, url: Optional[str] = None, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        api = self._api()
        session = open_session(
            api,
            timeout_s=self.timeout_s,
            idle_timeout_s=self.idle_timeout_s,
            # The tools drive the browser by steps and hold no connection, so the session must outlive one.
            keep_alive=True,
            allowed_domains=self.allowed_domains,
            block_media=self.block_media or None,
            headless=None if self.headless else False,
            metadata=self.metadata,
        )
        out = shown_session(session)
        first = (url or "").strip()
        if first and out.get("session_id"):
            out["page"] = step(api, str(out["session_id"]), "browser_navigate", {"url": first})
        out["message"] = "Call specstream_close_browser with this session_id when the work is done."
        return _json(out)


class _StepTool(_SpecStreamTool):
    def _step(self, session_id: str, tool: str, arguments: dict[str, Any] | None = None) -> str:
        return _json(step(self._api(), session_id, tool, arguments))


class SpecStreamBrowserNavigate(_StepTool):
    """Open an address in the session's browser."""

    name: str = "specstream_browser_navigate"
    description: str = (
        "Open an http or https address in the browser of a session. A page the site or the session's allowed "
        "hosts refuse comes back as an error with its reason. Then read it with specstream_browser_read or "
        "specstream_browser_snapshot."
    )
    args_schema: type[BaseModel] = NavigateInput

    def _run(self, session_id: str, url: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        return self._step(session_id, "browser_navigate", {"url": url.strip()})


class SpecStreamBrowserRead(_StepTool):
    """Read the text of the page the browser is on, as Markdown or plain text."""

    name: str = "specstream_browser_read"
    description: str = (
        "Read the text of the page the session's browser is on, as it stands after its JavaScript ran, in "
        "Markdown or plain text, with the page's address, its title and when it was read."
    )
    args_schema: type[BaseModel] = ReadInput

    def _run(self, session_id: str, format: str = "markdown", run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        return self._step(session_id, "browser_read", {"format": "text" if format == "text" else "markdown"})


class SpecStreamBrowserSnapshot(_StepTool):
    """List the page's elements with the reference each click or typed text needs."""

    name: str = "specstream_browser_snapshot"
    description: str = (
        "List the elements of the page the session's browser is on (links, buttons, fields), each with a "
        "reference. Call it before specstream_browser_click or specstream_browser_type, and again after the page changes."
    )
    args_schema: type[BaseModel] = SessionInput

    def _run(self, session_id: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        return self._step(session_id, "browser_snapshot")


class SpecStreamBrowserClick(_StepTool):
    """Click an element of the page."""

    name: str = "specstream_browser_click"
    description: str = "Click an element of the page in the session's browser, by its reference from the last snapshot."
    args_schema: type[BaseModel] = ClickInput

    def _run(
        self, session_id: str, target: str, element: Optional[str] = None, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        return self._step(session_id, "browser_click", {"target": target, "element": element})


class SpecStreamBrowserType(_StepTool):
    """Type text into a field of the page."""

    name: str = "specstream_browser_type"
    description: str = (
        "Type text into a field of the page in the session's browser, by its reference from the last snapshot. "
        "submit true presses Enter after the text."
    )
    args_schema: type[BaseModel] = TypeInput

    def _run(
        self, session_id: str, target: str, text: str, submit: bool = False, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        return self._step(session_id, "browser_type", {"target": target, "text": text, "submit": True if submit else None})


class SpecStreamBrowserAction(_StepTool):
    """Run any other browser step by its Playwright MCP name (a key press, a select, a wait, a form)."""

    name: str = "specstream_browser_action"
    description: str = (
        "Run any other step in the session's browser by its Playwright MCP tool name and arguments: "
        "browser_press_key {key}, browser_select_option, browser_fill_form, browser_hover, browser_wait_for, "
        "browser_navigate_back, browser_tabs, browser_handle_dialog. Use the named tools for opening, reading, "
        "clicking and typing."
    )
    args_schema: type[BaseModel] = ActionInput

    def _run(
        self, session_id: str, tool: str, arguments: Optional[dict[str, Any]] = None, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        return self._step(session_id, tool, arguments)


class SpecStreamCloseBrowser(_SpecStreamTool):
    """End a browser session, so its time stops being charged. Returns what the session cost."""

    name: str = "specstream_close_browser"
    description: str = (
        "Close the browser of a session when the work is done, so its time stops being charged. "
        "Returns the seconds it ran, the steps it counted and what it cost."
    )
    args_schema: type[BaseModel] = SessionInput

    def _run(self, session_id: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        return _json(close_session(self._api(), session_id))


def specstream_browser_tools(
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout_s: int = 300,
    idle_timeout_s: int = 120,
    allowed_domains: Optional[list[str]] = None,
    block_media: bool = False,
) -> list[BaseTool]:
    """The browser tools, ready for an agent: open, navigate, read, snapshot, click, type, any other step, close."""
    shared: dict[str, Any] = {}
    if api_key:
        shared["api_key"] = api_key
    if base_url:
        shared["base_url"] = base_url
    return [
        SpecStreamOpenBrowser(
            timeout_s=timeout_s, idle_timeout_s=idle_timeout_s, allowed_domains=allowed_domains, block_media=block_media, **shared
        ),
        SpecStreamBrowserNavigate(**shared),
        SpecStreamBrowserRead(**shared),
        SpecStreamBrowserSnapshot(**shared),
        SpecStreamBrowserClick(**shared),
        SpecStreamBrowserType(**shared),
        SpecStreamBrowserAction(**shared),
        SpecStreamCloseBrowser(**shared),
    ]
