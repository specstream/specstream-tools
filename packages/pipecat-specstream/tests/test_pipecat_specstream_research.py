"""SpecStreamResearch against a scripted SpecStream API: no network, no key, no spending."""

import pytest
from pipecat.adapters.llm.schemas.tools_schema import ToolsSchema
from test_pipecat_specstream import FakeSession, call

import pipecat_specstream
from pipecat_specstream import SpecStreamResearch
from pipecat_specstream.search import GET_RESEARCH, RESEARCH_PRICE, START_RESEARCH

RUN = "res_test1"
QUESTION = "How do the EU and the US regulate stablecoin reserves?"


def run(status, **extra):
    return {"id": RUN, "status": status, "depth": "quick", "price_usd": 0.1, **extra}


def report(citations=2):
    return {
        "title": "Stablecoin reserves",
        "content": "The EU asks for 1:1 reserves [1].",
        "citations": [
            {"n": n, "url": f"https://example.com/{n}", "title": f"Page {n}", "read_at": "2026-11-13T09:00:00Z",
             "excerpt": "long text the model does not need"}
            for n in range(1, citations + 1)
        ],
    }


def script(created=None, reads=None):
    return {
        ("POST", f"/v1/research/{RUN}/cancel"): run("cancelled"),
        ("POST", "/v1/research"): created or run("queued"),
        ("GET", f"/v1/research/{RUN}"): reads or [run("running"), run("completed", report=report())],
    }


def make(session, **kwargs):
    async def no_sleep(_):
        return None

    kwargs.setdefault("max_price_usd", 0.30)
    return SpecStreamResearch(api_key="ss_test_key", session=session, sleep=no_sleep, **kwargs)


def test_tools_carry_handlers_and_only_the_depths_within_the_ceiling():
    tools = make(FakeSession({})).tools()
    assert isinstance(tools, ToolsSchema)
    assert [s.name for s in tools.standard_tools] == [RESEARCH_PRICE, START_RESEARCH, GET_RESEARCH]
    assert all(s.handler for s in tools.standard_tools)
    start = tools.standard_tools[1]
    assert start.handler._pipecat_cancel_on_interruption is False
    assert start.properties["depth"]["enum"] == ["quick", "standard"]
    assert "approved_max_usd" in start.required


def test_without_asking_there_is_no_price_tool():
    schemas = make(FakeSession({}), ask_before_buying=False).function_schemas()
    assert [s.name for s in schemas] == [START_RESEARCH, GET_RESEARCH]
    assert "approved_max_usd" not in schemas[0].properties


def test_a_ceiling_under_the_quick_price_is_refused():
    with pytest.raises(ValueError):
        SpecStreamResearch(api_key="k", max_price_usd=0.05)


def test_the_package_exports_the_class_at_one_version():
    assert pipecat_specstream.SpecStreamResearch is SpecStreamResearch
    assert pipecat_specstream.__version__ == "0.2.0"


async def test_research_price_calls_nothing():
    session = FakeSession({})
    result, _ = await call(make(session), RESEARCH_PRICE, {})
    assert [(p["depth"], p["price_usd"]) for p in result["prices"]] == [("quick", 0.1), ("standard", 0.3)]
    assert session.calls == []


@pytest.mark.parametrize(
    ("arguments", "status"),
    [
        ({"question": QUESTION}, "needs_approval"),
        ({"question": QUESTION, "depth": "standard", "approved_max_usd": 0.1}, "needs_approval"),
        ({"question": QUESTION, "depth": "deep", "approved_max_usd": 1}, "over_maximum"),
    ],
)
async def test_start_research_without_a_yes_or_above_the_ceiling_runs_nothing(arguments, status):
    session = FakeSession(script())
    result, _ = await call(make(session), START_RESEARCH, arguments)
    assert result["status"] == status
    assert session.calls == []


async def test_start_research_starts_once_and_returns_the_report():
    session = FakeSession(script())
    arguments = {"question": QUESTION, "approved_max_usd": 0.1}
    result, params = await call(make(session, sources_in_answer=1), START_RESEARCH, arguments)
    method, path, body, headers = session.calls[0]
    assert (method, path) == ("POST", "/v1/research")
    assert body == {"input": QUESTION, "depth": "quick", "length": "short"}
    assert headers["Idempotency-Key"].startswith("pipecat-research-")
    assert headers["Authorization"] == "Bearer ss_test_key"
    update, properties = params.results[0]
    assert update == {"status": "running", "research_id": RUN, "message": update["message"]}
    assert properties.is_final is False and properties.run_llm is False
    assert result["status"] == "completed" and result["research_id"] == RUN
    assert result["content"] == "The EU asks for 1:1 reserves [1]."
    assert result["citations"] == [
        {"n": 1, "url": "https://example.com/1", "title": "Page 1", "read_at": "2026-11-13T09:00:00Z"}
    ]
    assert result["citation_count"] == 2 and result["price_usd"] == 0.1


async def test_the_same_question_sends_the_same_key(monkeypatch):
    monkeypatch.setattr("pipecat_specstream.search.time.gmtime", lambda *a: (2026, 11, 13, 9, 0, 0, 4, 317, 0))
    keys = []
    for _ in range(2):
        session = FakeSession(script(created=run("completed", report=report())))
        await call(make(session), START_RESEARCH, {"question": QUESTION, "approved_max_usd": 0.1})
        keys.append(session.calls[0][3]["Idempotency-Key"])
    assert keys[0] == keys[1]


async def test_a_report_that_outlasts_the_wait_returns_its_id():
    session = FakeSession(script(reads=run("running")))
    arguments = {"question": QUESTION, "approved_max_usd": 0.1}
    result, _ = await call(make(session, wait_secs=0), START_RESEARCH, arguments)
    assert result["status"] == "queued" and result["research_id"] == RUN
    assert GET_RESEARCH in result["message"]
    assert session.paths("GET") == []


async def test_a_price_above_the_ceiling_from_the_api_cancels_the_report():
    session = FakeSession(script(created=run("queued", price_usd=0.5)))
    result, params = await call(make(session), START_RESEARCH, {"question": QUESTION, "approved_max_usd": 0.1})
    assert result["status"] == "over_maximum" and result["price_usd"] == 0.5
    assert session.paths("POST") == ["/v1/research", f"/v1/research/{RUN}/cancel"]
    assert len(params.results) == 1


async def test_an_empty_balance_is_explained():
    session = FakeSession(script(created=run("payment_required")))
    result, _ = await call(make(session), START_RESEARCH, {"question": QUESTION, "approved_max_usd": 0.1})
    assert result["status"] == "payment_required" and "Add credit" in result["message"]


async def test_get_research_reads_a_report_by_its_id():
    session = FakeSession(script(reads=run("completed", report=report())))
    result, _ = await call(make(session), GET_RESEARCH, {"research_id": RUN})
    assert result["status"] == "completed" and result["title"] == "Stablecoin reserves"
    assert session.paths("GET") == [f"/v1/research/{RUN}"]


async def test_a_refusal_goes_to_the_model_not_the_pipeline():
    session = FakeSession({("POST", "/v1/research"): (402, {"error": {"message": "Add credit"}})})
    result, _ = await call(make(session, ask_before_buying=False), START_RESEARCH, {"question": QUESTION})
    assert result["status"] == "error" and "402" in result["error"]
