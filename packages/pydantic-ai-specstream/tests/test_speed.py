"""The search tool passes the Search API's speed: fast at $1 per 1,000, the API's default when left out."""

import httpx
import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from pydantic_ai_specstream import SpecStreamCapability, specstream_search_tool

SEARCH = {"data": {"kind": "fact", "answer": None, "rows": [], "sources": []}}


def make_client():
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=SEARCH)

    return httpx.AsyncClient(transport=httpx.MockTransport(record)), seen


async def test_a_fast_search_tool_sends_speed_fast():
    client, seen = make_client()
    await specstream_search_tool("ss_test", client=client, speed="fast").function(q="a question")
    assert seen[0].url.params["speed"] == "fast"


async def test_without_a_speed_the_api_default_runs():
    client, seen = make_client()
    await specstream_search_tool("ss_test", client=client).function(q="a question")
    assert "speed" not in seen[0].url.params


async def test_the_capability_carries_the_speed_to_its_search():
    client, seen = make_client()
    agent = Agent(TestModel(), capabilities=[SpecStreamCapability(api_key="ss_test", client=client, extract=False, speed="fast")])
    await agent.run("go")
    assert [r.url.params.get("speed") for r in seen] == ["fast"]


def test_an_unknown_speed_is_refused():
    with pytest.raises(ValueError, match="speed"):
        specstream_search_tool("ss_test", speed="turbo")
    with pytest.raises(ValueError, match="speed"):
        SpecStreamCapability(api_key="ss_test", speed="turbo")
