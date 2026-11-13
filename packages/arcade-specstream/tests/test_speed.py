import asyncio
import io
import json
import urllib.parse

import pytest
from arcade_core.schema import ToolContext
from arcade_mcp_server.exceptions import RetryableToolError

from arcade_specstream import web_search


@pytest.fixture
def queries(monkeypatch):
    seen = []

    def fake(request, timeout=None):
        url = urllib.parse.urlsplit(request.full_url)
        assert url.path == "/v1/web-search"
        seen.append(dict(urllib.parse.parse_qsl(url.query)))
        return io.BytesIO(json.dumps({"data": {"kind": "list", "sources": []}}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake)
    return seen


def context():
    ctx = ToolContext()
    ctx.set_secret("SPECSTREAM_API_KEY", "ss_live_test_key")
    return ctx


@pytest.mark.parametrize(
    ("speed", "sent"),
    [("fast", {"q": "espresso machines", "speed": "fast"}), ("", {"q": "espresso machines"})],
)
def test_web_search_sends_the_speed_only_when_one_is_given(queries, speed, sent):
    asyncio.run(web_search(context(), "espresso machines", False, speed))
    assert queries == [sent]


def test_an_unknown_speed_is_refused_before_any_call(queries):
    with pytest.raises(RetryableToolError):
        asyncio.run(web_search(context(), "espresso machines", False, "turbo"))
    assert queries == []
