# prefect-specstream

[SpecStream](https://specstream.ai) is the live web data engine for teams and agents. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. It runs through the API and MCP, and inside Sheets, CRMs, Slack, n8n, Zapier and the other tools teams already use.

Source URL and read time on every value.

This package gives Prefect flows a research report flow, tasks and a credentials block:

1. `web_search`: the Search API, `POST /v1/web-search`, $5 per 1,000 searches of up to 10 results, or $1 per 1,000 on the fast tier (`speed="fast"`).
2. `extract_pages`: the Extract API, `POST /v1/extract` (web pages, PDF, Word, Excel), $0.80 per 1,000 pages. A page with no text is not charged.
3. `research_report`: a flow that researches a question on the live web and returns a written report in Markdown, with the page behind each cited sentence (`POST /v1/research`). A report costs $0.10 (`quick`), $0.30 (`standard`) or $1.00 (`deep`), charged once, when it is delivered.
4. `SpecStreamCredentials`: a Prefect block that holds the API key.

## Install

```bash
pip install prefect-specstream
prefect block register -m prefect_specstream
```

A free account comes with $10 of credit and needs no card: [specstream.ai](https://specstream.ai/signup). Create a key under Agents & API in your SpecStream workspace.

## Save the key once

```python
from prefect_specstream import SpecStreamCredentials

SpecStreamCredentials(api_key="ss_live_...").save("specstream")
```

Without an `api_key`, the block reads `SPECSTREAM_API_KEY` from the environment.

## Use it in a flow

```python
from prefect import flow
from prefect_specstream import SpecStreamCredentials, extract_pages, web_search


@flow
def read_the_web(question: str):
    credentials = SpecStreamCredentials.load("specstream")
    found = web_search(question, credentials)
    urls = [source["url"] for source in found["sources"][:3]]
    pages = extract_pages(urls, credentials)
    return found, pages
```

| Task | Arguments | Returns |
| --- | --- | --- |
| `web_search` | `query`, `specstream_credentials`, `speed` (`"default"` or `"fast"`), `num`, `passages` | The `data` object of the reply: `sources`, and on the default speed `answer` and `rows` |
| `extract_pages` | `urls`, `specstream_credentials`, `format` (`"markdown"` or `"text"`) | `{"results": [...]}`, one result per URL. Lists longer than 20 URLs are sent in calls of 20. |

## Get a written report

```python
from prefect import flow
from prefect_specstream import SpecStreamCredentials, research_report


@flow
def weekly_brief():
    credentials = SpecStreamCredentials.load("specstream")
    report = research_report(
        "How do the EU and the US regulate stablecoin reserves in 2026?",
        credentials,
        depth="quick",
    )
    print(report["content"])       # the report in Markdown, with numbered citations
    return report["citations"]     # each cited sentence's page, read time and excerpt
```

`research_report` starts one report, waits until it is written (one to five minutes) and returns `research_id`, `depth`, `price_usd`, `title`, `content`, `citations` and `sources`. You set `depth` in code, so the price of a run is fixed before it starts. A retry in the same hour with the same question and depth returns the report that was already started; it is not bought twice.

To start a report in one flow and read it in another, use the tasks:

| Task | Arguments | Returns |
| --- | --- | --- |
| `start_research` | `question`, `specstream_credentials`, `depth` (`"quick"`, `"standard"` or `"deep"`), `options` | The run, with its `id`, `status` and `price_usd` |
| `get_research` | `research_id`, `specstream_credentials` | The run, with `report` when it is completed. Costs nothing. |
| `wait_for_research` | `research_id`, `specstream_credentials`, `wait_seconds`, `poll_seconds` | The completed run. Raises `SpecStreamError` when the run fails or is still running after `wait_seconds`. |

A refused call raises `SpecStreamError` with the API's message and `status_code`. The tasks do not retry on their own; add retries with `web_search.with_options(retries=2)`.

API reference: https://specstream.ai/docs/api

## License

MIT
