# llama-index-tools-specstream

[SpecStream](https://specstream.ai) is the live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. This package gives your LlamaIndex agent a tool spec and a retriever for it. A run starts only within a price you set in code, and the model can't raise it.

Source URL and read time on every value.

```bash
pip install -U llama-index-tools-specstream
export SPECSTREAM_API_KEY=ss_live_...   # Agents & API in your SpecStream workspace
```

A free account comes with $10 of credit and needs no card: [specstream.ai](https://specstream.ai/signup).

## An agent that can find data

```python
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.anthropic import Anthropic
from llama_index.tools.specstream import SpecStreamToolSpec

agent = FunctionAgent(
    tools=SpecStreamToolSpec(max_price_usd=5).to_tool_list(),
    llm=Anthropic(model="claude-sonnet-5-5"),
)
response = await agent.run(
    "Find open-source vector databases on GitHub with more than 5,000 stars. Which licenses are most common?"
)
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
| `specstream_web_search` | `q`, `passages` | Calls `GET /v1/web-search` and returns the answer, matching rows, ranked sources and optional page passages | $5 per 1,000 searches, $1 per 1,000 with `speed=fast` |
| `specstream_extract_pages` | `urls`, `format` | Calls `POST /v1/extract` and returns the clean main text, title and published date of 1 to 20 web pages, PDFs, Word or Excel files | $0.80 per 1,000 pages (empty pages free) |
| `specstream_find_list` | `request`, `max_results` | Reads the request, prices it, starts it only within `max_price_usd`, waits up to `wait_seconds` (7 minutes by default) and returns every row | Only delivered rows |
| `specstream_get_list_results` | `list_id` | Every row found so far, for a list that was still running | Free |

When the price is above your maximum, nothing runs: the tool returns the price, so the agent can ask for fewer rows or tell the user. When a request is too vague to price, it returns how SpecStream read it, so the agent can add the place or the conditions.

Settings live on the spec, never in the tool schema:

```python
spec = SpecStreamToolSpec(
    max_price_usd=20,     # the most one list may cost
    wait_seconds=600,     # how long find_list waits before handing back what it has
    locale="en-GB",       # the language the requests are written in
)
```

## As a retriever

```python
from llama_index.tools.specstream import SpecStreamRetriever

retriever = SpecStreamRetriever(max_price_usd=3, max_results=25)
nodes = retriever.retrieve("Breweries in Portland, Oregon that host events, with their website")

nodes[0].text                      # "Business location: Occidental Brewing Company\nPublished business website: http://occidentalbeers.com ..."
nodes[0].metadata["source_url"]    # the page that row was read from
```

One node per row, its facts as text and its source in the metadata. The model sees each row with the page behind it, so a query engine can cite every claim; the list's bookkeeping stays out of the prompt and out of embeddings. Above the maximum, the retriever raises `SpecStreamError` and nothing runs.

## Money, plainly

- `max_price_usd` lives on the spec, in your code. The model never sees it and can't change it.
- You pay for rows that match. Candidates SpecStream couldn't confirm are left out and aren't billed.
- A retried step asking for the same list within the hour gets the list it already started, not a second bill.
- Rates and plans: [specstream.ai/pricing](https://specstream.ai/pricing).

## When to reach for it

When the answer is many things that meet conditions. For a single fact or a summary of one page, a search tool fits better.

## More

- [SpecStream docs](https://specstream.ai/docs) and the [LlamaIndex page](https://specstream.ai/docs/llamaindex)
- Agents outside LlamaIndex: the [MCP server](https://specstream.ai/docs/mcp) at `https://api.specstream.ai/mcp`
- The [Python SDK](https://pypi.org/project/specstream-client/) for everything else in the API
- Questions: support@specstream.ai

MIT licensed. Made by [SpecStream](https://specstream.ai), the live web data engine for teams and agents.
