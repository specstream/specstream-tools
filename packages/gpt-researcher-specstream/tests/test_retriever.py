import io
import json
import urllib.error
from importlib.metadata import entry_points
from urllib.parse import parse_qs, urlsplit

import pytest

import gpt_researcher_specstream as pkg
from gpt_researcher_specstream import SpecStreamSearch

SEARCH = {
    "data": {
        "answer": {"value": "42", "page": "https://a.example/answer"},
        "rows": [{"name": "Row", "page": "https://c.example/row", "snippet": "row snippet"}],
        "sources": [
            {"url": "https://a.example/answer", "title": "A", "snippet": "a snippet"},
            {"url": "https://b.example/page", "title": "B", "snippet": "b snippet"},
        ],
        "passages": [{"url": "https://b.example/page", "title": "B", "text": "b passage"}],
    }
}


class Calls(list):
    replies: dict


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def calls(monkeypatch):
    seen = Calls()
    replies = {"search": SEARCH, "extract": {"data": {"results": []}}}

    def fake(request, timeout=None):
        seen.append(request)
        key = "extract" if request.full_url.endswith("/v1/extract") else "search"
        reply = replies[key]
        if isinstance(reply, Exception):
            raise reply
        return Reply(json.dumps(reply).encode())

    monkeypatch.setattr(pkg.urllib.request, "urlopen", fake)
    monkeypatch.setenv("SPECSTREAM_API_KEY", "ss_test")
    monkeypatch.delenv("SPECSTREAM_EXTRACT", raising=False)
    seen.replies = replies
    return seen


def test_search_returns_links_with_passages_and_the_answer(calls):
    results = SpecStreamSearch("q", query_domains=["a.example", "b.example"]).search(max_results=3)
    assert [r["href"] for r in results] == [
        "https://a.example/answer",
        "https://b.example/page",
        "https://c.example/row",
    ]
    assert results[0]["body"].startswith("42\n")
    assert results[1]["body"] == "b passage"
    request = calls[0]
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") == "Bearer ss_test"
    query = parse_qs(urlsplit(request.full_url).query)
    assert query["q"] == ["q (site:a.example OR site:b.example)"]
    assert query["passages"] == ["true"]
    assert SpecStreamSearch("q").requires_scraping is True


def test_max_results_caps_the_list(calls):
    assert len(SpecStreamSearch("q").search(max_results=1)) == 1


def test_extract_returns_page_text_and_declares_no_scraping(calls):
    calls.replies["extract"] = {
        "data": {
            "results": [
                {"url": "https://b.example/page", "status": "ok", "text": "full page"},
                {"url": "https://a.example/answer", "status": "blocked", "text": ""},
            ]
        }
    }
    retriever = SpecStreamSearch("q", extract=True)
    results = retriever.search(max_results=2)
    assert retriever.requires_scraping is False
    assert results == [{"href": "https://b.example/page", "body": "b passage", "raw_content": "full page"}]
    request = calls[1]
    assert request.get_method() == "POST"
    body = json.loads(request.data)
    assert body["urls"] == ["https://a.example/answer", "https://b.example/page"]
    assert body["format"] == "markdown"


def test_extract_setting_comes_from_the_environment(calls, monkeypatch):
    monkeypatch.setenv("SPECSTREAM_EXTRACT", "true")
    assert SpecStreamSearch("q").requires_scraping is False


def test_failed_extract_keeps_the_links(calls):
    calls.replies["extract"] = urllib.error.URLError("down")
    results = SpecStreamSearch("q", extract=True).search(max_results=2)
    assert [r["href"] for r in results] == ["https://a.example/answer", "https://b.example/page"]
    assert all("raw_content" not in r for r in results)


def test_errors_and_missing_input_return_an_empty_list(calls, monkeypatch):
    calls.replies["search"] = urllib.error.HTTPError("u", 402, "no balance", {}, None)
    assert SpecStreamSearch("q").search() == []
    assert SpecStreamSearch("   ").search() == []
    monkeypatch.delenv("SPECSTREAM_API_KEY")
    assert SpecStreamSearch("q").search() == []


def test_entry_point_is_registered():
    names = {ep.name: ep.value for ep in entry_points(group="gpt_researcher.retrievers")}
    assert names.get("specstream") == "gpt_researcher_specstream:SpecStreamSearch"
