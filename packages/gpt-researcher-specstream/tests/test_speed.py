"""The retriever passes the Search API's speed: fast at $1 per 1,000, the API's default when left out."""

import io
import json
from urllib.parse import parse_qs, urlsplit

import pytest

import gpt_researcher_specstream as pkg
from gpt_researcher_specstream import SpecStreamSearch


class Reply(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def queries(monkeypatch):
    seen = []

    def fake(request, timeout=None):
        seen.append(parse_qs(urlsplit(request.full_url).query))
        return Reply(json.dumps({"data": {"sources": [{"url": "https://a.example", "snippet": "a"}]}}).encode())

    monkeypatch.setattr(pkg.urllib.request, "urlopen", fake)
    monkeypatch.setenv("SPECSTREAM_API_KEY", "ss_test")
    monkeypatch.delenv("SPECSTREAM_EXTRACT", raising=False)
    monkeypatch.delenv("SPECSTREAM_SPEED", raising=False)
    return seen


def test_speed_fast_from_the_environment_reaches_the_search(queries, monkeypatch):
    monkeypatch.setenv("SPECSTREAM_SPEED", "fast")
    SpecStreamSearch("q").search()
    assert queries[0]["speed"] == ["fast"]


def test_the_argument_overrides_the_environment(queries, monkeypatch):
    monkeypatch.setenv("SPECSTREAM_SPEED", "fast")
    SpecStreamSearch("q", speed="default").search()
    assert queries[0]["speed"] == ["default"]


def test_without_a_speed_the_api_default_runs(queries):
    SpecStreamSearch("q").search()
    assert "speed" not in queries[0]


def test_an_unknown_speed_is_refused(queries):
    with pytest.raises(ValueError, match="speed"):
        SpecStreamSearch("q", speed="turbo")
