import json

import httpx
import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from pydantic_ai_specstream import (
    SpecStreamError,
    specstream_extract_tool,
    specstream_search_tool,
    specstream_toolset,
)

SEARCH = {"data": {"kind": "fact", "answer": {"value": "42", "page": "https://a.example"}, "rows": [], "sources": []}}
EXTRACT = {"data": {"results": [{"url": "https://a.example", "status": "ok", "text": "page"}], "price_usd": 0.0008}}


def make_client(handler):
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return httpx.AsyncClient(transport=httpx.MockTransport(record)), seen


def ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=EXTRACT if request.url.path == "/v1/extract" else SEARCH)


async def test_search_tool_sends_the_question_with_the_key():
    client, seen = make_client(ok)
    tool = specstream_search_tool("ss_test", client=client, passages=True)
    result = await tool.function(q="  a question  ")
    assert result["answer"]["value"] == "42"
    request = seen[0]
    assert request.method == "GET"
    assert request.headers["authorization"] == "Bearer ss_test"
    assert request.url.params["q"] == "a question"
    assert request.url.params["passages"] == "true"


async def test_extract_tool_posts_at_most_twenty_urls():
    client, seen = make_client(ok)
    tool = specstream_extract_tool("ss_test", client=client)
    urls = [f"https://a.example/{i}" for i in range(25)]
    result = await tool.function(urls=urls, format="text")
    assert result["results"][0]["status"] == "ok"
    body = json.loads(seen[0].content)
    assert seen[0].method == "POST" and seen[0].url.path == "/v1/extract"
    assert body["urls"] == urls[:20] and body["format"] == "text"


async def test_errors_carry_the_api_message_or_the_status(monkeypatch):
    client, _ = make_client(lambda r: httpx.Response(402, json={"error": {"message": "Balance is empty."}}))
    with pytest.raises(SpecStreamError, match="Balance is empty."):
        await specstream_search_tool("ss_test", client=client).function(q="x")
    client, _ = make_client(lambda r: httpx.Response(503, text="busy"))
    with pytest.raises(SpecStreamError, match="HTTP 503"):
        await specstream_extract_tool("ss_test", client=client).function(urls=["https://a.example"])
    monkeypatch.delenv("SPECSTREAM_API_KEY", raising=False)
    with pytest.raises(SpecStreamError, match="SPECSTREAM_API_KEY"):
        await specstream_search_tool().function(q="x")


async def test_agent_calls_both_tools_through_the_toolset():
    client, seen = make_client(ok)
    agent = Agent(TestModel(), toolsets=[specstream_toolset("ss_test", client=client)])
    await agent.run("go")
    assert {r.url.path for r in seen} == {"/v1/web-search", "/v1/extract"}
