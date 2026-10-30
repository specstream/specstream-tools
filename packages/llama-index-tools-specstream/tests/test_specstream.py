import io
import json
import urllib.error
import urllib.parse

import pytest

from llama_index.tools.specstream import SpecStreamError, SpecStreamRetriever, SpecStreamToolSpec

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


def tools(**kwargs):
    spec = SpecStreamToolSpec(api_key=KEY, max_price_usd=kwargs.pop("max_price_usd", 5), poll_interval=0, **kwargs)
    return {tool.metadata.name: tool for tool in spec.to_tool_list()}


def test_finds_a_list_within_the_maximum_and_returns_every_row(api):
    fake = api()
    output = tools()["specstream_find_list"](request="Dental clinics in Lisbon with online booking", max_results=25)
    result = json.loads(output.content)

    assert result["status"] == "completed"
    assert result["row_count"] == 2
    assert result["list_link"] == "https://specstream.ai/workspace/collections/fnd_1"
    first, second = result["rows"]
    assert first["Organization"] == "Clínica Sorriso"
    assert first["source_url"] == "https://filings.example/e1"
    assert first["name_source"] == "https://sorriso.pt/marcacoes"
    assert second["Website"] == ""
    run = next(body for method, path, body, _ in fake.calls if path == "/v1/capacity/executions")
    assert run["confirm_max_cents"] == 250
    assert run["idempotency_key"].startswith("llamaindex-")


def test_nothing_runs_when_the_price_is_above_the_maximum(api):
    fake = api(maximum_cents=900)
    result = json.loads(tools()["specstream_find_list"](request="Dental clinics in Lisbon").content)

    assert result["status"] == "over_maximum"
    assert "$9.00" in result["message"] and "$5.00" in result["message"]
    assert "/v1/capacity/executions" not in fake.paths()


def test_an_unclear_request_comes_back_with_how_it_was_read(api):
    fake = api(runnable=False)
    result = json.loads(tools()["specstream_find_list"](request="clinics").content)

    assert result["status"] == "needs_edit"
    assert "25 dental clinics in Lisbon" in result["message"]
    assert "/v1/capacity/quotes" not in fake.paths()


def test_the_model_sees_two_tools_and_cannot_set_the_price():
    found = tools()
    assert set(found) == {"specstream_find_list", "specstream_get_list_results"}
    schema = found["specstream_find_list"].metadata.get_parameters_dict()
    assert set(schema["properties"]) == {"request", "max_results"}
    assert schema["required"] == ["request"]
    assert "live web" in found["specstream_find_list"].metadata.description


def test_max_results_is_held_to_what_one_list_can_hold(api):
    fake = api()
    tools()["specstream_find_list"](request="Dental clinics in Lisbon", max_results=50000)
    quote = next(body for method, path, body, _ in fake.calls if path == "/v1/capacity/quotes")
    assert quote["requested_units"] == 1000


def test_a_retried_step_reuses_the_run_it_already_started(api):
    fake = api(existing={"find_id": "fnd_1", "maximum_cents": 250})
    result = json.loads(tools()["specstream_find_list"](request="Dental clinics in Lisbon").content)

    assert result["row_count"] == 2
    assert "/v1/parse" not in fake.paths() and "/v1/capacity/executions" not in fake.paths()


def test_reading_results_follows_every_page(api):
    fake = api()
    fake.polls = 1
    result = json.loads(tools()["specstream_get_list_results"](list_id="fnd_1").content)

    assert [row["position"] for row in result["rows"]] == [1, 2]


def test_the_key_goes_in_the_authorization_header_and_never_in_the_result(api):
    fake = api()
    output = tools()["specstream_find_list"](request="Dental clinics in Lisbon").content

    headers = fake.calls[0][3]
    assert headers["Authorization"] == f"Bearer {KEY}"
    assert headers["User-agent"].startswith("llama-index-tools-specstream/")
    assert KEY not in output


def test_the_tools_work_from_an_async_agent(api):
    import asyncio

    api()
    output = asyncio.run(tools()["specstream_find_list"].acall(request="Dental clinics in Lisbon"))
    assert json.loads(output.content)["row_count"] == 2


def test_the_retriever_returns_one_node_per_row_with_its_source(api):
    api()
    nodes = SpecStreamRetriever(api_key=KEY, max_price_usd=5, poll_interval=0).retrieve("Dental clinics in Lisbon")

    assert len(nodes) == 2
    first = nodes[0].node
    assert first.text == "Organization: Clínica Sorriso\nWebsite: https://sorriso.pt"
    assert first.metadata["source_url"] == "https://filings.example/e1"
    assert first.metadata["name_source"] == "https://sorriso.pt/marcacoes"
    assert first.node_id == "fnd_1:1"
    assert "source_url" in first.get_content(metadata_mode="llm")
    assert "list_link" not in first.get_content(metadata_mode="llm")
    assert nodes[1].node.text == "Organization: Dentes de Lisboa"


def test_the_retriever_raises_instead_of_spending_above_the_maximum(api):
    api(maximum_cents=900)
    with pytest.raises(SpecStreamError, match="above the maximum"):
        SpecStreamRetriever(api_key=KEY, max_price_usd=5).retrieve("Dental clinics in Lisbon")


def test_a_missing_key_says_where_to_get_one(monkeypatch):
    monkeypatch.delenv("SPECSTREAM_API_KEY", raising=False)
    with pytest.raises(ValueError, match="SPECSTREAM_API_KEY"):
        SpecStreamToolSpec(max_price_usd=5)


def test_the_key_can_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("SPECSTREAM_API_KEY", KEY)
    assert SpecStreamToolSpec(max_price_usd=5)._client.api_key == KEY


def test_a_price_cap_is_required():
    with pytest.raises(ValueError, match="max_price_usd"):
        SpecStreamToolSpec(api_key=KEY, max_price_usd=0)


def test_a_retry_after_the_turn_of_the_hour_reuses_the_run_from_the_hour_before(api):
    fake = api(existing={"find_id": "fnd_1", "maximum_cents": 250})
    fake.misses = 1
    result = json.loads(tools()["specstream_find_list"](request="Dental clinics in Lisbon").content)

    lookups = [path for path in fake.paths() if path.startswith("/v1/capacity/requests/")]
    assert len(lookups) == 2 and lookups[0] != lookups[1]
    assert result["row_count"] == 2
    assert "/v1/capacity/executions" not in fake.paths()
