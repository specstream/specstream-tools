"""A scripted Extract API (POST /v1/extract) and a scripted embedding. No network, no model and no spend."""

from __future__ import annotations

import hashlib
import math

from specstream_pinecone.api import SpecStreamAPI

LONG = "\n\n".join(f"Paragraph {n}: " + "word " * 60 for n in range(10))  # about 3,000 characters

PAGES = {
    "https://docs.example/guide": {
        "url": "https://docs.example/guide", "status": "ok", "title": "Guide", "text": LONG,
        "published": "2026-10-01", "modified": None, "read_from": "live", "final_url": None,
    },
    "https://news.example/a": {
        "url": "https://news.example/a", "status": "ok", "title": "", "text": "Short news item.",
        "published": None, "read_from": "archive",
    },
    "https://shut.example/": {
        "url": "https://shut.example/", "status": "blocked", "title": None, "text": "",
        "published": None, "reason": "The site refused us.",
    },
}


class ScriptedExtract:
    """Answers POST /v1/extract from PAGES; records each call."""

    def __init__(self, pages=PAGES) -> None:
        self.pages = pages
        self.calls: list[tuple[str, dict[str, str], dict | None]] = []

    def __call__(self, url, headers, body=None):
        self.calls.append((url, headers, body))
        assert url.endswith("/v1/extract") and body is not None
        results = [self.pages.get(u) or {"url": u, "status": "not_found", "title": None, "text": "",
                                         "published": None, "reason": "The page answered 404."}
                   for u in body["urls"]]
        ok = sum(r["status"] == "ok" for r in results)
        return {"data": {"request_id": "req_1", "results": results, "took_ms": 5, "price_usd": ok * 0.0008}}


def api(script=None):
    return SpecStreamAPI("sk_test", "https://api.test", fetch=script or ScriptedExtract())


def embed(texts):
    vectors = []
    for text in texts:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        raw = [b - 127.5 for b in digest[:8]]
        norm = math.sqrt(sum(v * v for v in raw)) or 1.0
        vectors.append([v / norm for v in raw])
    return vectors
