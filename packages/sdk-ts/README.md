# @specstream/sdk

TypeScript client for [SpecStream](https://specstream.ai), the live web data engine for teams and agents. Describe the list you need in plain words; SpecStream reads the web where those things live, hands back only the matches, and you pay for each result delivered.

Source URL and read time on every value.

The client has no runtime dependencies and needs Node 22 or newer. It uses the same account, permissions, projects and balance as the workspace.

```sh
npm install @specstream/sdk
```

Create an API key under **Agents & API** in your SpecStream workspace and keep it in the environment: `SPECSTREAM_API_KEY`.

## Search API and Extract API

SpecStream has three products: Search API, Extract API and Deep Search. The first two take one call at a flat price, with no quote or approval. The sections after this one cover Deep Search.

`client.webSearch` calls the [Search API](https://specstream.ai/docs/search-api), `GET /v1/web-search`, at $5 per 1,000 searches of up to 10 results, or $1 on the fast tier. It is the most accurate web search API in the world ([benchmarks](https://specstream.ai/benchmarks)) and answers from the live web in a few seconds. Write `q` in everyday words, in any language.

`client.extractPages` calls the [Extract API](https://specstream.ai/docs/extract-api), `POST /v1/extract`, at $0.80 per 1,000 pages. It takes up to 20 URLs a call, reads web pages, PDF, Word and Excel, and returns each one's main text as `markdown` (the default) or `text`. A page with no text is free.

```ts
import { Client } from "@specstream/sdk";

const client = new Client({ apiKey: process.env.SPECSTREAM_API_KEY! });

const search = await client.webSearch({ q: "What is the latest stable release of PostgreSQL?" });
console.log(search.answer?.value, search.answer?.page);

const extract = await client.extractPages({
  urls: search.sources.slice(0, 5).map((source) => source.url),
  format: "markdown",
});
for (const page of extract.results) console.log(page.url, page.status, page.text);
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

```ts
import { Client } from "@specstream/sdk";

const client = new Client({ apiKey: process.env.SPECSTREAM_API_KEY! });

const read = await client.compile(
  "Open-source document-signing tools I can self-host. Include the license and latest release.",
);
const offer = await client.quoteCapacityWork({
  ast_hash: String(read.ast_hash),
  operation: "find",
  requested_units: 25,
});
console.log(offer.maximum_cents, offer.expires_at);
```

Nothing has run yet. Show a person the quote: what will be found, the facts that come back, the most the work can cost, and when the price expires. A price lasts 30 minutes.

## Approve it, then read the results

After a person approves, send the approved maximum in cents and a request key you saved first:

```ts
const run = await client.authorizeCapacityWork({
  quote_id: offer.quote_id,
  quote_hash: offer.quote_hash,
  confirm_max_cents: approvedMaximumCents,
  idempotency_key: savedRequestKey,
});

if (!run.find_id) throw new Error("The work was not started; retry with the same key");
const page = await client.rows(run.find_id);
for (const row of page.rows) console.log(row);
```

If the response is lost, `getCapacityRequest(savedRequestKey)` returns the same work. Keep the original key when you retry, and you will not pay twice. `authorizeCapacityWork` throws before any network call unless the quote, its signature, a whole-number maximum and the key are all present. `getFind` reports progress, and `rows` pages with `next_cursor`. Reading, exporting and sharing results you own cost nothing.

## More

- `quoteCapacityWork` also prices `extend`, `add_facts` and `refresh` (a recheck, at half price) on a finished run.
- `specOptions(kind)` lists the facts you can ask for per kind of thing. `editSpec` changes a request without rereading it.
- `createCapacitySchedule` keeps a request current inside per-run and per-period limits.
- `export` and `downloadExport` give CSV, XLSX, JSON or HTML.
- Errors are `SpecstreamError` with `status`, `code` and `details`.

## Pricing

New accounts start with $10 of credit, no card. The Search API costs $5 per 1,000 searches of up to 10 results, or $1 on the fast tier, and the Extract API $0.80 per 1,000 pages. In Deep Search, a delivered result costs 5 cents, 15 cents or $1 depending on how many facts it carries. No result, no charge. See [pricing](https://specstream.ai/pricing).

## Links

- [SDK docs](https://specstream.ai/docs/sdk) and [API docs](https://specstream.ai/docs/api)
- [Source and issues](https://github.com/specstream/specstream-tools)
- [Python client](https://pypi.org/project/specstream-client/)
- Support: support@specstream.ai

MIT license.
