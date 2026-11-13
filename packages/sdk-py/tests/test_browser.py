"""Browser session calls: open, step, read, list, downloads and close, on a scripted API."""

from __future__ import annotations

import io
import json
import urllib.error
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from specstream_client import Client, SpecstreamError

SESSIONS = "/v1/browser/sessions"


class _Response:
    def __init__(self, content: bytes, status: int = 200) -> None:
        self.status = status
        self._buf = io.BytesIO(content)

    def read(self) -> bytes:
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class _Api:
    """Scripted API: answers by (method, path) and records each request."""

    def __init__(self, answers: dict[tuple[str, str], Any]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str, dict[str, list[str]], Any]] = []
        self.headers: list[dict[str, str]] = []

    def __call__(self, request, timeout):
        parts = urlsplit(request.full_url)
        body = json.loads(request.data) if request.data else None
        self.calls.append((request.get_method(), parts.path, parse_qs(parts.query), body))
        self.headers.append({name.lower(): value for name, value in request.header_items()})
        answer = self.answers[(request.get_method(), parts.path)]
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, bytes):
            return _Response(answer)
        status = 201 if (request.get_method(), parts.path) == ("POST", SESSIONS) else 200
        return _Response(json.dumps({"data": answer}).encode(), status)


def _session(**extra: Any) -> dict[str, Any]:
    data = {
        "id": "bs_1",
        "status": "running",
        "connect_url": "wss://api.example.test/v1/browser/connect/bs_1?token=fixture",
        "actions_url": "https://api.example.test/v1/browser/sessions/bs_1/actions",
        "timeout_s": 300,
        "seconds": 0,
        "actions": 0,
        "charged_usd": 0.0,
        "price": {"per_second_usd": 0.1 / 3600, "per_action_usd": 0.001},
    }
    data.update(extra)
    return data


def _step(text: str = "", **extra: Any) -> dict[str, Any]:
    data = {
        "result": [{"type": "text", "text": text}] if text else [],
        "error": None,
        "url": "https://example.com/",
        "title": "Example Domain",
        "took_ms": 12,
        "price_usd": 0.001,
    }
    data.update(extra)
    return data


def _client(api: _Api) -> Client:
    return Client("fixture-key", base_url="https://api.example.test", opener=api)


def test_open_browser_sends_only_the_settings_given_and_returns_the_session():
    api = _Api({("POST", SESSIONS): _session(timeout_s=120)})
    session = _client(api).open_browser(timeout_s=120, allowed_domains=["example.com"])

    assert session["id"] == "bs_1"
    assert session["connect_url"].startswith("wss://")
    assert api.calls == [
        ("POST", SESSIONS, {}, {"timeout_s": 120, "allowed_domains": ["example.com"]})
    ]
    assert api.headers[0]["authorization"] == "Bearer fixture-key"
    assert "idempotency-key" not in api.headers[0]


def test_open_browser_with_no_settings_sends_an_empty_object():
    api = _Api({("POST", SESSIONS): _session()})
    _client(api).open_browser()
    assert api.calls[0][3] == {}


def test_idempotency_key_goes_in_the_header_of_that_call_only():
    api = _Api({("POST", SESSIONS): _session(), ("GET", f"{SESSIONS}/bs_1"): _session()})
    client = _client(api)
    client.open_browser(idempotency_key="job-42")
    client.browser_session("bs_1")

    assert api.headers[0]["idempotency-key"] == "job-42"
    assert api.calls[0][3] == {}
    assert "idempotency-key" not in api.headers[1]


@pytest.mark.parametrize("key", ["", "   ", "k" * 129])
def test_a_bad_idempotency_key_sends_nothing(key):
    api = _Api({})
    with pytest.raises(ValueError, match="idempotency_key"):
        _client(api).open_browser(idempotency_key=key)
    assert api.calls == []


def test_steps_post_the_tool_and_its_arguments_to_the_actions_route():
    api = _Api({("POST", f"{SESSIONS}/bs_1/actions"): _step("- link \"More\" [ref=e2]")})
    client = _client(api)
    client.browser_navigate("bs_1", "https://example.com")
    client.browser_snapshot("bs_1")
    clicked = client.browser_step("bs_1", "browser_click", {"element": "More", "ref": "e2"})

    assert [call[3] for call in api.calls] == [
        {"tool": "browser_navigate", "arguments": {"url": "https://example.com"}},
        {"tool": "browser_snapshot", "arguments": {}},
        {"tool": "browser_click", "arguments": {"element": "More", "ref": "e2"}},
    ]
    assert clicked["price_usd"] == 0.001


def test_browser_read_returns_the_text_of_the_page():
    api = _Api({("POST", f"{SESSIONS}/bs_1/actions"): _step("# Example Domain")})
    text = _client(api).browser_read("bs_1", "text")

    assert text == "# Example Domain"
    assert api.calls[0][3] == {"tool": "browser_read", "arguments": {"format": "text"}}


def test_a_blocked_page_is_an_answer_for_a_step_and_an_error_for_a_read():
    blocked = _step(
        error={"code": "blocked", "reason": "robots", "message": "The site's robots file refuses"}
    )
    api = _Api({("POST", f"{SESSIONS}/bs_1/actions"): blocked})
    client = _client(api)

    step = client.browser_navigate("bs_1", "https://example.com")
    assert step["error"]["code"] == "blocked"
    with pytest.raises(SpecstreamError, match="robots file refuses") as caught:
        client.browser_read("bs_1")
    assert caught.value.body["error"]["reason"] == "robots"


def test_bad_arguments_send_nothing():
    api = _Api({})
    client = _client(api)
    with pytest.raises(ValueError):
        client.browser_step("bs_1", "click")
    with pytest.raises(ValueError):
        client.browser_step("", "browser_click")
    with pytest.raises(ValueError):
        client.browser_navigate("bs_1", " ")
    with pytest.raises(ValueError):
        client.browser_read("bs_1", "html")
    with pytest.raises(ValueError):
        client.browser_sessions(status="open")
    assert api.calls == []


def test_browser_sessions_lists_with_its_filters_in_the_query():
    api = _Api({("GET", SESSIONS): {"sessions": [_session()], "next_cursor": "c2"}})
    client = _client(api)
    page = client.browser_sessions(status="running", limit=5, cursor="c1")
    client.browser_sessions()

    assert page["next_cursor"] == "c2"
    assert api.calls[0][2] == {"status": ["running"], "limit": ["5"], "cursor": ["c1"]}
    assert api.calls[1][2] == {}


def test_close_browser_releases_the_session_and_the_id_is_escaped():
    ended = _session(status="ended", ended_reason="released", charged_usd=0.0032)
    api = _Api({("POST", f"{SESSIONS}/bs%2F1/release"): ended})
    closed = _client(api).close_browser("bs/1")

    assert closed["charged_usd"] == 0.0032
    assert api.calls == [("POST", f"{SESSIONS}/bs%2F1/release", {}, {})]


def test_browser_downloads_returns_the_zip_bytes():
    api = _Api({("GET", f"{SESSIONS}/bs_1/downloads"): b"PK\x03\x04zip"})
    assert _client(api).browser_downloads("bs_1") == b"PK\x03\x04zip"
    assert api.headers[0]["authorization"] == "Bearer fixture-key"


def test_browser_downloads_of_an_unknown_session_raises_with_the_status():
    missing = urllib.error.HTTPError("https://api.example.test", 404, "Not Found", None, None)
    api = _Api({("GET", f"{SESSIONS}/bs_9/downloads"): missing})
    with pytest.raises(SpecstreamError) as caught:
        _client(api).browser_downloads("bs_9")
    assert caught.value.status == 404


def test_the_with_block_closes_the_browser_after_an_error():
    api = _Api(
        {
            ("POST", SESSIONS): _session(),
            ("POST", f"{SESSIONS}/bs_1/release"): _session(status="ended"),
        }
    )
    client = _client(api)
    with pytest.raises(RuntimeError, match="the caller's own"):
        with client.browser(timeout_s=60) as session:
            assert session["id"] == "bs_1"
            raise RuntimeError("the caller's own")

    assert [call[:2] for call in api.calls] == [
        ("POST", SESSIONS),
        ("POST", f"{SESSIONS}/bs_1/release"),
    ]
    assert api.calls[0][3] == {"timeout_s": 60}
