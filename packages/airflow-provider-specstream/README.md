# airflow-provider-specstream

[SpecStream](https://specstream.ai) is the live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. It runs through the API and MCP, and inside Sheets, CRMs, Slack, n8n, Zapier and the other tools teams already use.

Source URL and read time on every value.

This package is the SpecStream provider for Apache Airflow 2.9 and later, Airflow 3 included: a hook, a `specstream` connection type and three operators.

```bash
pip install airflow-provider-specstream
```

## Connection

Create a connection of type **SpecStream** named `specstream_default` and put your API key (Agents & API in your SpecStream workspace) in the **API key** field. Or set it in the environment:

```bash
export AIRFLOW_CONN_SPECSTREAM_DEFAULT='{"conn_type": "specstream", "password": "<your API key>"}'
```

A free account comes with $10 of credit and needs no card: [specstream.ai](https://specstream.ai/signup).

## Operators

| Operator | API | Price |
| --- | --- | --- |
| `SpecStreamSearchOperator` | Search API, `GET /v1/web-search` | $5 per 1,000 searches of up to 10 results; $1 per 1,000 with `speed="fast"` |
| `SpecStreamExtractOperator` | Extract API, `POST /v1/extract`, 1 to 20 URLs | $0.80 per 1,000 pages; a page with no text is free |
| `SpecStreamDeepSearchOperator` | Deep Search | 5 cents, 15 cents or $1 per delivered row |

Each operator returns the API's reply, which Airflow pushes to XCom.

```python
from specstream_provider.operators.specstream import (
    SpecStreamDeepSearchOperator,
    SpecStreamExtractOperator,
    SpecStreamSearchOperator,
)

search = SpecStreamSearchOperator(task_id="search", query="Apache Airflow latest release", speed="fast")
read = SpecStreamExtractOperator(task_id="read", urls="{{ ti.xcom_pull(task_ids='search')['sources'][0]['url'] }}")
deep = SpecStreamDeepSearchOperator(
    task_id="deep_search",
    request="Open-source workflow orchestrators with their website and license",
    max_results=25,
    max_price_usd=5,
    retries=2,
)
search >> read
```

`SpecStreamDeepSearchOperator` starts a run only when its quoted maximum is at or below `max_price_usd`; otherwise nothing runs and the task fails with the price. A retry of the same task instance continues the same list and never buys it twice. When the list is still running after `wait_seconds` (420 by default), the task fails so that its retry picks the list up; set `fail_if_unfinished=False` to return the rows found so far. The result holds `list_id`, `status`, `list_link`, `row_count` and `rows`; each row carries `source_url` and `checked_at`.

A full DAG is in `specstream_provider/example_dags/example_specstream.py`.

## License

MIT
