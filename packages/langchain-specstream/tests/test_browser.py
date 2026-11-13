import io
import json
import urllib.error
import urllib.parse

import pytest
from langchain_tests.unit_tests import ToolsUnitTests

from langchain_specstream import (
    SpecStreamBrowserAction,
    SpecStreamBrowserClick,
    SpecStreamBrowserNavigate,
    SpecStreamBrowserRead,
    SpecStreamBrowserType,
    SpecStreamCloseBrowser,
    SpecStreamError,
    SpecStreamOpenBrowser,
    specstream_browser_tools,
)

KEY = "ss_live_test_key"
SESSION = {
    "id": "bs_1",
    "status": "running",
    "connect_url": "wss://browser.specstream.ai/cdp/bs_1?token=secret-token",
    "actions_url": "https://api.specstream.ai/v1/browser/sessions/bs_1/actions",
    "live_url": "https://api.specstream.ai/v1/browser/sessions/bs_1/live?token=view",
    "expires_at": "2026-11-13T10:05:00Z",
    "timeout_s": 300,
    "seconds": 0,
    "actions": 0,
    "charged_usd": 0.0,
    "price": {"per_second_usd": 0.0000278, "per_action_usd": 0.001},
}


class FakeBrowser:
    def __init__(self, blocked=False, refuse=None):
        self.blocked = blocked
        self.refuse = refuse
        self.calls = []

    def __call__(self, request, timeout=None):
        url = urllib.parse.urlsplit(request.full_url)
        body = json.loads(request.data) if request.data else None
        self.calls.append((request.get_method(), url.path, body, timeout))
        if self.refuse:
            payload = json.dumps({"error": {"code": "x", "message": self.refuse[1]}}).encode()
            raise urllib.error.HTTPError(request.full_url, self.refuse[0], "Refused", {}, io.BytesIO(payload))
        if request.get_method() != "POST":
            raise AssertionError(f"unexpected call {request.get_method()} {url.path}")
        if url.path == "/v1/browser/sessions":
            return self.reply(SESSION)
        if url.path == "/v1/browser/sessions/bs_1/release":
            return self.reply(SESSION | {"status": "ended", "ended_reason": "released", "connect_url": None, "live_url": None, "seconds": 42, "actions": 3, "charged_usd": 0.004167})
        if url.path == "/v1/browser/sessions/bs_1/actions":
            if self.blocked:
                return self.reply({"result": [], "error": {"code": "blocked", "reason": "outside_allowed_domains", "message": "The host is outside allowed_domains."}, "took_ms": 3, "price_usd": 0.0})
            if body["tool"] == "browser_take_screenshot":
                return self.reply({"result": [{"type": "image", "data": "QUJD" * 100, "mime_type": "image/png"}], "took_ms": 80, "price_usd": 0.001})
            text = "# Example Domain" if body["tool"] == "browser_read" else "- link \"More\" [ref=e2]"
            return self.reply({"result": [{"type": "text", "text": text}], "url": "https://example.com/", "title": "Example Domain", "took_ms": 120, "price_usd": 0.001, "read_at": "2026-11-13T10:00:05Z"})
        raise AssertionError(f"unexpected call {request.get_method()} {url.path}")

    @staticmethod
    def reply(data):
        return io.BytesIO(json.dumps({"data": data}).encode())


@pytest.fixture
def api(monkeypatch):
    def install(**kwargs):
        fake = FakeBrowser(**kwargs)
        monkeypatch.setattr("urllib.request.urlopen", fake)
        return fake

    return install


def test_open_sends_the_limits_set_in_code_and_keeps_the_token_from_the_model(api):
    fake = api()
    tool = SpecStreamOpenBrowser(api_key=KEY, timeout_s=120, allowed_domains=["example.com"], block_media=True)
    assert list(tool.args) == ["url"]
    raw = tool.invoke({})
    opened = json.loads(raw)

    assert fake.calls[0][:3] == (
        "POST",
        "/v1/browser/sessions",
        {"timeout_s": 120, "idle_timeout_s": 120, "keep_alive": True, "allowed_domains": ["example.com"], "block_media": True},
    )
    assert opened["session_id"] == "bs_1" and opened["status"] == "running"
    assert opened["price"]["per_action_usd"] == 0.001
    assert "specstream_close_browser" in opened["message"]
    assert "secret-token" not in raw and "connect_url" not in opened
    with pytest.raises(ValueError):
        SpecStreamOpenBrowser(api_key=KEY, timeout_s=7200)


def test_open_with_an_address_opens_that_page_in_the_new_session(api):
    fake = api()
    opened = json.loads(SpecStreamOpenBrowser(api_key=KEY).invoke({"url": " https://example.com "}))

    assert fake.calls[1][:3] == ("POST", "/v1/browser/sessions/bs_1/actions", {"tool": "browser_navigate", "arguments": {"url": "https://example.com"}})
    assert opened["page"]["title"] == "Example Domain"


@pytest.mark.parametrize(
    ("tool", "given", "sent"),
    [
        (SpecStreamBrowserNavigate, {"url": "https://example.com"}, {"tool": "browser_navigate", "arguments": {"url": "https://example.com"}}),
        (SpecStreamBrowserRead, {}, {"tool": "browser_read", "arguments": {"format": "markdown"}}),
        (SpecStreamBrowserClick, {"target": "e2"}, {"tool": "browser_click", "arguments": {"target": "e2"}}),
        (SpecStreamBrowserType, {"target": "e5", "text": "roofers", "submit": True}, {"tool": "browser_type", "arguments": {"target": "e5", "text": "roofers", "submit": True}}),
        (SpecStreamBrowserType, {"target": "e5", "text": ""}, {"tool": "browser_type", "arguments": {"target": "e5", "text": ""}}),
        (SpecStreamBrowserAction, {"tool": "browser_press_key", "arguments": {"key": "Enter"}}, {"tool": "browser_press_key", "arguments": {"key": "Enter"}}),
    ],
)
def test_each_step_is_one_action_call_and_comes_back_as_text_with_its_page_and_price(api, tool, given, sent):
    fake = api()
    result = json.loads(tool(api_key=KEY).invoke({"session_id": "bs_1", **given}))

    ((method, path, body, timeout),) = fake.calls
    assert (method, path, body) == ("POST", "/v1/browser/sessions/bs_1/actions", sent)
    assert timeout >= 130
    assert result["session_id"] == "bs_1"
    assert result["text"] and result["url"] == "https://example.com/" and result["price_usd"] == 0.001


def test_a_refused_page_comes_back_as_an_error_the_agent_can_read(api):
    api(blocked=True)
    result = json.loads(SpecStreamBrowserNavigate(api_key=KEY).invoke({"session_id": "bs_1", "url": "https://other.example"}))

    assert result["error"]["code"] == "blocked" and result["error"]["reason"] == "outside_allowed_domains"
    assert result["price_usd"] == 0.0 and "text" not in result


def test_a_screenshot_does_not_put_its_bytes_in_the_answer(api):
    api()
    raw = SpecStreamBrowserAction(api_key=KEY).invoke({"session_id": "bs_1", "tool": "browser_take_screenshot", "arguments": {"type": "png"}})

    assert json.loads(raw)["images"] == [{"mime_type": "image/png", "base64_chars": 400}]
    assert "QUJD" not in raw


def test_a_step_name_outside_the_browser_and_an_empty_session_are_refused_before_any_call(api):
    fake = api()
    with pytest.raises(ValueError):
        SpecStreamBrowserAction(api_key=KEY).invoke({"session_id": "bs_1", "tool": "open_browser"})
    with pytest.raises(ValueError):
        SpecStreamBrowserRead(api_key=KEY).invoke({"session_id": ""})
    assert fake.calls == []


def test_close_returns_the_seconds_steps_and_charge(api):
    fake = api()
    closed = json.loads(SpecStreamCloseBrowser(api_key=KEY).invoke({"session_id": "bs_1"}))

    assert fake.calls[0][:3] == ("POST", "/v1/browser/sessions/bs_1/release", None)
    assert closed["status"] == "ended" and closed["ended_reason"] == "released"
    assert (closed["seconds"], closed["actions"], closed["charged_usd"]) == (42, 3, 0.004167)
    assert "live_url" not in closed


def test_a_refusal_is_an_error_with_the_api_words(api):
    api(refuse=(402, "The balance does not hold a minute of browser time."))
    with pytest.raises(SpecStreamError, match="402: The balance does not hold"):
        SpecStreamOpenBrowser(api_key=KEY).invoke({})


def test_the_ready_list_shares_the_key_and_gives_the_limits_to_the_open_tool():
    tools = specstream_browser_tools(api_key=KEY, timeout_s=600, allowed_domains=["example.com"])

    assert [tool.name for tool in tools] == [
        "specstream_open_browser",
        "specstream_browser_navigate",
        "specstream_browser_read",
        "specstream_browser_snapshot",
        "specstream_browser_click",
        "specstream_browser_type",
        "specstream_browser_action",
        "specstream_close_browser",
    ]
    assert tools[0].timeout_s == 600 and tools[0].allowed_domains == ["example.com"]
    assert all(tool.api_key.get_secret_value() == KEY for tool in tools)


class TestOpenBrowserStandard(ToolsUnitTests):
    @property
    def tool_constructor(self):
        return SpecStreamOpenBrowser

    @property
    def tool_constructor_params(self):
        return {"api_key": KEY}

    @property
    def tool_invoke_params_example(self):
        return {"url": "https://example.com"}

    @property
    def init_from_env_params(self):
        return {"SPECSTREAM_API_KEY": KEY}, {}, {"api_key": KEY}


class TestBrowserReadStandard(ToolsUnitTests):
    @property
    def tool_constructor(self):
        return SpecStreamBrowserRead

    @property
    def tool_constructor_params(self):
        return {"api_key": KEY}

    @property
    def tool_invoke_params_example(self):
        return {"session_id": "bs_1", "format": "markdown"}

    @property
    def init_from_env_params(self):
        return {"SPECSTREAM_API_KEY": KEY}, {}, {"api_key": KEY}
