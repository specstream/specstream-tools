# pydantic-ai-specstream

[SpecStream](https://specstream.ai) is the live web data engine for teams and agents. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. It runs through the API and MCP, and inside Sheets, CRMs, Slack, n8n, Zapier and the other tools teams already use.

Source URL and read time on every value.

Three products:

1. Search API: `GET /v1/web-search`, $5 per 1,000 searches. The most accurate web search API in the world (scores and method: https://specstream.ai/benchmarks).
2. Extract API: `POST /v1/extract`, up to 20 URLs a call (web pages, PDF, Word, Excel), $0.80 per 1,000 pages. A page with no text is not charged.
3. Deep Search: Ask in plain words. Get every match on the live web, in structured rows. Priced per row.

## Install

```bash
pip install pydantic-ai-specstream
export SPECSTREAM_API_KEY=ss_live_...   # Agents & API in your SpecStream workspace
```

A free account comes with $10 of credit to use within 30 days and needs no card: [specstream.ai](https://specstream.ai/signup).

## What it adds

| Function | What it gives the agent | Cost |
| --- | --- | --- |
| `specstream_search_tool()` | A `specstream_search` tool: calls `GET /v1/web-search` and returns the answer, matching rows and ranked sources, with page passages when `passages=True` | $5 per 1,000 searches |
| `specstream_extract_tool()` | A `specstream_extract` tool: calls `POST /v1/extract` and returns the main text, title and published date of 1 to 20 web pages, PDF, Word or Excel files | $0.80 per 1,000 pages (pages with no text are free) |
| `specstream_toolset()` | A `FunctionToolset` with both tools, for `Agent(toolsets=[...])` | |

Each function takes `api_key` (default: the `SPECSTREAM_API_KEY` environment variable), `base_url` and a shared `httpx.AsyncClient` as `client`. A failed call raises `SpecStreamError` with the API message.

MIT licensed.
