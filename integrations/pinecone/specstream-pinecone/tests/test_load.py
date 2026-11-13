"""The loader against an in-memory Pinecone index, with a scripted SpecStream API and a scripted embedding.
No network, no Pinecone key."""

from __future__ import annotations

import hashlib
import inspect
import json

import pytest
from pinecone import Pinecone
from pinecone.db_data import Index

from specstream_pinecone import cli
from specstream_pinecone.api import SpecStreamAPI, SpecStreamError, shape_record
from specstream_pinecone.load import (
    BATCH,
    is_loaded,
    load,
    open_index,
    pinecone_embed,
    record_text,
    stored_ids,
    vector_id,
)

from fake_pinecone import FakeClient, FakeIndex
from fixtures import NEW, OLD, ScriptedAPI

DIM = 8
NS = "__default__"


def embed(texts):
    """Same text, same vector: a hash spread over DIM floats."""
    return [[b / 255 + 0.01 for b in hashlib.sha256(t.encode()).digest()[:DIM]] for t in texts]


def api(script=None):
    return SpecStreamAPI("sk_test", "https://api.test", fetch=script or ScriptedAPI())


def stored(index, namespace=NS):
    return index.spaces.get(namespace, {})


def test_found_row_keeps_values_sources_and_leaves_out_buttons():
    record = shape_record(NEW["rows"][0])
    assert record["fields"] == {"Name": "Acme Inc", "Rating": "4.7", "Phone": None}
    assert record_text("Companies", record) == "List: Companies\nName: Acme Inc\nRating: 4.7"


def test_first_load_writes_one_vector_per_record_with_flat_metadata():
    index = FakeIndex()
    result = load(index, api(), embed)

    assert (result.lists, result.records, result.list_ids) == (2, 3, ["col_new", "col_old"])
    got = stored(index)
    assert sorted(got) == ["col_new#0", "col_new#1", "col_old#r1"]
    acme = got[vector_id("col_new", "0")]["metadata"]
    assert json.loads(acme["fields"]) == {"Name": "Acme Inc", "Rating": "4.7", "Phone": None}
    assert json.loads(acme["sources"]) == {"Name": "https://acme.example/", "Rating": "https://maps.example/acme"}
    assert acme["source_urls"] == ["https://acme.example/", "https://maps.example/acme"]
    assert acme["entity_id"] == "ent_1"
    assert acme["list_name"] == "Companies"
    assert acme["link"] == "https://specstream.ai/workspace/collections/col_new"
    assert acme["text"].startswith("List: Companies\nName: Acme Inc")
    assert len(got["col_new#0"]["values"]) == DIM
    # No nulls reach Pinecone: a record without an entity has no entity_id key.
    assert "entity_id" not in got["col_old#r1"]["metadata"]
    assert json.loads(got["col_old#r1"]["metadata"]["fields"]) == {"Company": "Zed Co", "Employees": "12", "Notes": None}


def test_query_finds_a_record_by_its_vector_and_filters_by_list():
    index = FakeIndex()
    load(index, api(), embed)
    acme_text = stored(index)["col_new#0"]["metadata"]["text"]
    hits = index.query(top_k=5, vector=embed([acme_text])[0], namespace=NS,
                       filter={"list_id": {"$eq": "col_new"}}, include_metadata=True).matches
    assert hits[0].id == "col_new#0"
    assert {h.metadata["list_id"] for h in hits} == {"col_new"}


def test_later_load_reads_only_lists_not_yet_in_the_namespace():
    index = FakeIndex()
    load(index, api(), embed, list_ids=["col_old"])
    assert is_loaded(index, "col_old") and not is_loaded(index, "col_new")
    script = ScriptedAPI()
    assert load(index, api(script), embed).list_ids == ["col_new"]
    assert not any(url.endswith("/col_old") for url, _ in script.calls)
    assert load(index, api(), embed).list_ids == []


def test_loading_a_list_again_replaces_its_vectors_and_writes_before_deleting():
    index = FakeIndex()
    load(index, api(), embed)
    index.calls.clear()
    smaller = dict(NEW, rows=NEW["rows"][:1])
    result = load(index, api(ScriptedAPI(lists=(smaller, OLD))), embed, list_ids=["col_new", "col_new"])
    assert result.list_ids == ["col_new"]
    assert sorted(stored(index)) == ["col_new#0", "col_old#r1"]
    assert [name for name, _ in index.calls] == ["upsert", "delete"]
    assert index.calls[1][1]["ids"] == ["col_new#1"]
    assert load(index, api(), embed, full=True).list_ids == ["col_new", "col_old"]
    assert len(stored(index)) == 3


def test_namespaces_are_kept_apart():
    index = FakeIndex()
    load(index, api(), embed, namespace="sales")
    assert sorted(stored(index, "sales")) == ["col_new#0", "col_new#1", "col_old#r1"]
    assert stored(index) == {}
    assert load(index, api(), embed).list_ids == ["col_new", "col_old"]


def test_big_lists_go_in_batches_and_ids_are_listed_over_pages():
    rows = [{"ordinal": i, "cells": [{"column_id": "name", "label": "Name", "value": f"Co {i}"}]} for i in range(200)]
    big = dict(NEW, id="col big/é", rows=rows)
    index = FakeIndex(page_size=7)
    load(index, api(ScriptedAPI(lists=(big,))), embed)
    assert [c["count"] for name, c in index.calls if name == "upsert"] == [BATCH, BATCH, 200 - 2 * BATCH]
    ids = stored_ids(index, "col big/é")
    assert len(ids) == 200 and all(i.isascii() and i.count("#") == 1 for i in ids)


def test_an_embedding_of_another_size_is_refused_before_writing():
    index = FakeIndex()
    with pytest.raises(ValueError, match="size 8"):
        load(index, api(), lambda texts: [[0.5] * 4 for _ in texts], dimension=DIM)
    assert stored(index) == {}
    with pytest.raises(ValueError, match="2 vectors for 1"):
        load(index, api(), lambda texts: [[0.5] * 4, [0.5] * 4], list_ids=["col_old"])


def test_open_index_makes_a_serverless_index_once_and_checks_its_size():
    pc = FakeClient()
    index = open_index(pc, "web", DIM, cloud="gcp", region="europe-west4")
    created = pc.created[0]
    assert (created["name"], created["dimension"], created["metric"]) == ("web", DIM, "cosine")
    assert (created["spec"].cloud, created["spec"].region) == ("gcp", "europe-west4")
    assert open_index(pc, "web", DIM) is index and len(pc.created) == 1
    with pytest.raises(ValueError, match="size 8"):
        open_index(pc, "web", 1024)


def test_pinecone_embed_uses_the_hosted_model_as_passages():
    pc = FakeClient()
    vectors = pinecone_embed(pc, "llama-text-embed-v2")(["a", "bb"])
    assert len(vectors) == 2 and len(vectors[0]) == DIM
    assert pc.embedded == [{"model": "llama-text-embed-v2", "inputs": ["a", "bb"],
                            "parameters": {"input_type": "passage", "truncate": "END"}}]


def test_cli_loads_through_the_pinecone_client(monkeypatch, capsys):
    pc = FakeClient()
    monkeypatch.setattr(cli, "connect", lambda args: pc)
    monkeypatch.setattr(cli, "SpecStreamAPI", lambda key, url: api())
    monkeypatch.setenv("SPECSTREAM_API_KEY", "sk_test")
    assert cli.main(["load", "--index", "web", "--dimension", str(DIM)]) == 0
    assert "Loaded 2 list(s) and 3 record(s) into web." in capsys.readouterr().out
    assert len(pc.indexes["web"].store.spaces[NS]) == 3


def test_cli_without_a_pinecone_key_says_so(monkeypatch, capsys):
    monkeypatch.setenv("SPECSTREAM_API_KEY", "sk_test")
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    assert cli.main(["load"]) == 1
    assert "PINECONE_API_KEY" in capsys.readouterr().err


def test_the_fake_matches_the_pinecone_client_signatures():
    """Every keyword the loader passes exists on the real `pinecone` Index and client."""
    for method, keywords in {
        "upsert": {"vectors", "namespace"},
        "list": {"prefix", "namespace"},
        "list_paginated": {"prefix", "limit", "namespace"},
        "delete": {"ids", "namespace"},
        "query": {"top_k", "vector", "namespace", "filter", "include_metadata"},
    }.items():
        assert keywords <= set(inspect.signature(getattr(Index, method)).parameters), method
    assert {"name", "dimension", "metric", "spec"} <= set(inspect.signature(Pinecone.create_index).parameters)
    assert {"host", "source_tag"} <= set(inspect.signature(Pinecone.__init__).parameters)
    assert "host" in inspect.signature(Pinecone.Index).parameters


def test_calls_are_read_only_and_identify_the_integration():
    script = ScriptedAPI()
    load(FakeIndex(), SpecStreamAPI("sk_test", fetch=script), embed)
    for url, headers in script.calls:
        assert url.startswith("https://api.specstream.ai/v1/workspace/collections")
        assert headers["Authorization"] == "Bearer sk_test"
        assert headers["User-Agent"].startswith("specstream-pinecone/")
    with pytest.raises(SpecStreamError):
        SpecStreamAPI("")
