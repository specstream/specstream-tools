import asyncio
import io
import json
import urllib.error
import urllib.parse

import pytest
from arcade_core.schema import ToolContext
from arcade_mcp_server.exceptions import RetryableToolError, ToolExecutionError

import arcade_specstream
from arcade_specstream import extract_pages, find_list, get_list_results, tools, web_search

KEY = "ss_live_test_key"


def cell(label, value, source=None):
    provenance = {"source_url": source, "observed_at": "2026-10-14T08:00:00Z"} if source else None
    return {"label": label, "value": value, "display": value, "absence": None, "provenance": provenance}


ROWS = [
    {"entity_id": "e1", "ordinal": 1, "cells": [cell("Organization", "Clínica Sorriso", "https://sorriso.pt/marcacoes"), cell("Website", "https://sorriso.pt")]},
    {"entity_id": "e2", "ordinal": 2, "cells": [cell("Organization", "Dentes de Lisboa", "https://dentesdelisboa.pt"), cell("Website", None) | {"absence": "Not published"}]},
]

FLAT = {
    "e1": {"id": "fnd_1:e1", "name": "Clínica Sorriso", "name_source": "https://sorriso.pt/marcacoes", "source_url": "https://filings.example/e1", "checked_at": "2026-10-15T09:00:00Z"},
    "e2": {"id": "fnd_1:e2", "name": "Dentes de Lisboa", "name_source": "https://dentesdelisboa.pt", "source_url": "https://filings.example/e2", "checked_at": "2026-10-15T09:00:00Z"},
}


class FakeSpecStream:
    """Answers like the SpecStream API: the request, its quote, the run, then rows over two polls and two pages."""

    def __init__(self, maximum_cents=250, runnable=True, status=200):
        self.maximum_cents = maximum_cents
        self.runnable = runnable
        self.status = status
        self.calls = []
        self.polls = 0

    def __call__(self, request, timeout=None):
        url = urllib.parse.urlsplit(request.full_url)
        body = json.loads(request.data) if request.data else None
        self.calls.append((request.get_method(), url.path, body, dict(request.header_items()), dict(urllib.parse.parse_qsl(url.query))))
        query = dict(urllib.parse.parse_qsl(url.query))
        if self.status != 200:
            raise urllib.error.HTTPError(request.full_url, self.status, "Unauthorized", {}, io.BytesIO(b'{"error": {"message": "Invalid API key"}}'))
        if url.path.startswith("/v1/capacity/requests/"):
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
        if url.path == "/v1/web-search":
            return self.reply({"kind": "fact", "answer": {"value": "Lisbon", "page": "https://example.pt"}})
        if url.path == "/v1/extract":
            return self.reply({"results": [{"url": u, "title": "Page"} for u in body["urls"]]})
        raise AssertionError(f"unexpected call {request.get_method()} {url.path}")

    @staticmethod
    def reply(data):
        if "rows" in data:
            data = {**data, "flat_rows": [FLAT[row["entity_id"]] for row in data["rows"]]}
        return io.BytesIO(json.dumps({"data": data}).encode())

    def paths(self):
        return [call[1] for call in self.calls]


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(tools, "POLL_SECONDS", 0)

    def install(**kwargs):
        fake = FakeSpecStream(**kwargs)
        monkeypatch.setattr("urllib.request.urlopen", fake)
        return fake

    return install


def context(key=KEY, max_price="5"):
    ctx = ToolContext()
    if key is not None:
        ctx.set_secret("SPECSTREAM_API_KEY", key)
    if max_price is not None:
        ctx.set_secret("SPECSTREAM_MAX_PRICE_USD", max_price)
    return ctx


def run(coro):
    return asyncio.run(coro)


def test_finds_a_list_within_the_ceiling_and_returns_every_row(api):
    fake = api()
    result = run(find_list(context(), "Dental clinics in Lisbon with online booking", 25))

    assert result["status"] == "completed"
    assert result["row_count"] == 2
    assert result["list_link"] == "https://specstream.ai/workspace/collections/fnd_1"
    first, second = result["rows"]
    assert first["Organization"] == "Clínica Sorriso"
    assert first["source_url"] == "https://filings.example/e1"
    assert first["name_source"] == "https://sorriso.pt/marcacoes"
    assert second["Website"] == ""
    run_body = next(call[2] for call in fake.calls if call[1] == "/v1/capacity/executions")
    assert run_body["confirm_max_cents"] == 250
    assert run_body["idempotency_key"].startswith("arcade-")
    headers = fake.calls[0][3]
    assert headers["Authorization"] == f"Bearer {KEY}"
    assert headers["User-agent"].startswith("arcade-specstream/")


def test_nothing_runs_when_the_price_is_above_the_ceiling(api):
    fake = api(maximum_cents=900)
    result = run(find_list(context(max_price="$5"), "Dental clinics in Lisbon"))

    assert result["status"] == "over_maximum"
    assert "$9.00" in result["message"] and "$5.00" in result["message"]
    assert "/v1/capacity/executions" not in fake.paths()


def test_the_rows_asked_for_stay_between_1_and_1000(api):
    fake = api()
    run(find_list(context(), "Dental clinics in Lisbon", 50000))

    quote = next(call[2] for call in fake.calls if call[1] == "/v1/capacity/quotes")
    assert quote["requested_units"] == 1000


def test_an_unclear_request_comes_back_with_how_it_was_read(api):
    fake = api(runnable=False)
    result = run(find_list(context(), "clinics"))

    assert result["status"] == "needs_edit"
    assert "25 dental clinics in Lisbon" in result["message"]
    assert "/v1/capacity/quotes" not in fake.paths()


@pytest.mark.parametrize("max_price", [None, "", "0", "five"])
def test_without_a_price_ceiling_nothing_is_called(api, max_price):
    fake = api()
    with pytest.raises(ToolExecutionError) as error:
        run(find_list(context(max_price=max_price), "Dental clinics in Lisbon"))

    assert "SPECSTREAM_MAX_PRICE_USD" in error.value.developer_message
    assert fake.calls == []


def test_without_a_key_nothing_is_called(api):
    fake = api()
    with pytest.raises(ToolExecutionError) as error:
        run(web_search(context(key=None), "capital of Portugal"))

    assert "SPECSTREAM_API_KEY" in error.value.developer_message
    assert fake.calls == []


def test_an_api_refusal_is_a_tool_error_with_its_message(api):
    api(status=401)
    with pytest.raises(ToolExecutionError) as error:
        run(get_list_results(context(), "fnd_1"))

    assert "401" in str(error.value) and "Invalid API key" in str(error.value)
    assert KEY not in str(error.value)


def test_reading_a_list_follows_every_page(api):
    fake = api()
    fake.polls = 1
    result = run(get_list_results(context(), " fnd_1 "))

    assert result["status"] == "completed"
    assert [row["Organization"] for row in result["rows"]] == ["Clínica Sorriso", "Dentes de Lisboa"]


def test_web_search_sends_the_query_and_passages(api):
    fake = api()
    result = run(web_search(context(), "capital of Portugal", True))

    assert result["answer"]["value"] == "Lisbon"
    method, path, _, _, query = fake.calls[0]
    assert (method, path) == ("GET", "/v1/web-search")
    assert query == {"q": "capital of Portugal", "passages": "true"}


def test_an_empty_query_asks_the_model_again(api):
    fake = api()
    with pytest.raises(RetryableToolError):
        run(web_search(context(), "   "))
    assert fake.calls == []


def test_extract_pages_posts_the_urls(api):
    fake = api()
    result = run(extract_pages(context(), ["https://example.com/a", "https://example.com/b"], "text"))

    assert len(result["results"]) == 2
    assert fake.calls[0][2] == {"urls": ["https://example.com/a", "https://example.com/b"], "format": "text"}


def test_the_toolkit_registers_four_tools_with_their_secrets():
    from arcade_core.catalog import ToolCatalog

    catalog = ToolCatalog()
    catalog.add_module(arcade_specstream, "SpecStream")
    definitions = {tool.definition.name: tool.definition for tool in catalog}

    assert set(definitions) == {"FindList", "GetListResults", "WebSearch", "ExtractPages"}
    secrets = {name: {s.key for s in d.requirements.secrets or []} for name, d in definitions.items()}
    assert secrets["FindList"] == {"SPECSTREAM_API_KEY", "SPECSTREAM_MAX_PRICE_USD"}
    assert secrets["WebSearch"] == {"SPECSTREAM_API_KEY"}
    params = {p.name for p in definitions["FindList"].input.parameters}
    assert params == {"request", "max_results"}


def test_the_mcp_server_loads():
    from arcade_specstream.__main__ import app

    assert app is not None
