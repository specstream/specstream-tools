"""The Extract loader against Qdrant's own client in local (in-memory) mode, with a scripted Extract API and a
scripted embedding. No network, no model download and no spend."""

from __future__ import annotations

import pytest
from qdrant_client import QdrantClient, models

from specstream_qdrant import cli
from specstream_qdrant.api import SpecStreamAPI, SpecStreamError
from specstream_qdrant.pages import chunk_id, load_pages, split_text

from test_load import embed

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


def chunks(client, collection="specstream_pages"):
    found, _ = client.scroll(collection, limit=100, with_payload=True)
    return sorted((p.payload["url"], p.payload["chunk"]) for p in found)


def test_split_keeps_paragraphs_together_and_cuts_long_ones_with_overlap():
    assert split_text("a\n\nb\n\n\n\nc", size=10, overlap=0) == ["a\n\nb\n\nc"]
    assert split_text("aaaa\n\nbbbb", size=6, overlap=0) == ["aaaa", "bbbb"]
    long = "x" * 25
    parts = split_text(long, size=10, overlap=3)
    assert all(len(p) <= 10 for p in parts)
    assert "".join(p[3:] if i else p for i, p in enumerate(parts)) == long
    assert split_text("", 10, 0) == []
    with pytest.raises(ValueError):
        split_text("x", size=10, overlap=10)


def test_pages_fill_the_collection_one_point_per_chunk_and_skip_pages_without_text():
    client = QdrantClient(":memory:")
    result = load_pages(client, api(), embed, list(PAGES), chunk_chars=1000, overlap_chars=100)

    assert result.pages == 2
    assert result.loaded == ["https://docs.example/guide", "https://news.example/a"]
    assert result.skipped == [("https://shut.example/", "blocked", "The site refused us.")]
    assert result.price_usd == pytest.approx(0.0016)
    guide = [c for c in chunks(client) if c[0] == "https://docs.example/guide"]
    assert len(guide) == result.chunks - 1 >= 3
    info = client.get_collection("specstream_pages")
    assert info.config.params.vectors.size == 8
    point = client.retrieve("specstream_pages", [chunk_id("https://docs.example/guide", 0)], with_payload=True)[0]
    assert point.payload["title"] == "Guide"
    assert point.payload["published"] == "2026-10-01"
    assert point.payload["chunks"] == len(guide)
    assert point.payload["text"].startswith("Paragraph 0:")


def test_search_finds_a_chunk_by_vector_and_filters_by_url():
    client = QdrantClient(":memory:")
    load_pages(client, api(), embed, list(PAGES))
    hits = client.query_points(
        "specstream_pages",
        query=embed(["Short news item."])[0],
        query_filter=models.Filter(must=[models.FieldCondition(key="url", match=models.MatchValue(value="https://news.example/a"))]),
        limit=3,
    ).points
    assert [h.payload["text"] for h in hits] == ["Short news item."]


def test_reading_a_page_again_replaces_its_chunks():
    client = QdrantClient(":memory:")
    load_pages(client, api(), embed, list(PAGES), chunk_chars=500, overlap_chars=50)
    before = len(chunks(client))
    shorter = dict(PAGES, **{"https://docs.example/guide": dict(PAGES["https://docs.example/guide"], text="Now one line.")})
    load_pages(client, api(ScriptedExtract(shorter)), embed, ["https://docs.example/guide"], chunk_chars=500, overlap_chars=50)
    assert before > 2
    assert chunks(client) == [("https://docs.example/guide", 0), ("https://news.example/a", 0)]


def test_urls_go_twenty_to_a_call_once_each_with_the_key():
    script = ScriptedExtract()
    urls = [f"https://site.example/{n}" for n in range(45)] + ["https://site.example/0", " "]
    result = load_pages(QdrantClient(":memory:"), api(script), embed, urls)
    assert [len(body["urls"]) for _, _, body in script.calls] == [20, 20, 5]
    assert len(result.skipped) == 45 and result.pages == 0
    for url, headers, body in script.calls:
        assert url == "https://api.test/v1/extract"
        assert headers["Authorization"] == "Bearer sk_test"
        assert headers["User-Agent"].startswith("specstream-qdrant/")
        assert body["format"] == "markdown"


def test_bad_input_is_refused_before_any_call():
    script = ScriptedExtract()
    with pytest.raises(ValueError):
        load_pages(QdrantClient(":memory:"), api(script), embed, ["  "])
    with pytest.raises(ValueError):
        load_pages(QdrantClient(":memory:"), api(script), embed, ["https://a.example/"], chunk_chars=100, overlap_chars=100)
    with pytest.raises(ValueError):
        api(script).extract([f"https://a.example/{n}" for n in range(21)])
    assert script.calls == []


def test_cli_pages_reads_a_url_file_and_reports(tmp_path, monkeypatch, capsys):
    script = ScriptedExtract()
    monkeypatch.setenv("SPECSTREAM_API_KEY", "sk_test")
    monkeypatch.setattr(cli, "fastembed", lambda model: embed)
    monkeypatch.setattr(cli, "SpecStreamAPI", lambda key, url: SpecStreamAPI(key, "https://api.test", fetch=script))
    listing = tmp_path / "urls.txt"
    listing.write_text("# docs\nhttps://docs.example/guide\n\nhttps://shut.example/\n")
    code = cli.main(["pages", "https://news.example/a", "--file", str(listing), "--url", ":memory:"])
    out = capsys.readouterr()
    assert code == 0
    assert script.calls[0][2]["urls"] == ["https://news.example/a", "https://docs.example/guide", "https://shut.example/"]
    assert "Loaded 2 page(s)" in out.out and "into specstream_pages" in out.out
    assert "Not loaded (blocked): https://shut.example/ - The site refused us." in out.err
    assert cli.main(["pages", "--url", ":memory:"]) == 1
    with pytest.raises(SpecStreamError):
        SpecStreamAPI("")
