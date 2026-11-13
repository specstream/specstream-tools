import json

import httpx
import pytest
from prefect import flow
from prefect.testing.utilities import prefect_test_harness

import prefect_specstream
from prefect_specstream import SpecStreamCredentials, SpecStreamError, extract_pages, web_search
from prefect_specstream.credentials import SpecStreamClient

SEARCH = {"data": {"kind": "fact", "answer": {"value": "42", "page": "https://a.example"}, "rows": [], "sources": []}}


def extract_reply(request: httpx.Request) -> dict:
    urls = json.loads(request.content)["urls"]
    return {"data": {"results": [{"url": url, "status": "ok", "text": "page"} for url in urls]}}


class Recorder:
    def __init__(self, handler=None):
        self.seen: list[httpx.Request] = []
        self.handler = handler or self.ok

    @staticmethod
    def ok(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/extract":
            return httpx.Response(200, json=extract_reply(request))
        return httpx.Response(200, json=SEARCH)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        return self.handler(request)


@pytest.fixture
def recorder(monkeypatch):
    rec = Recorder()
    original = SpecStreamCredentials.get_client

    def get_client(self, transport=None):
        return original(self, transport=httpx.MockTransport(rec))

    monkeypatch.setattr(SpecStreamCredentials, "get_client", get_client)
    return rec


def credentials(key="ss_test"):
    return SpecStreamCredentials(api_key=key)


def test_search_posts_the_question_with_the_key(recorder):
    data = web_search.fn("  who won?  ", credentials())
    assert data == SEARCH["data"]
    request = recorder.seen[0]
    assert request.method == "POST"
    assert str(request.url) == "https://api.specstream.ai/v1/web-search"
    assert request.headers["Authorization"] == "Bearer ss_test"
    assert request.headers["User-Agent"] == f"prefect-specstream/{prefect_specstream.__version__}"
    assert json.loads(request.content) == {"q": "who won?"}


def test_search_sends_fast_num_and_passages_only_when_asked(recorder):
    web_search.fn("q", credentials(), speed="fast", num=20, passages=True)
    assert json.loads(recorder.seen[0].content) == {"q": "q", "speed": "fast", "num": 20, "passages": True}


def test_search_refuses_an_empty_question_without_a_call(recorder):
    with pytest.raises(SpecStreamError):
        web_search.fn("   ", credentials())
    assert recorder.seen == []


def test_extract_splits_long_lists_in_calls_of_twenty(recorder):
    urls = [f"https://a.example/{i}" for i in range(45)] + ["", "  "]
    data = extract_pages.fn(urls, credentials(), format="text")
    assert [len(json.loads(r.content)["urls"]) for r in recorder.seen] == [20, 20, 5]
    assert json.loads(recorder.seen[0].content)["format"] == "text"
    assert [r["url"] for r in data["results"]] == [f"https://a.example/{i}" for i in range(45)]


def test_api_error_message_is_raised_with_its_status(monkeypatch):
    def refuse(request):
        return httpx.Response(402, json={"error": {"message": "Add credit to continue."}})

    client = SpecStreamClient("ss_test", transport=httpx.MockTransport(refuse))
    with pytest.raises(SpecStreamError) as caught:
        client.call("POST", "/v1/extract", json={"urls": ["https://a.example"]})
    assert str(caught.value) == "Add credit to continue."
    assert caught.value.status_code == 402


def test_empty_key_fails_before_any_call(monkeypatch):
    monkeypatch.delenv("SPECSTREAM_API_KEY", raising=False)
    seen = []
    client = SpecStreamCredentials().get_client(transport=httpx.MockTransport(lambda r: seen.append(r)))
    with pytest.raises(SpecStreamError, match="API key is empty"):
        client.call("POST", "/v1/web-search", json={"q": "x"})
    assert seen == []


def test_key_defaults_to_the_environment_and_stays_secret(monkeypatch):
    monkeypatch.setenv("SPECSTREAM_API_KEY", "ss_env")
    block = SpecStreamCredentials()
    assert block.api_key.get_secret_value() == "ss_env"
    assert "ss_env" not in repr(block)


def test_block_is_registered_for_prefect():
    assert SpecStreamCredentials.get_block_type_slug() == "specstream-credentials"
    assert "api_key" in SpecStreamCredentials.model_json_schema()["properties"]


def test_tasks_run_inside_a_flow(recorder):
    @flow
    def research():
        found = web_search("q", credentials())
        pages = extract_pages(["https://a.example"], credentials())
        return found, pages

    # A loaded machine starts the local server slowly; the default 30 s fails there.
    with prefect_test_harness(server_startup_timeout=180):
        found, pages = research()
    assert found == SEARCH["data"]
    assert pages["results"][0]["status"] == "ok"
