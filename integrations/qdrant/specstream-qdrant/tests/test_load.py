"""The loader against Qdrant's own client in local (in-memory) mode, with a scripted SpecStream API and a
scripted embedding. No network and no model download."""

from __future__ import annotations

import hashlib

import pytest
from qdrant_client import QdrantClient, models

from specstream_qdrant.api import SpecStreamAPI, SpecStreamError, shape_record
from specstream_qdrant.load import load, point_id, record_text

from fixtures import NEW, OLD, ScriptedAPI

DIM = 8


def embed(texts):
    """Same text, same vector: a hash spread over DIM floats."""
    out = []
    for text in texts:
        digest = hashlib.sha256(text.encode()).digest()
        out.append([b / 255 + 0.01 for b in digest[:DIM]])
    return out


def api(script=None):
    return SpecStreamAPI("sk_test", "https://api.test", fetch=script or ScriptedAPI())


def points(client, collection="specstream"):
    found, _ = client.scroll(collection, limit=100, with_payload=True, with_vectors=True)
    return {p.payload["record_id"] + "@" + p.payload["list_id"]: p for p in found}


def test_found_row_keeps_values_sources_and_leaves_out_buttons():
    record = shape_record(NEW["rows"][0])
    assert record["fields"] == {"Name": "Acme Inc", "Rating": "4.7", "Phone": None}
    assert record_text("Companies", record) == "List: Companies\nName: Acme Inc\nRating: 4.7"


def test_first_load_fills_the_collection_with_one_point_per_record():
    client = QdrantClient(":memory:")
    result = load(client, api(), embed, collection="web")

    assert (result.lists, result.records, result.list_ids) == (2, 3, ["col_new", "col_old"])
    info = client.get_collection("web")
    assert info.config.params.vectors.size == DIM
    assert info.config.params.vectors.distance == models.Distance.COSINE
    got = points(client, "web")
    acme = got["0@col_new"]
    assert acme.id == point_id("col_new", "0")
    assert acme.payload["fields"]["Name"] == "Acme Inc"
    assert acme.payload["sources"] == {"Name": "https://acme.example/", "Rating": "https://maps.example/acme"}
    assert acme.payload["entity_id"] == "ent_1"
    assert acme.payload["link"] == "https://specstream.ai/workspace/collections/col_new"
    assert acme.payload["text"].startswith("List: Companies\nName: Acme Inc")
    assert got["r1@col_old"].payload["fields"] == {"Company": "Zed Co", "Employees": "12", "Notes": None}


def test_search_finds_a_record_by_its_vector_and_filters_by_list():
    client = QdrantClient(":memory:")
    load(client, api(), embed)
    acme_text = points(client)["0@col_new"].payload["text"]
    hits = client.query_points(
        "specstream",
        query=embed([acme_text])[0],
        query_filter=models.Filter(must=[models.FieldCondition(key="list_id", match=models.MatchValue(value="col_new"))]),
        limit=5,
    ).points
    assert hits[0].payload["fields"]["Name"] == "Acme Inc"
    assert {h.payload["list_id"] for h in hits} == {"col_new"}


def test_later_load_reads_only_lists_not_yet_in_the_collection():
    client = QdrantClient(":memory:")
    load(client, api(), embed, list_ids=["col_old"])
    script = ScriptedAPI()
    result = load(client, api(script), embed)
    assert result.list_ids == ["col_new"]
    assert not any(url.endswith("/col_old") for url, _ in script.calls)
    # Nothing new: the newest list is already in.
    assert load(client, api(), embed).list_ids == []


def test_loading_a_list_again_replaces_its_points():
    client = QdrantClient(":memory:")
    load(client, api(), embed)
    smaller = dict(NEW, rows=NEW["rows"][:1])
    result = load(client, api(ScriptedAPI(lists=(smaller, OLD))), embed, list_ids=["col_new", "col_new"])
    assert result.list_ids == ["col_new"]
    assert sorted(points(client)) == ["0@col_new", "r1@col_old"]
    assert load(client, api(), embed, full=True).list_ids == ["col_new", "col_old"]
    assert client.count("specstream", exact=True).count == 3


def test_a_model_of_another_size_is_refused_readably():
    client = QdrantClient(":memory:")
    load(client, api(), embed)
    with pytest.raises(ValueError, match="size 8"):
        load(client, api(), lambda texts: [[0.5] * 4 for _ in texts], list_ids=["col_new"])


def test_calls_are_read_only_and_identify_the_integration():
    script = ScriptedAPI()
    load(QdrantClient(":memory:"), SpecStreamAPI("sk_test", fetch=script), embed)
    for url, headers in script.calls:
        assert url.startswith("https://api.specstream.ai/v1/workspace/collections")
        assert headers["Authorization"] == "Bearer sk_test"
        assert headers["User-Agent"].startswith("specstream-qdrant/")
    with pytest.raises(SpecStreamError):
        SpecStreamAPI("")
