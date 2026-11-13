from __future__ import annotations

from datetime import datetime, timezone

import pytest

from specstream_clickhouse.api import SpecStreamAPI, SpecStreamError, shape_record
from specstream_clickhouse.load import LISTS_TABLE, RECORDS_TABLE, ddl, load

from fixtures import NEW, OLD, ScriptedAPI


class FakeResult:
    def __init__(self, rows):
        self.result_rows = rows


class FakeClient:
    def __init__(self, newest: datetime | None = None) -> None:
        self.commands: list[str] = []
        self.inserts: list[tuple[str, list, list, str]] = []
        self.newest = newest

    def command(self, cmd, parameters=None):
        self.commands.append(cmd)

    def query(self, query, parameters=None):
        if self.newest is None:
            return FakeResult([(0, datetime(1970, 1, 1))])
        return FakeResult([(1, self.newest.replace(tzinfo=None))])

    def insert(self, table, data, column_names="*", database=None):
        self.inserts.append((table, data, column_names, database))

    def rows(self, table):
        return [dict(zip(cols, row)) for t, data, cols, _ in self.inserts if t == table for row in data]


def test_found_row_keeps_values_sources_and_leaves_out_buttons():
    record = shape_record(NEW["rows"][0])
    assert record["record_id"] == "0"
    assert record["entity_id"] == "ent_1"
    assert record["fields"] == {"Name": "Acme Inc", "Rating": "4.7", "Phone": None}
    assert record["cells"][0]["source_url"] == "https://acme.example/"


def test_entity_id_comes_from_sources_and_imported_rows_keep_their_columns():
    assert shape_record(NEW["rows"][1])["entity_id"] == "ent_2"
    imported = shape_record(OLD["rows"][0])
    assert imported["record_id"] == "r1"
    assert imported["fields"] == {"Company": "Zed Co", "Employees": "12", "Notes": None}


def test_first_load_reads_every_list_over_pages_and_writes_both_tables():
    api = ScriptedAPI()
    client = FakeClient()
    result = load(client, SpecStreamAPI("sk_test", "https://api.test", fetch=api), database="web")

    assert (result.lists, result.records, result.list_ids) == (2, 3, ["col_new", "col_old"])
    assert any("CREATE TABLE IF NOT EXISTS web.specstream_records" in c for c in client.commands)
    lists = client.rows(LISTS_TABLE)
    assert [row["id"] for row in lists] == ["col_new", "col_old"]
    assert lists[0]["row_count"] == 2 and lists[1]["imported"] is True
    assert lists[0]["created_at"] == datetime(2026, 11, 10, 9, tzinfo=timezone.utc)
    records = client.rows(RECORDS_TABLE)
    acme = records[0]
    assert acme["list_id"] == "col_new" and acme["fields"]["Name"] == "Acme Inc"
    assert acme["cells"][0] == (
        "name", "Name", "Acme Inc", "https://acme.example/", datetime(2026, 11, 10, 8, 59, tzinfo=timezone.utc)
    )
    assert all(db == "web" for *_, db in client.inserts)


def test_later_load_reads_only_lists_newer_than_the_newest_loaded():
    api = ScriptedAPI()
    client = FakeClient(newest=datetime(2026, 11, 5, tzinfo=timezone.utc))
    result = load(client, SpecStreamAPI("sk_test", "https://api.test", fetch=api))
    assert result.list_ids == ["col_new"]
    # The older list's records were never read.
    assert not any(url.endswith("/col_old") for url, _ in api.calls)


def test_named_lists_and_full_reload_ignore_the_watermark():
    client = FakeClient(newest=datetime(2026, 12, 1, tzinfo=timezone.utc))
    named = load(client, SpecStreamAPI("k", fetch=ScriptedAPI()), list_ids=["col_old", "col_old"])
    assert named.list_ids == ["col_old"]
    full = load(client, SpecStreamAPI("k", fetch=ScriptedAPI()), full=True)
    assert full.list_ids == ["col_new", "col_old"]


def test_calls_are_read_only_and_identify_the_integration():
    api = ScriptedAPI()
    load(FakeClient(), SpecStreamAPI("sk_test", fetch=api))
    for url, headers in api.calls:
        assert url.startswith("https://api.specstream.ai/v1/workspace/collections")
        assert headers["Authorization"] == "Bearer sk_test"
        assert headers["User-Agent"].startswith("specstream-clickhouse/")


def test_missing_key_and_bad_database_name_fail_readably():
    with pytest.raises(SpecStreamError):
        SpecStreamAPI("")
    with pytest.raises(ValueError):
        ddl("web; DROP TABLE x")
