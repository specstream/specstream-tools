"""The drivers against a scripted SpecStream: no network, no key spent."""

from __future__ import annotations

import json
from typing import Any

import pytest

from griptape.artifacts import JsonArtifact, ListArtifact, TextArtifact
from griptape.specstream import SpecStreamError, SpecStreamWebScraperDriver, SpecStreamWebSearchDriver


class FakeResponse:
    def __init__(self, status: int, payload: Any) -> None:
        self.status_code = status
        self.ok = 200 <= status < 400
        self._payload = payload

    def json(self) -> Any:
        if isinstance(self._payload, str):
            raise ValueError("not JSON")
        return self._payload


class FakeSession:
    def __init__(self, *responses: FakeResponse) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, json: Any = None, headers: Any = None, timeout: Any = None) -> FakeResponse:
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return self.responses.pop(0)


SEARCH_REPLY = {
    "data": {
        "kind": "fact",
        "answer": {"value": "John Clarke, Michel H. Devoret and John M. Martinis", "page": "https://www.nobelprize.org/a"},
        "rows": [],
        "sources": [
            {"url": "https://www.nobelprize.org/a", "title": "Nobel Prize in Physics 2025", "site": "nobelprize.org",
             "snippet": "awarded jointly", "published": "2025-10-07", "cited": True},
            {"url": "https://example.org/b", "title": "B", "site": "example.org", "snippet": "", "excerpt": "Text."},
            {"title": "no url"},
        ],
    }
}


def test_search_sends_one_call_and_returns_answer_then_results() -> None:
    session = FakeSession(FakeResponse(200, SEARCH_REPLY))
    driver = SpecStreamWebSearchDriver(api_key="ss_test", session=session, results_count=3)
    out = driver.search("  Who won the 2025 Nobel Prize in Physics?  ")
    assert isinstance(out, ListArtifact)
    assert all(isinstance(item, JsonArtifact) for item in out.value)
    values = [item.value for item in out.value]
    assert values[0] == {"answer": "John Clarke, Michel H. Devoret and John M. Martinis", "url": "https://www.nobelprize.org/a"}
    assert values[1] == {"title": "Nobel Prize in Physics 2025", "url": "https://www.nobelprize.org/a",
                         "site": "nobelprize.org", "snippet": "awarded jointly", "published": "2025-10-07"}
    assert values[2] == {"title": "B", "url": "https://example.org/b", "site": "example.org", "excerpt": "Text."}
    assert len(values) == 3
    call = session.calls[0]
    assert call["url"] == "https://api.specstream.ai/v1/web-search"
    assert call["json"] == {"q": "Who won the 2025 Nobel Prize in Physics?", "num": 3}
    assert call["headers"]["Authorization"] == "Bearer ss_test"
    assert call["headers"]["User-Agent"].startswith("griptape-specstream/")


def test_search_options_and_params_reach_the_body() -> None:
    session = FakeSession(FakeResponse(200, {"data": {"sources": []}}))
    driver = SpecStreamWebSearchDriver(
        api_key="k", session=session, speed="fast", passages=True, params={"country": "DE"},
        base_url="https://example.test/", results_count=500,
    )
    assert driver.search("q", language="de").value == []
    call = session.calls[0]
    assert call["url"] == "https://example.test/v1/web-search"
    assert call["json"] == {"q": "q", "num": 100, "speed": "fast", "passages": True, "country": "DE", "language": "de"}


def test_search_without_answer_or_with_answer_off() -> None:
    session = FakeSession(FakeResponse(200, SEARCH_REPLY))
    out = SpecStreamWebSearchDriver(api_key="k", session=session, include_answer=False).search("x")
    assert "answer" not in out.value[0].value


def test_key_comes_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECSTREAM_API_KEY", "ss_env")
    monkeypatch.setenv("SPECSTREAM_BASE_URL", "https://env.test")
    session = FakeSession(FakeResponse(200, {"data": {"sources": []}}))
    SpecStreamWebSearchDriver(session=session).search("x")
    assert session.calls[0]["headers"]["Authorization"] == "Bearer ss_env"
    assert session.calls[0]["url"] == "https://env.test/v1/web-search"


def test_missing_key_and_empty_query_send_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPECSTREAM_API_KEY", raising=False)
    session = FakeSession()
    with pytest.raises(SpecStreamError, match="SPECSTREAM_API_KEY"):
        SpecStreamWebSearchDriver(session=session).search("x")
    with pytest.raises(SpecStreamError, match="1 to 2,000"):
        SpecStreamWebSearchDriver(api_key="k", session=session).search("   ")
    assert session.calls == []


def test_api_error_message_and_status_surface() -> None:
    reply = {"error": {"code": "insufficient_balance", "message": "The balance is empty."}}
    session = FakeSession(FakeResponse(402, reply), FakeResponse(502, "<html>"))
    driver = SpecStreamWebSearchDriver(api_key="k", session=session)
    with pytest.raises(SpecStreamError) as first:
        driver.search("x")
    assert str(first.value) == "The balance is empty." and first.value.status_code == 402
    with pytest.raises(SpecStreamError, match="SpecStream HTTP 502"):
        driver.search("x")


def test_scraper_reads_one_page_with_meta() -> None:
    reply = {"data": {"results": [{"url": "https://example.org/p", "status": "ok", "title": "P", "text": "# P\n\nBody.",
                                   "published": "2026-01-02", "read_from": "live"}]}}
    session = FakeSession(FakeResponse(200, reply))
    out = SpecStreamWebScraperDriver(api_key="k", session=session).scrape_url(" https://example.org/p ")
    assert isinstance(out, TextArtifact)
    assert out.value == "# P\n\nBody."
    assert out.meta == {"url": "https://example.org/p", "title": "P", "published": "2026-01-02"}
    call = session.calls[0]
    assert call["url"] == "https://api.specstream.ai/v1/extract"
    assert call["json"] == {"urls": ["https://example.org/p"], "format": "markdown"}


def test_scraper_text_format_and_fetch_extract_pair() -> None:
    reply = {"data": {"results": [{"url": "u", "status": "ok", "text": "plain"}]}}
    session = FakeSession(FakeResponse(200, reply))
    driver = SpecStreamWebScraperDriver(api_key="k", session=session, format="text")
    assert driver.extract_page(driver.fetch_url("https://example.org")).value == "plain"
    assert session.calls[0]["json"]["format"] == "text"


def test_scraper_page_not_read_raises() -> None:
    reply = {"data": {"results": [{"url": "u", "status": "blocked", "status_code": 403}]}}
    session = FakeSession(FakeResponse(200, reply))
    with pytest.raises(SpecStreamError, match="blocked") as error:
        SpecStreamWebScraperDriver(api_key="k", session=session).scrape_url("https://example.org")
    assert error.value.status_code == 403


def test_web_search_tool_and_web_scraper_tool_use_the_drivers() -> None:
    from griptape.tools import WebScraperTool, WebSearchTool
    from griptape.loaders import WebLoader

    search_session = FakeSession(FakeResponse(200, SEARCH_REPLY))
    tool = WebSearchTool(web_search_driver=SpecStreamWebSearchDriver(api_key="k", session=search_session))
    result = tool.search({"values": {"query": "Nobel physics 2025"}})
    assert isinstance(result, ListArtifact)
    assert json.loads(result.value[0].to_text())["answer"].startswith("John Clarke")

    page = {"data": {"results": [{"url": "https://example.org", "status": "ok", "title": "T", "text": "Body text."}]}}
    scrape_session = FakeSession(FakeResponse(200, page))
    loader = WebLoader(web_scraper_driver=SpecStreamWebScraperDriver(api_key="k", session=scrape_session))
    scraper = WebScraperTool(web_loader=loader)
    out = scraper.get_content({"values": {"url": "https://example.org"}})
    assert "Body text." in out.to_text()
