# specstream-clickhouse

SpecStream: the live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. It runs through the API and MCP, and inside Sheets, CRMs, Slack, n8n, Zapier and the other tools teams already use.

This package loads your SpecStream Deep Search lists into ClickHouse, through the official Python client (`clickhouse-connect`). It only reads from SpecStream: it never starts a request or spends from your balance.

## Tables

`specstream` database (change it with `--database`):

| Table | One row per | Columns |
| --- | --- | --- |
| `specstream_lists` | list (found, imported, combined) | `id`, `name`, `kind`, `imported`, `project_id`, `created_at`, `row_count`, `link`, `loaded_at` |
| `specstream_records` | record of a list | `list_id`, `list_created_at`, `record_id`, `entity_id`, `fields Map(String, Nullable(String))`, `cells Array(Tuple(column_id, label, value, source_url, observed_at))`, `loaded_at` |

- Source per value: `cells` keeps each value with the page it was read from (`source_url`) and when (`observed_at`).
- A value SpecStream could not find is NULL.
- `entity_id` is the same for a company, place, person or posting in every list, so records join across lists.
- Both tables are `ReplacingMergeTree`. Loading a list again replaces its rows. Query with `FINAL` for the newest copy.

## Use

```bash
pip install specstream-clickhouse
export SPECSTREAM_API_KEY=...            # Agents & API at specstream.ai; a $0 spending limit is enough
export CLICKHOUSE_HOST=localhost         # self-hosted: HTTP port 8123
# ClickHouse Cloud: CLICKHOUSE_HOST=<service>.clickhouse.cloud CLICKHOUSE_SECURE=1 (port 8443)
export CLICKHOUSE_USER=default CLICKHOUSE_PASSWORD=...

specstream-clickhouse load               # every list created since the last load
specstream-clickhouse load --list <id>   # one list, again
specstream-clickhouse load --full        # every list again
```

```sql
SELECT fields['Name'] AS name, fields['Website'] AS website
FROM specstream.specstream_records FINAL
WHERE list_id = '<id>';
```

From Python:

```python
import clickhouse_connect
from specstream_clickhouse.api import SpecStreamAPI
from specstream_clickhouse.load import load

client = clickhouse_connect.get_client(host="localhost", client_name="specstream-clickhouse/0.1.0")
load(client, SpecStreamAPI(api_key="..."), database="specstream")
```

## Known limits

- Values are stored as strings in `fields`; cast in SQL (`toFloat64OrNull(fields['Rating'])`).
- A load reads lists newer than the newest one loaded. A list that was still running when loaded, or a list a SpecStream schedule changed, is read again with `--list <id>` or `--full`.
- Each list is read in one API response and written in one insert.

## Test

```bash
uv run --frozen pytest -q                                  # scripted SpecStream API, no network
CLICKHOUSE_HOST=localhost uv run --frozen pytest -q        # also against a real ClickHouse server
```

Questions: support@specstream.ai or the [API reference](https://specstream.ai/docs/api).
