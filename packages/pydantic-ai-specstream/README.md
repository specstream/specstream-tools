# pydantic-ai-specstream

[SpecStream](https://specstream.ai) is the live web data engine for teams and agents. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. It runs through the API and MCP, and inside Sheets, CRMs, Slack, n8n, Zapier and the other tools teams already use.

Source URL and read time on every value.

Three products:

1. Search API: `GET /v1/web-search`, $5 per 1,000 searches of up to 10 results. The most accurate web search API in the world (scores and method: https://specstream.ai/benchmarks).
2. Extract API: `POST /v1/extract`, up to 20 URLs a call (web pages, PDF, Word, Excel), $0.80 per 1,000 pages. A page with no text is not charged.
3. Deep Search: Ask in plain words. Get every match on the live web, in structured rows. Priced per row.

## Install

```bash
pip install pydantic-ai-specstream
export SPECSTREAM_API_KEY=ss_live_...   # Agents & API in your SpecStream workspace
```

A free account comes with $10 of credit and needs no card: [specstream.ai](https://specstream.ai/signup).

## Use it as a capability

```python
from pydantic_ai import Agent
from pydantic_ai_specstream import SpecStreamCapability

agent = Agent('openai:gpt-5', capabilities=[SpecStreamCapability()])

result = agent.run_sync('Who won the 2025 Nobel Prize in Physics? Read the announcement page and quote one line.')
print(result.output)
```

The example needs `SPECSTREAM_API_KEY` and a model, here `pip install "pydantic-ai-slim[openai]"` with `OPENAI_API_KEY`. Any Pydantic AI model works.

`SpecStreamCapability` gives the agent the `specstream_search` and `specstream_extract` tools and instructions for when to call each. A call the API refuses as bad input goes back to the model as a `ModelRetry`, so the model corrects it. Every other failure raises `SpecStreamError`.

| Argument | Default | What it does |
| --- | --- | --- |
| `api_key` | `SPECSTREAM_API_KEY` | The SpecStream API key |
| `search` | `True` | Adds `specstream_search` (Search API) |
| `extract` | `True` | Adds `specstream_extract` (Extract API) |
| `passages` | `False` | Adds the text of the top pages to every search |
| `instructions` | built in | Your own guidance, or `None` for none |
| `base_url`, `client` | | The API address and a shared `httpx.AsyncClient` |
| `id`, `description`, `defer_loading` | | The standard capability fields. `defer_loading=True` needs an `id` |

It also loads from an [agent spec](https://ai.pydantic.dev/agent-spec/):

```yaml
# agent.yaml
model: openai:gpt-5
capabilities:
  - SpecStreamCapability:
      passages: true
```

```python
from pydantic_ai import Agent
from pydantic_ai_specstream import SpecStreamCapability

agent = Agent.from_file('agent.yaml', custom_capability_types=[SpecStreamCapability])
```

## Tools and toolset

| Function | What it gives the agent | Cost |
| --- | --- | --- |
| `specstream_search_tool()` | A `specstream_search` tool: calls `GET /v1/web-search` and returns the answer, matching rows and ranked sources, with page passages when `passages=True` | $5 per 1,000 searches of up to 10 results |
| `specstream_extract_tool()` | A `specstream_extract` tool: calls `POST /v1/extract` and returns the main text, title and published date of 1 to 20 web pages, PDF, Word or Excel files | $0.80 per 1,000 pages (pages with no text are free) |
| `specstream_toolset()` | A `FunctionToolset` with both tools, for `Agent(toolsets=[...])` | |

Each function takes `api_key` (default: the `SPECSTREAM_API_KEY` environment variable), `base_url` and a shared `httpx.AsyncClient` as `client`. A failed call raises `SpecStreamError` with the API message.

MIT licensed.
