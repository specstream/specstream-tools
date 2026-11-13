"""The web search tool passes the Search API's speed: fast at $1 per 1,000, the API's default when left out."""

import io
import json
import urllib.parse

import pytest

from langchain_specstream.tools import SpecStreamWebSearch

KEY = "ss_live_test_key"


@pytest.fixture
def queries(monkeypatch):
    seen = []

    def fake(request, timeout=None):
        url = urllib.parse.urlsplit(request.full_url)
        assert url.path == "/v1/web-search"
        seen.append(dict(urllib.parse.parse_qsl(url.query)))
        return io.BytesIO(json.dumps({"data": {"kind": "fact", "sources": []}}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake)
    return seen


def test_a_fast_search_sends_speed_fast(queries):
    SpecStreamWebSearch(api_key=KEY).invoke({"q": "capital of Portugal", "speed": "fast"})
    assert queries == [{"q": "capital of Portugal", "speed": "fast"}]


def test_without_a_speed_the_api_default_runs(queries):
    SpecStreamWebSearch(api_key=KEY).invoke({"q": "capital of Portugal"})
    assert "speed" not in queries[0]


def test_the_tool_says_what_a_fast_search_costs():
    tool = SpecStreamWebSearch(api_key=KEY)
    assert "$1 per 1,000" in tool.description
    assert "speed" in tool.args


def test_an_unknown_speed_is_refused(queries):
    with pytest.raises(Exception):
        SpecStreamWebSearch(api_key=KEY).invoke({"q": "capital of Portugal", "speed": "turbo"})
    assert queries == []
