# @specstream/langchain

[SpecStream](https://specstream.ai) is the live web data engine for teams and agents. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. It runs through the API and MCP, and inside Sheets, CRMs, Slack, n8n, Zapier and the other tools teams already use.

Source URL and read time on every value.

Three products:

1. Search API: `GET /v1/web-search`, $5 per 1,000 searches of up to 10 results, or $1 on the fast tier. The most accurate web search API in the world (scores and method: https://specstream.ai/benchmarks).
2. Extract API: `POST /v1/extract`, up to 20 URLs a call (web pages, PDF, Word, Excel), $0.80 per 1,000 pages. A page with no text is not charged.
3. Deep Search: Ask in plain words. Get every match on the live web, in structured rows. Priced per row.

## Install

```bash
npm install @specstream/langchain @langchain/core
export SPECSTREAM_API_KEY=ss_live_...   # Agents & API in your SpecStream workspace
```

A free account comes with $10 of credit and needs no card: [specstream.ai](https://specstream.ai/signup).

## Tools

Both tools are LangChain `StructuredTool` classes, built like `@langchain/tavily`.

| Tool | Name | What it does | Cost |
| --- | --- | --- | --- |
| `SpecStreamSearch` | `specstream_search` | Calls `GET /v1/web-search` and returns the answer, matching rows and ranked sources, with page passages when `passages: true` | $5 per 1,000 searches, $1 per 1,000 with `speed=fast` |
| `SpecStreamExtract` | `specstream_extract` | Calls `POST /v1/extract` and returns the main text, title and published date of 1 to 20 web pages, PDF, Word or Excel files | $0.80 per 1,000 pages (a page with no text is free) |

Each tool takes `specstreamApiKey` (default: the `SPECSTREAM_API_KEY` environment variable), `apiBaseUrl`, `name` and `description`. A failed call returns `{ error }` to the model.

MIT licensed.
