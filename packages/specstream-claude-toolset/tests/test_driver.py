"""The driver with a scripted SpecStream API and a scripted browser: no network, no key, no Chromium."""

from __future__ import annotations

import json

import pytest
from anthropic.tools import ToolError
from anthropic.types.beta import BetaToolUseBlock

from specstream_claude_toolset import SpecStreamBrowser, SpecStreamError, _page
from specstream_claude_toolset.browser import web_url


class FakeResponse:
    status = 200


class FakeKeyboard:
    def __init__(self, log: list) -> None:
        self.log = log

    def press(self, key: str) -> None:
        self.log.append(("press", key))

    def down(self, key: str) -> None:
        self.log.append(("down", key))

    def up(self, key: str) -> None:
        self.log.append(("up", key))

    def type(self, text: str) -> None:
        self.log.append(("type", text))


class FakeMouse:
    def __init__(self, log: list) -> None:
        self.log = log

    def click(self, x: int, y: int, **options: object) -> None:
        self.log.append(("click", x, y, options))

    def move(self, x: int, y: int, **options: object) -> None:
        self.log.append(("move", x, y))

    def wheel(self, dx: int, dy: int) -> None:
        self.log.append(("wheel", dx, dy))

    def down(self) -> None:
        self.log.append(("mouse_down",))

    def up(self) -> None:
        self.log.append(("mouse_up",))


class FakePage:
    def __init__(self, log: list) -> None:
        self.log = log
        self.url = "about:blank"
        self.keyboard = FakeKeyboard(log)
        self.mouse = FakeMouse(log)
        self.closed = False

    def is_closed(self) -> bool:
        return self.closed

    def on(self, event: str, handler: object) -> None:
        pass

    def set_default_timeout(self, value: int) -> None:
        pass

    def title(self) -> str:
        return "Example Domain" if self.url != "about:blank" else ""

    def goto(self, url: str, **options: object) -> FakeResponse:
        if "refused" in url:
            raise RuntimeError("net::ERR_BLOCKED_BY_CLIENT at " + url + "\nCall log:\n  - navigating")
        self.log.append(("goto", url))
        self.url = url
        return FakeResponse()


class FakeContext:
    def __init__(self, log: list) -> None:
        self.log = log
        self.pages = [FakePage(log)]

    def new_page(self) -> FakePage:
        page = FakePage(self.log)
        self.pages.append(page)
        return page


class FakeBrowser:
    def __init__(self, log: list) -> None:
        self.log = log
        self.contexts = [FakeContext(log)]

    def close(self) -> None:
        self.log.append(("browser_close",))


class FakeHandle:
    def __init__(self, log: list) -> None:
        self.log = log

    def stop(self) -> None:
        self.log.append(("stop",))


def make(status: int = 201, body: dict | None = None, **options: object):
    requests: list[tuple[str, dict, dict]] = []
    log: list = []

    def api(url: str, sent: dict, headers: dict) -> tuple[int, bytes]:
        requests.append((url, sent, headers))
        if url.endswith("/release"):
            return 200, json.dumps({"id": "bs_1", "status": "ended"}).encode()
        answer = (
            body if body is not None else {"id": "bs_1", "connect_url": "wss://connect.test/s", "status": "running"}
        )
        return status, json.dumps(answer).encode()

    def connect(url: str):
        log.append(("connect", url))
        return FakeHandle(log), FakeBrowser(log)

    toolset = SpecStreamBrowser("sk-test", send=api, connect=connect, **options)
    return toolset, requests, log


_COUNT = iter(range(1, 10_000))


def run(toolset: SpecStreamBrowser, member: str, **input: object) -> dict:
    block = BetaToolUseBlock(
        id=f"toolu_{next(_COUNT)}", type="tool_use", name=member, input=input, toolset_name=toolset.toolset_name
    )
    return dict(toolset.tool_result(block))


def text_of(result: dict) -> str:
    return "\n".join(part["text"] for part in result["content"] if part["type"] == "text")


def test_no_session_opens_before_the_first_call_and_the_key_goes_in_the_header():
    toolset, requests, log = make(allowed_domains=["example.com"], timeout_s=600, block_media=True)
    assert requests == [] and toolset.session is None
    result = run(toolset, "navigate", url="example.com")
    assert not result.get("is_error"), result
    assert "Navigated to https://example.com" in text_of(result)
    assert len(requests) == 1 and requests[0][2]["Authorization"] == "Bearer sk-test"
    assert requests[0][0] == "https://api.specstream.ai/v1/browser/sessions"
    sent = requests[0][1]
    assert sent["allowed_domains"] == ["example.com"] and sent["timeout_s"] == 600 and sent["block_media"] is True
    assert ("connect", "wss://connect.test/s") in log and ("goto", "https://example.com") in log
    run(toolset, "navigate", url="https://example.com/a")
    assert len(requests) == 1  # one session serves every call
    toolset.close()
    assert requests[-1][0] == "https://api.specstream.ai/v1/browser/sessions/bs_1/release"
    assert ("browser_close",) in log and ("stop",) in log


def test_the_toolset_entry_offers_only_what_the_driver_serves():
    toolset, _, _ = make()
    entry = toolset.to_dict()
    off = {name for name, config in entry.get("configs", {}).items() if config.get("enabled") is False}
    assert off == {"javascript_exec", "file_upload", "read_console", "read_network"}
    toolset.close()


def test_an_api_refusal_reaches_claude_as_an_error_with_its_message():
    toolset, _, _ = make(status=402, body={"error": {"code": "insufficient_balance", "message": "Add credit first."}})
    result = run(toolset, "navigate", url="example.com")
    assert result["is_error"] is True
    assert "402" in text_of(result) and "Add credit first." in text_of(result)
    toolset.close()


def test_a_browser_error_is_one_line_without_the_call_log():
    toolset, _, _ = make()
    result = run(toolset, "navigate", url="https://refused.example")
    assert result["is_error"] is True
    assert "ERR_BLOCKED_BY_CLIENT" in text_of(result) and "Call log" not in text_of(result)
    toolset.close()


def test_keys_modifiers_and_scroll_reach_the_browser_in_playwright_names():
    toolset, _, log = make()
    run(toolset, "key", text="ctrl+a Backspace", repeat=2)
    assert [item for item in log if item[0] == "press"] == [
        ("press", "Control+a"), ("press", "Backspace"), ("press", "Control+a"), ("press", "Backspace"),
    ]  # fmt: skip
    del log[:]
    result = run(toolset, "left_click", target={"type": "coordinate", "x": 10, "y": 20}, modifiers="ctrl+shift")
    assert not result.get("is_error"), result
    assert log == [
        ("down", "Control"), ("down", "Shift"),
        ("click", 10, 20, {"button": "left", "click_count": 1}),
        ("up", "Shift"), ("up", "Control"),
    ]  # fmt: skip
    del log[:]
    run(toolset, "scroll", target={"type": "coordinate", "x": 5, "y": 5}, scroll_direction="up")
    assert log == [("move", 5, 5), ("wheel", 0, -300)]
    del log[:]
    run(
        toolset,
        "left_click_drag",
        **{"from": {"type": "coordinate", "x": 1, "y": 2}},
        target={"type": "coordinate", "x": 30, "y": 40},
    )
    assert log == [("move", 1, 2), ("mouse_down",), ("move", 30, 40), ("mouse_up",)]
    toolset.close()


def test_a_missing_key_is_said_at_construction(monkeypatch):
    monkeypatch.delenv("SPECSTREAM_API_KEY", raising=False)
    with pytest.raises(SpecStreamError, match="SPECSTREAM_API_KEY"):
        SpecStreamBrowser()


def test_web_url_adds_https_and_refuses_other_schemes():
    assert web_url("example.com/a") == "https://example.com/a"
    assert web_url("localhost:8080/x") == "https://localhost:8080/x"
    assert web_url("HTTP://example.com") == "HTTP://example.com"
    for bad in ("javascript:alert(1)", "file:///etc/passwd", "data:text/html,x", "view-source:https://a.b"):
        with pytest.raises(ToolError):
            web_url(bad)


def test_chords_and_modifiers():
    assert _page.chords("cmd+shift+P") == ["Meta+Shift+P"]
    assert _page.chords("Enter esc F5 pagedown") == ["Enter", "Escape", "F5", "PageDown"]
    assert _page.chord("ctrl++") == "Control++"
    assert _page.modifiers("alt+cmd") == ["Alt", "Meta"]
    with pytest.raises(ToolError):
        _page.modifiers("ctrl+a")


def test_render_and_match():
    lines = [
        {"depth": 1, "role": "navigation", "name": "", "ref": "ref_1"},
        {"depth": 2, "role": "link", "name": "Pricing", "ref": "ref_2", "href": "/pricing"},
        {"depth": 1, "role": "textbox", "name": "Search docs", "ref": "ref_3"},
        {"depth": 1, "role": "button", "name": 'Say "hi"', "ref": "ref_4"},
    ]
    assert _page.render(lines).splitlines() == [
        "navigation [ref_1]",
        '  link "Pricing" href=/pricing [ref_2]',
        'textbox "Search docs" [ref_3]',
        "button \"Say 'hi'\" [ref_4]",
    ]
    assert [line["ref"] for line in _page.match(lines, "search field")] == ["ref_3"]
    assert _page.match(lines, "pricing link")[0]["ref"] == "ref_2"
    many = [{"depth": 1, "role": "link", "name": "x" * 100, "ref": f"ref_{n}"} for n in range(2_000)]
    cut = _page.render(many)
    assert len(cut) < 50_300 and "Cut at 50,000 characters" in cut.splitlines()[-1]
