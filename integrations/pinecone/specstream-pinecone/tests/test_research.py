"""The research command: research reports into an in-memory Pinecone index, with a scripted research API and a
scripted embedding. No network, no Pinecone key, no spend."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from extract_script import embed
from fake_pinecone import FakeClient, FakeIndex
from research_script import CONTENT, ScriptedResearch, api, run
from specstream_pinecone import cli
from specstream_pinecone.api import SpecStreamAPI, SpecStreamError
from specstream_pinecone.load import open_index, vector_id
from specstream_pinecone.pages import chunk_id
from specstream_pinecone.research import (
    is_research_loaded,
    load_research,
    research_chunk_id,
    research_metadata,
    wait_for_research,
)


def stored(index, namespace="__default__"):
    space = index.spaces.get(namespace, {})
    return {i: v["metadata"] for i, v in space.items() if i.startswith("research:")}


def test_a_report_is_written_one_vector_per_chunk_with_the_pages_each_chunk_cites():
    index = FakeIndex()
    script = ScriptedResearch()
    result = load_research(api(script), embed, index, report_ids=["res_done", "res_done"], namespace="r",
                           chunk_chars=300, overlap_chars=30)

    assert result.loaded == ["res_done"] and result.reports == 1 and result.price_usd == 0
    assert [c[:2] for c in script.calls] == [("GET", "/res_done")]  # read once, nothing started
    found = stored(index, "r")
    assert len(found) == result.chunks >= 3
    first = found[research_chunk_id("res_done", 0)]
    assert first["kind"] == "research" and first["report_id"] == "res_done" and first["depth"] == "quick"
    assert first["title"] == "Solid-state batteries in 2026" and first["completed_at"] == "2026-11-13T02:01:00Z"
    assert first["chunks"] == len(found) and first["text"].startswith("## Who makes")
    assert json.loads(first["sources"]) == {"1": "https://toyota.example/plan", "2": "https://qs.example/b"}
    assert first["source_urls"] == ["https://toyota.example/plan", "https://qs.example/b"]
    assert first["source_titles"] == ["Toyota plan", "B samples"] and "question" not in first
    # A marker with no page behind it names no source.
    last = found[research_chunk_id("res_done", len(found) - 1)]
    assert "[9]" in last["text"] and last["source_urls"] == [] and last["sources"] == "{}"
    assert is_research_loaded(index, "res_done", "r") and not is_research_loaded(index, "res_done")


def test_writing_a_report_again_replaces_its_chunks_and_leaves_lists_and_pages_alone():
    index = FakeIndex()
    others = [vector_id("col_1", "r1"), chunk_id("https://docs.example/guide", 0)]
    index.upsert(vectors=[{"id": i, "values": [0.1] * 8, "metadata": {"kind": "other"}} for i in others],
                 namespace="__default__")
    load_research(api(), embed, index, report_ids=["res_done"], chunk_chars=200, overlap_chars=20)
    assert len(stored(index)) > 3
    shorter = ScriptedResearch([run(content="One line [1].")])
    load_research(api(shorter), embed, index, report_ids=["res_done"], chunk_chars=200, overlap_chars=20)
    assert list(stored(index)) == [research_chunk_id("res_done", 0)]
    assert stored(index)[research_chunk_id("res_done", 0)]["source_urls"] == ["https://toyota.example/plan"]
    assert all(i in index.spaces["__default__"] for i in others)


def test_a_question_starts_a_report_waits_for_it_and_keeps_the_question_and_the_price():
    index = FakeIndex()
    script = ScriptedResearch(runs=[], polls_before_done=2)
    naps: list[float] = []
    result = load_research(api(script), embed, index, questions=["Who makes solid-state batteries?", " "],
                           depth="deep", sleep=naps.append, include_domains=["toyota.example"], exclude_domains=None)

    assert script.started == [{"input": "Who makes solid-state batteries?", "depth": "deep",
                               "include_domains": ["toyota.example"]}]
    method, path, headers, _ = script.calls[0]
    assert (method, path) == ("POST", "") and headers["Authorization"] == "Bearer sk_test"
    assert headers["Idempotency-Key"].startswith("specstream-pinecone-")
    assert headers["User-Agent"].startswith("specstream-pinecone/")
    assert "Idempotency-Key" not in script.calls[1][2]
    assert len(naps) == 2 and result.loaded == ["res_new1"] and result.price_usd == pytest.approx(1.00)
    meta = stored(index)[research_chunk_id("res_new1", 0)]
    assert meta["question"] == "Who makes solid-state batteries?" and meta["depth"] == "deep"


def test_a_report_that_fails_or_runs_past_the_wait_writes_nothing_and_is_not_counted_as_paid():
    index = FakeIndex()
    failed = load_research(api(ScriptedResearch(runs=[], polls_before_done=0, ends="failed")), embed, index,
                           questions=["q"], depth="quick", sleep=lambda s: None)
    assert failed.skipped == [("res_new1", "failed", "No page answered the question.")]
    assert failed.reports == 0 and failed.price_usd == 0 and index.spaces == {}

    ticks = iter(range(0, 10_000, 4))
    slow = ScriptedResearch(runs=[run("res_slow", "running")])
    with pytest.raises(SpecStreamError, match="load it later with --id res_slow"):
        wait_for_research(api(slow), "res_slow", wait_seconds=10, sleep=lambda s: None, clock=lambda: next(ticks))
    assert not any(c[0] == "POST" for c in slow.calls)  # Waiting never cancels and never starts a report.

    empty = load_research(api(ScriptedResearch([run(content="  ")])), embed, index, report_ids=["res_done"])
    assert empty.skipped == [("res_done", "empty", "The report has no text.")] and index.spaces == {}


def test_every_loads_the_completed_reports_the_index_lacks_page_by_page_and_spends_nothing():
    runs = [run("res_5"), run("res_4", "running"), run("res_3"), run("res_2", "failed"), run("res_1")]
    index = FakeIndex()
    script = ScriptedResearch(runs, page_size=2)
    load_research(api(script), embed, index, report_ids=["res_3"])
    script.calls.clear()

    result = load_research(api(script), embed, index, every=True)
    assert result.loaded == ["res_5", "res_1"] and result.skipped == [] and result.price_usd == 0
    paths = [c[1] for c in script.calls]
    assert [p for p in paths if p.startswith("?")] == ["?limit=100", "?limit=100&after=res_4",
                                                       "?limit=100&after=res_2"]
    assert [p for p in paths if p.startswith("/")] == ["/res_5", "/res_1"]  # the list has no text: each is read
    assert not any(c[0] == "POST" for c in script.calls)
    assert load_research(api(script), embed, index, every=True).reports == 0
    assert load_research(api(script), embed, index, every=True, full=True).loaded == ["res_5", "res_3", "res_1"]


def test_bad_input_starts_nothing():
    script = ScriptedResearch()
    for kwargs in ({"index": FakeIndex()},
                   {"index": FakeIndex(), "questions": ["  "]},
                   {"questions": ["q"]},
                   {"every": True, "open": lambda d: FakeIndex()},
                   {"index": FakeIndex(), "questions": ["q"], "depth": "huge"},
                   {"index": FakeIndex(), "questions": ["q"], "chunk_chars": 50, "overlap_chars": 50}):
        with pytest.raises(ValueError):
            load_research(api(script), embed, **kwargs)
    assert script.calls == []
    index = FakeIndex()
    with pytest.raises(ValueError, match="size 1024"):
        load_research(api(script), embed, index, report_ids=["res_done"], dimension=1024)
    assert index.spaces == {}


def test_metadata_holds_only_values_pinecone_takes():
    items = research_metadata(run(), datetime(2026, 11, 13, tzinfo=timezone.utc), 400, 40, question="q" * 5000)
    assert len(items[0]["question"]) == 2000
    for item in items:
        for value in item.values():
            assert isinstance(value, (str, int, float, bool)) or all(isinstance(x, str) for x in value)
    assert CONTENT.startswith(items[0]["text"][:50])


def test_cli_research_loads_reports_into_the_index_lists_use(monkeypatch, capsys):
    script = ScriptedResearch([run("res_b"), run("res_a", "failed")], polls_before_done=0)
    pc = FakeClient(dim=8)
    monkeypatch.setenv("SPECSTREAM_API_KEY", "sk_test")
    monkeypatch.setattr(cli, "connect", lambda args: pc)
    monkeypatch.setattr(cli, "SpecStreamAPI", lambda key, url: SpecStreamAPI(key, "https://api.test", fetch=script))

    assert cli.main(["research", "Who makes solid-state batteries?", "--depth", "quick", "--id", "res_a",
                     "--all", "--dimension", "8", "--exclude-domain", "spam.example"]) == 0
    out = capsys.readouterr()
    assert script.started == [{"input": "Who makes solid-state batteries?", "depth": "quick",
                               "exclude_domains": ["spam.example"]}]
    assert "Loaded 2 report(s)" in out.out and "into specstream; new reports cost $0.10." in out.out
    assert "Not loaded (failed): res_a - No page answered the question." in out.err
    assert pc.created[0]["name"] == "specstream" and pc.created[0]["dimension"] == 8
    index = open_index(pc, "specstream", 8)
    assert {m["report_id"] for m in stored(index).values()} == {"res_new1", "res_b"}

    assert cli.main(["research"]) == 1
    assert "Give a question, --id" in capsys.readouterr().err
    assert cli.main(["research", "--id", "res_a", "--dimension", "8"]) == 1  # nothing loaded
