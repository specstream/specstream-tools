"""A scripted SpecStream API: two lists, newest first, over two pages. No network."""

from __future__ import annotations

import urllib.parse

NEW = {
    "id": "col_new",
    "name": "Companies",
    "kind": "find",
    "imported": False,
    "project_id": None,
    "created_at": "2026-11-10T09:00:00Z",
    "total": 2,
    "rows": [
        {
            "ordinal": 0,
            "entity_id": "ent_1",
            "cells": [
                {"column_id": "name", "label": "Name", "value": "Acme Inc",
                 "provenance": {"source_url": "https://acme.example/", "observed_at": "2026-11-10T08:59:00Z"}},
                {"column_id": "rating", "label": "Rating", "value": 4.7, "display": "4.7",
                 "provenance": {"source_url": "https://maps.example/acme", "observed_at": "2026-11-10T08:58:00Z"}},
                {"column_id": "phone", "label": "Phone", "absence": {"reason": "not_found"}},
                {"column_id": "open", "label": "Open", "value": "button"},
            ],
        },
        {
            "ordinal": 1,
            "sources": [{"row": {"entity_id": "ent_2"}}],
            "cells": [{"column_id": "name", "label": "Name", "value": "Beta Ltd"}],
        },
    ],
}

OLD = {
    "id": "col_old",
    "name": "My import",
    "kind": "import",
    "imported": True,
    "project_id": "prj_1",
    "created_at": "2026-11-01T09:00:00Z",
    "total": 1,
    "rows": [{"id": "r1", "provided": {"Company": "Zed Co", "Employees": 12, "Notes": None}}],
}


class ScriptedAPI:
    """Answers the two GET calls the loader makes; records each URL and header set."""

    def __init__(self, lists=(NEW, OLD)) -> None:
        self.by_id = {c["id"]: c for c in lists}
        self.order = [c["id"] for c in lists]
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str]) -> dict:
        self.calls.append((url, headers))
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/v1/workspace/collections":
            start = int(query.get("after", ["0"])[0])
            ids = self.order[start : start + 1]  # One list a page, to exercise next_after.
            nxt = str(start + 1) if start + 1 < len(self.order) else None
            summaries = [{k: v for k, v in self.by_id[i].items() if k != "rows"} for i in ids]
            return {"data": {"collections": summaries, "next_after": nxt}}
        list_id = urllib.parse.unquote(parsed.path.rsplit("/", 1)[1])
        return {"data": self.by_id[list_id]}
