"""Load and reload end to end through Qdrant's client: always in local (in-memory) mode, and also against a
real server when QDRANT_URL is set, for example a local `docker run -p 6333:6333 qdrant/qdrant`."""

from __future__ import annotations

import os
import uuid

import pytest
from qdrant_client import QdrantClient

from specstream_qdrant.api import SpecStreamAPI
from specstream_qdrant.load import load

from fixtures import ScriptedAPI
from test_load import embed

URL = os.environ.get("QDRANT_URL")


@pytest.fixture(
    params=[
        "local",
        pytest.param("server", marks=pytest.mark.skipif(not URL, reason="QDRANT_URL is not set")),
    ]
)
def client(request):
    if request.param == "local":
        qdrant = QdrantClient(":memory:")
    else:
        qdrant = QdrantClient(url=URL, api_key=os.environ.get("QDRANT_API_KEY") or None)
    yield request.param, qdrant
    qdrant.close()


def test_load_and_reload_end_to_end(client):
    mode, client = client
    name = f"specstream_test_{uuid.uuid4().hex[:8]}"
    try:
        api = SpecStreamAPI("sk_test", "https://api.test", fetch=ScriptedAPI())
        assert load(client, api, embed, collection=name).records == 3
        assert load(client, api, embed, collection=name).list_ids == []
        assert load(client, api, embed, collection=name, full=True).list_ids == ["col_new", "col_old"]
        assert client.count(name, exact=True).count == 3
        if mode == "server":
            # Local mode keeps no payload indexes; a server must have both.
            indexed = client.get_collection(name).payload_schema
            assert {"list_id", "entity_id"} <= set(indexed)
    finally:
        client.delete_collection(name)
