# @specstream/ai-sdk

[SpecStream](https://specstream.ai) is the live web data engine for teams and agents. One platform to build, search, extract, enrich, map, and monitor data across the entire web. Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. Source URL and read time on every value.

```bash
npm install @specstream/ai-sdk ai zod
export SPECSTREAM_API_KEY=ss_live_...   # Agents & API in your SpecStream workspace
```

A free account comes with $10 of credit to use within 30 days and needs no card: [specstream.ai](https://specstream.ai/signup).

## An agent that can find lists

```ts
import { generateText, stepCountIs } from "ai";
import { specstreamTools } from "@specstream/ai-sdk";

const { text } = await generateText({
  model: "openai/gpt-5-mini",
  tools: specstreamTools({ maxPriceUsd: 5 }),
  stopWhen: stepCountIs(5),
  prompt: "Find US startups that raised $5M or more in a Form D filed after October 8, 2026. Which industries lead?",
});

console.log(text);
```

The agent writes the request and picks how many rows. You decide what one list may cost. `streamText` and `ToolLoopAgent` take the same `tools`.

## What comes back

One flat row per match: the list's own columns, then where the row was read. This is a real row from the request above.

```json
{
  "list_id": "fnd_gk5y3d0r97bvyz0t08zzh75kr6",
  "position": 26,
  "Organization": "RapidCanvas Inc",
  "Published address": "801 BARTON SPRINGS RD, AUSTIN, TEXAS, 78704",
  "Source industry classification": "Other Technology",
  "Amount sold (USD)": "28999988",
  "Funding filing date": "2026-10-14",
  "source_url": "https://www.sec.gov/Archives/edgar/data/2052031/000205203126000006/primary_doc.xml",
  "checked_at": "2026-10-14T19:56:02.016693Z",
  "list_link": "https://specstream.ai/workspace/collections/fnd_gk5y3d0r97bvyz0t08zzh75kr6"
}
```

Columns follow the request. Ask for "breweries in Portland, Oregon that host events, with their website" and the rows carry the brewery and its website instead. A fact a source doesn't publish comes back empty, never guessed.

The tool's result wraps the rows with `status`, `list_id`, `list_link`, `row_count` and `maximum_price_usd`, so the agent can cite the list and hand your user a link to it.

## The four tools

| Tool | The model gives | What happens | Cost |
| --- | --- | --- | --- |
| `specstream_web_search` | `q`, `passages` | Calls `GET /v1/web-search` and returns the answer, matching rows, ranked sources and optional page passages | $5 per 1,000 searches |
| `specstream_extract_pages` | `urls`, `format` | Calls `POST /v1/extract` and returns the clean main text, title and published date of 1 to 20 web pages, PDFs, Word or Excel files | $0.80 per 1,000 pages (empty pages free) |
| `specstream_find_list` | `request`, `maxResults` (1 to 1000, default 25) | Reads the request, prices it, starts it only within `maxPriceUsd`, waits up to `waitSeconds` (7 minutes by default) and returns every row | Only delivered rows |
| `specstream_get_list_results` | `listId` | Every row found so far, for a list that was still running | Free |

When the price is above your maximum, nothing runs: the tool returns `status: "over_maximum"` and the price, so the agent can ask for fewer rows or tell the user. When a request is too vague to price ("clinics"), it returns `status: "needs_edit"` and how SpecStream read it, so the agent can add the place or the conditions.

Settings, all optional except the price:

| Option | Default | What it does |
| --- | --- | --- |
| `maxPriceUsd` | required | The most one list may cost, in US dollars. Not a tool input |
| `apiKey` | `SPECSTREAM_API_KEY` | Your SpecStream API key |
| `waitSeconds` | `420` | How long `specstream_find_list` waits before returning the rows found so far |
| `pollIntervalSeconds` | `3` | Seconds between checks while a list runs |
| `locale` | `en-US` | The language and region the request is written in |
| `baseUrl` | `https://api.specstream.ai` | The SpecStream API address |
| `fetch` | global `fetch` | Your own `fetch`, for a proxy or a test |

Running on a serverless function? Set `waitSeconds` below the function's time limit. A list that's still running when the wait ends comes back with its `list_id`, and the agent reads the rest with `specstream_get_list_results`.

## Without a model

The client the tools are built on is exported, for the same calls from your own code:

```ts
import { SpecStreamClient } from "@specstream/ai-sdk";

const client = new SpecStreamClient({ apiKey: process.env.SPECSTREAM_API_KEY });

const list = await client.findList("Breweries in Portland, Oregon that host events, with their website", {
  maxResults: 25,
  maxPriceUsd: 3,
});

if ("rows" in list) console.log(list.row_count, list.rows[0].source_url);
else console.log(list.message); // "over_maximum" or "needs_edit": nothing ran
```

## Money, plainly

- `maxPriceUsd` lives in your code. The model never sees it and can't change it.
- You pay for rows that match. Candidates SpecStream couldn't confirm are left out and aren't billed.
- A retried step asking for the same list within the hour gets the list it already started, not a second bill. Agents retry. Your card shouldn't notice.
- Rates and plans: [specstream.ai/pricing](https://specstream.ai/pricing).

## When to reach for it

When the answer is many things that meet conditions: companies in a city, clinics with a service, funding filings, open grants, tenders, repositories, people in a role. For a single fact or a summary of one page, a search tool fits better.

## Versions

Works with AI SDK 6 and 7 (`ai` ^6 or ^7) and zod 3.25.76 or 4. Node 18 or newer to run it; AI SDK 7 itself needs Node 22.

## More

- [SpecStream docs](https://specstream.ai/docs) and the [AI SDK page](https://specstream.ai/docs/vercel-ai-sdk)
- Agents outside the AI SDK: the [MCP server](https://specstream.ai/docs/mcp) at `https://api.specstream.ai/mcp`
- The [TypeScript SDK](https://www.npmjs.com/package/@specstream/sdk) for everything else in the API
- Questions: support@specstream.ai

MIT licensed. Made by [SpecStream](https://specstream.ai), the live web data engine for teams and agents.
