"""The pages command: Extract API pages into an in-memory Pinecone index, with a scripted Extract API and a
scripted embedding. No network, no Pinecone key."""

from __future__ import annotations

import pytest

from extract_script import PAGES, ScriptedExtract, api, embed
from fake_pinecone import FakeClient, FakeIndex
from specstream_pinecone import cli
from specstream_pinecone.api import SpecStreamAPI
from specstream_pinecone.load import open_index, vector_id
from specstream_pinecone.pages import chunk_id, load_pages, split_text

GUIDE = "https://docs.example/guide"
NEWS = "https://news.example/a"


def chunks(index, namespace="__default__"):
    space = index.spaces.get(namespace, {}).values()
    return sorted((v["metadata"]["url"], v["metadata"]["chunk"]) for v in space if v["metadata"]["kind"] == "page")


def test_split_keeps_paragraphs_together_and_cuts_long_ones_with_overlap():
    assert split_text("a\n\nb\n\n\n\nc", size=10, overlap=0) == ["a\n\nb\n\nc"]
    assert split_text("aaaa\n\nbbbb", size=6, overlap=0) == ["aaaa", "bbbb"]
    long = "x" * 25
    parts = split_text(long, size=10, overlap=3)
    assert all(len(p) <= 10 for p in parts)
    assert "".join(p[3:] if i else p for i, p in enumerate(parts)) == long
    with pytest.raises(ValueError):
        split_text("x", size=10, overlap=10)


def test_pages_fill_the_index_one_vector_per_chunk_and_skip_pages_without_text():
    index = FakeIndex()
    result = load_pages(api(), embed, list(PAGES), index=index, namespace="web", chunk_chars=1000, overlap_chars=100)

    assert result.loaded == [GUIDE, NEWS] and result.pages == 2
    assert result.skipped == [("https://shut.example/", "blocked", "The site refused us.")]
    assert result.price_usd == pytest.approx(0.0016)
    guide = [c for c in chunks(index, "web") if c[0] == GUIDE]
    assert len(guide) == result.chunks - 1 >= 3
    meta = index.spaces["web"][chunk_id(GUIDE, 0)]["metadata"]
    assert meta["kind"] == "page" and meta["title"] == "Guide" and meta["published"] == "2026-10-01"
    assert meta["chunks"] == len(guide) and meta["text"].startswith("Paragraph 0:")
    assert "final_url" not in meta and "modified" not in meta
    assert index.spaces["web"][chunk_id(NEWS, 0)]["metadata"]["text"] == "Short news item."


def test_reading_a_page_again_replaces_its_chunks_and_leaves_lists_alone():
    index = FakeIndex()
    list_vector = vector_id("col_1", "r1")
    index.upsert(vectors=[{"id": list_vector, "values": [0.1] * 8, "metadata": {"kind": "list"}}],
                 namespace="__default__")
    load_pages(api(), embed, list(PAGES), index=index, chunk_chars=500, overlap_chars=50)
    assert len(chunks(index)) > 3
    shorter = dict(PAGES, **{GUIDE: dict(PAGES[GUIDE], text="Now one line.")})
    load_pages(api(ScriptedExtract(shorter)), embed, [GUIDE], index=index, chunk_chars=500, overlap_chars=50)
    space = index.spaces["__default__"]
    assert sorted(i for i in space if i.startswith("page:")) == sorted([chunk_id(GUIDE, 0), chunk_id(NEWS, 0)])
    assert space[chunk_id(GUIDE, 0)]["metadata"]["text"] == "Now one line."
    assert list_vector in space


def test_urls_go_twenty_to_a_call_once_each_and_bad_input_costs_nothing():
    script = ScriptedExtract()
    urls = [f"https://site.example/{n}" for n in range(45)] + ["https://site.example/0", " "]
    result = load_pages(api(script), embed, urls, index=FakeIndex())
    assert [len(body["urls"]) for _, _, body in script.calls] == [20, 20, 5]
    assert len(result.skipped) == 45 and result.pages == 0
    url, headers, body = script.calls[0]
    assert url == "https://api.test/v1/extract" and headers["Authorization"] == "Bearer sk_test"
    assert headers["User-Agent"].startswith("specstream-pinecone/") and body["format"] == "markdown"

    script = ScriptedExtract()
    for kwargs in ({"urls": ["  "], "index": FakeIndex()},
                   {"urls": [GUIDE], "index": FakeIndex(), "chunk_chars": 100, "overlap_chars": 100},
                   {"urls": [GUIDE]}):
        with pytest.raises(ValueError):
            load_pages(api(script), embed, **kwargs)
    assert script.calls == []


def test_an_embedding_of_another_size_is_refused_before_a_write():
    index = FakeIndex()
    with pytest.raises(ValueError, match="size 1024"):
        load_pages(api(), embed, [GUIDE], index=index, dimension=1024)
    assert index.spaces == {}


def test_cli_pages_reads_a_url_file_into_the_index_lists_use(tmp_path, monkeypatch, capsys):
    script = ScriptedExtract()
    pc = FakeClient(dim=8)
    monkeypatch.setenv("SPECSTREAM_API_KEY", "sk_test")
    monkeypatch.setattr(cli, "connect", lambda args: pc)
    monkeypatch.setattr(cli, "SpecStreamAPI", lambda key, url: SpecStreamAPI(key, "https://api.test", fetch=script))
    listing = tmp_path / "urls.txt"
    listing.write_text(f"# docs\n{GUIDE}\n\nhttps://shut.example/\n")

    assert cli.main(["pages", NEWS, "--file", str(listing), "--dimension", "8"]) == 0
    out = capsys.readouterr()
    assert script.calls[0][2]["urls"] == [NEWS, GUIDE, "https://shut.example/"]
    assert "Loaded 2 page(s)" in out.out and "into specstream;" in out.out
    assert "Not loaded (blocked): https://shut.example/ - The site refused us." in out.err
    assert pc.created[0]["name"] == "specstream" and pc.created[0]["dimension"] == 8
    assert {e["parameters"]["input_type"] for e in pc.embedded} == {"passage"}
    index = open_index(pc, "specstream", 8)
    assert chunks(index)[0][0] == GUIDE
    assert cli.main(["pages"]) == 1
    assert "Give one or more URLs" in capsys.readouterr().err
