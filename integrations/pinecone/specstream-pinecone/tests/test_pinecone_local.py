"""The loader end to end against a real Pinecone data plane: Pinecone Local (the `pinecone-local`
container), reached at PINECONE_HOST, e.g. http://localhost:5080. Skipped without it.

Pinecone Local speaks the 2025 control API, which `pinecone` 10 no longer reads, so the test index is
made and removed with plain HTTP; upsert, list, delete and query go through the `pinecone` client."""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.request
import uuid

import pytest

from specstream_pinecone.api import SpecStreamAPI
from specstream_pinecone.load import load, stored_ids

from fixtures import NEW, OLD, ScriptedAPI

HOST = os.environ.get("PINECONE_HOST")
pytestmark = pytest.mark.skipif(not HOST, reason="PINECONE_HOST is not set (Pinecone Local)")
DIM = 8
NS = "__default__"


def embed(texts):
    return [[b / 255 + 0.01 for b in hashlib.sha256(t.encode()).digest()[:DIM]] for t in texts]


def control(method, path, body=None):
    request = urllib.request.Request(
        f"{HOST.rstrip('/')}{path}", method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Content-Type": "application/json", "X-Pinecone-API-Version": "2025-01"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


def wait_for(check, seconds=20):
    end = time.time() + seconds
    while not check():
        assert time.time() < end, "Pinecone did not show the write in time"
        time.sleep(0.5)


def test_load_replace_and_query_on_a_real_pinecone_data_plane():
    from pinecone import Pinecone

    name = f"specstream-test-{uuid.uuid4().hex[:8]}"
    made = control("POST", "/indexes", {"name": name, "dimension": DIM, "metric": "cosine",
                                       "spec": {"serverless": {"cloud": "aws", "region": "us-east-1"}}})
    try:
        host = made["host"] if made["host"].startswith("http") else f"http://{made['host']}"
        index = Pinecone(api_key="pclocal", host=HOST, source_tag="specstream").Index(host=host)
        api = SpecStreamAPI("sk_test", "https://api.test", fetch=ScriptedAPI())
        assert load(index, api, embed, dimension=DIM).records == 3
        wait_for(lambda: len(stored_ids(index, "col_new")) == 2)
        assert stored_ids(index, "col_old") == {"col_old#r1"}

        hits = index.query(top_k=3, vector=embed(["List: Companies\nName: Acme Inc\nRating: 4.7"])[0],
                           filter={"list_id": {"$eq": "col_new"}}, include_metadata=True, namespace=NS).matches
        assert hits[0].id == "col_new#0"
        assert hits[0].metadata["entity_id"] == "ent_1"
        assert json.loads(hits[0].metadata["fields"])["Name"] == "Acme Inc"

        # The next load without --list finds every list in and reads nothing.
        assert load(index, SpecStreamAPI("sk_test", "https://api.test", fetch=ScriptedAPI()), embed).list_ids == []

        smaller = dict(NEW, rows=NEW["rows"][:1])
        load(index, SpecStreamAPI("sk_test", "https://api.test", fetch=ScriptedAPI(lists=(smaller, OLD))),
             embed, list_ids=["col_new"])
        wait_for(lambda: stored_ids(index, "col_new") == {"col_new#0"})
    finally:
        control("DELETE", f"/indexes/{name}")
