"""SpecStreamDeepSearch against a scripted SpecStream API: no network, no key, no spending."""

import json
from types import SimpleNamespace
from typing import Any

import pytest
from pipecat.adapters.llm.schemas.tools_schema import ToolsSchema

from pipecat_specstream import SpecStreamDeepSearch
from pipecat_specstream.search import FIND_LIST, LIST_RESULTS, PRICE_LIST, READ_PAGES, WEB_SEARCH

FIND = "fnd_test1"


class FakeResponse:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._payload = payload

    async def json(self, content_type=None):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """Answers each (method, path prefix) from a script and records every call."""

    def __init__(self, script: dict[tuple[str, str], Any]) -> None:
        self.script = script
        self.calls: list[tuple[str, str, Any, dict]] = []

    def request(self, method, url, json=None, headers=None, timeout=None):
        path = url.removeprefix("https://api.specstream.ai")
        self.calls.append((method, path, json, headers))
        for (m, prefix), answer in self.script.items():
            if m == method and path.startswith(prefix):
                answer = answer.pop(0) if isinstance(answer, list) else answer
                status, payload = answer if isinstance(answer, tuple) else (200, {"data": answer})
                return FakeResponse(status, payload)
        raise AssertionError(f"unscripted call {method} {path}")

    def paths(self, method):
        return [path for m, path, _, _ in self.calls if m == method]


def rows_page(status):
    return {
        "status": status,
        "rows": [{"ordinal": 1, "entity_id": "e1", "details": [{"label": "Name", "display": "Clinica Sorriso"}]}],
        "flat_rows": [
            {"id": f"{FIND}:e1", "Name": "Clinica Sorriso", "Name_source": "https://sorriso.pt",
             "source_url": "https://sorriso.pt", "checked_at": "2026-11-12T10:00:00Z"}
        ],
        "next_cursor": None,
    }


def priced_script(maximum_cents=300, rows=None):
    return {
        ("GET", "/v1/capacity/requests/"): (404, {"error": {"message": "not found"}}),
        ("POST", "/v1/parse"): {"status": "runnable", "ast_hash": "h1", "canonical_sentence": "Dental clinics in Lisbon"},
        ("POST", "/v1/capacity/quotes"): {"quote_id": "q1", "quote_hash": "qh1", "maximum_cents": maximum_cents},
        ("POST", "/v1/capacity/executions"): {"find_id": FIND},
        ("GET", f"/v1/finds/{FIND}/rows"): rows or [rows_page("running"), rows_page("completed")],
    }


def make(session, **kwargs):
    async def no_sleep(_):
        return None

    kwargs.setdefault("max_price_usd", 5)
    return SpecStreamDeepSearch(api_key="ss_test_key", session=session, sleep=no_sleep, **kwargs)


class Params(SimpleNamespace):
    def __init__(self, name, arguments):
        super().__init__(function_name=name, arguments=arguments, results=[])

        async def result_callback(result, *, properties=None):
            self.results.append((result, properties))

        self.result_callback = result_callback


async def call(search, name, arguments):
    schema = next(s for s in search.function_schemas() if s.name == name)
    params = Params(name, arguments)
    await schema.handler(params)
    final, properties = params.results[-1]
    assert properties is None
    return json.loads(final), params


def test_tools_carry_handlers_and_find_list_runs_in_background():
    search = make(FakeSession({}))
    tools = search.tools()
    assert isinstance(tools, ToolsSchema)
    names = [s.name for s in tools.standard_tools]
    assert names == [WEB_SEARCH, READ_PAGES, PRICE_LIST, FIND_LIST, LIST_RESULTS]
    assert all(s.handler for s in tools.standard_tools)
    find = next(s for s in tools.standard_tools if s.name == FIND_LIST)
    assert find.handler._pipecat_cancel_on_interruption is False
    assert "approved_max_usd" in find.required


def test_without_asking_there_is_no_price_tool():
    search = make(FakeSession({}), ask_before_buying=False)
    names = [s.name for s in search.function_schemas()]
    assert PRICE_LIST not in names
    find = next(s for s in search.function_schemas() if s.name == FIND_LIST)
    assert "approved_max_usd" not in find.properties


async def test_web_search_uses_fast_speed_and_bearer_key():
    session = FakeSession({("GET", "/v1/web-search"): {"kind": "fact", "answer": {"value": "42"}}})
    result, _ = await call(make(session), WEB_SEARCH, {"q": "meaning of life"})
    assert result["answer"]["value"] == "42"
    method, path, _, headers = session.calls[0]
    assert "speed=fast" in path and "q=meaning+of+life" in path
    assert headers["Authorization"] == "Bearer ss_test_key"


async def test_read_pages_posts_urls():
    session = FakeSession({("POST", "/v1/extract"): {"results": [{"url": "https://example.com", "text": "Example"}]}})
    result, _ = await call(make(session), READ_PAGES, {"urls": ["https://example.com"]})
    assert result["results"][0]["text"] == "Example"
    assert session.calls[0][2] == {"urls": ["https://example.com"], "format": "text"}


async def test_price_list_runs_nothing():
    session = FakeSession(priced_script(300))
    result, _ = await call(make(session), PRICE_LIST, {"request": "Dental clinics in Lisbon", "max_results": 20})
    assert result["status"] == "priced" and result["maximum_price_usd"] == 3.0
    assert "/v1/capacity/executions" not in session.paths("POST")


async def test_find_list_without_approval_runs_nothing():
    session = FakeSession(priced_script())
    result, _ = await call(make(session), FIND_LIST, {"request": "Dental clinics in Lisbon"})
    assert result["status"] == "needs_approval"
    assert session.calls == []


async def test_find_list_over_the_ceiling_runs_nothing():
    session = FakeSession(priced_script(900))
    result, _ = await call(make(session), FIND_LIST, {"request": "Dental clinics in Lisbon", "approved_max_usd": 20})
    assert result["status"] == "over_maximum"
    assert "/v1/capacity/executions" not in session.paths("POST")


async def test_find_list_above_the_accepted_price_runs_nothing():
    session = FakeSession(priced_script(400))
    result, _ = await call(make(session), FIND_LIST, {"request": "Dental clinics in Lisbon", "approved_max_usd": 3})
    assert result["status"] == "price_changed" and result["maximum_price_usd"] == 4.0
    assert "/v1/capacity/executions" not in session.paths("POST")


async def test_find_list_starts_within_the_accepted_price_and_returns_rows():
    session = FakeSession(priced_script(300))
    result, params = await call(
        make(session), FIND_LIST, {"request": "Dental clinics in Lisbon", "max_results": 20, "approved_max_usd": 3}
    )
    started = next(c for c in session.calls if c[1] == "/v1/capacity/executions")
    assert started[2]["confirm_max_cents"] == 300
    assert started[2]["idempotency_key"].startswith("pipecat-")
    update, properties = params.results[0]
    assert update["status"] == "running" and properties.is_final is False
    assert result["status"] == "completed" and result["row_count"] == 1
    row = result["rows"][0]
    assert row["Name"] == "Clinica Sorriso" and row["Name_source"] == "https://sorriso.pt"
    assert result["list_link"].endswith(FIND)


async def test_a_repeated_call_reuses_the_run_it_already_has():
    script = priced_script()
    script[("GET", "/v1/capacity/requests/")] = {"find_id": FIND, "maximum_cents": 300}
    session = FakeSession(script)
    result, _ = await call(make(session), FIND_LIST, {"request": "Dental clinics in Lisbon", "approved_max_usd": 3})
    assert result["list_id"] == FIND
    assert session.paths("POST") == []


async def test_list_results_pages_the_rows():
    page = rows_page("completed")
    page["rows"] = [dict(page["rows"][0], ordinal=i, entity_id=f"e{i}") for i in range(1, 6)]
    session = FakeSession({("GET", f"/v1/finds/{FIND}/rows"): page})
    result, _ = await call(make(session, rows_in_answer=2), LIST_RESULTS, {"list_id": FIND, "start": 2})
    assert [r["position"] for r in result["rows"]] == [3, 4]
    assert "start=4" in result["more"]


async def test_a_refusal_goes_to_the_model_not_the_pipeline():
    session = FakeSession({("GET", "/v1/web-search"): (401, {"error": {"message": "Invalid API key"}})})
    result, _ = await call(make(session), WEB_SEARCH, {"q": "anything"})
    assert result["status"] == "error" and "401" in result["error"]


async def test_a_missing_key_is_explained(monkeypatch):
    monkeypatch.delenv("SPECSTREAM_API_KEY", raising=False)
    search = SpecStreamDeepSearch(max_price_usd=1, session=FakeSession({}))
    result, _ = await call(search, WEB_SEARCH, {"q": "anything"})
    assert "SPECSTREAM_API_KEY" in result["error"]


def test_the_ceiling_is_required():
    with pytest.raises(ValueError):
        SpecStreamDeepSearch(api_key="k", max_price_usd=0)
