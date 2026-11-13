# dagster-specstream

[SpecStream](https://specstream.ai) is the live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. It runs through the API and MCP, and inside Sheets, CRMs, Slack, n8n, Zapier and the other tools teams already use.

Source URL and read time on every value.

This package is the SpecStream integration for Dagster 1.8 and later: one resource, `SpecStreamResource`, for assets and ops.

```bash
pip install dagster-specstream
```

## Resource

Put your API key (Agents & API in your SpecStream workspace) in `SPECSTREAM_API_KEY` and add the resource to your definitions:

```python
from dagster import Definitions, EnvVar
from dagster_specstream import SpecStreamResource

defs = Definitions(
    assets=[...],
    resources={"specstream": SpecStreamResource(api_key=EnvVar("SPECSTREAM_API_KEY"))},
)
```

A free account comes with $10 of credit and needs no card: [specstream.ai](https://specstream.ai/signup).

| Method | API | Price |
| --- | --- | --- |
| `web_search(query, speed=..., num=...)` | Search API, `GET /v1/web-search` | $5 per 1,000 searches of up to 10 results; $1 per 1,000 with `speed="fast"` |
| `extract_pages(urls, format=...)` | Extract API, `POST /v1/extract`, 1 to 20 URLs | $0.80 per 1,000 pages; a page with no text is not charged |
| `deep_search(context, request, max_results=..., max_price_usd=...)` | Deep Search | 5 cents, 15 cents or $1 per delivered row |

Each method returns the API's reply as a dict.

```python
from dagster import AssetExecutionContext, RetryPolicy, asset
from dagster_specstream import SpecStreamResource


@asset
def release_news(specstream: SpecStreamResource) -> dict:
    return specstream.web_search("Dagster latest release", speed="fast")


@asset
def release_page(release_news: dict, specstream: SpecStreamResource) -> dict:
    return specstream.extract_pages(release_news["sources"][0]["url"])


@asset(retry_policy=RetryPolicy(max_retries=3))
def orchestrators(context: AssetExecutionContext, specstream: SpecStreamResource) -> list[dict]:
    result = specstream.deep_search(
        context,
        "Open-source workflow orchestrators with their website and license",
        max_results=25,
        max_price_usd=5,
    )
    return result["rows"]
```

`deep_search` starts a run only when its quoted maximum is at or below `max_price_usd`; otherwise nothing runs and the step fails with the price, without a retry. The idempotency key comes from the run (the first run's id when a run is re-executed), the asset and the partition, so a retry or a re-execution continues the same list and never buys it twice. Pass `idempotency_key` to choose it yourself. When the list is still running after `wait_seconds` (420 by default), the step asks Dagster to retry it (`retries_while_running`, 3 by default) and the retry picks the list up. The result holds `list_id`, `status`, `list_link`, `row_count` and `rows`; each row carries `source_url` and `checked_at`.

`find_list(request, max_results=..., max_price_usd=..., idempotency_key=...)` is the same call without Dagster's handling: it returns every status, `needs_edit` and `over_maximum` included.

## License

MIT
