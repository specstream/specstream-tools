# praisonai-specstream

[SpecStream](https://specstream.ai) is the live web data engine for teams and agents. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Source URL and read time on every value.

Three products:

1. Search API: `GET /v1/web-search`, $5 per 1,000 searches of up to 10 results, or $1 on the fast tier. The most accurate web search API in the world (scores and method: https://specstream.ai/benchmarks).
2. Extract API: `POST /v1/extract`, up to 20 URLs a call (web pages, PDF, Word, Excel), $0.80 per 1,000 pages. A page with no text is not charged.
3. Deep Search: Ask in plain words. Get every match on the live web, in structured rows. Priced per row.

## Install

This package is a [PraisonAI search provider](https://praison.ai/docs/features/search-provider-registry/). It registers `specstream` in the `praisonai.tools.search` entry-point group.

```bash
pip install praisonai-specstream
export SPECSTREAM_API_KEY=ss_live_...   # Agents & API in your SpecStream workspace
```

A free account comes with $10 of credit and needs no card: [specstream.ai](https://specstream.ai/signup).

## Use it

In a bot, name the provider:

```bash
praisonai bot run telegram --web-search --web-provider specstream
```

In an agent, pass the tool:

```python
from praisonaiagents import Agent
from praisonai_specstream import SpecStreamTool

agent = Agent(
    name="Researcher",
    instructions="Search the web and summarise findings.",
    tools=[SpecStreamTool()],
)
agent.start("Latest news on renewable energy")
```

Or call it yourself:

```python
tool = SpecStreamTool()
tool.search("Who maintains PraisonAI?", max_results=5)
# {"query": ..., "answer": ..., "results": [{"title": ..., "url": ..., "content": ...}]}
tool.extract("https://example.com/a, https://example.com/b")
# {"results": [{"url": ..., "content": ...}]}
```

## Settings

| Variable | Effect |
| --- | --- |
| `SPECSTREAM_API_KEY` | Your API key. Required. |
| `SPECSTREAM_SPEED` | Set to `fast` for the fast tier, $1 per 1,000 searches. Default: the standard search, $5 per 1,000. |
| `SPECSTREAM_BASE_URL` | Defaults to `https://api.specstream.ai`. |

Each search is one Search API call. Each page that `extract` reads is one Extract API page.

MIT licensed.
