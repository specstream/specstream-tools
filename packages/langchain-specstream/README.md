# langchain-specstream

[SpecStream](https://specstream.ai) is the live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. This package gives your LangChain agent two tools and a retriever for it. A run starts only within a price you set in code, and the model can't raise it.

Source URL and read time on every value.

```bash
pip install -U langchain-specstream
export SPECSTREAM_API_KEY=ss_live_...   # Agents & API in your SpecStream workspace
```

A free account comes with $10 of credit and needs no card: [specstream.ai](https://specstream.ai/signup).

## An agent that can find data

```python
from langchain.agents import create_agent
from langchain_specstream import specstream_tools

agent = create_agent(
    "anthropic:claude-sonnet-5-5",
    tools=specstream_tools(max_price_usd=5),
)
agent.invoke({"messages": [{"role": "user", "content":
    "Find open-source vector databases on GitHub with more than 5,000 stars. Which licenses are most common?"}]})
```

The agent writes the request and picks how many rows. You decide what one list may cost.

## What comes back

One flat row per match: the request's own columns, then where the row was read. For the request above, each row has this shape:

```json
{
  "list_id": "fnd_...",
  "position": 1,
  "Repository": "<owner/name>",
  "Stars": "<star count>",
  "License": "<license>",
  "source_url": "https://github.com/<owner>/<name>",
  "checked_at": "<when SpecStream read the page>",
  "list_link": "https://specstream.ai/workspace/collections/fnd_..."
}
```

Columns follow the request, so a different request brings different columns. A fact a source doesn't publish comes back empty, never guessed.

## The four tools

| Tool | The model gives | What happens | Cost |
| --- | --- | --- | --- |
| `specstream_web_search` | `q`, `passages`, `speed` | Calls `GET /v1/web-search` and returns the answer, matching rows, ranked sources and optional page passages. `speed="fast"` returns the ranked results in about a second | $5 per 1,000 searches of up to 10 results; a fast search costs $1 per 1,000 |
| `specstream_extract_pages` | `urls`, `format` | Calls `POST /v1/extract` and returns the clean main text, title and published date of 1 to 20 web pages, PDFs, Word or Excel files | $0.80 per 1,000 pages (empty pages free) |
| `specstream_find_list` | `request`, `max_results` | Reads the request, prices it, starts it only within `max_price_usd`, waits up to `wait_seconds` (7 minutes by default) and returns every row | Only delivered rows |
| `specstream_get_list_results` | `list_id` | Every row found so far, for a list that was still running | Free |

When the price is above your maximum, nothing runs: the tool returns the price, so the agent can ask for fewer rows or tell the user. When a request is too vague to price, it returns how SpecStream read it, so the agent can add the place or the conditions.

Use the classes directly when you want different settings per tool:

```python
from langchain_specstream import SpecStreamFindList, SpecStreamGetListResults

find = SpecStreamFindList(max_price_usd=20, wait_seconds=600)
results = SpecStreamGetListResults()
```

## Research reports

`SpecStreamResearch` answers a question in plain words with a written report from the live web. Each cited sentence links to a page read in that run, with its read time. Use it when the answer needs many pages read and compared, not a table of rows.

```python
from langchain_specstream import SpecStreamGetResearch, SpecStreamResearch

research = SpecStreamResearch(depth="quick")
report = research.invoke({"input": "How do the EU and the US regulate stablecoin reserves in 2026?"})
tools = [research, SpecStreamGetResearch()]
```

| Tool | The model gives | What happens | Cost |
| --- | --- | --- | --- |
| `specstream_research` | `input` | Calls `POST /v1/research` at the `depth` you set, waits up to `wait_seconds` (7 minutes by default) and returns the report: `content` in Markdown with `[1]` markers, `citations` (page, read time and passage of each cited sentence) and `sources` (every page read) | $0.10 (`quick`), $0.30 (`standard`) or $1.00 (`deep`) a report |
| `specstream_get_research` | `research_id` | Calls `GET /v1/research/{id}`: the state of a report that was still running, and the report when it is completed | Free |

`depth` lives on the tool, in your code, so the model can't choose a higher price. A report is charged once, when it is delivered. A quick report takes about a minute, a standard report about four minutes and a deep report about five. `include_domains` and `exclude_domains` choose the sites, `length` is `short`, `standard` or `long`, and `json_schema` (a JSON Schema) brings the report back as JSON under `structured` as well. A retried step with the same question and settings within the hour gets the report it already started, not a second bill.

## Browser sessions

Some pages show nothing until a button is clicked, a form is filled in or their JavaScript runs. For those, the agent opens a real browser that SpecStream runs, drives it step by step and closes it.

```python
from langchain.agents import create_agent
from langchain_specstream import specstream_browser_tools

agent = create_agent(
    "anthropic:claude-haiku-5-5",
    tools=specstream_browser_tools(timeout_s=300, allowed_domains=["example.com"]),
)
```

| Tool | The model gives | What happens | Cost |
| --- | --- | --- | --- |
| `specstream_open_browser` | `url` (optional) | Calls `POST /v1/browser/sessions` with the limits you set in code and returns the `session_id` | $0.10 an hour of browser time, charged by the second |
| `specstream_browser_navigate` | `session_id`, `url` | Opens the address | $1 per 1,000 steps |
| `specstream_browser_read` | `session_id`, `format` | The page's text as it stands after its JavaScript ran, in Markdown or plain text | $1 per 1,000 steps |
| `specstream_browser_snapshot` | `session_id` | The page's links, buttons and fields, each with a reference | $1 per 1,000 steps |
| `specstream_browser_click`, `specstream_browser_type` | `session_id`, `target`, `text` | Clicks an element or types into a field, by its reference | $1 per 1,000 steps |
| `specstream_browser_action` | `session_id`, `tool`, `arguments` | Any other Playwright MCP step: a key press, a select, a wait, a form | $1 per 1,000 steps |
| `specstream_close_browser` | `session_id` | Calls `POST /v1/browser/sessions/{id}/release` and returns the seconds, the steps and the charge | Free |

`timeout_s` lives on the tool, in your code: the browser ends then, whatever the model does, so 300 seconds is at most $0.0084 of time. `allowed_domains` keeps the browser on the hosts you name. A page a site or your own list refuses comes back as an error the agent can read, not an exception. Browser sessions need langchain-specstream 0.4.0 or later.

## As a retriever

```python
from langchain_specstream import SpecStreamRetriever

retriever = SpecStreamRetriever(max_price_usd=3, max_results=25)
docs = retriever.invoke("Breweries in Portland, Oregon that host events, with their website")

docs[0].page_content          # "Business location: Occidental Brewing Company\nPublished business website: http://occidentalbeers.com ..."
docs[0].metadata["source_url"]  # the page that row was read from
```

One document per row, its facts as text and its source in the metadata, so a chain can cite every claim. Above the maximum, the retriever raises `SpecStreamError` and nothing runs.

## Money, plainly

- `max_price_usd` lives on the tool, in your code. The model never sees it and can't change it.
- You pay for rows that match. Candidates SpecStream couldn't confirm are left out and aren't billed.
- A retried step asking for the same list within the hour gets the list it already started, not a second bill.
- Rates and plans: [specstream.ai/pricing](https://specstream.ai/pricing).

## When to reach for it

When the answer is many things that meet conditions. For a single fact or a summary of one page, a search tool fits better.

## More

- [SpecStream docs](https://specstream.ai/docs) and the [LangChain page](https://specstream.ai/docs/langchain)
- Agents outside LangChain: the [MCP server](https://specstream.ai/docs/mcp) at `https://api.specstream.ai/mcp`
- The [Python SDK](https://pypi.org/project/specstream-client/) for everything else in the API
- Questions: support@specstream.ai

MIT licensed. Made by [SpecStream](https://specstream.ai), the live web data engine for teams and agents.
