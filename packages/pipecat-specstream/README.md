# pipecat-specstream

[SpecStream](https://specstream.ai) for [Pipecat](https://pipecat.ai) voice and multimodal agents: live web search, page reading, Deep Search lists and research reports as function-calling tools.

This integration is maintained by SpecStream, the company behind the service.
Tested with Pipecat v1.16.0.

SpecStream has three products:

1. Search API: `GET /v1/web-search`, $5 per 1,000 searches of up to 10 results, or $1 per 1,000 with `speed=fast`, the default here because it suits voice.
2. Extract API: `POST /v1/extract`, up to 20 URLs a call (web pages, PDF, Word, Excel), $0.80 per 1,000 pages. A page with no text is not charged.
3. Deep Search: ask for a list in plain words and get every match on the live web as structured rows, each value with the page it was read from. Each delivered row is charged 5¢, 15¢ or $1 depending on what the row needs.

## Install

```bash
uv add pipecat-specstream
export SPECSTREAM_API_KEY=ss_live_...   # Agents & API in your SpecStream workspace
```

A free account comes with $10 of credit and needs no card: [specstream.ai](https://specstream.ai/signup).

## Use it in a Pipecat pipeline

```python
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat_specstream import SpecStreamDeepSearch

specstream = SpecStreamDeepSearch(api_key=os.getenv("SPECSTREAM_API_KEY"), max_price_usd=5)
context = LLMContext(tools=specstream.tools())
```

The schemas carry their handlers, so the LLM service registers them on its own. Put the context in an `LLMContextAggregatorPair` and the pipeline is the usual one: `transport.input(), stt, user_aggregator, llm, tts, transport.output(), assistant_aggregator`. Call `await specstream.close()` at teardown.

| Tool | What it does |
| - | - |
| `specstream_web_search` | One fact or a quick answer from the live web, with the page it came from. |
| `specstream_read_pages` | The text, title and date of 1 to 20 known pages. |
| `specstream_price_list` | The most a Deep Search list can cost. Nothing runs and nothing is charged. |
| `specstream_find_list` | A Deep Search list of every match. It runs as an async function call: the bot keeps talking and the rows reach the model when the list is done. |
| `specstream_get_list_results` | The rows of a list again, for example the next ones. Free. |

## Spending

- `max_price_usd` is the most one list may cost. Only the developer sets it; the model can't raise it, and a list priced above it never starts.
- With `ask_before_buying=True` (the default), the model must call `specstream_price_list`, tell the user the price and pass the price the user accepted as `approved_max_usd`. If the price has grown, nothing runs.
- A repeated call for the same list within the hour gets the list it already started, so it is never bought twice.

| Argument | Default | What it does |
| - | - | - |
| `api_key` | `SPECSTREAM_API_KEY` | Your SpecStream API key. |
| `max_price_usd` | required | The most one list may cost, in dollars. |
| `ask_before_buying` | `True` | Ask the user to accept the price before a list starts. |
| `search_speed` | `"fast"` | `"fast"` for the lowest latency, `"default"` for the most accurate answer. |
| `rows_in_answer` | `10` | How many rows go back to the model at once; the rest are at the list's link. |
| `wait_secs` | `420` | How long a list may run before the rows found so far are returned. |

## Research reports

`SpecStreamResearch` gives the agent a written report that answers a question from the live web, with the page behind each cited sentence. A report costs $0.10 (`quick`), $0.30 (`standard`) or $1.00 (`deep`), charged once, when it is delivered. A failed or cancelled report is not charged.

```python
from pipecat.adapters.llm.schemas.tools_schema import ToolsSchema
from pipecat_specstream import SpecStreamDeepSearch, SpecStreamResearch

search = SpecStreamDeepSearch(max_price_usd=5)
research = SpecStreamResearch(max_price_usd=0.30)   # quick and standard reports, never deep
tools = ToolsSchema(standard_tools=search.function_schemas() + research.function_schemas())
context = LLMContext(tools=tools)
```

| Tool | What it does |
| - | - |
| `specstream_research_price` | The price of a report at each depth the agent may buy. Nothing runs and nothing is charged. |
| `specstream_start_research` | Starts the report. It runs as an async function call: the bot keeps talking and the report reaches the model when it is done, about a minute for a quick one. |
| `specstream_get_research` | A report by its id: its status while it runs, the text and its cited pages when it is completed. Free. |

- `max_price_usd` is the most one report may cost. The model sees only the depths at or under it and can't raise it.
- With `ask_before_buying=True` (the default), the model must tell the user the price and pass the price the user accepted as `approved_max_usd`. Without it, nothing runs.
- A repeated call for the same question within the hour gets the report it already started, so it is never bought twice.
- `length` is `"short"` by default, which suits a spoken answer; `include_domains` and `exclude_domains` choose the sites it reads.

A failed call goes back to the model as `{"status": "error", "error": "..."}`; it never stops the pipeline.

## Run the example

```bash
cd examples
export SPECSTREAM_API_KEY=... DEEPGRAM_API_KEY=... CARTESIA_API_KEY=... OPENAI_API_KEY=...
uv run --with "pipecat-ai[daily,deepgram,cartesia,openai,silero,runner]" --with pipecat-specstream python foundational.py
```

Open the address it prints and ask: "What's in the news today?", "Read https://example.com", or "Find dental clinics in Lisbon with online booking".

`research.py` is the same bot with research reports: ask "Research how the EU and the US regulate stablecoin reserves".

## License

BSD 2-Clause.
