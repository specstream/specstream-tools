"""Writes SpecStream lists and their records into two ClickHouse tables.

Both tables are ReplacingMergeTree keyed on the list (and record), so loading a list again replaces its
rows instead of doubling them. Query with FINAL, or argMax on loaded_at, for the newest copy before merges.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from specstream_clickhouse.api import SpecStreamAPI, shape_record

LISTS_TABLE = "specstream_lists"
RECORDS_TABLE = "specstream_records"

LIST_COLUMNS = ["id", "name", "kind", "imported", "project_id", "created_at", "row_count", "link", "loaded_at"]
RECORD_COLUMNS = ["list_id", "list_created_at", "record_id", "entity_id", "fields", "cells", "loaded_at"]

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class ClickHouseClient(Protocol):
    """The part of clickhouse_connect's client this module uses."""

    def command(self, cmd: str, parameters: Any = None) -> Any: ...

    def query(self, query: str, parameters: Any = None) -> Any: ...

    def insert(self, table: str, data: Any, column_names: Any = "*", database: str | None = None) -> Any: ...


def ddl(database: str) -> list[str]:
    if not _IDENTIFIER.match(database):
        raise ValueError(f"Database name {database!r} must be letters, digits and underscores.")
    return [
        f"CREATE DATABASE IF NOT EXISTS {database}",
        f"""CREATE TABLE IF NOT EXISTS {database}.{LISTS_TABLE} (
    id String,
    name String,
    kind LowCardinality(String),
    imported Bool,
    project_id Nullable(String),
    created_at DateTime64(3, 'UTC'),
    row_count UInt64,
    link String,
    loaded_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(loaded_at)
ORDER BY id""",
        f"""CREATE TABLE IF NOT EXISTS {database}.{RECORDS_TABLE} (
    list_id String,
    list_created_at DateTime64(3, 'UTC'),
    record_id String,
    entity_id Nullable(String),
    fields Map(String, Nullable(String)),
    cells Array(Tuple(
        column_id String,
        label String,
        value Nullable(String),
        source_url Nullable(String),
        observed_at Nullable(DateTime64(3, 'UTC')))),
    loaded_at DateTime64(3, 'UTC')
) ENGINE = ReplacingMergeTree(loaded_at)
ORDER BY (list_id, record_id)""",
    ]


def ensure_tables(client: ClickHouseClient, database: str) -> None:
    for statement in ddl(database):
        client.command(statement)


def when(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def synced_through(client: ClickHouseClient, database: str) -> datetime | None:
    """The creation time of the newest list already loaded, or None for an empty table."""
    result = client.query(f"SELECT count(), max(created_at) FROM {database}.{LISTS_TABLE}")
    count, newest = result.result_rows[0]
    if not count:
        return None
    return newest if newest.tzinfo else newest.replace(tzinfo=timezone.utc)


@dataclass
class LoadResult:
    lists: int = 0
    records: int = 0
    list_ids: list[str] = field(default_factory=list)


def list_row(collection: dict[str, Any], loaded_at: datetime) -> list[Any]:
    return [
        collection["id"],
        collection.get("name") or "",
        collection.get("kind") or "",
        bool(collection.get("imported")),
        collection.get("project_id"),
        when(collection.get("created_at")) or EPOCH,
        int(collection.get("row_count", collection.get("total")) or 0),
        f"https://specstream.ai/workspace/collections/{collection['id']}",
        loaded_at,
    ]


def record_rows(collection: dict[str, Any], loaded_at: datetime) -> list[list[Any]]:
    created = when(collection.get("created_at")) or EPOCH
    rows = []
    for raw in collection.get("rows") or []:
        record = shape_record(raw)
        cells = [
            (c["column_id"], c["label"], c["value"], c["source_url"], when(c["observed_at"]))
            for c in record["cells"]
        ]
        rows.append(
            [collection["id"], created, record["record_id"], record["entity_id"], record["fields"], cells, loaded_at]
        )
    return rows


def load(
    client: ClickHouseClient,
    api: SpecStreamAPI,
    database: str = "specstream",
    list_ids: list[str] | None = None,
    full: bool = False,
) -> LoadResult:
    """Load lists into ClickHouse.

    With `list_ids`, those lists are (re)loaded. Otherwise every list created after the newest one already
    loaded is read; `full` reads every list again.
    """
    ensure_tables(client, database)
    if list_ids:
        wanted = list(dict.fromkeys(list_ids))
    else:
        since = None if full else synced_through(client, database)
        wanted = []
        for summary in api.lists():
            created = when(summary.get("created_at"))
            if since and created and created <= since:
                break  # Newest first: the rest were loaded before.
            wanted.append(summary["id"])

    result = LoadResult()
    for list_id in wanted:
        collection = api.list(list_id)
        loaded_at = datetime.now(timezone.utc)
        records = record_rows(collection, loaded_at)
        if records:
            client.insert(RECORDS_TABLE, records, column_names=RECORD_COLUMNS, database=database)
        client.insert(LISTS_TABLE, [list_row(collection, loaded_at)], column_names=LIST_COLUMNS, database=database)
        result.lists += 1
        result.records += len(records)
        result.list_ids.append(list_id)
    return result
