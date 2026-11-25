"""The web search component passes the Search API's speed: fast at $1 per 1,000, the API's default when left out."""

import io
import json
import urllib.parse

import pytest
from haystack.utils import Secret

from haystack_integrations.components.fetchers.specstream import SpecStreamWebSearch

KEY = Secret.from_token("ss_live_test_key")


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
    SpecStreamWebSearch(api_key=KEY).run(q="capital of Portugal", speed="fast")
    assert queries == [{"q": "capital of Portugal", "speed": "fast"}]


def test_the_speed_set_on_the_component_is_used_and_run_overrides_it(queries):
    search = SpecStreamWebSearch(api_key=KEY, speed="fast")
    search.run(q="capital of Portugal")
    search.run(q="capital of Portugal", speed="default")
    assert [query.get("speed") for query in queries] == ["fast", "default"]


def test_without_a_speed_the_api_default_runs(queries):
    SpecStreamWebSearch(api_key=KEY).run(q="capital of Portugal")
    assert "speed" not in queries[0]


def test_an_unknown_speed_is_refused():
    with pytest.raises(ValueError, match="speed"):
        SpecStreamWebSearch(api_key=KEY, speed="turbo")


def test_the_speed_survives_serialization():
    data = SpecStreamWebSearch(api_key=Secret.from_env_var("SPECSTREAM_API_KEY"), speed="fast").to_dict()
    assert SpecStreamWebSearch.from_dict(data).speed == "fast"
