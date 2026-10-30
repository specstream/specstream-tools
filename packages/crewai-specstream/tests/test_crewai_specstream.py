import asyncio
import io
import json
import urllib.error
import urllib.parse

import pytest
from pydantic import ValidationError

from crewai_specstream import (
    SpecStreamError,
    SpecStreamFindListTool,
    SpecStreamGetListResultsTool,
    specstream_tools,
)

KEY = "ss_live_test_key"


def cell(label, value, source=None):
    provenance = {"source_url": source, "observed_at": "2026-10-14T08:00:00Z"} if source else None
    return {"label": label, "value": value, "display": value, "absence": None, "provenance": provenance}


ROWS = [
    {"entity_id": "e1", "ordinal": 1, "cells": [cell("Organization", "Clínica Sorriso", "https://sorriso.pt/marcacoes"), cell("Website", "https://sorriso.pt")]},
    {"entity_id": "e2", "ordinal": 2, "cells": [cell("Organization", "Dentes de Lisboa", "https://dentesdelisboa.pt"), cell("Website", None) | {"absence": "Not published"}]},
]

# The API's flat rows: the page of each value, and of the fact that put the row in the list.
FLAT = {
    "e1": {"id": "fnd_1:e1", "name": "Clínica Sorriso", "name_source": "https://sorriso.pt/marcacoes", "source_url": "https://filings.example/e1", "checked_at": "2026-10-15T09:00:00Z"},
    "e2": {"id": "fnd_1:e2", "name": "Dentes de Lisboa", "name_source": "https://dentesdelisboa.pt", "source_url": "https://filings.example/e2", "checked_at": "2026-10-15T09:00:00Z"},
}


class FakeSpecStream:
    """Answers like the SpecStream API: the request, its quote, the run, then rows over two polls and two pages."""

    def __init__(self, maximum_cents=250, runnable=True, existing=None):
        self.maximum_cents = maximum_cents
        self.runnable = runnable
        self.existing = existing
        self.calls = []
        self.polls = 0
        self.misses = 0

    def __call__(self, request, timeout=None):
        url = urllib.parse.urlsplit(request.full_url)
        body = json.loads(request.data) if request.data else None
        self.calls.append((request.get_method(), url.path, body, dict(request.header_items())))
        query = dict(urllib.parse.parse_qsl(url.query))
        if url.path.startswith("/v1/capacity/requests/"):
            if self.misses:
                self.misses -= 1
                raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(b"{}"))
            if self.existing:
                return self.reply(self.existing)
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(b"{}"))
        if url.path == "/v1/parse":
            return self.reply({"status": "runnable" if self.runnable else "needs_input", "ast_hash": "a" * 64, "canonical_sentence": "25 dental clinics in Lisbon"})
        if url.path == "/v1/capacity/quotes":
            return self.reply({"quote_id": "cqt_1", "quote_hash": "b" * 64, "maximum_cents": self.maximum_cents})
        if url.path == "/v1/capacity/executions":
            return self.reply({"find_id": "fnd_1", "state": "running"})
        if url.path == "/v1/finds/fnd_1/rows":
            if query.get("cursor") == "page-2":
                return self.reply({"status": "completed", "rows": ROWS[1:], "next_cursor": None})
            self.polls += 1
            if self.polls == 1:
                return self.reply({"status": "running", "rows": [], "next_cursor": None})
            return self.reply({"status": "completed", "rows": ROWS[:1], "next_cursor": "page-2"})
        raise AssertionError(f"unexpected call {request.get_method()} {url.path}")

    @staticmethod
    def reply(data):
        if "rows" in data:
            data = {**data, "flat_rows": [FLAT[row["entity_id"]] for row in data["rows"]]}
        return io.BytesIO(json.dumps({"data": data}).encode())

    def paths(self):
        return [path for _, path, _, _ in self.calls]


@pytest.fixture
def api(monkeypatch):
    def install(**kwargs):
        fake = FakeSpecStream(**kwargs)
        monkeypatch.setattr("urllib.request.urlopen", fake)
        return fake

    return install


def test_finds_a_list_within_the_maximum_and_returns_every_row(api):
    fake = api()
    tool = SpecStreamFindListTool(api_key=KEY, max_price_usd=5, poll_interval=0)
    result = json.loads(tool.run(request="Dental clinics in Lisbon with online booking", max_results=25))

    assert result["status"] == "completed"
    assert result["row_count"] == 2
    assert result["list_link"] == "https://specstream.ai/workspace/collections/fnd_1"
    first, second = result["rows"]
    assert first["Organization"] == "Clínica Sorriso"
    assert first["source_url"] == "https://filings.example/e1"
    assert first["checked_at"] == "2026-10-15T09:00:00Z"
    assert first["name_source"] == "https://sorriso.pt/marcacoes"
    assert second["Website"] == ""
    run = next(body for method, path, body, _ in fake.calls if path == "/v1/capacity/executions")
    assert run["confirm_max_cents"] == 250
    assert run["idempotency_key"].startswith("crewai-")


def test_the_result_is_a_json_string_the_agent_can_read(api):
    api()
    output = SpecStreamFindListTool(api_key=KEY, max_price_usd=5, poll_interval=0).run(request="Dental clinics in Lisbon")

    assert isinstance(output, str)
    assert "Clínica Sorriso" in output


def test_nothing_runs_when_the_price_is_above_the_maximum(api):
    fake = api(maximum_cents=900)
    result = json.loads(SpecStreamFindListTool(api_key=KEY, max_price_usd=5).run(request="Dental clinics in Lisbon"))

    assert result["status"] == "over_maximum"
    assert "$9.00" in result["message"] and "$5.00" in result["message"]
    assert "/v1/capacity/executions" not in fake.paths()


def test_an_unclear_request_comes_back_with_how_it_was_read(api):
    fake = api(runnable=False)
    result = json.loads(SpecStreamFindListTool(api_key=KEY, max_price_usd=5).run(request="clinics"))

    assert result["status"] == "needs_edit"
    assert "25 dental clinics in Lisbon" in result["message"]
    assert "/v1/capacity/quotes" not in fake.paths()


def test_the_model_cannot_set_the_price():
    tool = SpecStreamFindListTool(api_key=KEY, max_price_usd=2)
    assert set(tool.args_schema.model_fields) == {"request", "max_results"}
    assert "max_price_usd" not in json.dumps(tool.args_schema.model_json_schema())
    assert "max_price_usd" not in tool.description


def test_the_price_cap_is_required_and_must_be_positive():
    with pytest.raises(ValidationError):
        SpecStreamFindListTool(api_key=KEY)
    with pytest.raises(ValidationError):
        SpecStreamFindListTool(api_key=KEY, max_price_usd=0)


def test_max_results_is_clamped_to_1_through_1000(api):
    fake = api()
    tool = SpecStreamFindListTool(api_key=KEY, max_price_usd=5, poll_interval=0)
    units = []
    for asked in (5000, 0, -3):
        tool._run("Dental clinics in Lisbon", asked)
        quote = [body for _, path, body, _ in fake.calls if path == "/v1/capacity/quotes"][-1]
        units.append(quote["requested_units"])
        fake.polls = 0

    assert units == [1000, 1, 1]


def test_the_schema_shows_the_model_the_same_bounds():
    field = SpecStreamFindListTool(api_key=KEY, max_price_usd=5).args_schema.model_json_schema()["properties"]["max_results"]
    assert field["minimum"] == 1 and field["maximum"] == 1000 and field["default"] == 25


def test_a_retried_step_reuses_the_run_it_already_started(api):
    fake = api(existing={"find_id": "fnd_1", "maximum_cents": 250})
    result = json.loads(SpecStreamFindListTool(api_key=KEY, max_price_usd=5, poll_interval=0).run(request="Dental clinics in Lisbon"))

    assert result["row_count"] == 2
    assert "/v1/parse" not in fake.paths() and "/v1/capacity/executions" not in fake.paths()


def test_a_retry_after_the_turn_of_the_hour_reuses_the_run_from_the_hour_before(api):
    fake = api(existing={"find_id": "fnd_1", "maximum_cents": 250})
    fake.misses = 1
    result = json.loads(SpecStreamFindListTool(api_key=KEY, max_price_usd=5, poll_interval=0).run(request="Dental clinics in Lisbon"))

    lookups = [path for path in fake.paths() if path.startswith("/v1/capacity/requests/")]
    assert len(lookups) == 2 and lookups[0] != lookups[1]
    assert result["row_count"] == 2
    assert "/v1/capacity/executions" not in fake.paths()


def test_a_list_still_running_points_to_the_free_read(api):
    api()
    result = json.loads(SpecStreamFindListTool(api_key=KEY, max_price_usd=5, wait_seconds=0).run(request="Dental clinics in Lisbon"))

    assert result["status"] == "running"
    assert "specstream_get_list_results" in result["message"]


def test_reading_results_follows_every_page(api):
    fake = api()
    fake.polls = 1
    result = json.loads(SpecStreamGetListResultsTool(api_key=KEY).run(list_id="fnd_1"))

    assert [row["position"] for row in result["rows"]] == [1, 2]
    assert result["row_count"] == 2
    pages = [path for path in fake.paths() if path == "/v1/finds/fnd_1/rows"]
    assert len(pages) == 2


def test_reading_results_costs_nothing(api):
    fake = api()
    fake.polls = 1
    SpecStreamGetListResultsTool(api_key=KEY).run(list_id="fnd_1")

    assert all(method == "GET" for method, _, _, _ in fake.calls)


def test_the_key_goes_in_the_authorization_header_and_never_in_the_result(api):
    fake = api()
    tool = SpecStreamFindListTool(api_key=KEY, max_price_usd=5, poll_interval=0)
    output = tool.run(request="Dental clinics in Lisbon")

    headers = fake.calls[0][3]
    assert headers["Authorization"] == f"Bearer {KEY}"
    assert headers["User-agent"].startswith("crewai-specstream/")
    assert KEY not in output
    assert KEY not in repr(tool) and KEY not in str(tool)
    assert KEY not in str(tool.model_dump(exclude={"args_schema", "cache_function"}))


def test_the_key_is_read_from_the_environment(api, monkeypatch):
    fake = api()
    monkeypatch.setenv("SPECSTREAM_API_KEY", "ss_live_from_env")
    SpecStreamGetListResultsTool().run(list_id="fnd_1")

    assert fake.calls[0][3]["Authorization"] == "Bearer ss_live_from_env"


def test_a_missing_key_says_where_to_get_one(monkeypatch):
    monkeypatch.delenv("SPECSTREAM_API_KEY", raising=False)
    with pytest.raises(ValueError, match="SPECSTREAM_API_KEY"):
        SpecStreamFindListTool(max_price_usd=5)
    with pytest.raises(ValueError, match="Agents & API"):
        SpecStreamGetListResultsTool()
    with pytest.raises(ValueError, match="SPECSTREAM_API_KEY"):
        SpecStreamGetListResultsTool(api_key="  ")


def test_a_refused_call_raises_with_the_reason(api, monkeypatch):
    def refuse(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error": {"message": "Bad key"}}'))

    monkeypatch.setattr("urllib.request.urlopen", refuse)
    with pytest.raises(SpecStreamError, match="401: Bad key"):
        SpecStreamGetListResultsTool(api_key=KEY).run(list_id="fnd_1")


def test_both_tools_share_the_key_and_the_cap(api):
    find, results = specstream_tools(max_price_usd=5, api_key=KEY, wait_seconds=60)
    assert find.name == "specstream_find_list" and results.name == "specstream_get_list_results"
    assert find.max_price_usd == 5 and find.wait_seconds == 60
    assert results.api_key.get_secret_value() == KEY


def test_the_tools_declare_their_environment_variable():
    for tool in specstream_tools(max_price_usd=5, api_key=KEY):
        assert [(var.name, var.required) for var in tool.env_vars] == [("SPECSTREAM_API_KEY", True)]


def test_an_agent_calls_the_tool_through_its_structured_form(api):
    api()
    find, _ = specstream_tools(max_price_usd=5, api_key=KEY, poll_interval=0)
    structured = find.to_structured_tool()
    result = json.loads(structured.invoke({"request": "Dental clinics in Lisbon", "max_results": 10}))

    assert structured.name == "specstream_find_list"
    assert result["row_count"] == 2


def test_the_tools_run_without_blocking_an_event_loop(api):
    api()
    find, results = specstream_tools(max_price_usd=5, api_key=KEY, poll_interval=0)

    async def go():
        found = json.loads(await find._arun("Dental clinics in Lisbon", 25))
        again = json.loads(await results._arun("fnd_1"))
        return found, again

    found, again = asyncio.run(go())
    assert found["row_count"] == 2 and again["row_count"] == 2


def test_only_a_finished_list_is_cached():
    find = SpecStreamFindListTool(api_key=KEY, max_price_usd=5)
    done = json.dumps({"status": "completed"})
    for waiting in (json.dumps({"status": "running"}), json.dumps({"status": "over_maximum"}), json.dumps({"status": "needs_edit"}), "not json"):
        assert find.cache_function({}, waiting) is False
    assert find.cache_function({}, done) is True
    assert SpecStreamGetListResultsTool(api_key=KEY).cache_function({}, done) is False


def test_an_agent_accepts_both_tools():
    from crewai import LLM, Agent

    agent = Agent(
        role="Researcher",
        goal="Find lists",
        backstory="Finds lists.",
        tools=specstream_tools(max_price_usd=5, api_key=KEY),
        llm=LLM(model="gpt-4o-mini", api_key="sk-test"),
    )
    assert [tool.name for tool in agent.tools] == ["specstream_find_list", "specstream_get_list_results"]


SCRIPTED = []
SEEN = []


def test_a_crew_finds_a_list_end_to_end_with_a_scripted_model(api):
    """A real Agent, Task and Crew run the agent loop; only the model's replies are scripted."""
    from crewai import Agent, BaseLLM, Crew, Task

    class Scripted(BaseLLM):
        def call(self, messages, tools=None, callbacks=None, available_functions=None, **kwargs):
            SEEN.append(messages)
            return SCRIPTED.pop(0)

        def supports_function_calling(self):
            return False

        def supports_stop_words(self):
            return True

        def get_context_window_size(self):
            return 8000

    fake = api()
    SEEN.clear()
    SCRIPTED[:] = [
        'Thought: I need the list.\nAction: specstream_find_list\nAction Input: {"request": "Dental clinics in Lisbon", "max_results": 10}',
        "Thought: I have the rows.\nFinal Answer: Found 2 clinics.",
    ]
    find, results = specstream_tools(max_price_usd=5, api_key=KEY, poll_interval=0)
    agent = Agent(role="Researcher", goal="Find lists", backstory="Finds lists.", tools=[find, results], llm=Scripted(model="scripted"))
    task = Task(description="Find dental clinics in Lisbon.", expected_output="A short answer.", agent=agent)
    output = Crew(agents=[agent], tasks=[task], verbose=False).kickoff()

    assert output.raw == "Found 2 clinics."
    assert "Clínica Sorriso" in json.dumps(SEEN[-1], ensure_ascii=False)
    assert KEY not in json.dumps(SEEN, ensure_ascii=False)
    assert "/v1/capacity/executions" in fake.paths()
