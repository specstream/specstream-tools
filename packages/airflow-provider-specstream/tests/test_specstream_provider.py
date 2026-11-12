import io
import json
import urllib.error
import urllib.parse
from importlib.metadata import entry_points
from types import SimpleNamespace

import pytest
from airflow.exceptions import AirflowException

from specstream_provider import _api, get_provider_info
from specstream_provider.hooks.specstream import SpecStreamHook
from specstream_provider.operators.specstream import (
    SpecStreamDeepSearchOperator,
    SpecStreamExtractOperator,
    SpecStreamSearchOperator,
)

FIND_ID = "fnd_test123"


@pytest.fixture(autouse=True)
def connection(monkeypatch):
    monkeypatch.setenv("AIRFLOW_CONN_SPECSTREAM_DEFAULT", json.dumps({"conn_type": "specstream", "password": "ss_test"}))
    monkeypatch.setenv("AIRFLOW_CONN_SPECSTREAM_LOCAL", json.dumps({"conn_type": "specstream", "password": "ss_other", "host": "localhost:9000"}))


class Recorder:
    """Stands in for the network: records each request and answers with the next scripted reply."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return io.BytesIO(json.dumps({"data": reply}).encode())


def _context(run_id="manual__1", try_number=1):
    return {"ti": SimpleNamespace(dag_id="d", task_id="t", run_id=run_id, map_index=-1, try_number=try_number)}


def test_provider_info_names_the_hook_and_is_registered():
    info = get_provider_info()
    assert info["package-name"] == "airflow-provider-specstream"
    assert info["connection-types"] == [{"connection-type": "specstream", "hook-class-name": "specstream_provider.hooks.specstream.SpecStreamHook"}]
    names = {ep.value for ep in entry_points(group="apache_airflow_provider")}
    assert "specstream_provider:get_provider_info" in names


def test_hook_reads_key_and_host_from_the_connection():
    api = SpecStreamHook().get_conn()
    assert (api.api_key, api.base_url) == ("ss_test", "https://api.specstream.ai")
    api = SpecStreamHook(specstream_conn_id="specstream_local").get_conn()
    assert (api.api_key, api.base_url) == ("ss_other", "https://localhost:9000")


def test_search_operator_sends_query_speed_and_key(monkeypatch):
    recorder = Recorder({"query": "q", "sources": [{"url": "https://a.example"}]})
    op = SpecStreamSearchOperator(task_id="s", query="airflow release", speed="fast", num=5)
    op.hook.get_conn().opener = recorder
    out = op.execute(_context())
    assert out["sources"][0]["url"] == "https://a.example"
    request = recorder.requests[0]
    url = urllib.parse.urlparse(request.full_url)
    assert (url.netloc, url.path) == ("api.specstream.ai", "/v1/web-search")
    assert urllib.parse.parse_qs(url.query) == {"q": ["airflow release"], "speed": ["fast"], "num": ["5"]}
    assert request.get_header("Authorization") == "Bearer ss_test"
    assert request.get_method() == "GET"


def test_search_operator_refuses_a_bad_speed_without_a_call():
    recorder = Recorder({})
    op = SpecStreamSearchOperator(task_id="s", query="x", speed="turbo")
    op.hook.get_conn().opener = recorder
    with pytest.raises(AirflowException, match="speed"):
        op.execute(_context())
    assert recorder.requests == []


def test_extract_operator_posts_urls_and_accepts_a_single_templated_url():
    recorder = Recorder({"results": [{"url": "https://a.example", "text": "hi"}]})
    op = SpecStreamExtractOperator(task_id="e", urls="https://a.example", format="text")
    op.hook.get_conn().opener = recorder
    out = op.execute(_context())
    assert out["results"][0]["text"] == "hi"
    request = recorder.requests[0]
    assert request.get_method() == "POST"
    assert request.full_url.endswith("/v1/extract")
    assert json.loads(request.data) == {"urls": ["https://a.example"], "format": "text"}


def test_api_error_becomes_an_airflow_error_with_the_message():
    error = urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(json.dumps({"error": {"message": "bad key"}}).encode()))
    op = SpecStreamSearchOperator(task_id="s", query="x")
    op.hook.get_conn().opener = Recorder(error)
    with pytest.raises(AirflowException, match="401: bad key"):
        op.execute(_context())


def _row(ordinal, name):
    return {"entity_id": f"e{ordinal}", "ordinal": ordinal, "details": [{"label": "Organization", "display": name}]}


def _rows_page(status, *names):
    rows = [_row(i + 1, n) for i, n in enumerate(names)]
    flat = [{"id": f"{FIND_ID}:e{i + 1}", "Organization": n, "Organization_source": f"https://src/{n}", "source_url": f"https://src/{n}", "checked_at": "2026-11-12T00:00:00Z"} for i, n in enumerate(names)]
    return {"status": status, "rows": rows, "flat_rows": flat}


class FakeApi:
    def __init__(self, maximum_cents=300, existing=None, pages=None, parse=None):
        self.calls = []
        self.maximum_cents = maximum_cents
        self.existing = existing
        self.pages = pages or [_rows_page("completed", "Alpha", "Beta")]
        self.parse = parse or {"status": "runnable", "ast_hash": "h1"}

    def request(self, method, path, body=None, *, allow_404=False):
        self.calls.append((method, path, body))
        if path.startswith("/v1/capacity/requests/"):
            return self.existing
        if path == "/v1/parse":
            return self.parse
        if path == "/v1/capacity/quotes":
            return {"quote_id": "q1", "quote_hash": "qh", "maximum_cents": self.maximum_cents}
        if path == "/v1/capacity/executions":
            return {"find_id": FIND_ID}
        if "/rows" in path:
            return self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]
        raise AssertionError(path)

    def paths(self):
        return [p for _, p, _ in self.calls]


@pytest.fixture
def fake(monkeypatch):
    def install(**kwargs):
        api = FakeApi(**kwargs)
        monkeypatch.setattr(_api.SpecStreamAPI, "request", lambda self, *a, **k: api.request(*a, **k))
        return api

    return install


def _deep(**kwargs):
    op = SpecStreamDeepSearchOperator(task_id="t", request=kwargs.pop("request", "Open-source orchestrators"), max_price_usd=kwargs.pop("max_price_usd", 5), poll_interval=0, **kwargs)
    op.hook.get_conn().sleep = lambda s: None
    return op


def test_deep_search_buys_within_the_maximum_and_returns_rows_with_sources(fake):
    api = fake()
    out = _deep().execute(_context())
    assert api.paths()[1:4] == ["/v1/parse", "/v1/capacity/quotes", "/v1/capacity/executions"]
    execution = api.calls[3][2]
    assert execution["confirm_max_cents"] == 300 and execution["idempotency_key"].startswith("airflow-")
    assert out["status"] == "completed" and out["row_count"] == 2
    assert out["rows"][0]["Organization"] == "Alpha"
    assert out["rows"][0]["Organization_source"] == "https://src/Alpha"
    assert out["rows"][0]["list_link"].endswith(FIND_ID)


def test_deep_search_over_the_maximum_runs_nothing(fake):
    api = fake(maximum_cents=900)
    with pytest.raises(AirflowException, match=r"up to \$9.00"):
        _deep(max_price_usd=5).execute(_context())
    assert "/v1/capacity/executions" not in api.paths()


def test_deep_search_unclear_request_runs_nothing(fake):
    api = fake(parse={"status": "needs_input", "canonical_sentence": "things"})
    with pytest.raises(AirflowException, match="clearer request"):
        _deep().execute(_context())
    assert "/v1/capacity/quotes" not in api.paths()


def test_a_retry_continues_the_same_list_and_never_buys_twice(fake):
    first = fake()
    _deep().execute(_context(try_number=1))
    key = first.calls[3][2]["idempotency_key"]
    retry = fake(existing={"find_id": FIND_ID, "maximum_cents": 300})
    out = _deep().execute(_context(try_number=2))
    assert retry.paths()[0] == f"/v1/capacity/requests/{key}"
    assert "/v1/capacity/executions" not in retry.paths()
    assert out["list_id"] == FIND_ID


def test_another_run_gets_another_key(fake):
    a = fake()
    _deep().execute(_context(run_id="r1"))
    b = fake()
    _deep().execute(_context(run_id="r2"))
    assert a.calls[3][2]["idempotency_key"] != b.calls[3][2]["idempotency_key"]


def test_deep_search_still_running_fails_for_a_retry_unless_asked_not_to(fake):
    fake(pages=[_rows_page("running", "Alpha")])
    with pytest.raises(AirflowException, match="still running"):
        _deep(wait_seconds=0).execute(_context())
    fake(pages=[_rows_page("running", "Alpha")])
    out = _deep(wait_seconds=0, fail_if_unfinished=False).execute(_context())
    assert out["status"] == "running" and out["row_count"] == 1


def test_deep_search_failed_list_fails_the_task(fake):
    fake(pages=[_rows_page("failed")])
    with pytest.raises(AirflowException, match="stopped with status failed"):
        _deep().execute(_context())


def test_example_dag_loads():
    from specstream_provider.example_dags import example_specstream  # noqa: F401
