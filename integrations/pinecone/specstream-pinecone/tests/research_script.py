"""A scripted research API (POST /v1/research, GET /v1/research, GET /v1/research/{id}). No network, no model
and no spend."""

from __future__ import annotations

from specstream_pinecone.api import RESEARCH_PRICES, SpecStreamAPI

CONTENT = (
    "## Who makes solid-state batteries\n\n"
    "Toyota plans cells for 2027 [1]. QuantumScape ships B samples [2].\n\n"
    "## What it costs\n\n"
    "Cell cost is still above lithium-ion [2][3]. " + "More detail follows. " * 40 + "\n\n"
    "## Outlook\n\nNo maker names a volume date [9]."
)


def run(report_id="res_done", status="completed", content=CONTENT, depth="quick"):
    report = None
    if status == "completed":
        report = {
            "title": "Solid-state batteries in 2026", "format": "markdown", "content": content, "structured": None,
            "citations": [
                {"n": 1, "url": "https://toyota.example/plan", "title": "Toyota plan",
                 "read_at": "2026-11-13T02:00:00Z", "excerpt": "cells for 2027", "start": 40, "end": 70,
                 "supported": True},
            ],
            "sources": [
                {"n": 1, "url": "https://toyota.example/plan", "title": "Toyota plan",
                 "read_at": "2026-11-13T02:00:00Z", "cited": True},
                {"n": 2, "url": "https://qs.example/b", "title": "B samples",
                 "read_at": "2026-11-13T02:00:01Z", "cited": True},
                {"n": 3, "url": "https://cost.example/", "title": "",
                 "read_at": "2026-11-13T02:00:02Z", "cited": True},
                {"n": 4, "url": "https://unused.example/", "title": "Unused",
                 "read_at": "2026-11-13T02:00:03Z", "cited": False},
            ],
            "basis": [],
        }
    return {
        "id": report_id, "status": status, "stage": "done" if status == "completed" else "writing", "depth": depth,
        "progress": {"searches": 4, "pages_read": 9, "sources": 4}, "created_at": "2026-11-13T01:59:00Z",
        "started_at": "2026-11-13T01:59:01Z",
        "completed_at": "2026-11-13T02:01:00Z" if status == "completed" else None,
        "report": report,
        "usage": {"searches": 4, "pages_read": 9,
                  "charged_usd": RESEARCH_PRICES[depth] if status == "completed" else 0.0},
        "metadata": {},
        "error": {"code": "no_sources", "message": "No page answered the question."} if status == "failed" else None,
    }


class ScriptedResearch:
    """`runs` are the reports the account has, newest first. A started report answers `running` for
    `polls_before_done` reads, then ends with `ends`. Each call is recorded as (method, path, headers, body)."""

    def __init__(self, runs=None, polls_before_done=2, ends="completed", page_size=2) -> None:
        self.runs = {r["id"]: r for r in (runs if runs is not None else [run()])}
        self.polls_before_done = polls_before_done
        self.ends = ends
        self.page_size = page_size
        self.pending: dict[str, int] = {}
        self.started: list[dict] = []
        self.calls: list[tuple[str, str, dict[str, str], dict | None]] = []

    def __call__(self, url, headers, body=None):
        path = url.split("/v1/research", 1)[1]
        self.calls.append(("POST" if body is not None else "GET", path, headers, body))
        if body is not None:
            assert path == "" and headers.get("Idempotency-Key")
            report_id = f"res_new{len(self.started) + 1}"
            self.started.append(body)
            self.pending[report_id] = self.polls_before_done
            self.runs = {report_id: run(report_id, "running", depth=body["depth"]), **self.runs}
            return {"data": {"id": report_id, "status": "queued", "depth": body["depth"],
                             "price_usd": RESEARCH_PRICES[body["depth"]], "created_at": "2026-11-13T01:59:00Z",
                             "links": {"self": f"/v1/research/{report_id}",
                                       "events": f"/v1/research/{report_id}/events"}}}
        if path.startswith("?"):
            ids = list(self.runs)
            after = dict(p.split("=") for p in path[1:].split("&")).get("after")
            start = ids.index(after) + 1 if after else 0
            page = ids[start : start + self.page_size]
            more = start + self.page_size < len(ids)
            # The list shows each report without its text.
            return {"data": [dict(self.runs[i], report=None) for i in page], "has_more": more,
                    "next_after": page[-1] if more else None}
        report_id = path.lstrip("/")
        if report_id in self.pending:
            if self.pending[report_id] > 0:
                self.pending[report_id] -= 1
            else:
                del self.pending[report_id]
                self.runs[report_id] = run(report_id, self.ends, depth=self.runs[report_id]["depth"])
        return {"data": self.runs[report_id]}


def api(script=None):
    return SpecStreamAPI("sk_test", "https://api.test", fetch=script or ScriptedResearch())
