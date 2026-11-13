"""The public-records feed against an in-memory Pinecone index, with a scripted licence delivery and a
scripted feed. No network, no Pinecone key, no licence."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import urllib.error
from datetime import date

import pytest

from specstream_pinecone import cli
from specstream_pinecone.api import SpecStreamError
from specstream_pinecone.records import (
    STATE_NAMESPACE,
    RecordFiles,
    feed_slug,
    item_id,
    read_state,
    record_id,
    sync_feed,
    sync_records,
)

from fake_pinecone import FakeClient, FakeIndex

DIM = 8
NS = "__default__"
TOKEN = "t" * 43
LINK = f"https://specstream.ai/data/files/{TOKEN}"
HEADER = ["Company", "State", "Amount", "Source"]
ACME = ["Acme Inc", "CA", "5000000", "https://sec.test/acme"]
BOLT = ["Bolt LLC", "NY", "", "https://sec.test/bolt"]
CORE = ["Core Corp", "TX", "7000000", "https://sec.test/core"]
DUNE = ["Dune Co", "WA", "9000000", "https://sec.test/dune"]
TODAY = date(2026, 11, 12)


def embed(texts):
    return [[b / 255 + 0.01 for b in hashlib.sha256(t.encode()).digest()[:DIM]] for t in texts]


def gz(header, rows):
    text = io.StringIO()
    csv.writer(text).writerows([header, *rows])
    return gzip.compress(text.getvalue().encode())


class Delivery:
    """A licence's link: index.json, the whole file, day files and the public dictionary of one family."""

    def __init__(self, whole, built="2026-11-10T08:30:00Z", new=None, removed=None, key="Source", family="formd"):
        self.family, self.key, self.built = family, key, built
        self.whole, self.new, self.removed = whole, new or {}, removed or {}
        self.opened: list[str] = []

    def _days(self, kind, held):
        return [{"date": d, "rows": len(r), "url": f"{LINK}/{self.family}/{kind}/{d}.csv.gz"}
                for d, r in sorted(held.items(), reverse=True)]

    def __call__(self, url, headers):
        assert headers["User-Agent"].startswith("specstream-pinecone/")
        self.opened.append(url.replace(TOKEN, "TOKEN"))
        f = self.family
        if url == f"https://specstream.ai/data/licence/{f}/dictionary.json":
            return io.BytesIO(json.dumps({"family": f, "key": self.key}).encode())
        if url == f"{LINK}/index.json":
            return io.BytesIO(json.dumps({"licence": {"id": "lic_1"}, "families": [{
                "family": f, "title": "Form D filings", "hub": "https://specstream.ai/data/form-d",
                "rows": len(self.whole), "built": self.built, "columns": HEADER, "url": f"{LINK}/{f}.csv.gz",
                "new": self._days("new", self.new), "removed": self._days("removed", self.removed)}]}).encode())
        if url == f"{LINK}/{f}.csv.gz":
            return io.BytesIO(gz(HEADER, self.whole))
        for kind, held in (("new", self.new), ("removed", self.removed)):
            for day, rows in held.items():
                if url == f"{LINK}/{f}/{kind}/{day}.csv.gz":
                    return io.BytesIO(gz(HEADER if kind == "new" else ["Source", "Company", "Reason"], rows))
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)


def run(index, delivery, **kw):
    return sync_records(index, RecordFiles(LINK, delivery), embed, DIM, today=TODAY, **kw)


def ids(index, namespace=NS):
    return set(index.spaces.get(namespace, {}))


def rid(row):
    return record_id("formd", row[3])


def test_first_run_loads_the_whole_file_one_vector_per_record():
    index = FakeIndex()
    [result] = run(index, Delivery([ACME, BOLT]))
    assert (result.mode, result.written, result.deleted, result.through) == ("whole", 2, 0, "2026-11-10")
    assert ids(index) == {rid(ACME), rid(BOLT)}
    meta = index.spaces[NS][rid(BOLT)]["metadata"]
    assert meta["family"] == "formd" and meta["family_title"] == "Form D filings"
    assert meta["name"] == "Bolt LLC" and meta["key"] == "https://sec.test/bolt"
    assert meta["source_urls"] == ["https://sec.test/bolt"]
    assert meta["link"] == "https://specstream.ai/data/form-d"
    assert json.loads(meta["fields"]) == {"Company": "Bolt LLC", "State": "NY", "Source": "https://sec.test/bolt"}
    assert meta["text"] == "Records: Form D filings\nCompany: Bolt LLC\nState: NY"
    assert read_state(index, "formd")["through"] == "2026-11-10"


def test_a_later_run_applies_only_the_days_after_the_marker_removals_first():
    index = FakeIndex()
    delivery = Delivery([ACME, BOLT])
    run(index, delivery)
    delivery.new = {"2026-11-10": [BOLT], "2026-11-11": [CORE], "2026-11-12": [DUNE]}
    delivery.removed = {"2026-11-11": [[ACME[3], "Acme Inc", "left the file"]],
                        "2026-11-12": [[BOLT[3], "Bolt LLC", "value removed"]]}
    delivery.opened.clear()
    [result] = run(index, delivery)
    assert (result.mode, result.days, result.written, result.deleted) == ("days", ["2026-11-11", "2026-11-12"], 2, 2)
    assert ids(index) == {rid(CORE), rid(DUNE)}
    assert not any(u.endswith("/formd.csv.gz") or "2026-11-10" in u for u in delivery.opened)
    assert read_state(index, "formd")["through"] == "2026-11-12"

    before = len(index.calls)
    [again] = run(index, delivery)
    assert (again.mode, again.written, again.deleted) == ("current", 0, 0)
    assert len(index.calls) == before  # nothing new: nothing embedded, written or deleted


def test_full_loads_the_whole_file_again_and_deletes_what_left_it():
    index = FakeIndex()
    run(index, Delivery([ACME, BOLT]))
    [result] = run(index, Delivery([ACME, CORE], built="2026-11-12T08:30:00Z"), full=True)
    assert (result.mode, result.written, result.deleted, result.through) == ("whole", 2, 1, "2026-11-12")
    assert ids(index) == {rid(ACME), rid(CORE)}


def test_a_marker_older_than_the_days_the_delivery_keeps_loads_the_whole_file():
    index = FakeIndex()
    run(index, Delivery([ACME], built="2026-09-01T08:30:00Z"))
    [result] = run(index, Delivery([ACME, DUNE], built="2026-11-12T08:30:00Z", new={"2026-11-12": [DUNE]}))
    assert result.mode == "whole" and ids(index) == {rid(ACME), rid(DUNE)}


def test_a_family_with_no_key_column_is_loaded_whole_once_per_build():
    index = FakeIndex()
    delivery = Delivery([ACME, ACME, BOLT], key=None)
    [first] = run(index, delivery)
    assert first.mode == "whole" and len(ids(index)) == 3  # the repeated row keeps a vector of its own
    assert run(index, delivery)[0].mode == "current"
    delivery.whole, delivery.built = [ACME, BOLT], "2026-11-12T08:30:00Z"
    [third] = run(index, delivery)
    assert (third.mode, third.deleted) == ("whole", 1) and len(ids(index)) == 2


def test_the_marker_is_kept_apart_from_the_records_and_per_namespace():
    index = FakeIndex()
    run(index, Delivery([ACME]), namespace="a")
    assert ids(index, "a") == {rid(ACME)}
    assert ids(index, STATE_NAMESPACE) == {"records:formd@a"}
    assert read_state(index, "formd", "b") is None
    assert run(index, Delivery([ACME]), namespace="b")[0].mode == "whole"


def test_big_files_go_in_batches_of_96():
    index = FakeIndex()
    rows = [[f"Co {i}", "CA", "1", f"https://sec.test/{i}"] for i in range(200)]
    assert run(index, Delivery(rows))[0].written == 200
    assert [c[1]["count"] for c in index.calls if c[0] == "upsert" and c[1]["namespace"] == NS] == [96, 96, 8]


def test_a_family_the_licence_does_not_hold_is_named():
    with pytest.raises(SpecStreamError, match="does not hold osha. It holds: formd"):
        run(FakeIndex(), Delivery([ACME]), families=["osha"])


def test_the_licence_link_is_checked_and_never_shown():
    with pytest.raises(SpecStreamError, match="SPECSTREAM_RECORDS_LINK"):
        RecordFiles("https://specstream.ai/data/files/short")

    def gone(url, headers):
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    with pytest.raises(SpecStreamError) as caught:
        RecordFiles(LINK + "/index.json", gone).index()
    assert TOKEN not in str(caught.value) and "<licence>/index.json" in str(caught.value)


def test_an_embedding_of_another_size_is_refused_before_writing():
    index = FakeIndex()
    with pytest.raises(ValueError, match="vectors of size 4"):
        sync_records(index, RecordFiles(LINK, Delivery([ACME])), embed, 4, today=TODAY)
    assert ids(index) == set() and ids(index, STATE_NAMESPACE) == set()


FEED_URL = "https://specstream.ai/feeds/us-funding-rounds.json"


def feed(*items):
    body = {"version": "https://jsonfeed.org/version/1.1", "title": "US funding rounds", "items": list(items)}
    return lambda url, headers: io.BytesIO(json.dumps(body).encode())


def entry(n):
    return {"id": f"https://sec.test/{n}", "url": f"https://sec.test/{n}", "title": f"Co {n} raised $5M",
            "content_text": f"Co {n} filed a Form D.", "date_published": "2026-11-06T12:00:00+00:00", "tags": ["Health"]}


def test_a_public_feed_is_loaded_and_a_later_run_writes_only_new_items():
    index = FakeIndex()
    first = sync_feed(index, embed, DIM, FEED_URL, open_url=feed(entry(1), entry(2)))
    assert (first.items, first.written) == (2, 2)
    vid = item_id("us-funding-rounds", "https://sec.test/1")
    meta = index.spaces[NS][vid]["metadata"]
    assert meta["kind"] == "feed_item" and meta["feed"] == "us-funding-rounds" and meta["tags"] == ["Health"]
    assert meta["text"] == "Co 1 raised $5M\nCo 1 filed a Form D." and meta["link"] == "https://sec.test/1"

    second = sync_feed(index, embed, DIM, FEED_URL, open_url=feed(entry(1), entry(2), entry(3)))
    assert (second.items, second.written) == (3, 1) and len(ids(index)) == 3
    hit = index.query(top_k=1, vector=embed(["Co 3 raised $5M\nCo 3 filed a Form D."])[0], namespace=NS,
                      filter={"feed": {"$eq": "us-funding-rounds"}}, include_metadata=True).matches[0]
    assert hit.metadata["name"] == "Co 3 raised $5M"


def test_a_page_that_is_not_a_feed_is_refused():
    assert feed_slug("https://specstream.ai/feeds/US-Funding.json?x=1") == "us-funding"
    with pytest.raises(SpecStreamError, match="not a JSON Feed"):
        sync_feed(FakeIndex(), embed, DIM, FEED_URL, open_url=lambda u, h: io.BytesIO(b"<html>"))
    with pytest.raises(SpecStreamError, match="http"):
        sync_feed(FakeIndex(), embed, DIM, "file:///etc/passwd")


def test_cli_records_feed_goes_through_the_pinecone_client(monkeypatch, capsys):
    pc = FakeClient(dim=DIM)
    monkeypatch.setattr(cli, "connect", lambda args: pc)
    monkeypatch.setattr(cli, "sync_feed", lambda index, emb, dim, url, ns: sync_feed(
        index, emb, dim, url, ns, open_url=feed(entry(1))))
    assert cli.main(["records", "--feed", "--dimension", str(DIM)]) == 0
    assert "1 item(s), 1 new in specstream" in capsys.readouterr().out
    assert pc.created[0]["dimension"] == DIM


def test_cli_records_without_a_link_says_how_to_get_one(monkeypatch, capsys):
    monkeypatch.delenv("SPECSTREAM_RECORDS_LINK", raising=False)
    assert cli.main(["records"]) == 1
    err = capsys.readouterr().err
    assert "SPECSTREAM_RECORDS_LINK" in err and "https://specstream.ai/data/licence" in err and "--feed" in err
