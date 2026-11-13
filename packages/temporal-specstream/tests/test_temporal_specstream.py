"""The Activities against a scripted SpecStream, and the Plugin on a real Worker.

No test calls SpecStream: an httpx.MockTransport answers every request.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

import httpx
import pytest
from temporalio import workflow
from temporalio.client import WorkflowFailureError
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from temporalio.worker import Worker

from temporal_specstream import (
    EXTRACT,
    PLUGIN_NAME,
    WEB_SEARCH,
    ExtractInput,
    SpecStreamActivities,
    SpecStreamPlugin,
    WebSearchInput,
)

SEARCH_ANSWER = {
    "kind": "answer",
    "answer": "Lyon has three roasters.",
    "rows": [],
    "sources": [{"url": "https://example.org/a", "cited": True}],
}
EXTRACT_ANSWER = {"pages": [{"url": "https://example.org/a", "title": "A", "text": "Roasters of Lyon"}]}


class Script:
    """Answers each request with the next scripted reply and keeps what was asked."""

    def __init__(self, *replies: httpx.Response | Exception) -> None:
        self.replies = list(replies)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def plugin(script: Script, api_key: str | None = "fixture-key") -> SpecStreamPlugin:
    return SpecStreamPlugin(api_key, transport=script.transport)


async def test_web_search_sends_the_query_and_returns_the_answer() -> None:
    script = Script(httpx.Response(200, json=SEARCH_ANSWER))
    found = await ActivityEnvironment().run(
        plugin(script).specstream.web_search, WebSearchInput(q=" roasters in Lyon ", speed="fast", passages=True)
    )
    assert found == SEARCH_ANSWER
    request = script.requests[0]
    assert (request.method, request.url.path) == ("GET", "/v1/web-search")
    assert dict(request.url.params) == {"q": "roasters in Lyon", "speed": "fast", "passages": "true"}
    assert request.url.host == "api.specstream.ai"
    assert request.headers["authorization"] == "Bearer fixture-key"
    assert request.headers["user-agent"].startswith("temporal-specstream/")


async def test_extract_posts_the_urls() -> None:
    script = Script(httpx.Response(200, json=EXTRACT_ANSWER))
    pages = await ActivityEnvironment().run(
        plugin(script).specstream.extract, ExtractInput(urls=["https://example.org/a", " "], format="markdown")
    )
    assert pages == EXTRACT_ANSWER
    request = script.requests[0]
    assert (request.method, request.url.path) == ("POST", "/v1/extract")
    assert json.loads(request.content) == {"urls": ["https://example.org/a"], "format": "markdown"}


async def test_the_key_comes_from_the_environment_on_each_call(monkeypatch: pytest.MonkeyPatch) -> None:
    script = Script(httpx.Response(200, json=SEARCH_ANSWER))
    activities = plugin(script, api_key=None).specstream
    monkeypatch.delenv("SPECSTREAM_API_KEY", raising=False)
    with pytest.raises(ApplicationError) as missing:
        await ActivityEnvironment().run(activities.web_search, WebSearchInput(q="x"))
    assert missing.value.non_retryable and "SPECSTREAM_API_KEY" in str(missing.value)
    assert script.requests == []
    monkeypatch.setenv("SPECSTREAM_API_KEY", "env-key")
    await ActivityEnvironment().run(activities.web_search, WebSearchInput(q="x"))
    assert script.requests[0].headers["authorization"] == "Bearer env-key"


@pytest.mark.parametrize("status", [401, 422])
async def test_a_refusal_is_not_retried(status: int) -> None:
    script = Script(httpx.Response(status, json={"error": {"message": "refused for a reason"}}))
    with pytest.raises(ApplicationError) as failure:
        await ActivityEnvironment().run(plugin(script).specstream.web_search, WebSearchInput(q="x"))
    assert failure.value.non_retryable
    assert failure.value.type == "SpecStreamError"
    assert failure.value.message == f"SpecStream answered {status}: refused for a reason"


@pytest.mark.parametrize("reply", [httpx.Response(429, json={"error": "slow down"}), httpx.Response(503, text="down")])
async def test_a_rate_limit_or_a_server_error_can_be_retried(reply: httpx.Response) -> None:
    with pytest.raises(ApplicationError) as failure:
        await ActivityEnvironment().run(plugin(Script(reply)).specstream.extract, ExtractInput(urls=["https://a.io"]))
    assert not failure.value.non_retryable


async def test_a_network_error_can_be_retried_and_does_not_show_the_key() -> None:
    script = Script(httpx.ConnectError("no route with Bearer fixture-key"))
    with pytest.raises(ApplicationError) as failure:
        await ActivityEnvironment().run(plugin(script).specstream.web_search, WebSearchInput(q="x"))
    assert not failure.value.non_retryable
    assert "fixture-key" not in str(failure.value)


@pytest.mark.parametrize("urls", [[], ["https://example.org/x"] * 21])
async def test_extract_refuses_a_wrong_number_of_urls_before_any_call(urls: list[str]) -> None:
    script = Script(httpx.Response(200, json=EXTRACT_ANSWER))
    with pytest.raises(ApplicationError) as failure:
        await ActivityEnvironment().run(plugin(script).specstream.extract, ExtractInput(urls=urls))
    assert failure.value.non_retryable and script.requests == []


def test_the_plugin_is_named_and_registers_both_activities() -> None:
    made = plugin(Script(httpx.Response(200, json={})))
    assert made.name() == PLUGIN_NAME == "specstream.SpecStreamPlugin"
    assert (WEB_SEARCH, EXTRACT) == ("specstream.web_search", "specstream.extract")


@workflow.defn
class ResearchWorkflow:
    @workflow.run
    async def run(self, question: str) -> dict:
        found = await workflow.execute_activity(
            SpecStreamActivities.web_search,
            WebSearchInput(q=question),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(initial_interval=timedelta(milliseconds=10), maximum_attempts=3),
        )
        # By name, as a Workflow in another language calls it.
        pages = await workflow.execute_activity(
            "specstream.extract",
            ExtractInput(urls=[source["url"] for source in found["sources"]]),
            start_to_close_timeout=timedelta(seconds=30),
        )
        return {"answer": found["answer"], "pages": pages}


@pytest.fixture
async def env():
    async with await WorkflowEnvironment.start_time_skipping() as started:
        yield started


async def _worker_client(env: WorkflowEnvironment, made: SpecStreamPlugin):
    config = env.client.config()
    config["plugins"] = [made]
    return type(env.client)(**config)


async def test_a_workflow_runs_both_activities_through_the_plugin_and_retries_a_server_error(env) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=EXTRACT_ANSWER if request.url.path == "/v1/extract" else SEARCH_ANSWER)

    calls: list[str] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if calls == ["/v1/web-search"]:
            return httpx.Response(503, text="down")
        return answer(request)

    made = SpecStreamPlugin("fixture-key", transport=httpx.MockTransport(flaky))
    client = await _worker_client(env, made)
    queue = f"q-{uuid.uuid4()}"
    # The Worker names no activity: the Plugin brings them. The sandbox stays on.
    async with Worker(client, task_queue=queue, workflows=[ResearchWorkflow]):
        result = await client.execute_workflow(
            ResearchWorkflow.run, "roasters in Lyon", id=f"w-{uuid.uuid4()}", task_queue=queue
        )
    assert result == {"answer": "Lyon has three roasters.", "pages": EXTRACT_ANSWER}
    assert calls == ["/v1/web-search", "/v1/web-search", "/v1/extract"]


async def test_a_refusal_fails_the_workflow_after_one_attempt(env) -> None:
    script = Script(httpx.Response(401, json={"error": {"message": "unknown key"}}))
    client = await _worker_client(env, plugin(script))
    queue = f"q-{uuid.uuid4()}"
    async with Worker(client, task_queue=queue, workflows=[ResearchWorkflow]):
        with pytest.raises(WorkflowFailureError) as failure:
            await client.execute_workflow(ResearchWorkflow.run, "x", id=f"w-{uuid.uuid4()}", task_queue=queue)
    assert isinstance(failure.value.cause, ActivityError)
    assert "SpecStream answered 401: unknown key" in str(failure.value.cause.cause)
    assert len(script.requests) == 1
