import io
import json
import urllib.error
import urllib.parse
from types import SimpleNamespace

import pytest
from dagster import (
    AssetExecutionContext,
    Definitions,
    EnvVar,
    Failure,
    RetryRequested,
    StaticPartitionsDefinition,
    asset,
    build_asset_context,
    materialize,
)

from dagster_specstream import SpecStreamError, SpecStreamResource, _api, run_key

FIND_ID = "fnd_test123"


class FakeAPI:
    """Stands in for the network: answers each call by its method and path, and records it."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        url = urllib.parse.urlparse(request.full_url)
        for (method, prefix), reply in self.routes.items():
            if request.get_method() == method and url.path.startswith(prefix):
                if callable(reply):
                    reply = reply(request)
                if isinstance(reply, Exception):
                    raise reply
                return io.BytesIO(json.dumps({"data": reply}).encode())
        raise AssertionError(f"unexpected call {request.get_method()} {url.path}")

    def calls(self, method, prefix):
        return [r for r in self.requests if r.get_method() == method and urllib.parse.urlparse(r.full_url).path.startswith(prefix)]


def _not_found(request):
    return urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, io.BytesIO(b"{}"))


def _rows(status="completed"):
    return {
        "status": status,
        "rows": [{"ordinal": 1, "entity_id": "e1", "details": [{"label": "name", "value": "Dagster"}]}],
        "flat_rows": [{"id": f"{FIND_ID}:e1", "source_url": "https://dagster.io", "checked_at": "2026-11-12T10:00:00Z"}],
        "next_cursor": None,
    }


def _deep_routes(status="completed", quote_cents=250):
    return {
        ("GET", "/v1/capacity/requests/"): _not_found,
        ("POST", "/v1/parse"): {"status": "runnable", "ast_hash": "h1"},
        ("POST", "/v1/capacity/quotes"): {"quote_id": "q1", "quote_hash": "qh", "maximum_cents": quote_cents},
        ("POST", "/v1/capacity/executions"): {"find_id": FIND_ID},
        ("GET", f"/v1/finds/{FIND_ID}/rows"): _rows(status),
    }


@pytest.fixture
def fake(monkeypatch):
    def install(routes):
        api = FakeAPI(routes)
        monkeypatch.setattr(_api, "_urlopen", api)
        return api

    return install


def test_web_search_sends_query_speed_key_and_user_agent(fake):
    api = fake({("GET", "/v1/web-search"): {"query": "q", "sources": [{"url": "https://a.example"}]}})
    out = SpecStreamResource(api_key="ss_test").web_search("dagster release", speed="fast", num=5)
    assert out["sources"][0]["url"] == "https://a.example"
    request = api.requests[0]
    url = urllib.parse.urlparse(request.full_url)
    assert (url.netloc, url.path) == ("api.specstream.ai", "/v1/web-search")
    assert urllib.parse.parse_qs(url.query) == {"q": ["dagster release"], "speed": ["fast"], "num": ["5"]}
    assert request.get_header("Authorization") == "Bearer ss_test"
    assert request.get_header("User-agent") == "dagster-specstream/0.1.0"


def test_extract_takes_one_url_or_a_list(fake):
    api = fake({("POST", "/v1/extract"): {"pages": []}})
    resource = SpecStreamResource(api_key="ss_test", base_url="http://localhost:9000/")
    resource.extract_pages("https://dagster.io")
    resource.extract_pages(["https://a.example", "https://b.example"], format="text")
    bodies = [json.loads(r.data) for r in api.requests]
    assert bodies == [
        {"urls": ["https://dagster.io"], "format": "markdown"},
        {"urls": ["https://a.example", "https://b.example"], "format": "text"},
    ]
    assert api.requests[0].full_url == "http://localhost:9000/v1/extract"


def test_bad_input_and_missing_key_fail_without_a_call(fake):
    api = fake({})
    with pytest.raises(ValueError, match="speed"):
        SpecStreamResource(api_key="ss_test").web_search("x", speed="turbo")
    with pytest.raises(SpecStreamError, match="no API key"):
        SpecStreamResource(api_key=" ").web_search("x")
    assert api.requests == []


def test_api_error_carries_the_message(fake):
    def refused(request):
        return urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error": {"message": "Invalid API key"}}'))

    fake({("GET", "/v1/web-search"): refused})
    with pytest.raises(SpecStreamError, match="401: Invalid API key"):
        SpecStreamResource(api_key="ss_bad").web_search("x")


def test_asset_runs_a_deep_search_with_the_run_key(fake, monkeypatch):
    api = fake(_deep_routes())
    monkeypatch.setenv("SPECSTREAM_API_KEY", "ss_env")

    @asset
    def orchestrators(context: AssetExecutionContext, specstream: SpecStreamResource) -> list:
        return specstream.deep_search(context, "Open-source workflow orchestrators", max_results=10, max_price_usd=5)["rows"]

    defs = Definitions(assets=[orchestrators], resources={"specstream": SpecStreamResource(api_key=EnvVar("SPECSTREAM_API_KEY"))})
    result = materialize([orchestrators], resources=defs.resources)
    assert result.success
    rows = result.output_for_node("orchestrators")
    assert rows[0]["name"] == "Dagster"
    assert rows[0]["source_url"] == "https://dagster.io"
    assert rows[0]["list_link"].endswith(FIND_ID)
    execution = json.loads(api.calls("POST", "/v1/capacity/executions")[0].data)
    assert execution["confirm_max_cents"] == 250
    assert execution["idempotency_key"].startswith("dagster-")
    assert all(r.get_header("Authorization") == "Bearer ss_env" for r in api.requests)


def test_over_the_maximum_nothing_runs_and_the_step_fails_once(fake):
    api = fake(_deep_routes(quote_cents=900))
    with pytest.raises(Failure, match=r"up to \$9.00, above the maximum of \$5.00") as caught:
        SpecStreamResource(api_key="ss_test").deep_search(build_asset_context(), "x", max_results=10, max_price_usd=5, idempotency_key="k1")
    assert caught.value.allow_retries is False
    assert api.calls("POST", "/v1/capacity/executions") == []


def test_a_retry_continues_the_list_it_already_started(fake):
    routes = _deep_routes()
    routes[("GET", "/v1/capacity/requests/")] = {"find_id": FIND_ID, "maximum_cents": 250}
    api = fake(routes)
    out = SpecStreamResource(api_key="ss_test").deep_search(build_asset_context(), "x", max_results=10, max_price_usd=5, idempotency_key="k1")
    assert out["row_count"] == 1
    assert api.calls("POST", "/v1/parse") == []
    assert api.calls("POST", "/v1/capacity/executions") == []
    assert api.calls("GET", "/v1/capacity/requests/")[0].full_url.endswith("/v1/capacity/requests/k1")


def test_a_list_still_running_asks_dagster_to_retry(fake):
    fake(_deep_routes(status="running"))
    with pytest.raises(RetryRequested) as caught:
        SpecStreamResource(api_key="ss_test").deep_search(
            build_asset_context(), "x", max_results=10, max_price_usd=5, idempotency_key="k1", wait_seconds=0, retries_while_running=4
        )
    assert caught.value.max_retries == 4


def test_a_stopped_list_fails_with_its_link(fake):
    fake(_deep_routes(status="failed"))
    with pytest.raises(Failure, match=f"{FIND_ID} stopped with status failed"):
        SpecStreamResource(api_key="ss_test").deep_search(build_asset_context(), "x", max_results=10, max_price_usd=5, idempotency_key="k1")


def test_run_key_holds_across_re_execution_and_splits_by_partition_and_step():
    first = SimpleNamespace(run=SimpleNamespace(root_run_id=None, run_id="run-1"), asset_key=SimpleNamespace(to_user_string=lambda: "a"))
    again = SimpleNamespace(run=SimpleNamespace(root_run_id="run-1", run_id="run-2"), asset_key=SimpleNamespace(to_user_string=lambda: "a"))
    assert run_key(first) == run_key(again)
    assert run_key(first) != run_key(first, name="other")

    us = SimpleNamespace(run=SimpleNamespace(root_run_id="run-1", run_id="run-2"), has_partition_key=True, partition_key="us")
    fr = SimpleNamespace(run=SimpleNamespace(root_run_id="run-1", run_id="run-2"), has_partition_key=True, partition_key="fr")
    assert run_key(us, name="a") != run_key(fr, name="a")


def test_run_key_reads_a_real_partitioned_asset_context():
    seen = []

    @asset(partitions_def=StaticPartitionsDefinition(["us", "fr"]))
    def regional(context: AssetExecutionContext) -> None:
        seen.append(run_key(context))

    assert materialize([regional], partition_key="us").success
    assert materialize([regional], partition_key="fr").success
    assert all(key.startswith("dagster-") for key in seen)
    assert len(set(seen)) == 2
