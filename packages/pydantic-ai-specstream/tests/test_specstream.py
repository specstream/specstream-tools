import json

import httpx
import pytest
from pydantic_ai import Agent, AgentSpec, ModelRetry
from pydantic_ai.agent.spec import CapabilitySpec
from pydantic_ai.messages import ModelRequest
from pydantic_ai.models.test import TestModel

import pydantic_ai_specstream
from pydantic_ai_specstream import (
    DEFAULT_INSTRUCTIONS,
    SpecStreamCapability,
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


# The capability. Every call below goes to an httpx.MockTransport: nothing reaches the live API.

WRAPPED_SEARCH = {
    "request_id": "req_1",
    "status": "ok",
    "data": {
        "kind": "fact",
        "answer": {"value": "42", "page": "https://a.example"},
        "rows": [],
        "sources": [{"url": "https://a.example", "title": "A", "site": "a.example", "snippet": "42", "cited": True}],
    },
    "error": None,
}
WRAPPED_EXTRACT = {
    "request_id": "req_2",
    "status": "ok",
    "data": {"results": [{"url": "https://a.example", "status": "ok", "title": "A", "text": "page"}], "price_usd": 0.0008},
    "error": None,
}


def wrapped(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=WRAPPED_EXTRACT if request.url.path == "/v1/extract" else WRAPPED_SEARCH)


def tool_returns(result) -> dict:
    return {
        part.tool_name: part.content
        for message in result.all_messages()
        if isinstance(message, ModelRequest)
        for part in message.parts
        if part.part_kind == "tool-return"
    }


async def test_capability_gives_the_agent_both_tools_and_the_instructions():
    client, seen = make_client(wrapped)
    model = TestModel()
    agent = Agent(model, capabilities=[SpecStreamCapability(api_key="ss_test", client=client)])
    result = await agent.run("go")
    assert {r.url.path for r in seen} == {"/v1/web-search", "/v1/extract"}
    assert {tool.name for tool in model.last_model_request_parameters.function_tools} == {"specstream_search", "specstream_extract"}
    returns = tool_returns(result)
    assert returns["specstream_search"]["sources"][0]["url"] == "https://a.example"
    assert returns["specstream_extract"]["results"][0]["text"] == "page"
    assert any(
        DEFAULT_INSTRUCTIONS in (message.instructions or "")
        for message in result.all_messages()
        if isinstance(message, ModelRequest)
    )


async def test_capability_sends_the_key_and_the_package_user_agent():
    client, seen = make_client(wrapped)
    agent = Agent(TestModel(), capabilities=[SpecStreamCapability(api_key="ss_test", client=client, passages=True)])
    await agent.run("go")
    by_path = {r.url.path: r for r in seen}
    for request in seen:
        assert request.url.host == "api.specstream.ai"
        assert request.headers["authorization"] == "Bearer ss_test"
        assert request.headers["user-agent"] == f"pydantic-ai-specstream/{pydantic_ai_specstream.__version__}"
    assert by_path["/v1/web-search"].method == "GET" and by_path["/v1/web-search"].url.params["passages"] == "true"
    assert by_path["/v1/extract"].method == "POST" and "urls" in json.loads(by_path["/v1/extract"].content)


async def test_capability_reads_the_key_from_the_environment(monkeypatch):
    monkeypatch.setenv("SPECSTREAM_API_KEY", "ss_env")
    client, seen = make_client(wrapped)
    await Agent(TestModel(), capabilities=[SpecStreamCapability(client=client)]).run("go")
    assert {r.headers["authorization"] for r in seen} == {"Bearer ss_env"}


async def test_capability_can_carry_one_tool_and_no_instructions():
    client, seen = make_client(wrapped)
    model = TestModel()
    capability = SpecStreamCapability(api_key="ss_test", client=client, search=False, instructions=None)
    result = await Agent(model, capabilities=[capability]).run("go")
    assert [tool.name for tool in model.last_model_request_parameters.function_tools] == ["specstream_extract"]
    assert {r.url.path for r in seen} == {"/v1/extract"}
    assert all(not m.instructions for m in result.all_messages() if isinstance(m, ModelRequest))
    with pytest.raises(ValueError):
        SpecStreamCapability(search=False, extract=False)


async def test_capability_hands_bad_input_back_to_the_model_and_raises_the_rest():
    def tools(handler):
        client, _ = make_client(handler)
        toolset = SpecStreamCapability(api_key="ss_test", client=client).get_toolset()
        return {name: tool.function for name, tool in toolset.tools.items()}

    refused = tools(lambda r: httpx.Response(422, json={"status": "error", "data": None, "error": {"message": "q is too long."}}))
    with pytest.raises(ModelRetry, match="q is too long."):
        await refused["specstream_search"](q="x")
    with pytest.raises(ModelRetry, match="1 to 20"):
        await refused["specstream_extract"](urls=[" "])
    empty = tools(lambda r: httpx.Response(402, json={"error": {"message": "Balance is empty."}}))
    with pytest.raises(SpecStreamError, match="Balance is empty.") as raised:
        await empty["specstream_extract"](urls=["https://a.example"])
    assert raised.value.status_code == 402
    wrapped_error = tools(lambda r: httpx.Response(200, json={"status": "error", "data": {}, "error": {"message": "Stopped."}}))
    with pytest.raises(SpecStreamError, match="Stopped."):
        await wrapped_error["specstream_search"](q="x")


def test_capability_keeps_the_key_out_of_its_repr_and_names_itself():
    capability = SpecStreamCapability(api_key="ss_secret")
    assert "ss_secret" not in repr(capability)
    assert capability.description
    assert SpecStreamCapability.get_serialization_name() == "SpecStreamCapability"


async def test_capability_loads_from_an_agent_spec(monkeypatch):
    monkeypatch.setenv("SPECSTREAM_API_KEY", "ss_env")
    spec = AgentSpec(
        model="test",
        capabilities=[CapabilitySpec(name="SpecStreamCapability", arguments={"extract": False, "passages": True})],
    )
    agent = Agent.from_spec(spec, custom_capability_types=[SpecStreamCapability])
    loaded = [c for c in agent.root_capability.capabilities if isinstance(c, SpecStreamCapability)]
    assert len(loaded) == 1 and loaded[0].passages and not loaded[0].extract and loaded[0].client is None
