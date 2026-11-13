import httpx
import pytest

from gptme_specstream import SpecStreamError, client
from gptme_specstream.tools.specstream import search_web

SEARCH = {"data": {"kind": "list", "answer": None, "rows": [], "sources": []}}


@pytest.fixture
def queries(monkeypatch):
    monkeypatch.delenv("SPECSTREAM_API_KEY", raising=False)
    monkeypatch.delenv("SPECSTREAM_BASE_URL", raising=False)
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/web-search"
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=SEARCH)

    client.reset()
    client.configure(api_key="ss_test", client=httpx.Client(transport=httpx.MockTransport(handler)))
    yield seen
    client.reset()


@pytest.mark.parametrize(
    ("speed", "sent"),
    [("fast", {"q": "espresso machines", "speed": "fast"}), (None, {"q": "espresso machines"})],
)
def test_search_sends_the_speed_only_when_one_is_given(queries, speed, sent):
    search_web("espresso machines", speed=speed)
    assert queries == [sent]


def test_an_unknown_speed_is_refused_before_any_call(queries):
    with pytest.raises(SpecStreamError):
        search_web("espresso machines", speed="turbo")
    assert queries == []
