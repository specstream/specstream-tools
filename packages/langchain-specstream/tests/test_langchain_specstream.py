import io
import json
import urllib.error
import urllib.parse

import pytest

from langchain_specstream import (
    SpecStreamError,
    SpecStreamFindList,
    SpecStreamGetListResults,
    SpecStreamRetriever,
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
    tool = SpecStreamFindList(api_key=KEY, max_price_usd=5, poll_interval=0)
    result = json.loads(tool.invoke({"request": "Dental clinics in Lisbon with online booking", "max_results": 25}))

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
    assert run["idempotency_key"].startswith("langchain-")


def test_nothing_runs_when_the_price_is_above_the_maximum(api):
    fake = api(maximum_cents=900)
    result = json.loads(SpecStreamFindList(api_key=KEY, max_price_usd=5).invoke({"request": "Dental clinics in Lisbon"}))

    assert result["status"] == "over_maximum"
    assert "$9.00" in result["message"] and "$5.00" in result["message"]
    assert "/v1/capacity/executions" not in fake.paths()


def test_an_unclear_request_comes_back_with_how_it_was_read(api):
    fake = api(runnable=False)
    result = json.loads(SpecStreamFindList(api_key=KEY, max_price_usd=5).invoke({"request": "clinics"}))

    assert result["status"] == "needs_edit"
    assert "25 dental clinics in Lisbon" in result["message"]
    assert "/v1/capacity/quotes" not in fake.paths()


def test_the_model_cannot_set_the_price():
    tool = SpecStreamFindList(api_key=KEY, max_price_usd=2)
    assert set(tool.args) == {"request", "max_results"}


def test_a_retried_step_reuses_the_run_it_already_started(api):
    fake = api(existing={"find_id": "fnd_1", "maximum_cents": 250})
    result = json.loads(SpecStreamFindList(api_key=KEY, max_price_usd=5, poll_interval=0).invoke({"request": "Dental clinics in Lisbon"}))

    assert result["row_count"] == 2
    assert "/v1/parse" not in fake.paths() and "/v1/capacity/executions" not in fake.paths()


def test_reading_results_follows_every_page(api):
    fake = api()
    fake.polls = 1
    result = json.loads(SpecStreamGetListResults(api_key=KEY).invoke({"list_id": "fnd_1"}))

    assert [row["position"] for row in result["rows"]] == [1, 2]


def test_the_key_goes_in_the_authorization_header_and_never_in_the_result(api):
    fake = api()
    output = SpecStreamFindList(api_key=KEY, max_price_usd=5, poll_interval=0).invoke({"request": "Dental clinics in Lisbon"})

    headers = fake.calls[0][3]
    assert headers["Authorization"] == f"Bearer {KEY}"
    assert headers["User-agent"].startswith("langchain-specstream/")
    assert KEY not in output


def test_the_retriever_returns_one_document_per_row_with_its_source(api):
    api()
    docs = SpecStreamRetriever(api_key=KEY, max_price_usd=5, poll_interval=0).invoke("Dental clinics in Lisbon")

    assert len(docs) == 2
    assert docs[0].page_content == "Organization: Clínica Sorriso\nWebsite: https://sorriso.pt"
    assert docs[0].metadata["source_url"] == "https://filings.example/e1"
    assert docs[0].metadata["name_source"] == "https://sorriso.pt/marcacoes"
    assert docs[1].page_content == "Organization: Dentes de Lisboa"


def test_the_retriever_raises_instead_of_spending_above_the_maximum(api):
    api(maximum_cents=900)
    with pytest.raises(SpecStreamError, match="above the maximum"):
        SpecStreamRetriever(api_key=KEY, max_price_usd=5).invoke("Dental clinics in Lisbon")


def test_both_tools_share_the_key(api):
    search, extract, find, results = specstream_tools(max_price_usd=5, api_key=KEY)
    assert search.name == "specstream_web_search" and extract.name == "specstream_extract_pages"
    assert find.name == "specstream_find_list" and results.name == "specstream_get_list_results"
    assert results.api_key.get_secret_value() == KEY


def test_a_missing_key_says_where_to_get_one(monkeypatch):
    monkeypatch.delenv("SPECSTREAM_API_KEY", raising=False)
    with pytest.raises(ValueError, match="SPECSTREAM_API_KEY"):
        SpecStreamFindList(max_price_usd=5)


def test_a_retry_after_the_turn_of_the_hour_reuses_the_run_from_the_hour_before(api):
    fake = api(existing={"find_id": "fnd_1", "maximum_cents": 250})
    fake.misses = 1
    result = json.loads(SpecStreamFindList(api_key=KEY, max_price_usd=5, poll_interval=0).invoke({"request": "Dental clinics in Lisbon"}))

    lookups = [path for path in fake.paths() if path.startswith("/v1/capacity/requests/")]
    assert len(lookups) == 2 and lookups[0] != lookups[1]
    assert result["row_count"] == 2
    assert "/v1/capacity/executions" not in fake.paths()
