import json

import httpx
import pytest
from prefect.testing.utilities import prefect_test_harness

from prefect_specstream import (
    SpecStreamCredentials,
    SpecStreamError,
    get_research,
    research,
    research_report,
    start_research,
    wait_for_research,
)

REPORT = {
    "title": "Stablecoin reserves",
    "content": "The EU asks for full reserves [1].",
    "citations": [{"n": 1, "url": "https://a.example", "excerpt": "full reserves", "supported": True}],
    "sources": [{"n": 1, "url": "https://a.example", "cited": True}],
}


class Api:
    """A scripted SpecStream: POST starts run r_1, each GET answers the next state in `states`."""

    def __init__(self, states):
        self.states = list(states)
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if request.method == "POST":
            body = json.loads(request.content)
            return httpx.Response(200, json={"data": {"id": "r_1", "status": "queued", "depth": body["depth"], "price_usd": 0.1}})
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        return httpx.Response(200, json={"data": {"id": "r_1", "depth": "quick", "price_usd": 0.1, **state}})


@pytest.fixture
def api(monkeypatch):
    original = SpecStreamCredentials.get_client

    def make(*states):
        scripted = Api(states)
        monkeypatch.setattr(
            SpecStreamCredentials, "get_client", lambda self, transport=None: original(self, transport=httpx.MockTransport(scripted))
        )
        return scripted

    monkeypatch.setattr(research, "_sleep", lambda seconds: None)
    return make


def credentials():
    return SpecStreamCredentials(api_key="ss_test")


def test_start_posts_the_question_and_depth_with_a_stable_idempotency_key(api):
    scripted = api({"status": "running"})
    first = start_research.fn("  How are reserves regulated?  ", credentials(), depth="quick")
    start_research.fn("How are reserves regulated?", credentials(), depth="quick")
    start_research.fn("How are reserves regulated?", credentials(), depth="deep")
    assert first["id"] == "r_1"
    request = scripted.seen[0]
    assert (request.method, str(request.url)) == ("POST", "https://api.specstream.ai/v1/research")
    assert request.headers["Authorization"] == "Bearer ss_test"
    assert json.loads(request.content) == {"input": "How are reserves regulated?", "depth": "quick"}
    keys = [r.headers["Idempotency-Key"] for r in scripted.seen]
    assert keys[0].startswith("prefect-research-")
    assert keys[0] == keys[1] != keys[2]


def test_start_sends_options_but_never_lets_them_replace_the_question_or_depth(api):
    scripted = api({"status": "running"})
    start_research.fn("q", credentials(), depth="quick", options={"language": "fr", "depth": "deep", "empty": None})
    assert json.loads(scripted.seen[0].content) == {"input": "q", "depth": "quick", "language": "fr"}


@pytest.mark.parametrize("question, depth", [("   ", "quick"), ("x" * 15_001, "quick"), ("q", "huge")])
def test_start_refuses_a_bad_request_without_a_call(api, question, depth):
    scripted = api({"status": "running"})
    with pytest.raises(SpecStreamError):
        start_research.fn(question, credentials(), depth=depth)
    assert scripted.seen == []


def test_get_reads_the_run_by_its_id(api):
    scripted = api({"status": "completed", "report": REPORT})
    run = get_research.fn("r/1", credentials())
    assert run["report"] == REPORT
    assert (scripted.seen[0].method, scripted.seen[0].url.raw_path) == ("GET", b"/v1/research/r%2F1")
    with pytest.raises(SpecStreamError):
        get_research.fn("  ", credentials())


def test_wait_reads_until_the_report_is_written(api):
    scripted = api({"status": "queued"}, {"status": "running"}, {"status": "completed", "report": REPORT})
    run = wait_for_research.fn("r_1", credentials())
    assert run["status"] == "completed"
    assert len(scripted.seen) == 3


def test_wait_raises_with_the_id_when_time_runs_out(api):
    scripted = api({"status": "running"})
    with pytest.raises(SpecStreamError, match="r_1 is still running"):
        wait_for_research.fn("r_1", credentials(), wait_seconds=0)
    assert len(scripted.seen) == 1


def test_wait_raises_when_the_run_fails_or_the_balance_is_short(api):
    api({"status": "failed", "error": {"message": "No page answered."}})
    with pytest.raises(SpecStreamError, match="ended as failed: No page answered."):
        wait_for_research.fn("r_1", credentials())
    api({"status": "payment_required"})
    with pytest.raises(SpecStreamError, match="Add credit") as caught:
        wait_for_research.fn("r_1", credentials())
    assert caught.value.status_code == 402


def test_the_flow_returns_the_written_report(api):
    scripted = api({"status": "running"}, {"status": "completed", "report": REPORT})
    # A loaded machine starts the local server slowly; the default 30 s fails there.
    with prefect_test_harness(server_startup_timeout=180):
        result = research_report("How are reserves regulated?", credentials(), depth="quick")
    assert result == {
        "research_id": "r_1",
        "depth": "quick",
        "price_usd": 0.1,
        "title": "Stablecoin reserves",
        "content": "The EU asks for full reserves [1].",
        "citations": REPORT["citations"],
        "sources": REPORT["sources"],
    }
    assert [r.method for r in scripted.seen] == ["POST", "GET", "GET"]
