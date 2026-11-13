# specstream-client

`pip install specstream-client` (the `specstream` package on PyPI is a different project)

Python client and command line for [SpecStream](https://specstream.ai), the live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change.

- Source URL and read time on every value.
- You pay for each row delivered.

The client has no dependencies and needs Python 3.12 or newer. It uses the same account, permissions, projects and balance as the workspace.

```sh
pip install specstream-client
```

The package installs the import name `specstream` and the command `specstream`.

Create an API key under **Agents & API** in your SpecStream workspace and keep it in the environment:

```sh
export SPECSTREAM_API_KEY="ss_live_..."
```

## Search the web

`web_search` calls the [Search API](https://specstream.ai/docs/search-api), `GET /v1/web-search`, at $5 per 1,000 searches of up to 10 results, or $1 on the fast tier.

```python
import os
from specstream_client import Client

client = Client(os.environ["SPECSTREAM_API_KEY"])

search = client.web_search(q="What is the population of Japan?")
for source in search["sources"][:1]:
    print(source["title"], source["url"], source["snippet"])
```

## Extract pages

`extract_pages` calls the [Extract API](https://specstream.ai/docs/extract-api), `POST /v1/extract`, at $0.80 per 1,000 pages, and a page with no text is not charged.

```python
import os
from specstream_client import Client

client = Client(os.environ["SPECSTREAM_API_KEY"])

extract = client.extract_pages({"urls": ["https://example.com"]})
for page in extract["results"][:1]:
    print(page["title"], page["url"], page["text"])
```

## Drop-in for the API you already call

SpecStream answers calls written for these search APIs at its own address, in each API's own reply shape. To switch, change the base address and the key. Each search call is one Search API web search on your SpecStream key. A drop-in call runs the fast search: $0.001 for up to 10 results ($1 per 1,000 searches), and each 10 results more in the same call add $0.0012. A call that asks for an answer or the API's thorough mode runs the default search: $0.005 for up to 10 results, and $0.006 for each 10 more.

| API you call | Base address you have | SpecStream address | Where the SpecStream key goes |
| --- | --- | --- | --- |
| Tavily | `https://api.tavily.com` | `https://api.specstream.ai/tavily` | Bearer token or `api_key` |
| Exa | `https://api.exa.ai` | `https://api.specstream.ai/exa` | `x-api-key` or Bearer token |
| Brave Search API | `https://api.search.brave.com` | `https://api.specstream.ai` | `X-Subscription-Token` |
| Serper | `https://google.serper.dev` | `https://api.specstream.ai/serper` | `X-API-KEY` |
| Bing Web Search API v7 | `https://api.bing.microsoft.com/v7.0/search` | `https://api.specstream.ai/v7.0/search` | `Ocp-Apim-Subscription-Key` |
| Google Custom Search JSON API | `https://www.googleapis.com` or `https://customsearch.googleapis.com` | `https://api.specstream.ai` | `key=` (`cx` is accepted and not used) |
| SearXNG (JSON) | your instance address | `https://api.specstream.ai/searxng/<key>` | in the address, `key=`, `X-API-Key` or Bearer token |
| Firecrawl v2 | `https://api.firecrawl.dev` | `https://api.specstream.ai/firecrawl` | Bearer token |

The official Tavily and Exa Python SDKs take the address as an argument:

```python
import os
from tavily import TavilyClient
from exa_py import Exa

tavily = TavilyClient(api_key=os.environ["SPECSTREAM_API_KEY"], api_base_url="https://api.specstream.ai/tavily")
exa = Exa(api_key=os.environ["SPECSTREAM_API_KEY"], base_url="https://api.specstream.ai/exa")
```

- A call that names no result count returns 10 results, at $0.001 on the fast search. Brave's own default is 20: send `count=20` for 20 results at $0.0022.
- A Firecrawl `/v2/scrape` call is one Extract API page at $0.0008. The Firecrawl JavaScript SDK works with this address; the Firecrawl Python SDK does not yet.
- Each route's request and reply fields: [specstream.ai/agents.md](https://specstream.ai/agents.md). Create a key under **Agents & API** at [specstream.ai/workspace](https://specstream.ai/workspace). New accounts start with $10 of credit, no card.

## Read a request, get the price

```python
import os
from specstream_client import Client

client = Client(os.environ["SPECSTREAM_API_KEY"])

read = client.compile("Open-source document-signing tools I can self-host. Include the license and latest release.")
offer = client.quote_capacity_work({
    "ast_hash": read["ast_hash"],
    "operation": "find",
    "requested_units": read["ast"]["limit"]["max"],
})
print(offer["maximum_cents"], offer["expires_at"])
```

Nothing has run yet. Review the quote: what will be found, the facts that come back, the most the work can cost, and when the price expires. A price lasts 30 minutes.

## Approve it, then read the results

After a person approves, send the approved maximum in cents and a request key you saved first:

```python
run = client.authorize_capacity_work({
    "quote_id": offer["quote_id"],
    "quote_hash": offer["quote_hash"],
    "confirm_max_cents": approved_maximum_cents,
    "idempotency_key": saved_request_key,
})
find_id = run["find_id"]

page = client.rows(find_id)
for row in page["rows"]:
    print(row)
```

If the response is lost, `get_capacity_request(saved_request_key)` returns the same work. Keep the original key when you retry, and you will not pay twice. `get_find` reports progress, and `rows` pages through results with `next_cursor`. Reading, exporting and sharing results you own cost nothing.

`authorize_capacity_work` refuses to send anything unless the quote, its signature, the maximum and the key are all present.

## Keep a list current on a schedule

A monitor checks a list again on the live web every hour, day, week or month ("month" is every 30 days).
Each check is a refresh: half the row rate for a row that changed or is new, and 1 cent for a row that comes back unchanged.

```python
monitor = client.monitor_list(
    find_id,
    every="week",
    max_price_per_run_usd=2,
    max_price_per_month_usd=8,
)

if monitor["status"] == "saved":
    print(monitor["monitor_id"], monitor["next_run_at"])
else:
    print(monitor["message"])  # "over_maximum": one check costs more than max_price_per_run_usd, nothing was saved
```

The client prices one check before it saves anything.
When one check can cost more than `max_price_per_run_usd`, nothing is saved.
`max_price_per_month_usd` is the most the monitor spends in one UTC calendar month, checks run on demand included.
Without it, the limit is `max_price_per_run_usd` times the checks in 31 days.
The first check runs one interval after the current hour began, and the monitor ends a year after it, unless you set `first_run_at=` and `ends_at=` (a `datetime` with a time zone or an ISO 8601 string).
The same call again in the same hour returns the monitor already saved, not a second one.

| Call | What it does | Cost |
| --- | --- | --- |
| `monitor_list(list_id, ...)` | Prices one check of the list and saves the schedule within your limits | Each check, within the limits |
| `monitors()` | Every monitor of the account, with its state, next check and last list | Free |
| `monitor_runs(monitor_id)` | The recent checks, newest first: when, the outcome, the reason and the list each one made | Free |
| `run_monitor_now(monitor_id)` | One check now, inside the monitor's limits. The regular times stay as they are | One check |
| `pause_monitor(monitor_id)`, `resume_monitor(monitor_id)` | Stops and starts the checks. A missed check is never bought later | Free |
| `delete_monitor(monitor_id)` | Ends the monitor. The lists it made stay yours | Free |
| `revisit(list_id)` | Each record of a refreshed list: still matches, no longer matches, unresolved or unavailable | Free |

A blocked or missed check is not an unchanged result, and it is not bought later.
For a calendar schedule (for example Mondays at 9:00 in your time zone), call `create_capacity_schedule` with the API's own fields, including `calendar_schedule`; `list_capacity_schedules`, `update_capacity_schedule`, `list_capacity_occurrences` and `run_capacity_schedule_now` are there too.

### Send new and changed records to a webhook

```python
delivery = client.set_monitor_delivery(monitor["monitor_id"], webhook="https://example.com/hooks/specstream")
signing_secret = delivery["webhook_secret"]  # shown once: store it, never log it
```

`set_monitor_delivery` also takes `slack=` (a channel of your connected Slack workspace), `send_to=` (a connected tool) and `notify=` (SpecStream notifications). Nothing runs when you set it.
Slack and webhook delivery need a plan that includes deliveries.

Each delivery is a JSON POST with the headers `Specstream-Event-Id` and `Specstream-Signature: t=<unix time>,v1=<hex>`.
Check it before you trust the body, and use the event id to drop repeats:

```python
import json
import os
from specstream_client import verify_webhook

# In your web endpoint, with the raw request body
verify_webhook(
    secret=os.environ["SPECSTREAM_WEBHOOK_SECRET"],
    signature=request.headers["Specstream-Signature"],
    body=raw_body,
)  # raises SpecstreamError when the signature is wrong or older than 5 minutes
event = json.loads(raw_body)
```

## More than a first request

- `quote_capacity_work` also prices `extend` (more results), `add_facts` and `refresh` (a recheck, at half price) on a finished run. Pass the original `parent_find_id`.
- `spec_options(kind)` lists the facts you can ask for, per kind of thing. `edit_spec` changes a request without rereading it.
- `create_capacity_schedule` keeps any request up to date, hourly to yearly, inside per-run and per-period limits.
- `export` and `download_export` give CSV, XLSX, JSON or HTML. `create_customer_webhook` sends signed events.
- Projects, members, shares and starred items have their own methods.

## Command line

```sh
specstream compile "Open-source vector databases on GitHub with more than 5,000 stars, with their license."
specstream get-capacity-balance
specstream quote-capacity-work --body quote-request.json
specstream authorize-capacity-work --body approved-execution.json
specstream rows --find-id FIND_ID
```

`--body` takes a JSON file or `-` for stdin. Every command's `--help` describes its parameters. The command line exposes the same operations as the client.

## Pricing

New accounts start with $10 of credit, no card. A delivered result costs 5 cents, 15 cents or $1 depending on how many facts it carries. No result, no charge. Rechecks cost half. People and agents share one balance. See [pricing](https://specstream.ai/pricing).

## Links

- [SDK docs](https://specstream.ai/docs/sdk) and [API docs](https://specstream.ai/docs/api)
- [Source and issues](https://github.com/specstream/specstream-tools)
- [TypeScript client](https://www.npmjs.com/package/@specstream/sdk)
- Support: support@specstream.ai

MIT license.
