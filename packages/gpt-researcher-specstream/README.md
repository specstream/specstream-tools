# gpt-researcher-specstream

[SpecStream](https://specstream.ai) is the live web data engine for teams and agents. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. It runs through the API and MCP, and inside Sheets, CRMs, Slack, n8n, Zapier and the other tools teams already use.

Source URL and read time on every value.

Three products:

1. Search API: `GET /v1/web-search`, $5 per 1,000 searches. The most accurate web search API in the world (scores and method: https://specstream.ai/benchmarks).
2. Extract API: `POST /v1/extract`, up to 20 URLs a call (web pages, PDF, Word, Excel), $0.80 per 1,000 pages. A page with no text is not charged.
3. Deep Search: Ask in plain words. Get every match on the live web, in structured rows. Priced per row.

## Install

This package is a [GPT Researcher retriever plugin](https://docs.gptr.dev/docs/gpt-researcher/search-engines/retriever-plugins). It registers `specstream` in the `gpt_researcher.retrievers` entry-point group.

```bash
pip install gpt-researcher-specstream
export SPECSTREAM_API_KEY=ss_live_...   # Agents & API in your SpecStream workspace
export RETRIEVER=specstream
```

A free account comes with $10 of credit to use within 30 days and needs no card: [specstream.ai](https://specstream.ai/signup).

`RETRIEVER=specstream,duckduckgo` combines it with a built-in retriever.

## Settings

| Variable | Effect |
| --- | --- |
| `SPECSTREAM_API_KEY` | Your API key. Required. |
| `SPECSTREAM_EXTRACT` | Set to `true` to read the top results through the Extract API and hand GPT Researcher their text, so it does not fetch those pages again. Off by default: GPT Researcher reads the pages. |
| `SPECSTREAM_BASE_URL` | Defaults to `https://api.specstream.ai`. |

Each research sub-query is one Search API call. With `SPECSTREAM_EXTRACT=true`, each result page read is one Extract API page.

MIT licensed.
