"""SpecStreamBrowser: the members of the Claude browser toolset, each sent as one step of a SpecStream session.

A session takes Playwright MCP's tools, which address an element by the ref its snapshot gives it. So
`read_page` returns that snapshot, and the members that act on an element take a ref target. The few
members that take a coordinate (`left_click` at a point, `scroll`) run as a script in the page.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx2 as httpx
from anthropic.tools import ToolError
from anthropic.tools.browser import (
    BetaAbstractBrowserToolset20260801,
    BetaBrowserNavigateResult,
    BetaBrowserState,
    BetaScreenshotResult,
    BetaToolsetCallContext,
    TabMissingError,
)
from anthropic.types.beta import (
    BetaBrowserDoubleClickInput,
    BetaBrowserFindInput,
    BetaBrowserFormInputInput,
    BetaBrowserGetPageTextInput,
    BetaBrowserHoverInput,
    BetaBrowserJavascriptExecInput,
    BetaBrowserKeyInput,
    BetaBrowserLeftClickInput,
    BetaBrowserMiddleClickInput,
    BetaBrowserNavigateInput,
    BetaBrowserReadConsoleInput,
    BetaBrowserReadNetworkInput,
    BetaBrowserReadPageInput,
    BetaBrowserRightClickInput,
    BetaBrowserScreenshotInput,
    BetaBrowserScrollInput,
    BetaBrowserScrollToInput,
    BetaBrowserStateTabEntryParam,
    BetaBrowserTypeInput,
    BetaBrowserWaitInput,
)

from specstream_claude_browser._client import BASE_URL, SessionClient, SpecStreamError, StepResult

# A session has one page the driver follows, so the report always names this one tab.
TAB_ID = "tab-1"
# The API's own bounds for a session's length and for its idle wait, in seconds.
TIMEOUT_MIN_S, TIMEOUT_MAX_S = 60, 3600
IDLE_MIN_S, IDLE_MAX_S = 10, 600
# One wheel tick, in CSS pixels.
SCROLL_TICK_PX = 100
# The longest wait one step may ask for, in seconds: below the API's own wait for a step.
WAIT_MAX_S = 60.0

REF_ONLY = "This browser addresses elements by ref. Call read_page and pass a ref target."

_MODIFIERS = {
    "ctrl": "Control",
    "control": "Control",
    "cmd": "Meta",
    "command": "Meta",
    "meta": "Meta",
    "super": "Meta",
    "win": "Meta",
    "alt": "Alt",
    "option": "Alt",
    "shift": "Shift",
}
_KEYS = {
    "return": "Enter",
    "enter": "Enter",
    "backspace": "Backspace",
    "delete": "Delete",
    "del": "Delete",
    "escape": "Escape",
    "esc": "Escape",
    "tab": "Tab",
    "space": "Space",
    "up": "ArrowUp",
    "down": "ArrowDown",
    "left": "ArrowLeft",
    "right": "ArrowRight",
    "arrowup": "ArrowUp",
    "arrowdown": "ArrowDown",
    "arrowleft": "ArrowLeft",
    "arrowright": "ArrowRight",
    "page_up": "PageUp",
    "pageup": "PageUp",
    "prior": "PageUp",
    "page_down": "PageDown",
    "pagedown": "PageDown",
    "next": "PageDown",
    "home": "Home",
    "end": "End",
    "insert": "Insert",
}
_RESULT_SECTION = re.compile(r"^### Result\s*\n(.*?)(?=^### |\Z)", re.MULTILINE | re.DOTALL)


def playwright_key(chord: str) -> str:
    """One key or chord as Claude writes it ("ctrl+a", "Return") in Playwright's spelling ("Control+a", "Enter")."""
    if chord == "+":
        return chord
    parts = chord.split("+")
    if chord.endswith("++"):  # a chord that ends in the plus key itself, such as "ctrl++"
        parts = [*chord[:-2].split("+"), "+"]
    out: list[str] = []
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        low = part.lower()
        if not last and low in _MODIFIERS:
            out.append(_MODIFIERS[low])
        elif low in _KEYS:
            out.append(_KEYS[low])
        elif low in _MODIFIERS:
            out.append(_MODIFIERS[low])
        elif re.fullmatch(r"f\d{1,2}", low):
            out.append(low.upper())
        else:
            out.append(part)
    return "+".join(out)


def _modifiers(chord: str | None) -> list[str]:
    if not chord:
        return []
    names: list[str] = []
    for part in chord.split("+"):
        name = _MODIFIERS.get(part.strip().lower())
        if name is None:
            raise ToolError(f"Unknown modifier {part!r}. Use ctrl, shift, alt or cmd.")
        if name not in names:
            names.append(name)
    return names


def _evaluated(text: str) -> str:
    """The value a browser_evaluate step returned, without the sections Playwright MCP writes around it."""
    match = _RESULT_SECTION.search(text)
    return (match.group(1) if match else text).strip()


class SpecStreamBrowser(BetaAbstractBrowserToolset20260801):
    """The Claude browser toolset on a SpecStream browser session.

    The session opens at the first call and ends at `close()` (or at the end of the `with` block), so
    a toolset that is never called costs nothing. Time is charged by the second and each step once.

    Args:
        api_key: A SpecStream API key. Default: the SPECSTREAM_API_KEY environment variable.
        session_id: Drive a session that is already open, and leave it open at `close()`.
        timeout_s: The longest the session lasts, 60 to 3600 seconds.
        idle_timeout_s: The session ends after this long without a step, 10 to 600 seconds.
        allowed_domains: Hosts the session may open ("example.com", "*.example.com"). The session
            refuses every other host itself, in addition to any `url_policy` you pass.
        block_media: Do not load images, video and fonts.
        base_url: The API's address.
        transport: Replaces the network, for tests.
        **options: The toolset's own options: `url_policy`, `confirm`, `configs`, `file_policy`,
            `tool_configs`. `javascript_exec` is served only when you pass `confirm`.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        session_id: str | None = None,
        timeout_s: int = 900,
        idle_timeout_s: int = 300,
        allowed_domains: list[str] | None = None,
        block_media: bool = False,
        base_url: str = BASE_URL,
        transport: httpx.BaseTransport | None = None,
        **options: Any,
    ) -> None:
        if not TIMEOUT_MIN_S <= timeout_s <= TIMEOUT_MAX_S:
            raise ValueError(f"timeout_s must be {TIMEOUT_MIN_S} to {TIMEOUT_MAX_S} seconds.")
        if not IDLE_MIN_S <= idle_timeout_s <= IDLE_MAX_S:
            raise ValueError(f"idle_timeout_s must be {IDLE_MIN_S} to {IDLE_MAX_S} seconds.")
        # The API serves javascript_exec only when it is switched on, and the SDK then asks for a confirm
        # callable. So it is on with `confirm` and off without, and the few-line start works; a caller's
        # own entry wins.
        configs = dict(options.get("configs") or {})
        configs.setdefault("javascript_exec", {"enabled": options.get("confirm") is not None})
        options["configs"] = configs
        super().__init__(**options)
        self._client = SessionClient(
            api_key if api_key is not None else os.environ.get("SPECSTREAM_API_KEY", ""),
            base_url=base_url,
            transport=transport,
        )
        self._open_options = {
            "timeout_s": timeout_s,
            "idle_timeout_s": idle_timeout_s,
            "allowed_domains": allowed_domains,
            "block_media": block_media,
        }
        self._session_id = session_id
        self._owns_session = session_id is None
        self._released = False
        self._url = "about:blank"
        self._title = ""
        self.live_url: str | None = None

    @property
    def session_id(self) -> str | None:
        """The session's id once it is open."""
        return self._session_id

    # --- the session -----------------------------------------------------------------------

    def _session(self) -> str:
        if self._session_id is None:
            try:
                session = self._client.open(**self._open_options)
            except SpecStreamError as exc:
                raise ToolError(str(exc)) from exc
            self._session_id = str(session["id"])
            live = session.get("live_url")
            self.live_url = live if isinstance(live, str) else None
        return self._session_id

    def _step(self, tool: str, arguments: dict[str, Any] | None = None, *, tab_id: str | None = None) -> StepResult:
        if tab_id is not None and tab_id != TAB_ID:
            raise TabMissingError()
        try:
            result = self._client.step(self._session(), tool, arguments)
        except SpecStreamError as exc:
            raise ToolError(str(exc)) from exc
        if result.url:
            self._url = result.url
        if result.title is not None:
            self._title = result.title
        if result.error:
            raise ToolError(result.error)
        return result

    def _evaluate(self, function: str, *, tab_id: str | None, ref: str | None = None) -> str:
        arguments: dict[str, Any] = {"function": function}
        if ref is not None:
            arguments["target"] = ref
            arguments["element"] = "the target element"
        return _evaluated(self._step("browser_evaluate", arguments, tab_id=tab_id).text)

    def close(self) -> None:
        super().close()  # first, so no call is still using the browser when it ends
        if self._session_id is not None and self._owns_session and not self._released:
            self._released = True
            try:
                self._client.release(self._session_id)
            except SpecStreamError:
                # The session also ends by itself at its idle wait; closing must not raise in the host.
                pass
        self._client.close()

    # --- the state report -------------------------------------------------------------------

    def _browser_state(self, context: BetaToolsetCallContext) -> BetaBrowserState:
        if self._session_id is None:
            return BetaBrowserState(tabs=[], state_changes=[])
        return BetaBrowserState(
            tabs=[BetaBrowserStateTabEntryParam(tab_id=TAB_ID, title=self._title, url=self._url, active=True)],
            state_changes=[],
        )

    # --- members ------------------------------------------------------------------------------

    def navigate(self, context: BetaToolsetCallContext, input: BetaBrowserNavigateInput) -> BetaBrowserNavigateResult:
        word = input.url.strip().lower()
        if word == "back":
            self._step("browser_navigate_back", tab_id=input.tab_id)
        elif word == "forward":
            self._evaluate("() => { history.forward(); }", tab_id=input.tab_id)
        elif word == "reload":
            self._evaluate("() => { location.reload(); }", tab_id=input.tab_id)
        else:
            self._step("browser_navigate", {"url": input.url}, tab_id=input.tab_id)
        return BetaBrowserNavigateResult(url=self._url, status=None, title=self._title or None)

    def screenshot(self, context: BetaToolsetCallContext, input: BetaBrowserScreenshotInput) -> BetaScreenshotResult:
        # scale=css: one image pixel is one CSS pixel, so a coordinate read off the image is a page coordinate.
        result = self._step("browser_take_screenshot", {"type": "png", "scale": "css"}, tab_id=input.tab_id)
        if not result.image_data:
            raise ToolError("The browser returned no image.")
        media_type = result.image_media_type if result.image_media_type in ("image/png", "image/jpeg") else "image/png"
        return BetaScreenshotResult(data=result.image_data, media_type=media_type)

    def _click(self, input: Any, **extra: Any) -> None:
        target = input.target
        if target.type != "ref":
            raise ToolError(REF_ONLY)
        arguments: dict[str, Any] = {"target": target.ref, "element": "the target element", **extra}
        modifiers = _modifiers(input.modifiers)
        if modifiers:
            arguments["modifiers"] = modifiers
        self._step("browser_click", arguments, tab_id=input.tab_id)

    def left_click(self, context: BetaToolsetCallContext, input: BetaBrowserLeftClickInput) -> str | None:
        target = input.target
        if target.type == "ref":
            self._click(input)
            return None
        if input.modifiers:
            raise ToolError("A click at a coordinate takes no modifiers here. " + REF_ONLY)
        # A session has no pointer tool, so a click at a point is the element under it, clicked by script.
        found = self._evaluate(
            f"() => {{ const el = document.elementFromPoint({int(target.x)}, {int(target.y)}); "
            "if (!el) return false; el.click(); return true; }",
            tab_id=input.tab_id,
        )
        if found == "false":
            raise ToolError(f"No element at ({target.x}, {target.y}).")
        return "Clicked the element at that point by script. A ref target from read_page clicks with the pointer."

    def right_click(self, context: BetaToolsetCallContext, input: BetaBrowserRightClickInput) -> str | None:
        self._click(input, button="right")
        return None

    def middle_click(self, context: BetaToolsetCallContext, input: BetaBrowserMiddleClickInput) -> str | None:
        self._click(input, button="middle")
        return None

    def double_click(self, context: BetaToolsetCallContext, input: BetaBrowserDoubleClickInput) -> str | None:
        self._click(input, doubleClick=True)
        return None

    def hover(self, context: BetaToolsetCallContext, input: BetaBrowserHoverInput) -> str | None:
        if input.target.type != "ref":
            raise ToolError(REF_ONLY)
        self._step("browser_hover", {"target": input.target.ref, "element": "the target element"}, tab_id=input.tab_id)
        return None

    def scroll(self, context: BetaToolsetCallContext, input: BetaBrowserScrollInput) -> str | None:
        amount = (input.scroll_amount or 3) * SCROLL_TICK_PX
        dx, dy = {"up": (0, -amount), "down": (0, amount), "left": (-amount, 0), "right": (amount, 0)}[
            input.scroll_direction
        ]
        # Scrolls the nearest scrollable box under the point, or the page when there is none.
        self._evaluate(
            f"() => {{ let el = document.elementFromPoint({int(input.target.x)}, {int(input.target.y)}); "
            "while (el && el !== document.documentElement) { const s = getComputedStyle(el); "
            "const y = /(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight; "
            "const x = /(auto|scroll)/.test(s.overflowX) && el.scrollWidth > el.clientWidth; "
            f"if (({dy} !== 0 && y) || ({dx} !== 0 && x)) {{ el.scrollBy({dx}, {dy}); return true; }} "
            f"el = el.parentElement; }} window.scrollBy({dx}, {dy}); return true; }}",
            tab_id=input.tab_id,
        )
        return None

    def scroll_to(self, context: BetaToolsetCallContext, input: BetaBrowserScrollToInput) -> str | None:
        self._evaluate(
            "(element) => { element.scrollIntoView({block: 'center', inline: 'center'}); }",
            tab_id=input.tab_id,
            ref=input.target.ref,
        )
        return None

    def type(self, context: BetaToolsetCallContext, input: BetaBrowserTypeInput) -> str | None:
        # Types into the focused field: insertText fires the input events a page's own code listens for.
        typed = self._evaluate(
            f"() => document.execCommand('insertText', false, {json.dumps(input.text)})", tab_id=input.tab_id
        )
        if typed == "false":
            raise ToolError("No editable field has the focus. Click a field first, or use form_input with its ref.")
        return None

    def key(self, context: BetaToolsetCallContext, input: BetaBrowserKeyInput) -> str | None:
        chords = [playwright_key(chord) for chord in input.text.split()]
        if not chords:
            raise ToolError("No key to press.")
        for _ in range(max(1, input.repeat or 1)):
            for chord in chords:
                self._step("browser_press_key", {"key": chord}, tab_id=input.tab_id)
        return None

    def form_input(self, context: BetaToolsetCallContext, input: BetaBrowserFormInputInput) -> str | None:
        ref, value = input.target.ref, input.value
        if isinstance(value, bool):
            kind, text = "checkbox", "true" if value else "false"
        else:
            # A <select> takes the text of one of its options; every other field is filled as text.
            tag = self._evaluate("(element) => element.tagName", tab_id=input.tab_id, ref=ref)
            kind = "combobox" if "SELECT" in tag.upper() else "textbox"
            text = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
        field = {"name": "the target field", "type": kind, "target": ref, "value": text}
        self._step("browser_fill_form", {"fields": [field]}, tab_id=input.tab_id)
        return None

    def read_page(self, context: BetaToolsetCallContext, input: BetaBrowserReadPageInput) -> str:
        arguments: dict[str, Any] = {}
        if input.depth is not None:
            arguments["depth"] = input.depth
        if input.ref is not None:
            arguments["target"] = input.ref
        return self._step("browser_snapshot", arguments, tab_id=input.tab_id).text

    def find(self, context: BetaToolsetCallContext, input: BetaBrowserFindInput) -> str:
        # The session matches the words in the page's snapshot; it does not read a description.
        return self._step("browser_find", {"text": input.query}, tab_id=input.tab_id).text

    def get_page_text(self, context: BetaToolsetCallContext, input: BetaBrowserGetPageTextInput) -> str:
        return self._step("browser_read", {"format": "text"}, tab_id=input.tab_id).text

    def wait(self, context: BetaToolsetCallContext, input: BetaBrowserWaitInput) -> str | None:
        seconds = min(max(float(input.duration), 0.0), WAIT_MAX_S)
        self._step("browser_wait_for", {"time": seconds}, tab_id=input.tab_id)
        return None

    def read_console(self, context: BetaToolsetCallContext, input: BetaBrowserReadConsoleInput) -> str:
        return self._step("browser_console_messages", {"level": "info"}, tab_id=input.tab_id).text

    def read_network(self, context: BetaToolsetCallContext, input: BetaBrowserReadNetworkInput) -> str:
        return self._step("browser_network_requests", {"static": False}, tab_id=input.tab_id).text

    def javascript_exec(self, context: BetaToolsetCallContext, input: BetaBrowserJavascriptExecInput) -> str:
        return self._evaluate(f"async () => await (0, eval)({json.dumps(input.text)})", tab_id=input.tab_id)
