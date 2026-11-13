import io
import json
import urllib.error
from importlib.metadata import entry_points
from urllib.parse import parse_qs, urlsplit

import pytest
from praisonaiagents.tools.base import BaseTool

import praisonai_specstream as pkg
from praisonai_specstream import SpecStreamTool

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
EXTRACT = {
    "data": {
        "results": [
            {"url": "https://a.example/answer", "status": "ok", "text": "# A"},
            {"url": "https://b.example/page", "status": "empty", "text": ""},
        ]
    }
}


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Calls(list):
    replies: dict


@pytest.fixture
def calls(monkeypatch):
    seen = Calls()
    seen.replies = {"search": SEARCH, "extract": EXTRACT}

    def fake(request, timeout=None):
        seen.append(request)
        reply = seen.replies["extract" if request.full_url.endswith("/v1/extract") else "search"]
        if isinstance(reply, Exception):
            raise reply
        return Reply(json.dumps(reply).encode())

    monkeypatch.setattr(pkg.urllib.request, "urlopen", fake)
    monkeypatch.setenv("SPECSTREAM_API_KEY", "ss_test")
    monkeypatch.delenv("SPECSTREAM_SPEED", raising=False)
    monkeypatch.delenv("SPECSTREAM_BASE_URL", raising=False)
    return seen


def test_the_entry_point_registers_specstream_as_a_search_provider():
    found = {ep.name: ep for ep in entry_points(group="praisonai.tools.search")}
    assert found["specstream"].load() is SpecStreamTool


def test_praisonai_builds_the_tool_with_no_arguments_and_gets_a_tool_schema(calls):
    tool = SpecStreamTool()
    assert isinstance(tool, BaseTool)
    assert tool.name == "specstream"
    schema = tool.get_schema()["function"]
    assert schema["name"] == "specstream"
    assert {"query", "max_results", "action", "urls"} <= set(schema["parameters"]["properties"])
    assert calls == []


def test_search_returns_the_answer_and_one_result_per_page(calls):
    result = SpecStreamTool().run(query="meaning of life", max_results=2)
    assert result == {
        "query": "meaning of life",
        "answer": "42",
        "results": [
            {"title": "A", "url": "https://a.example/answer", "content": "a snippet"},
            {"title": "B", "url": "https://b.example/page", "content": "b passage"},
        ],
    }
    (request,) = calls
    assert request.get_method() == "GET"
    assert urlsplit(request.full_url).netloc == "api.specstream.ai"
    assert urlsplit(request.full_url).path == "/v1/web-search"
    assert parse_qs(urlsplit(request.full_url).query) == {"q": ["meaning of life"], "passages": ["true"]}
    assert request.get_header("Authorization") == "Bearer ss_test"
    assert request.get_header("User-agent") == f"praisonai-specstream/{pkg.__version__}"


def test_rows_follow_the_sources(calls):
    urls = [r["url"] for r in SpecStreamTool().search("q", max_results=10)["results"]]
    assert urls == ["https://a.example/answer", "https://b.example/page", "https://c.example/row"]


def test_speed_fast_goes_to_the_fast_tier(calls, monkeypatch):
    monkeypatch.setenv("SPECSTREAM_SPEED", "fast")
    SpecStreamTool().search("q")
    assert parse_qs(urlsplit(calls[0].full_url).query)["speed"] == ["fast"]


def test_extract_reads_pages_and_leaves_out_the_empty_ones(calls):
    result = SpecStreamTool().run(action="extract", urls="https://a.example/answer, https://b.example/page")
    assert result == {"results": [{"url": "https://a.example/answer", "content": "# A"}]}
    (request,) = calls
    assert request.get_method() == "POST"
    assert json.loads(request.data) == {
        "urls": ["https://a.example/answer", "https://b.example/page"],
        "format": "markdown",
    }


def test_no_key_and_no_query_answer_an_error_without_a_call(calls, monkeypatch):
    assert SpecStreamTool().search("  ") == {"error": "query is required"}
    assert SpecStreamTool().extract("") == {"error": "urls is required"}
    monkeypatch.delenv("SPECSTREAM_API_KEY")
    assert SpecStreamTool().search("q") == {"error": "SPECSTREAM_API_KEY not configured"}
    assert calls == []


def test_an_api_error_is_an_error_result_not_an_exception(calls):
    calls.replies["search"] = urllib.error.HTTPError("u", 402, "Payment Required", {}, None)
    assert SpecStreamTool().search("q") == {"error": "SpecStream answered HTTP 402"}
    calls.replies["search"] = urllib.error.URLError("no route")
    assert "no route" in SpecStreamTool().search("q")["error"]
