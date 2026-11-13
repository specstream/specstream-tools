import io
import json
import urllib.error
import urllib.parse

import pytest
from langchain_tests.unit_tests import ToolsUnitTests

from langchain_specstream import SpecStreamError, SpecStreamGetResearch, SpecStreamResearch

KEY = "ss_live_test_key"
REPORT = {
    "title": "Stablecoin reserves",
    "format": "markdown",
    "content": "The EU asks for reserves held 1:1 [1].",
    "structured": None,
    "citations": [
        {"n": 1, "url": "https://eur-lex.example/mica", "title": "MiCA", "read_at": "2026-11-13T08:00:00Z", "excerpt": "reserve of assets", "start": 0, "end": 37, "supported": True}
    ],
    "sources": [
        {"n": 1, "url": "https://eur-lex.example/mica", "title": "MiCA", "read_at": "2026-11-13T08:00:00Z", "cited": True},
        {"n": 2, "url": "https://sec.example/rule", "title": "Rule", "read_at": "2026-11-13T08:00:05Z", "cited": False},
    ],
    "basis": [],
}


class FakeResearch:
    def __init__(self, running_polls=1, end="completed", refuse=None):
        self.running_polls = running_polls
        self.end = end
        self.refuse = refuse
        self.calls = []

    def __call__(self, request, timeout=None):
        url = urllib.parse.urlsplit(request.full_url)
        body = json.loads(request.data) if request.data else None
        self.calls.append((request.get_method(), url.path, body, {k.lower(): v for k, v in request.header_items()}))
        if request.get_method() == "POST" and url.path == "/v1/research":
            if self.refuse:
                payload = json.dumps({"error": {"code": "x", "message": self.refuse[1]}}).encode()
                raise urllib.error.HTTPError(request.full_url, self.refuse[0], "Refused", {}, io.BytesIO(payload))
            price = {"quick": 0.1, "standard": 0.3, "deep": 1.0}[body["depth"]]
            return self.reply({"id": "res_1", "status": "queued", "depth": body["depth"], "price_usd": price})
        if request.get_method() == "GET" and url.path == "/v1/research/res_1":
            if self.running_polls > 0:
                self.running_polls -= 1
                return self.reply({"id": "res_1", "status": "running", "depth": "quick", "progress": {"searches": 2, "pages_read": 5, "sources": 3}})
            run = {"id": "res_1", "status": self.end, "depth": "quick"}
            if self.end == "completed":
                run |= {"report": REPORT, "usage": {"searches": 4, "pages_read": 9, "charged_usd": 0.1}}
            if self.end == "failed":
                run |= {"error": {"code": "write_failed", "message": "The report could not be written."}}
            return self.reply(run)
        raise AssertionError(f"unexpected call {request.get_method()} {url.path}")

    @staticmethod
    def reply(data):
        return io.BytesIO(json.dumps({"data": data}).encode())

    def posts(self):
        return [call for call in self.calls if call[0] == "POST"]


@pytest.fixture
def api(monkeypatch):
    def install(**kwargs):
        fake = FakeResearch(**kwargs)
        monkeypatch.setattr("urllib.request.urlopen", fake)
        return fake

    return install


def test_a_report_comes_back_with_its_text_and_the_page_of_each_cited_sentence(api):
    fake = api()
    result = json.loads(SpecStreamResearch(api_key=KEY, depth="quick", poll_interval=0).invoke({"input": " How are stablecoin reserves regulated? "}))

    assert result["status"] == "completed"
    assert result["research_id"] == "res_1"
    assert result["price_usd"] == 0.1
    assert result["content"] == "The EU asks for reserves held 1:1 [1]."
    assert result["citations"] == [
        {"n": 1, "url": "https://eur-lex.example/mica", "title": "MiCA", "read_at": "2026-11-13T08:00:00Z", "excerpt": "reserve of assets", "supported": True}
    ]
    assert [source["url"] for source in result["sources"]] == ["https://eur-lex.example/mica", "https://sec.example/rule"]
    assert result["usage"]["charged_usd"] == 0.1
    assert "message" not in result
    ((_, _, body, headers),) = fake.posts()
    assert body == {"input": "How are stablecoin reserves regulated?", "depth": "quick"}
    assert headers["authorization"] == f"Bearer {KEY}"
    assert headers["idempotency-key"].startswith("langchain-research-") and len(headers["idempotency-key"]) <= 128


def test_the_model_cannot_choose_the_depth(api):
    tool = SpecStreamResearch(api_key=KEY)
    assert list(tool.args) == ["input"]
    assert tool.depth == "standard"
    fake = api(running_polls=0)
    tool.invoke({"input": "What changed in MiCA?"})
    assert fake.posts()[0][2]["depth"] == "standard"
    with pytest.raises(ValueError):
        SpecStreamResearch(api_key=KEY, depth="deepest")


def test_the_settings_in_code_go_into_the_request(api):
    fake = api(running_polls=0)
    schema = {"type": "object", "properties": {"rule": {"type": "string"}}}
    tool = SpecStreamResearch(api_key=KEY, depth="deep", length="short", include_domains=["europa.eu"], exclude_domains=["example.com"], json_schema=schema)
    tool.invoke({"input": "What changed in MiCA?"})

    assert fake.posts()[0][2] == {
        "input": "What changed in MiCA?",
        "depth": "deep",
        "length": "short",
        "include_domains": ["europa.eu"],
        "exclude_domains": ["example.com"],
        "output": {"type": "json", "schema": schema},
    }


def test_a_retried_step_sends_the_same_key_and_another_question_another_key(api):
    fake = api(running_polls=0)
    tool = SpecStreamResearch(api_key=KEY, depth="quick")
    tool.invoke({"input": "What changed in MiCA?"})
    tool.invoke({"input": "What changed in MiCA?"})
    tool.invoke({"input": "What changed in the GENIUS Act?"})
    SpecStreamResearch(api_key=KEY, depth="deep").invoke({"input": "What changed in MiCA?"})

    keys = [headers["idempotency-key"] for _, _, _, headers in fake.posts()]
    assert keys[0] == keys[1]
    assert len(set(keys)) == 3


def test_a_report_still_running_after_the_wait_comes_back_with_its_id(api):
    fake = api(running_polls=5)
    result = json.loads(SpecStreamResearch(api_key=KEY, depth="quick", wait_seconds=0).invoke({"input": "What changed in MiCA?"}))

    assert result["status"] == "running"
    assert result["research_id"] == "res_1"
    assert "specstream_get_research" in result["message"]
    assert result["progress"]["pages_read"] == 5
    assert "content" not in result
    assert len(fake.calls) == 2

    fake.running_polls = 0
    later = json.loads(SpecStreamGetResearch(api_key=KEY).invoke({"research_id": "res_1"}))
    assert later["status"] == "completed" and later["title"] == "Stablecoin reserves"


def test_a_failed_report_says_why_and_a_missing_balance_says_what_to_do(api):
    api(running_polls=0, end="failed")
    failed = json.loads(SpecStreamResearch(api_key=KEY, poll_interval=0).invoke({"input": "What changed in MiCA?"}))
    assert failed["status"] == "failed" and failed["error"]["code"] == "write_failed"

    api(running_polls=0, end="payment_required")
    unpaid = json.loads(SpecStreamResearch(api_key=KEY, poll_interval=0).invoke({"input": "What changed in MiCA?"}))
    assert unpaid["status"] == "payment_required" and "Add credit" in unpaid["message"]


def test_a_refusal_is_an_error_with_the_api_words(api):
    api(refuse=(402, "The balance does not hold this report's price."))
    with pytest.raises(SpecStreamError, match="402: The balance does not hold"):
        SpecStreamResearch(api_key=KEY).invoke({"input": "What changed in MiCA?"})


class TestResearchStandard(ToolsUnitTests):
    @property
    def tool_constructor(self):
        return SpecStreamResearch

    @property
    def tool_constructor_params(self):
        return {"api_key": KEY, "depth": "quick"}

    @property
    def tool_invoke_params_example(self):
        return {"input": "How do the EU and the US regulate stablecoin reserves in 2026?"}

    @property
    def init_from_env_params(self):
        return {"SPECSTREAM_API_KEY": KEY}, {"depth": "quick"}, {"api_key": KEY}


class TestGetResearchStandard(ToolsUnitTests):
    @property
    def tool_constructor(self):
        return SpecStreamGetResearch

    @property
    def tool_constructor_params(self):
        return {"api_key": KEY}

    @property
    def tool_invoke_params_example(self):
        return {"research_id": "res_1"}

    @property
    def init_from_env_params(self):
        return {"SPECSTREAM_API_KEY": KEY}, {}, {"api_key": KEY}
