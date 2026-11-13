"""`SpecStreamBrowser`: a driver for the Claude SDK's browser toolset on a SpecStream browser session.

The driver opens a session with `POST /v1/browser/sessions` on the first call Claude makes, connects
Playwright to the session's `connect_url` (the Chrome DevTools Protocol) and runs each member of the
toolset there. `close()` releases the session, which ends its charge.

Playwright's synchronous objects belong to the thread that made them, and the SDK may call a toolset
from more than one thread (the tool runner's early start). So the driver keeps one worker thread and
runs every browser call on it, in the order the calls arrive.
"""

from __future__ import annotations

import base64
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

from anthropic.tools import ToolError
from anthropic.tools.browser import (
    BetaAbstractBrowserToolset20260801,
    BetaBrowserNavigateResult,
    BetaBrowserState,
    BetaDialogDismissed,
    BetaScreenshotResult,
    BetaToolsetCallContext,
)

from . import _page
from ._session import Send, SessionClient, SpecStreamError

log = logging.getLogger("specstream_claude_toolset")

T = TypeVar("T")

_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
_HOST_PORT = re.compile(r"^[^/?#:@]+:\d+(?:[/?#]|$)")
HISTORY = ("back", "forward", "reload")
NOTCH_PX = 100
NAVIGATION_TIMEOUT_MS = 45_000
ACTION_TIMEOUT_MS = 15_000
MAX_WAIT_S = 30.0
# The changes kept between two reports: a page that opens dialogs in a loop does not grow the list.
MAX_PENDING = 50


def _connect_playwright(connect_url: str) -> tuple[Any, Any]:
    """Playwright connected to the session over CDP: (the Playwright handle, the browser)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:  # pragma: no cover - playwright is a declared dependency
        raise SpecStreamError("Playwright is not installed. Run: pip install playwright") from error
    handle = sync_playwright().start()
    try:
        return handle, handle.chromium.connect_over_cdp(connect_url)
    except Exception:
        handle.stop()
        raise


def _short(error: BaseException) -> str:
    """The first line of a browser error, without Playwright's call log."""
    text = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
    return text[:300]


def web_url(url: str) -> str:
    """The address `navigate` opens: `https://` for one with no scheme, and only http and https."""
    url = url.strip()
    if not url:
        raise ToolError("An empty URL. Send an http or https address, or back, forward or reload.")
    if not _SCHEME.match(url) or _HOST_PORT.match(url):
        return f"https://{url}"
    scheme = url.split(":", 1)[0].lower()
    if scheme not in ("http", "https"):
        raise ToolError(f"A {scheme}: address is not opened. Send an http or https address.")
    return url


class SpecStreamBrowser(BetaAbstractBrowserToolset20260801):
    """The Claude browser toolset on a SpecStream browser session.

    Args:
        api_key: A SpecStream API key. Without one, the `SPECSTREAM_API_KEY` environment variable.
        allowed_domains: Hosts the session may open, such as `example.com` or `*.example.com`.
            SpecStream refuses every other host for the whole session: links, redirects and the
            requests a page makes, not only `navigate`. Empty allows every public host.
        timeout_s: The most seconds the session runs (60 to 3,600; default 300).
        idle_timeout_s: The session ends after this many seconds with no client (10 to 600).
        viewport: `(width, height)` of the page and of every screenshot. Default 1280 by 720.
        block_media: True skips images, video, audio and fonts.
        headless: False runs the browser with a screen.
        metadata: Your own labels for the session.
        base_url: The API's address, for a test server.
        send: Your own `(url, body, headers) -> (status, bytes)` for the two session calls.
        configs, confirm, url_policy, file_policy, tool_configs: the SDK's own options, passed on.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        allowed_domains: list[str] | None = None,
        timeout_s: int = 300,
        idle_timeout_s: int = 60,
        viewport: tuple[int, int] = (1280, 720),
        block_media: bool = False,
        headless: bool = True,
        metadata: dict[str, Any] | None = None,
        base_url: str | None = None,
        send: Send | None = None,
        connect: Callable[[str], tuple[Any, Any]] | None = None,
        **options: Any,
    ) -> None:
        super().__init__(**options)
        self._client = SessionClient(api_key, base_url=base_url, send=send)
        self._create: dict[str, Any] = {
            "timeout_s": timeout_s,
            "idle_timeout_s": idle_timeout_s,
            "viewport": {"width": int(viewport[0]), "height": int(viewport[1])},
        }
        if allowed_domains:
            self._create["allowed_domains"] = list(allowed_domains)
        if block_media:
            self._create["block_media"] = True
        if not headless:
            self._create["headless"] = False
        if metadata:
            self._create["metadata"] = dict(metadata)
        self._viewport = (int(viewport[0]), int(viewport[1]))
        self._connect = connect or _connect_playwright
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="specstream-browser")
        self._session: dict[str, Any] | None = None
        self._handle: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._tabs: dict[str, Any] = {}
        self._next_tab = 1
        self._active: str | None = None
        self._pending: list[Any] = []
        self._watched: set[int] = set()
        self._done = False

    # --- The session ---------------------------------------------------------------------------

    @property
    def session(self) -> dict[str, Any] | None:
        """The session as SpecStream answered it (`id`, `live_url`, `expires_at`), once one is open."""
        return self._session

    def _on_worker(self, call: Callable[[], T]) -> T:
        return self._worker.submit(call).result()

    def _run(self, call: Callable[[], T]) -> T:
        """Run a browser call on the worker thread; a browser error reaches Claude as one line."""

        def guarded() -> T:
            self._open()
            try:
                return call()
            except ToolError:
                raise
            except SpecStreamError:
                raise
            except Exception as error:
                raise ToolError(_short(error)) from error

        try:
            return self._on_worker(guarded)
        except SpecStreamError as error:
            raise ToolError(str(error)) from error

    def _open(self) -> None:
        if self._context is not None:
            return
        if self._done:
            raise ToolError("The browser is closed.")
        if self._session is None:
            self._session = self._client.open(self._create)
            log.debug("SpecStream browser session %s is open", self._session.get("id"))
        handle, browser = self._connect(str(self._session["connect_url"]))
        self._handle, self._browser = handle, browser
        contexts = list(browser.contexts)
        self._context = contexts[0] if contexts else browser.new_context()
        if not list(self._context.pages):
            self._context.new_page()
        self._sync_tabs(report=False)

    def close(self) -> None:
        """End the toolset, then the browser and the session. Safe to call twice."""
        super().close()  # first, so no call is still using the browser when it closes
        if self._done:
            return
        self._done = True

        def end() -> None:
            for step in (
                lambda: self._browser.close() if self._browser is not None else None,
                lambda: self._handle.stop() if self._handle is not None else None,
                lambda: self._client.release(str(self._session["id"])) if self._session else None,
            ):
                try:
                    step()
                except Exception as error:  # the session also ends by itself at its timeout
                    log.debug("closing the SpecStream browser: %s", _short(error))
            self._context = None

        try:
            self._on_worker(end)
        finally:
            self._worker.shutdown(wait=False)

    # --- Tabs and state --------------------------------------------------------------------------

    def _remember(self, change: Any) -> None:
        if len(self._pending) < MAX_PENDING:
            self._pending.append(change)

    def _watch(self, page: Any) -> None:
        if id(page) in self._watched:
            return
        self._watched.add(id(page))

        def dismiss(dialog: Any) -> None:
            kind, message = str(dialog.type), str(dialog.message)[:500]
            try:
                dialog.dismiss()
            except Exception:
                pass
            self._remember(BetaDialogDismissed(kind=kind, message=message))

        try:
            page.on("dialog", dismiss)
        except Exception as error:
            log.debug("no dialog watch on a tab: %s", _short(error))

    def _sync_tabs(self, *, report: bool = True) -> None:
        """Match the tab ids to the pages the browser has now: a page a click opened gets an id."""
        pages = [page for page in self._context.pages if not page.is_closed()]
        self._tabs = {tab: page for tab, page in self._tabs.items() if any(page is p for p in pages)}
        for page in pages:
            if not any(page is known for known in self._tabs.values()):
                tab_id = f"tab-{self._next_tab}"
                self._next_tab += 1
                self._tabs[tab_id] = page
                self._watch(page)
                if report:
                    self._remember({"type": "tab_opened", "tab_id": tab_id})
                    self._active = tab_id  # a tab the page opened comes to the front, as in a browser
        if self._active not in self._tabs:
            self._active = next(reversed(self._tabs), None)

    def _page(self, tab_id: str | None) -> Any:
        self._sync_tabs()
        wanted = tab_id or self._active
        if wanted is None:
            raise ToolError("No tab is open. Open one with new_tab.")
        page = self._tabs.get(wanted)
        if page is None:
            raise ToolError(f"No tab {wanted!r}. Open tabs: {', '.join(self._tabs) or 'none'}.")
        return page

    def _entry(self, tab_id: str) -> dict[str, Any]:
        page = self._tabs[tab_id]
        try:
            title = page.title()
        except Exception:
            title = ""
        entry: dict[str, Any] = {"tab_id": tab_id, "title": title, "url": page.url}
        if tab_id == self._active:
            entry["active"] = True
        return entry

    def _browser_state(self, context: BetaToolsetCallContext) -> BetaBrowserState:
        def report() -> BetaBrowserState:
            if self._context is None:
                return BetaBrowserState(tabs=[])
            self._sync_tabs()
            changes, self._pending = self._pending, []
            open_now = set(self._tabs)
            changes = [
                change
                for change in changes
                if not (isinstance(change, dict) and change.get("type") == "tab_opened") or change["tab_id"] in open_now
            ]
            return BetaBrowserState(tabs=[self._entry(tab) for tab in self._tabs], state_changes=changes)

        return self._on_worker(report)

    def new_tab(self, context: BetaToolsetCallContext, input: Any) -> Any:
        def act() -> dict[str, Any]:
            self._sync_tabs()
            page = self._context.new_page()
            self._sync_tabs(report=False)
            tab_id = next(tab for tab, known in self._tabs.items() if known is page)
            self._remember({"type": "tab_opened", "tab_id": tab_id})
            self._active = tab_id
            return self._entry(tab_id)

        return self._run(act)

    def list_tabs(self, context: BetaToolsetCallContext, input: Any) -> Any:
        def act() -> list[dict[str, Any]]:
            self._sync_tabs()
            return [self._entry(tab) for tab in self._tabs]

        return self._run(act)

    def switch_tab(self, context: BetaToolsetCallContext, input: Any) -> Any:
        def act() -> dict[str, Any]:
            page = self._page(input.tab_id)
            self._active = input.tab_id
            try:
                page.bring_to_front()
            except Exception as error:
                log.debug("bring_to_front: %s", _short(error))
            return self._entry(input.tab_id)

        return self._run(act)

    def close_tab(self, context: BetaToolsetCallContext, input: Any) -> None:
        def act() -> None:
            self._page(input.tab_id).close()
            self._sync_tabs()

        return self._run(act)

    # --- Navigation and capture ------------------------------------------------------------------

    def navigate(self, context: BetaToolsetCallContext, input: Any) -> BetaBrowserNavigateResult:
        def act() -> BetaBrowserNavigateResult:
            page = self._page(input.tab_id)
            page.set_default_timeout(ACTION_TIMEOUT_MS)
            word = input.url.strip().lower()
            options = {"wait_until": "domcontentloaded", "timeout": NAVIGATION_TIMEOUT_MS}
            if word == "back":
                response = page.go_back(**options)
            elif word == "forward":
                response = page.go_forward(**options)
            elif word == "reload":
                response = page.reload(**options)
            else:
                response = page.goto(web_url(input.url), **options)
            status = response.status if response is not None else None
            return BetaBrowserNavigateResult(url=page.url, status=status, title=page.title())

        return self._run(act)

    def screenshot(self, context: BetaToolsetCallContext, input: Any) -> BetaScreenshotResult:
        def act() -> BetaScreenshotResult:
            data = self._page(input.tab_id).screenshot(type="png", scale="css")
            return BetaScreenshotResult(data=base64.b64encode(data).decode("ascii"), media_type="image/png")

        return self._run(act)

    def zoom(self, context: BetaToolsetCallContext, input: Any) -> BetaScreenshotResult:
        def act() -> BetaScreenshotResult:
            region = list(input.region)
            if len(region) != 4:
                raise ToolError("region is [x0, y0, x1, y1] in viewport pixels.")
            x0, y0, x1, y1 = (int(value) for value in region)
            width, height = self._viewport
            x0, x1 = max(0, min(x0, x1)), min(width, max(x0, x1))
            y0, y1 = max(0, min(y0, y1)), min(height, max(y0, y1))
            if x1 - x0 < 1 or y1 - y0 < 1:
                raise ToolError(f"region is empty inside the {width} by {height} viewport.")
            data = self._page(input.tab_id).screenshot(
                type="png", scale="device", clip={"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}
            )
            return BetaScreenshotResult(data=base64.b64encode(data).decode("ascii"), media_type="image/png")

        return self._run(act)

    # --- Pointer ---------------------------------------------------------------------------------

    def _point(self, target: Any) -> tuple[int, int]:
        if getattr(target, "type", None) != "coordinate":
            raise ToolError("This member takes a coordinate target: {type: coordinate, x, y}.")
        x, y = int(target.x), int(target.y)
        width, height = self._viewport
        if not (0 <= x < width and 0 <= y < height):
            raise ToolError(f"({x}, {y}) is outside the {width} by {height} viewport.")
        return x, y

    def _element(self, page: Any, target: Any) -> Any:
        ref = getattr(target, "ref", None)
        if getattr(target, "type", None) != "ref" or not ref:
            raise ToolError("This member takes an element reference: {type: ref, ref}.")
        element = page.evaluate_handle(_page.ELEMENT_SCRIPT, ref).as_element()
        if element is None:
            raise ToolError(
                f"{ref} is stale or not found on the current page. Re-read the page to get fresh references."
            )
        return element

    def _click(self, input: Any, *, button: str = "left", count: int = 1) -> None:
        def act() -> None:
            page = self._page(input.tab_id)
            held = _page.modifiers(getattr(input, "modifiers", None))
            if input.target.type == "ref":
                self._element(page, input.target).click(
                    button=button, click_count=count, modifiers=held or None, timeout=ACTION_TIMEOUT_MS
                )
                return
            x, y = self._point(input.target)
            for name in held:
                page.keyboard.down(name)
            try:
                page.mouse.click(x, y, button=button, click_count=count)
            finally:
                for name in reversed(held):
                    page.keyboard.up(name)

        self._run(act)

    def left_click(self, context: BetaToolsetCallContext, input: Any) -> None:
        self._click(input)

    def right_click(self, context: BetaToolsetCallContext, input: Any) -> None:
        self._click(input, button="right")

    def middle_click(self, context: BetaToolsetCallContext, input: Any) -> None:
        self._click(input, button="middle")

    def double_click(self, context: BetaToolsetCallContext, input: Any) -> None:
        self._click(input, count=2)

    def triple_click(self, context: BetaToolsetCallContext, input: Any) -> None:
        self._click(input, count=3)

    def hover(self, context: BetaToolsetCallContext, input: Any) -> None:
        def act() -> None:
            page = self._page(input.tab_id)
            if input.target.type == "ref":
                self._element(page, input.target).hover(timeout=ACTION_TIMEOUT_MS)
            else:
                page.mouse.move(*self._point(input.target))

        self._run(act)

    def mouse_move(self, context: BetaToolsetCallContext, input: Any) -> None:
        self._run(lambda: self._page(input.tab_id).mouse.move(*self._point(input.target)))

    def left_mouse_down(self, context: BetaToolsetCallContext, input: Any) -> None:
        def act() -> None:
            page = self._page(input.tab_id)
            page.mouse.move(*self._point(input.target))
            page.mouse.down()

        self._run(act)

    def left_mouse_up(self, context: BetaToolsetCallContext, input: Any) -> None:
        def act() -> None:
            page = self._page(input.tab_id)
            page.mouse.move(*self._point(input.target))
            page.mouse.up()

        self._run(act)

    def left_click_drag(self, context: BetaToolsetCallContext, input: Any) -> None:
        def act() -> None:
            page = self._page(input.tab_id)
            start, end = self._point(input.from_), self._point(input.target)
            page.mouse.move(*start)
            page.mouse.down()
            try:
                page.mouse.move(*end, steps=10)
            finally:
                page.mouse.up()

        self._run(act)

    def scroll(self, context: BetaToolsetCallContext, input: Any) -> None:
        def act() -> None:
            page = self._page(input.tab_id)
            notches = input.scroll_amount if input.scroll_amount is not None else 3
            distance = max(1, min(int(notches), 10)) * NOTCH_PX
            dx, dy = {"up": (0, -distance), "down": (0, distance), "left": (-distance, 0), "right": (distance, 0)}[
                str(input.scroll_direction)
            ]
            page.mouse.move(*self._point(input.target))
            page.mouse.wheel(dx, dy)

        self._run(act)

    def scroll_to(self, context: BetaToolsetCallContext, input: Any) -> None:
        def act() -> None:
            page = self._page(input.tab_id)
            self._element(page, input.target).scroll_into_view_if_needed(timeout=ACTION_TIMEOUT_MS)

        self._run(act)

    # --- Keyboard and timing ---------------------------------------------------------------------

    def type(self, context: BetaToolsetCallContext, input: Any) -> None:
        self._run(lambda: self._page(input.tab_id).keyboard.type(input.text))

    def key(self, context: BetaToolsetCallContext, input: Any) -> None:
        def act() -> None:
            page = self._page(input.tab_id)
            keys = _page.chords(input.text)
            repeat = max(1, min(int(input.repeat or 1), 100))
            for _ in range(repeat):
                for name in keys:
                    page.keyboard.press(name)

        self._run(act)

    def hold_key(self, context: BetaToolsetCallContext, input: Any) -> None:
        def act() -> None:
            page = self._page(input.tab_id)
            names = _page.chord(input.text).split("+") if input.text.strip() != "+" else ["+"]
            names = [name for name in names if name]
            if not names:
                raise ToolError("An empty key. Send a key such as Shift, or a chord such as ctrl+a.")
            for name in names:
                page.keyboard.down(name)
            try:
                time.sleep(max(0.0, min(float(input.duration), MAX_WAIT_S)))
            finally:
                for name in reversed(names):
                    page.keyboard.up(name)

        self._run(act)

    def wait(self, context: BetaToolsetCallContext, input: Any) -> None:
        def act() -> None:
            self._page(input.tab_id)
            time.sleep(max(0.0, min(float(input.duration), MAX_WAIT_S)))

        self._run(act)

    # --- Reading ---------------------------------------------------------------------------------

    def _tree(self, page: Any, *, filter: str, depth: int, ref: str | None) -> list[dict]:
        answer = page.evaluate(
            _page.TREE_SCRIPT, {"filter": filter, "depth": max(1, int(depth)), "ref": ref, "maxLines": 5_000}
        )
        if answer.get("stale"):
            raise ToolError(
                f"{ref} is stale or not found on the current page. Re-read the page to get fresh references."
            )
        return list(answer.get("lines") or [])

    def read_page(self, context: BetaToolsetCallContext, input: Any) -> str:
        def act() -> str:
            lines = self._tree(
                self._page(input.tab_id),
                filter=str(input.filter) if input.filter else "visible",
                depth=input.depth if input.depth is not None else 15,
                ref=input.ref,
            )
            return _page.render(lines)

        return self._run(act)

    def find(self, context: BetaToolsetCallContext, input: Any) -> str:
        def act() -> str:
            lines = self._tree(self._page(input.tab_id), filter="all", depth=1_000, ref=None)
            found = _page.match(lines, input.query)
            if not found:
                return f"No element matches {input.query!r}. Try other words, or read_page."
            return _page.render(found)

        return self._run(act)

    def get_page_text(self, context: BetaToolsetCallContext, input: Any) -> str:
        def act() -> str:
            text = str(self._page(input.tab_id).evaluate(_page.TEXT_SCRIPT) or "")
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            if len(text) > _page.TEXT_LIMIT:
                text = text[: _page.TEXT_LIMIT] + "\n(Cut at 100,000 characters.)"
            return text

        return self._run(act)

    def form_input(self, context: BetaToolsetCallContext, input: Any) -> None:
        def act() -> None:
            page = self._page(input.tab_id)
            element = self._element(page, input.target)
            kind = element.evaluate(_page.KIND_SCRIPT)
            value = input.value
            if kind["tag"] == "input" and kind["type"] in ("checkbox", "radio"):
                if not isinstance(value, bool):
                    raise ToolError("A checkbox or radio takes true or false.")
                element.set_checked(value, timeout=ACTION_TIMEOUT_MS)
            elif kind["tag"] == "select":
                try:
                    element.select_option(value=str(value), timeout=2_000)
                except Exception:
                    element.select_option(label=str(value), timeout=ACTION_TIMEOUT_MS)
            else:
                text = ("true" if value else "false") if isinstance(value, bool) else str(value)
                element.fill(text, timeout=ACTION_TIMEOUT_MS)

        self._run(act)
