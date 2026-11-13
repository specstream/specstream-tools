from __future__ import annotations

import json
from typing import Any

import httpx2 as httpx
import pytest
from anthropic.types.beta import BetaToolUseBlock

from specstream_claude_browser import TAB_ID, SpecStreamBrowser, SpecStreamError
from specstream_claude_browser._driver import playwright_key

SESSION = {"id": "bs_1", "status": "running", "live_url": "https://api.specstream.ai/v1/browser/sessions/bs_1/live"}


class Api:
    def __init__(self, answers: dict[str, dict[str, Any]] | None = None, open_status: int = 201) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.answers = answers or {}
        self.open_status = open_status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        self.calls.append((request.method, request.url.path, body))
        assert request.headers["authorization"] == "Bearer test-key"
        if request.url.path == "/v1/browser/sessions":
            if self.open_status >= 400:
                return httpx.Response(self.open_status, json={"error": {"message": "The key is not valid."}})
            return httpx.Response(201, json={"data": SESSION})
        if request.url.path.endswith("/release"):
            return httpx.Response(200, json={"data": {**SESSION, "status": "ended"}})
        answer = {
            "result": [],
            "url": "https://example.com/",
            "title": "Example Domain",
            "took_ms": 5,
            "price_usd": 0.001,
        }
        answer.update(self.answers.get(body["tool"], {}))
        return httpx.Response(200, json={"data": answer})

    def steps(self) -> list[tuple[str, dict[str, Any]]]:
        return [(body["tool"], body["arguments"]) for _, path, body in self.calls if path.endswith("/actions")]


def browser(api: Api, **options: Any) -> SpecStreamBrowser:
    return SpecStreamBrowser(api_key="test-key", transport=httpx.MockTransport(api), **options)


def call(toolset: SpecStreamBrowser, name: str, **input: Any) -> dict[str, Any]:
    block = BetaToolUseBlock(
        type="tool_use", id=f"toolu_{name}", name=name, input=input, toolset_name=toolset.toolset_name
    )
    return toolset.tool_result(block)


def texts(result: dict[str, Any]) -> str:
    content = result["content"]
    if isinstance(content, str):
        return content
    return "\n".join(str(part.get("text", "")) for part in content if part.get("type") == "text")


def test_the_tools_entry_serves_what_the_driver_implements_and_turns_the_rest_off() -> None:
    api = Api()
    with browser(api) as toolset:
        entry = toolset.to_dict()
    configs = entry["configs"]
    for served in ("navigate", "screenshot", "left_click", "read_page", "get_page_text", "type", "key", "form_input"):
        assert configs.get(served, {}).get("enabled", True) is not False, served
    for off in ("javascript_exec", "new_tab", "switch_tab", "close_tab", "file_upload", "zoom", "left_click_drag"):
        assert configs[off]["enabled"] is False, off
    assert api.calls == []  # a toolset that is never called opens no session and costs nothing


def test_navigate_opens_one_session_reports_the_page_and_close_releases_it() -> None:
    api = Api()
    with browser(api, allowed_domains=["example.com"]) as toolset:
        result = call(toolset, "navigate", url="example.com")
        assert not result.get("is_error")
        assert "Navigated to https://example.com/" in texts(result)
        assert "Example Domain" in texts(result)
        call(toolset, "navigate", url="back")
        assert toolset.session_id == "bs_1"
        assert toolset.live_url == SESSION["live_url"]
    method, path, body = api.calls[0]
    assert (method, path) == ("POST", "/v1/browser/sessions")
    assert body["keep_alive"] is True and body["allowed_domains"] == ["example.com"]
    assert api.steps() == [("browser_navigate", {"url": "example.com"}), ("browser_navigate_back", {})]
    assert [path for _, path, _ in api.calls].count("/v1/browser/sessions") == 1
    assert api.calls[-1][1] == "/v1/browser/sessions/bs_1/release"


def test_the_state_report_names_the_one_tab_with_the_page_after_the_step() -> None:
    api = Api()
    with browser(api) as toolset:
        result = call(toolset, "navigate", url="https://example.com")
        state = [part for part in result["content"] if part.get("type") == "browser_state"]
        assert len(state) == 1
        (tab,) = state[0]["tabs"]
        assert tab == {"tab_id": TAB_ID, "title": "Example Domain", "url": "https://example.com/", "active": True}


def test_screenshot_returns_the_image_the_session_took() -> None:
    api = Api(
        {"browser_take_screenshot": {"result": [{"type": "image", "data": "aGVsbG8=", "mime_type": "image/png"}]}}
    )
    with browser(api) as toolset:
        result = call(toolset, "screenshot")
    (image,) = [part for part in result["content"] if part.get("type") == "image"]
    assert image["source"]["data"] == "aGVsbG8=" and image["source"]["media_type"] == "image/png"
    assert api.steps() == [("browser_take_screenshot", {"type": "png", "scale": "css"})]


def test_clicks_by_ref_go_to_the_pointer_and_a_point_is_clicked_by_script() -> None:
    api = Api({"browser_evaluate": {"result": [{"type": "text", "text": "### Result\ntrue\n### Page\n- Page URL: x"}]}})
    with browser(api) as toolset:
        assert not call(toolset, "left_click", target={"type": "ref", "ref": "e12"}, modifiers="ctrl+shift").get(
            "is_error"
        )
        assert not call(toolset, "double_click", target={"type": "ref", "ref": "e3"}).get("is_error")
        assert not call(toolset, "right_click", target={"type": "ref", "ref": "e3"}).get("is_error")
        assert not call(toolset, "left_click", target={"type": "coordinate", "x": 10, "y": 20}).get("is_error")
        refused = call(toolset, "hover", target={"type": "coordinate", "x": 1, "y": 2})
        assert refused["is_error"] and "read_page" in texts(refused)
    steps = api.steps()
    assert steps[0] == (
        "browser_click",
        {"target": "e12", "element": "the target element", "modifiers": ["Control", "Shift"]},
    )
    assert steps[1][1]["doubleClick"] is True and steps[2][1]["button"] == "right"
    assert steps[3][0] == "browser_evaluate" and "elementFromPoint(10, 20)" in steps[3][1]["function"]
    assert len(steps) == 4  # the refused hover sent nothing


def test_type_key_and_form_input_reach_the_page() -> None:
    api = Api({"browser_evaluate": {"result": [{"type": "text", "text": '### Result\n"SELECT"\n'}]}})
    with browser(api) as toolset:
        assert not call(toolset, "type", text='say "hi"').get("is_error")
        assert not call(toolset, "key", text="ctrl+a BackSpace", repeat=2).get("is_error")
        assert not call(toolset, "form_input", target={"type": "ref", "ref": "e7"}, value=True).get("is_error")
        assert not call(toolset, "form_input", target={"type": "ref", "ref": "e8"}, value="France").get("is_error")
    steps = api.steps()
    assert steps[0][0] == "browser_evaluate" and json.dumps('say "hi"') in steps[0][1]["function"]
    assert [args["key"] for tool, args in steps if tool == "browser_press_key"] == ["Control+a", "Backspace"] * 2
    fills = [args["fields"][0] for tool, args in steps if tool == "browser_fill_form"]
    assert fills[0] == {"name": "the target field", "type": "checkbox", "target": "e7", "value": "true"}
    assert fills[1] == {"name": "the target field", "type": "combobox", "target": "e8", "value": "France"}


def test_typing_with_no_focused_field_is_an_error_claude_can_act_on() -> None:
    api = Api({"browser_evaluate": {"result": [{"type": "text", "text": "### Result\nfalse\n"}]}})
    with browser(api) as toolset:
        result = call(toolset, "type", text="hello")
    assert result["is_error"] and "form_input" in texts(result)


def test_reading_members_return_the_sessions_text() -> None:
    api = Api(
        {
            "browser_snapshot": {"result": [{"type": "text", "text": '- link "More information" [ref=e6]'}]},
            "browser_read": {
                "result": [{"type": "text", "text": "Example Domain\nThis domain is for use in examples."}]
            },
            "browser_find": {"result": [{"type": "text", "text": '- link "More information" [ref=e6]'}]},
        }
    )
    with browser(api) as toolset:
        assert "[ref=e6]" in texts(call(toolset, "read_page", depth=4))
        assert "This domain is for use in examples." in texts(call(toolset, "get_page_text"))
        assert "[ref=e6]" in texts(call(toolset, "find", query="More information"))
        assert not call(toolset, "scroll", target={"type": "coordinate", "x": 5, "y": 5}, scroll_direction="down").get(
            "is_error"
        )
        assert not call(toolset, "wait", duration=2).get("is_error")
    steps = api.steps()
    assert steps[0] == ("browser_snapshot", {"depth": 4})
    assert steps[1] == ("browser_read", {"format": "text"})
    assert steps[2] == ("browser_find", {"text": "More information"})
    assert "scrollBy(0, 300)" in steps[3][1]["function"]
    assert steps[4] == ("browser_wait_for", {"time": 2.0})


def test_a_refused_page_and_an_unknown_tab_are_errors_and_the_run_goes_on() -> None:
    blocked = {
        "code": "blocked",
        "reason": "outside_allowed_domains",
        "message": "The host is outside allowed_domains.",
    }
    api = Api({"browser_navigate": {"error": blocked}})
    with browser(api) as toolset:
        refused = call(toolset, "navigate", url="https://other.example")
        assert refused["is_error"] and "outside allowed_domains" in texts(refused)
        missing = call(toolset, "get_page_text", tab_id="tab-9")
        assert missing["is_error"]
        assert not call(toolset, "get_page_text", tab_id=TAB_ID).get("is_error")
    assert [tool for tool, _ in api.steps()] == ["browser_navigate", "browser_read"]


def test_a_refused_key_is_an_error_result_not_a_crash() -> None:
    api = Api(open_status=401)
    with browser(api) as toolset:
        result = call(toolset, "navigate", url="https://example.com")
    assert result["is_error"] and "401" in texts(result) and "The key is not valid." in texts(result)
    assert "test-key" not in json.dumps(result)
    assert len(api.calls) == 1  # no session was opened, so there is none to release


def test_javascript_exec_is_served_only_with_a_confirm_callable() -> None:
    api = Api({"browser_evaluate": {"result": [{"type": "text", "text": "### Result\n42\n"}]}})
    with browser(api, confirm=lambda context: True) as toolset:
        assert toolset.to_dict()["configs"].get("javascript_exec", {}).get("enabled", True) is not False
        assert "42" in texts(call(toolset, "javascript_exec", text="6 * 7"))
    assert json.dumps("6 * 7") in api.steps()[0][1]["function"]


def test_a_session_that_was_handed_in_is_driven_and_left_open() -> None:
    api = Api()
    with browser(api, session_id="bs_mine") as toolset:
        call(toolset, "get_page_text")
    assert [path for _, path, _ in api.calls] == ["/v1/browser/sessions/bs_mine/actions"]


def test_options_are_checked_before_anything_is_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPECSTREAM_API_KEY", raising=False)
    with pytest.raises(SpecStreamError, match="SPECSTREAM_API_KEY"):
        SpecStreamBrowser()
    with pytest.raises(ValueError, match="timeout_s"):
        SpecStreamBrowser(api_key="test-key", timeout_s=5)
    with pytest.raises(ValueError, match="idle_timeout_s"):
        SpecStreamBrowser(api_key="test-key", idle_timeout_s=5000)


@pytest.mark.parametrize(
    ("claude", "playwright"),
    [
        ("ctrl+a", "Control+a"),
        ("cmd+shift+p", "Meta+Shift+p"),
        ("Return", "Enter"),
        ("BackSpace", "Backspace"),
        ("Page_Down", "PageDown"),
        ("alt+Left", "Alt+ArrowLeft"),
        ("f5", "F5"),
        ("shift", "Shift"),
        ("ctrl++", "Control++"),
        ("a", "a"),
    ],
)
def test_keys_are_spelled_as_playwright_names_them(claude: str, playwright: str) -> None:
    assert playwright_key(claude) == playwright
