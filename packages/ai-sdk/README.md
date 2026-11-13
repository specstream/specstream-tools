# @specstream/ai-sdk

[SpecStream](https://specstream.ai) is the live web data engine for teams and agents. One platform to build, search, extract, enrich, map, and monitor data across the entire web. Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. Source URL and read time on every value.

```bash
npm install @specstream/ai-sdk ai zod
export SPECSTREAM_API_KEY=ss_live_...   # Agents & API in your SpecStream workspace
```

A free account comes with $10 of credit and needs no card: [specstream.ai](https://specstream.ai/signup).

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
| `specstream_web_search` | `q`, `passages` | Calls `GET /v1/web-search` and returns the answer, matching rows, ranked sources and optional page passages | $5 per 1,000 searches of up to 10 results, $1 per 1,000 with `speed=fast` |
| `specstream_extract_pages` | `urls`, `format` | Calls `POST /v1/extract` and returns the clean main text, title and published date of 1 to 20 web pages, PDFs, Word or Excel files | $0.80 per 1,000 pages (empty pages free) |
| `specstream_find_list` | `request`, `maxResults` (1 to 1000, default 25) | Reads the request, prices it, starts it only within `maxPriceUsd`, waits up to `waitSeconds` (7 minutes by default) and returns every row | Only delivered rows |
| `specstream_get_list_results` | `listId` | Every row found so far, for a list that was still running | Free |

When the price is above your maximum, nothing runs: the tool returns `status: "over_maximum"` and the price, so the agent can ask for fewer rows or tell the user. When a request is too vague to price, it returns `status: "needs_edit"` and how SpecStream read it, so the agent can add the place or the conditions.

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
| `monitorMaxPricePerRunUsd` | not set | The most one check of a monitored list may cost. Set it to give the model the two monitor tools |
| `monitorMaxPricePerMonthUsd` | per check × checks in 31 days | The most one monitor may spend in a UTC calendar month |

Running on a serverless function? Set `waitSeconds` below the function's time limit. A list that's still running when the wait ends comes back with its `list_id`, and the agent reads the rest with `specstream_get_list_results`.

## Browser sessions

Some pages show nothing until a button is clicked, a form is filled in or their JavaScript runs. For those, the agent opens a real browser that SpecStream runs, drives it step by step and closes it.

```ts
import { generateText, stepCountIs } from "ai";
import { specstreamBrowserTools } from "@specstream/ai-sdk";

const { text } = await generateText({
  model: "openai/gpt-5-mini",
  tools: specstreamBrowserTools({ timeoutSeconds: 300, allowedDomains: ["example.com"] }),
  stopWhen: stepCountIs(12),
  prompt: "Open example.com, accept the cookie banner and read the pricing table.",
});
```

| Tool | Input | What it does | Price |
| --- | --- | --- | --- |
| `specstream_open_browser` | `url` (optional) | Calls `POST /v1/browser/sessions` with the limits you set in code and returns the `session_id` | $0.10 an hour of browser time, charged by the second |
| `specstream_browser_navigate` | `session_id`, `url` | Opens the address | $1 per 1,000 steps |
| `specstream_browser_read` | `session_id`, `format` | The page's text as it stands after its JavaScript ran, in Markdown or plain text | $1 per 1,000 steps |
| `specstream_browser_snapshot` | `session_id` | The page's links, buttons and fields, each with a reference | $1 per 1,000 steps |
| `specstream_browser_click`, `specstream_browser_type` | `session_id`, `target`, `text` | Clicks an element or types into a field, by its reference | $1 per 1,000 steps |
| `specstream_browser_action` | `session_id`, `tool`, `arguments` | Any other Playwright MCP step: a key press, a select, a wait, a form | $1 per 1,000 steps |
| `specstream_close_browser` | `session_id` | Calls `POST /v1/browser/sessions/{id}/release` and returns the seconds, the steps and the charge | Free |

`timeoutSeconds` (60 to 3600, default 300) is set in your code and is not a tool input: the browser ends then, whatever the model does, so 300 seconds is at most $0.0084 of time. `idleTimeoutSeconds` (default 120) ends a browser no step has touched. `allowedDomains` keeps the browser on the hosts you name, `blockMedia` skips images, video and fonts. A page a site or your own list refuses comes back as an `error` the agent can read, not an exception. Spread both sets into one agent with `tools: { ...specstreamTools({ maxPriceUsd: 5 }), ...specstreamBrowserTools() }`.

Without a model, the same calls are on the client: `openBrowser()`, `browserStep(sessionId, tool, args)`, `browserSession(sessionId)` and `closeBrowser(sessionId)`.

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

## Keep a list current on a schedule

A monitor checks a list again on the live web every hour, day, week or month.
Each check is a refresh: half the row rate for a row that changed or is new, and 1¢ for a row that comes back unchanged.

```ts
import { SpecStreamClient } from "@specstream/ai-sdk";

const client = new SpecStreamClient();

const monitor = await client.monitorList("fnd_gk5y3d0r97bvyz0t08zzh75kr6", {
  every: "week",
  maxPricePerRunUsd: 2,
  maxPricePerMonthUsd: 8,
});

if (monitor.status === "saved") console.log(monitor.monitor_id, monitor.next_run_at);
else console.log(monitor.message); // "over_maximum": one check costs more than maxPricePerRunUsd, nothing was saved
```

The client prices one check before it saves anything.
When one check can cost more than `maxPricePerRunUsd`, nothing is saved.
`maxPricePerMonthUsd` is the most the monitor spends in one UTC calendar month, checks run on demand included.
Without it, the limit is `maxPricePerRunUsd` times the checks in 31 days.
The first check runs one interval after the current hour began, and the monitor ends a year after it, unless you set `firstRunAt` and `until`.

| Call | What it does | Cost |
| --- | --- | --- |
| `monitorList(listId, options)` | Prices one check of the list and saves the schedule within your limits | Each check, within the limits |
| `monitors()` | Every monitor of the account, with its state, next check and last list | Free |
| `monitorRuns(monitorId)` | The recent checks, newest first: when, the outcome, the reason and the list each one made | Free |
| `runMonitorNow(monitorId)` | One check now, inside the monitor's limits. The regular times stay as they are | One check |
| `pauseMonitor(monitorId)`, `resumeMonitor(monitorId)` | Stops and starts the checks. A missed check is never bought later | Free |
| `deleteMonitor(monitorId)` | Ends the monitor. The lists it made stay yours | Free |

To let an agent start monitors, give the tools a maximum per check.
The model then gets `specstream_monitor_list` (it picks the list and how often) and `specstream_list_monitors`.
Without `monitorMaxPricePerRunUsd`, the model can't start recurring work.

```ts
const tools = specstreamTools({ maxPriceUsd: 5, monitorMaxPricePerRunUsd: 2, monitorMaxPricePerMonthUsd: 20 });
```

Where each check's new and changed rows go (Slack, email, a sheet, a CRM or a webhook) is set on the monitor in your SpecStream workspace.

## Money, plainly

- `maxPriceUsd` and the monitor limits live in your code. The model never sees them and can't change them.
- You pay for rows that match. Candidates SpecStream couldn't confirm are left out and aren't billed.
- A retried step asking for the same list within the hour gets the list it already started, not a second bill. Agents retry. Your card shouldn't notice.
- Rates and plans: [specstream.ai/pricing](https://specstream.ai/pricing).

## When to reach for it

When the answer is many things that meet conditions. For a single fact or a summary of one page, a search tool fits better.

## Versions

Works with AI SDK 6 and 7 (`ai` ^6 or ^7) and zod 3.25.76 or 4. Node 18 or newer to run it; AI SDK 7 itself needs Node 22.

## More

- [SpecStream docs](https://specstream.ai/docs) and the [AI SDK page](https://specstream.ai/docs/vercel-ai-sdk)
- Agents outside the AI SDK: the [MCP server](https://specstream.ai/docs/mcp) at `https://api.specstream.ai/mcp`
- The [TypeScript SDK](https://www.npmjs.com/package/@specstream/sdk) for everything else in the API
- Questions: support@specstream.ai

MIT licensed. Made by [SpecStream](https://specstream.ai), the live web data engine for teams and agents.
