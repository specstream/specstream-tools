# arcade-specstream

SpecStream tools for [Arcade](https://www.arcade.dev). [SpecStream](https://specstream.ai) is the live web data engine for teams and agents: ask for any dataset in plain words and get every match on the live web, in structured rows, with the source page and read time of every value.

```bash
pip install arcade-specstream
```

A free account comes with $10 of credit and needs no card: [specstream.ai](https://specstream.ai/signup). Create an API key under Agents & API in your SpecStream workspace.

## Tools

| Tool | What it does | Price |
| --- | --- | --- |
| `FindList` | Deep Search: a list of real things that meet conditions, from a plain-English request, with the page each row was read from | per delivered row, within the ceiling you set |
| `GetListResults` | Every row found so far for a list | free |
| `WebSearch` | Search the live web in seconds (Search API). `speed` set to `fast` returns the ranked results in about a second | $5 per 1,000 searches of up to 10 results; a fast search costs $1 per 1,000 |
| `ExtractPages` | Main text, title and date of 1 to 20 URLs, PDF, Word or Excel (Extract API) | $0.80 per 1,000 pages; empty pages free |

## Secrets

| Secret | Used by | Value |
| --- | --- | --- |
| `SPECSTREAM_API_KEY` | every tool | your SpecStream API key |
| `SPECSTREAM_MAX_PRICE_USD` | `FindList` | the most one list may cost, in US dollars, for example `5` |

The model writes the request and picks how many rows. It can't raise the price ceiling: a list whose price is above it doesn't run, and the tool answers `over_maximum` with the price. Rows that couldn't be confirmed are left out and aren't charged. The same request within the hour returns the same list, so a retried step never buys it twice.

## Run it

Locally, as an MCP server over stdio (secrets come from the environment):

```bash
export SPECSTREAM_API_KEY=ss_live_...
export SPECSTREAM_MAX_PRICE_USD=5
arcade-specstream            # stdio
arcade-specstream http 127.0.0.1 8000
```

Or add the tools to your own Arcade server:

```python
from arcade_mcp_server import MCPApp
import arcade_specstream

app = MCPApp(name="SpecStream")
app.add_tools_from_module(arcade_specstream)
app.run()
```

## What `FindList` returns

`status`, `list_id`, `list_link` (the list in your workspace), `row_count` and `rows`. Each row holds the list's own columns, the page of each value (`<field>_source`), `source_url` and `checked_at`. If the list is still running after about seven minutes, call `GetListResults` with its `list_id` for the rest.

MIT licensed. Source: [specstream/specstream-tools](https://github.com/specstream/specstream-tools/tree/main/packages/arcade-specstream).
