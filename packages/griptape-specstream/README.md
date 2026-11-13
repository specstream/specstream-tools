# griptape-specstream

SpecStream drivers for [Griptape](https://github.com/griptape-ai/griptape): live web search and page reading for Griptape agents, pipelines and workflows.

- `SpecStreamWebSearchDriver`: a web search driver on the SpecStream Search API, $5 per 1,000 searches of up to 10 results, or $1 per 1,000 with `speed="fast"`.
- `SpecStreamWebScraperDriver`: a web scraper driver on the SpecStream Extract API, $0.80 per 1,000 pages. A page with no text is not charged. It reads web pages, PDF, Word and Excel files.

## Install

```bash
pip install griptape-specstream
export SPECSTREAM_API_KEY=ss_live_...   # Agents & API in your SpecStream workspace
```

A free account comes with $10 of credit and needs no card: [specstream.ai](https://specstream.ai/signup).

## Use it

```python
from griptape.loaders import WebLoader
from griptape.structures import Agent
from griptape.tools import WebScraperTool, WebSearchTool

from griptape.specstream import SpecStreamWebScraperDriver, SpecStreamWebSearchDriver

agent = Agent(
    tools=[
        WebSearchTool(web_search_driver=SpecStreamWebSearchDriver()),
        WebScraperTool(web_loader=WebLoader(web_scraper_driver=SpecStreamWebScraperDriver())),
    ]
)
agent.run("Who won the 2025 Nobel Prize in Physics? Read the announcement page and quote one line.")
```

The agent needs a prompt driver too; Griptape's default reads `OPENAI_API_KEY`.

`search()` returns a `ListArtifact` of `JsonArtifact`s: first the answer, when the question has one, with the page it was read from, then one item per result with its `title`, `url`, `site` and `snippet`.

| Argument | Default | What it does |
| --- | --- | --- |
| `api_key` | `SPECSTREAM_API_KEY` | The SpecStream API key |
| `results_count` | `5` | How many results come back, 1 to 100 |
| `speed` | `None` | `"fast"` for the fast tier ($1 per 1,000 searches) |
| `passages` | `False` | Adds the text of each top page closest to the query (`excerpt`) |
| `include_answer` | `True` | Puts the answer first when the question has one |
| `params` | `{}` | More Search API parameters, for example `{"country": "DE"}` |
| `base_url`, `session` | | The API address and a shared `requests.Session` |

`SpecStreamWebScraperDriver` takes `api_key`, `base_url`, `session` and `format` (`"markdown"`, the default, or `"text"`). The artifact's `meta` holds the page's `url` and `title`.

A call SpecStream refuses raises `SpecStreamError` with the API's message and `status_code`.

## Develop

```bash
pip install -e ".[test]"
pytest -q
```

The tests answer from a scripted SpecStream and spend nothing.

API reference: [specstream.ai/docs/api](https://specstream.ai/docs/api). License: MIT.
