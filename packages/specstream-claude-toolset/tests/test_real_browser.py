"""The driver against a real Chromium on this machine and a page served from loopback.

The SpecStream API is scripted, so no key is used and nothing is charged. The
tests are skipped where Playwright has no Chromium (`playwright install chromium`, or the path of
one in SPECSTREAM_TEST_CHROMIUM).
"""

from __future__ import annotations

import base64
import http.server
import json
import os
import threading

import pytest
from anthropic.types.beta import BetaToolUseBlock

from specstream_claude_toolset import SpecStreamBrowser

PAGE = """<!doctype html><html><head><title>Shop</title></head><body>
<h1>Tea shop</h1>
<a href="/second">Second page</a>
<a href="/popup" target="_blank">Open the list</a>
<form>
  <label for="q">Search teas</label><input id="q" name="q" type="text">
  <label><input id="news" type="checkbox"> Newsletter</label>
  <select id="size" aria-label="Size"><option value="s">Small</option><option value="l">Large</option></select>
  <button type="button" id="go" onclick="document.getElementById('out').textContent = 'Clicked ' + document.getElementById('q').value">Add to cart</button>
  <button type="button" id="ask" onclick="confirm('Delete everything?')">Delete</button>
</form>
<p id="out">Nothing yet</p>
<div style="height:3000px"></div>
<button type="button" id="far">Far button</button>
</body></html>"""
SECOND = "<!doctype html><html><head><title>Second</title></head><body><h1>Second page</h1></body></html>"


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = (PAGE if self.path == "/" else SECOND).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture(scope="module")
def site():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _launch(connect_url: str):
    from playwright.sync_api import sync_playwright

    handle = sync_playwright().start()
    try:
        return handle, handle.chromium.launch(executable_path=os.environ.get("SPECSTREAM_TEST_CHROMIUM") or None)
    except Exception:
        handle.stop()
        raise


def _chromium_runs() -> bool:
    found: list[bool] = []

    def probe() -> None:
        try:
            handle, browser = _launch("")
            browser.close()
            handle.stop()
            found.append(True)
        except Exception:
            found.append(False)

    thread = threading.Thread(target=probe)
    thread.start()
    thread.join()
    return found[0]


pytestmark = pytest.mark.skipif(not _chromium_runs(), reason="Playwright has no Chromium on this machine")


@pytest.fixture
def browser():
    calls: list[tuple[str, dict]] = []

    def api(url: str, sent: dict, headers: dict) -> tuple[int, bytes]:
        calls.append((url.removeprefix("https://api.specstream.ai"), sent))
        return 201, json.dumps({"id": "bs_test", "connect_url": "wss://connect.test/x", "status": "running"}).encode()

    toolset = SpecStreamBrowser("sk-test", send=api, connect=_launch)
    toolset.api_calls = calls  # type: ignore[attr-defined]
    yield toolset
    toolset.close()


_COUNT = iter(range(1, 10_000))


def run(toolset: SpecStreamBrowser, member: str, **input: object) -> dict:
    block = BetaToolUseBlock(
        id=f"toolu_{next(_COUNT)}", type="tool_use", name=member, input=input, toolset_name=toolset.toolset_name
    )
    return dict(toolset.tool_result(block))


def text_of(result: dict) -> str:
    return "\n".join(part["text"] for part in result["content"] if part["type"] == "text")


def state_of(result: dict) -> dict:
    return next(part for part in result["content"] if part["type"] == "browser_state")


def ref_of(tree: str, words: str) -> str:
    line = next(line for line in tree.splitlines() if words in line)
    return line[line.rindex("[") + 1 : -1]


def test_navigate_reports_the_page_and_the_tab(browser, site):
    result = run(browser, "navigate", url=site + "/")
    assert not result.get("is_error"), result
    assert "Shop" in text_of(result) and "HTTP 200" in text_of(result)
    tabs = state_of(result)["tabs"]
    assert len(tabs) == 1 and tabs[0]["active"] is True and tabs[0]["title"] == "Shop"
    assert browser.api_calls[0][0] == "/v1/browser/sessions"
    assert browser.api_calls[0][1]["viewport"] == {"width": 1280, "height": 720}


def test_navigate_refuses_a_scheme_that_is_not_the_web(browser, site):
    run(browser, "navigate", url=site + "/")
    result = run(browser, "navigate", url="file:///etc/passwd")
    assert result["is_error"] is True
    assert "http or https" in text_of(result)


def test_screenshot_is_a_png_of_the_viewport(browser, site):
    run(browser, "navigate", url=site + "/")
    result = run(browser, "screenshot")
    image = next(part for part in result["content"] if part["type"] == "image")
    data = base64.b64decode(image["source"]["data"])
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert int.from_bytes(data[16:20], "big") == 1280 and int.from_bytes(data[20:24], "big") == 720
    zoomed = run(browser, "zoom", region=[0, 0, 400, 100])
    crop = base64.b64decode(next(p for p in zoomed["content"] if p["type"] == "image")["source"]["data"])
    assert int.from_bytes(crop[16:20], "big") == 400 and int.from_bytes(crop[20:24], "big") == 100


def test_read_page_tags_elements_and_a_reference_clicks(browser, site):
    run(browser, "navigate", url=site + "/")
    tree = text_of(run(browser, "read_page", filter="interactive"))
    assert 'button "Add to cart" [ref_' in tree and 'textbox "Search teas" [ref_' in tree
    assert "Far button" not in tree  # outside the viewport
    assert "Far button" in text_of(run(browser, "read_page", filter="all"))

    box = ref_of(tree, "Search teas")
    assert not run(browser, "left_click", target={"type": "ref", "ref": box}).get("is_error")
    assert not run(browser, "type", text="oolong").get("is_error")
    assert not run(browser, "left_click", target={"type": "ref", "ref": ref_of(tree, "Add to cart")}).get("is_error")
    assert "Clicked oolong" in text_of(run(browser, "get_page_text"))
    # A second read keeps the references Claude already holds.
    assert ref_of(text_of(run(browser, "read_page", filter="interactive")), "Search teas") == box


def test_a_coordinate_click_lands_on_the_element(browser, site):
    run(browser, "navigate", url=site + "/")
    box = browser._on_worker(lambda: browser._page(None).locator("#go").bounding_box())
    x, y = int(box["x"] + box["width"] / 2), int(box["y"] + box["height"] / 2)
    assert not run(browser, "left_click", target={"type": "coordinate", "x": x, "y": y}).get("is_error")
    assert "Clicked" in text_of(run(browser, "get_page_text"))
    outside = run(browser, "left_click", target={"type": "coordinate", "x": 5000, "y": 10})
    assert outside["is_error"] is True and "outside" in text_of(outside)


def test_form_input_sets_text_checkbox_and_select(browser, site):
    run(browser, "navigate", url=site + "/")
    tree = text_of(run(browser, "read_page", filter="interactive"))
    for words, value in (("Search teas", "sencha"), ("Newsletter", True), ("Size", "Large")):
        result = run(browser, "form_input", target={"type": "ref", "ref": ref_of(tree, words)}, value=value)
        assert not result.get("is_error"), result
    values = browser._on_worker(
        lambda: browser._page(None).evaluate(
            "() => [document.getElementById('q').value, document.getElementById('news').checked, document.getElementById('size').value]"
        )
    )
    assert values == ["sencha", True, "l"]


def test_find_keys_scroll_and_a_stale_reference(browser, site):
    run(browser, "navigate", url=site + "/")
    found = text_of(run(browser, "find", query="add to cart button"))
    assert found.splitlines()[0].startswith('button "Add to cart" [ref_')
    far = ref_of(text_of(run(browser, "find", query="far button")), "Far button")
    assert not run(browser, "scroll_to", target={"type": "ref", "ref": far}).get("is_error")
    assert browser._on_worker(lambda: browser._page(None).evaluate("() => scrollY")) > 1000
    assert not run(browser, "key", text="ctrl+Home").get("is_error")
    scroll = run(
        browser, "scroll", target={"type": "coordinate", "x": 600, "y": 300}, scroll_direction="down", scroll_amount=5
    )
    assert not scroll.get("is_error")
    # The wheel scrolls on the next frames, so the page is asked until it has moved.
    browser._on_worker(lambda: browser._page(None).wait_for_function("() => scrollY >= 400", timeout=5_000))

    run(browser, "navigate", url=site + "/second")
    stale = run(browser, "left_click", target={"type": "ref", "ref": far})
    assert stale["is_error"] is True and "stale or not found" in text_of(stale)
    back = run(browser, "navigate", url="back")
    assert "Shop" in text_of(back)


def test_tabs_open_switch_and_close(browser, site):
    first = state_of(run(browser, "navigate", url=site + "/"))["tabs"][0]["tab_id"]
    opened = state_of(run(browser, "new_tab"))
    second = next(tab["tab_id"] for tab in opened["tabs"] if tab.get("active"))
    assert second != first and {"type": "tab_opened", "tab_id": second} in opened["state_changes"]
    run(browser, "navigate", url=site + "/second")
    listed = state_of(run(browser, "list_tabs"))["tabs"]
    assert [tab["title"] for tab in listed] == ["Shop", "Second"]
    switched = state_of(run(browser, "switch_tab", tab_id=first))["tabs"]
    assert next(tab["tab_id"] for tab in switched if tab.get("active")) == first
    closed = state_of(run(browser, "close_tab", tab_id=second))["tabs"]
    assert [tab["tab_id"] for tab in closed] == [first]
    missing = run(browser, "switch_tab", tab_id=second)
    assert missing["is_error"] is True


def test_a_tab_the_page_opens_and_a_dialog_are_reported(browser, site):
    run(browser, "navigate", url=site + "/")
    tree = text_of(run(browser, "read_page", filter="interactive"))
    clicked = run(browser, "left_click", target={"type": "ref", "ref": ref_of(tree, "Open the list")})
    browser._on_worker(
        lambda: browser._context.wait_for_event("page", timeout=5_000) if len(browser._context.pages) < 2 else None
    )
    tabs = state_of(run(browser, "list_tabs"))["tabs"]
    assert len(tabs) == 2, clicked
    first = tabs[0]["tab_id"]
    run(browser, "switch_tab", tab_id=first)
    asked = run(browser, "left_click", target={"type": "ref", "ref": ref_of(tree, "Delete")}, tab_id=first)
    assert not asked.get("is_error"), asked
    assert "Delete everything?" in text_of(asked) and "dismissed" in text_of(asked)


def test_close_releases_the_session(browser, site):
    run(browser, "navigate", url=site + "/")
    browser.close()
    assert browser.api_calls[-1][0] == "/v1/browser/sessions/bs_test/release"
    browser.close()  # a second close does nothing
    assert [path for path, _ in browser.api_calls].count("/v1/browser/sessions/bs_test/release") == 1
