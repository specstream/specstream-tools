"""Against a real ClickHouse server: set CLICKHOUSE_HOST (and CLICKHOUSE_PORT, CLICKHOUSE_USER,
CLICKHOUSE_PASSWORD, CLICKHOUSE_SECURE for Cloud). The SpecStream side stays scripted."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

from specstream_clickhouse.api import SpecStreamAPI
from specstream_clickhouse.cli import connect, parser
from specstream_clickhouse.load import load

from fixtures import ScriptedAPI

pytestmark = pytest.mark.skipif(not os.environ.get("CLICKHOUSE_HOST"), reason="needs CLICKHOUSE_HOST")


@pytest.fixture
def client_and_db():
    client = connect(parser().parse_args(["load"]))
    database = f"specstream_test_{uuid.uuid4().hex[:8]}"
    yield client, database
    client.command(f"DROP DATABASE IF EXISTS {database}")


def test_load_round_trips_types_and_reload_replaces(client_and_db):
    client, db = client_and_db
    first = load(client, SpecStreamAPI("k", fetch=ScriptedAPI()), database=db)
    assert (first.lists, first.records) == (2, 3)

    rows = client.query(
        f"SELECT fields['Name'], fields['Phone'], cells[1].source_url, cells[1].observed_at, entity_id "
        f"FROM {db}.specstream_records FINAL WHERE list_id = 'col_new' ORDER BY record_id"
    ).result_rows
    assert rows[0][:3] == ("Acme Inc", None, "https://acme.example/")
    assert rows[0][3].replace(tzinfo=timezone.utc) == datetime(2026, 11, 10, 8, 59, tzinfo=timezone.utc)
    assert rows[1][4] == "ent_2"

    # Nothing new: a second run loads nothing. A named reload replaces, not doubles.
    assert load(client, SpecStreamAPI("k", fetch=ScriptedAPI()), database=db).lists == 0
    load(client, SpecStreamAPI("k", fetch=ScriptedAPI()), database=db, list_ids=["col_new"])
    count = client.query(f"SELECT count() FROM {db}.specstream_records FINAL").result_rows[0][0]
    assert count == 3

    joined = client.query(
        f"SELECT l.name, count() FROM {db}.specstream_records AS r FINAL "
        f"INNER JOIN {db}.specstream_lists AS l FINAL ON l.id = r.list_id GROUP BY l.name ORDER BY l.name"
    ).result_rows
    assert joined == [("Companies", 2), ("My import", 1)]
