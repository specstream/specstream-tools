import json

import pytest
from haystack import Pipeline
from haystack.tools import ComponentTool
from haystack.utils import Secret

from haystack_integrations.components.fetchers.specstream import SpecStreamError, SpecStreamListFetcher, _api
from haystack_integrations.tools.specstream import SpecStreamListTool

FIND_ID = "fnd_test123"


def _row(ordinal, name, url):
    return {
        "entity_id": f"e{ordinal}",
        "ordinal": ordinal,
        "details": [
            {"label": "Organization", "display": name, "provenance": {"source_url": url, "observed_at": "2026-10-14T19:56:02Z"}},
            {"label": "Website", "display": f"https://{name.lower()}.example"},
            {"label": "source_url", "display": "clashes"},
        ],
    }


def _flat(row):
    """The API's flat row: the page of each value, and of the fact that put the row in the list."""
    name = row["details"][0]
    return {
        "id": f"{FIND_ID}:{row['entity_id']}",
        "name": name["display"],
        "name_source": name["provenance"]["source_url"],
        "source_url": f"{name['provenance']['source_url']}/filing",
        "checked_at": "2026-10-14T19:56:02Z",
    }


class FakeApi:
    """Stands in for the SpecStream REST API and records the calls."""

    def __init__(self, parse=None, maximum_cents=300, existing=None, pages=None):
        self.calls = []
        self.parse = parse or {"status": "runnable", "ast_hash": "h1"}
        self.maximum_cents = maximum_cents
        self.existing = existing
        self.pages = pages or [{"status": "completed", "rows": [_row(1, "Alpha", "https://src/a"), _row(2, "Beta", "https://src/b")]}]

    def request(self, api, method, path, body=None, *, allow_404=False):
        self.calls.append((method, path, body))
        if path == "/v1/parse":
            return self.parse
        if path.startswith("/v1/capacity/requests/"):
            return self.existing
        if path == "/v1/capacity/quotes":
            return {"quote_id": "q1", "quote_hash": "qh", "maximum_cents": self.maximum_cents}
        if path == "/v1/capacity/executions":
            return {"find_id": FIND_ID}
        if "/rows" in path:
            page = self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]
            return {**page, "flat_rows": [_flat(row) for row in page["rows"]]}
        raise AssertionError(path)

    def paths(self):
        return [p for _, p, _ in self.calls]


@pytest.fixture
def fake(monkeypatch):
    def install(**kwargs):
        api = FakeApi(**kwargs)
        monkeypatch.setattr(_api.SpecStreamAPI, "request", lambda self, *a, **k: api.request(self, *a, **k))
        monkeypatch.setattr(_api.SpecStreamAPI, "sleep", lambda s: None, raising=False)
        return api

    return install


def _fetcher(**kwargs):
    return SpecStreamListFetcher(
        max_price_usd=kwargs.pop("max_price_usd", 5), api_key=Secret.from_token("ss_test"), poll_interval=0, **kwargs
    )


def test_rows_become_documents_with_source_in_meta(fake):
    fake()
    result = _fetcher().run(request="Breweries in Portland")
    docs = result["documents"]
    assert [d.meta["source_url"] for d in docs] == ["https://src/a/filing", "https://src/b/filing"]
    first = docs[0]
    assert json.loads(first.content)["Organization"] == "Alpha"
    assert first.meta["checked_at"] == "2026-10-14T19:56:02Z"
    assert first.meta["list_id"] == FIND_ID
    assert first.meta["list_link"].endswith(FIND_ID)
    assert first.meta["fields"]["Website"] == "https://alpha.example"
    # A column called source_url can't overwrite the real source.
    assert "source_url (column)" in first.meta["fields"]
    assert result["status"] == "completed" and result["list_id"] == FIND_ID


def test_runs_the_quote_then_executes_with_the_quoted_ceiling_and_key(fake):
    api = fake(maximum_cents=250)
    _fetcher().run(request="Breweries in Portland", max_results=10)
    quote = next(b for _, p, b in api.calls if p == "/v1/capacity/quotes")
    assert quote["requested_units"] == 10
    run = next(b for _, p, b in api.calls if p == "/v1/capacity/executions")
    assert run["confirm_max_cents"] == 250
    assert run["idempotency_key"].startswith("haystack-")


def test_price_above_the_ceiling_runs_nothing(fake):
    api = fake(maximum_cents=900)
    with pytest.raises(SpecStreamError, match="above the maximum"):
        _fetcher(max_price_usd=5).run(request="Breweries in Portland")
    assert "/v1/capacity/executions" not in api.paths()


def test_vague_request_raises_with_the_reading(fake):
    api = fake(parse={"status": "needs_edit", "canonical_sentence": "clinics"})
    with pytest.raises(SpecStreamError, match="clinics"):
        _fetcher().run(request="clinics")
    assert "/v1/capacity/quotes" not in api.paths()


def test_a_retried_request_reaches_the_run_it_already_started(fake):
    api = fake(existing={"find_id": FIND_ID, "maximum_cents": 300})
    result = _fetcher().run(request="Breweries in Portland")
    assert result["list_id"] == FIND_ID
    assert "/v1/capacity/executions" not in api.paths()
    assert "/v1/parse" not in api.paths()


def test_follows_row_pages(fake):
    fake(
        pages=[
            {"status": "running", "rows": [_row(1, "Alpha", "https://src/a")], "next_cursor": "c2"},
            {"status": "completed", "rows": [_row(2, "Beta", "https://src/b")]},
        ]
    )
    assert len(_fetcher().run(request="Breweries in Portland")["documents"]) == 2


def test_unfinished_list_says_so(fake, monkeypatch):
    fake(pages=[{"status": "running", "rows": [_row(1, "Alpha", "https://src/a")]}])
    result = _fetcher(wait_seconds=0).run(request="Breweries in Portland")
    assert result["status"] == "running"
    assert "Still running" in result["message"]


def test_missing_key_is_explained(monkeypatch):
    monkeypatch.delenv("SPECSTREAM_API_KEY", raising=False)
    with pytest.raises(Exception):
        SpecStreamListFetcher(max_price_usd=1).run(request="x")


def test_init_rejects_a_zero_ceiling():
    with pytest.raises(ValueError):
        SpecStreamListFetcher(max_price_usd=0)


def test_serialization_round_trip_keeps_the_key_out():
    data = SpecStreamListFetcher(max_price_usd=2, max_results=7).to_dict()
    assert data["init_parameters"]["api_key"] == {"type": "env_var", "env_vars": ["SPECSTREAM_API_KEY"], "strict": True}
    again = SpecStreamListFetcher.from_dict(data)
    assert again.max_price_usd == 2 and again.max_results == 7


def test_works_in_a_pipeline(fake):
    fake()
    pipe = Pipeline()
    pipe.add_component("fetcher", _fetcher())
    out = pipe.run({"fetcher": {"request": "Breweries in Portland"}})
    assert len(out["fetcher"]["documents"]) == 2


def test_tool_hides_the_price_from_the_model_and_returns_rows_with_sources(fake):
    fake()
    tool = SpecStreamListTool(max_price_usd=5, api_key=Secret.from_token("ss_test"), poll_interval=0)
    assert isinstance(tool, ComponentTool)
    assert tool.name == "specstream_find_list"
    assert set(tool.parameters["properties"]) == {"request", "max_results"}
    result = tool.invoke(request="Breweries in Portland")
    text = tool.outputs_to_string["handler"](result["documents"])
    assert "Alpha" in text and "https://src/b" in text
