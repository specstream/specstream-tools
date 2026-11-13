# SpecStream for Convex

[![npm version](https://img.shields.io/npm/v/@specstream/convex.svg)](https://www.npmjs.com/package/@specstream/convex)

[SpecStream](https://specstream.ai) is the live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. This component puts those records in your Convex tables as they arrive, so your UI updates while the run works.

Source URL and read time on every value.

```ts
const specstream = new SpecStreamClient(components.specstream);

// One call. The price is capped by your code, and nothing runs above the cap.
const result = await specstream.findList(ctx, {
  request: "open-source vector databases on GitHub with more than 5,000 stars, with their license",
  rows: 100,
  maxPriceUsd: 15,
  onComplete: internal.lists.onFinished,
});

// Rows land in your tables as SpecStream finds them.
const page = await specstream.listRows(ctx, {
  listId: result.listId,
  paginationOpts: { numItems: 50, cursor: null },
});
```

You pay for each row delivered, and a run that finds nothing costs nothing. A free account starts with $10 of credit and needs no card.

## What you get

| | |
| --- | --- |
| `findList` | Read a request, price it, and start it only when the most it can cost is within your maximum |
| `quote` and `approve` | The same in two steps: show the person the price, then approve exactly that price |
| `getList` and `listRows` | Status, a live row count and the rows, as plain Convex queries your client subscribes to |
| Every row's page | Each cell carries its source URL and read time. `row.sourceUrl` is the page behind the row |
| `onComplete` | Your mutation runs once when the list finishes, with whatever context you passed |
| Webhook route | Optional. SpecStream calls your deployment when a list finishes, so it shows up without waiting for a status check |
| `cancel`, `resume`, `deleteList` | Stop a list and keep the rows found so far, pick tracking back up, clean up |

Lists take minutes, so they outlive any single action. The component owns the `quotes`, `lists` and `rows` tables, follows each list until it is done, and exposes plain queries. Your UI subscribes to a list the way it subscribes to anything else in Convex.

## Install

```sh
npm install @specstream/convex
```

Add the component to your app and wire the API key through typed component env:

```ts
// convex/convex.config.ts
import { defineApp } from "convex/server";
import { v } from "convex/values";
import specstream from "@specstream/convex/convex.config";

const app = defineApp({
  env: {
    SPECSTREAM_API_KEY: v.string(),
    SPECSTREAM_WEBHOOK_SECRET: v.optional(v.string()),
  },
});

app.use(specstream, {
  // Mounts the webhook route at <your-site>/specstream/webhook. Optional.
  httpPrefix: "/specstream/",
  env: {
    SPECSTREAM_API_KEY: app.env.SPECSTREAM_API_KEY,
    SPECSTREAM_WEBHOOK_SECRET: app.env.SPECSTREAM_WEBHOOK_SECRET,
  },
});

export default app;
```

Create a key under **Agents & API** in your [SpecStream workspace](https://specstream.ai/workspace/agents), then set it on your deployment:

```sh
npx convex env set SPECSTREAM_API_KEY ss_live_your_key
npx convex dev
```

Give the key a spending limit in the workspace too. It stacks with the cap in your code.

## Search the web and read pages

Two calls need no quote and no list. Both are charged to your API key when they run, so keep them behind your own sign-in check like any spending action.

```ts
// convex/web.ts
import { v } from "convex/values";
import { SpecStreamClient } from "@specstream/convex";
import { action } from "./_generated/server";
import { components } from "./_generated/api";

const specstream = new SpecStreamClient(components.specstream);

export const search = action({
  args: { q: v.string() },
  handler: async (ctx, args) => await specstream.webSearch(ctx, args.q, { passages: true }),
});

export const readPages = action({
  args: { urls: v.array(v.string()) },
  handler: async (ctx, args) => await specstream.extractPages(ctx, args.urls),
});
```

`webSearch` calls the Search API (`GET /v1/web-search`, $5 per 1,000 searches of up to 10 results). Pass `{ speed: "fast" }` for the ranked results in about a second: a fast search costs $1 per 1,000. `extractPages` calls the Extract API (`POST /v1/extract`, up to 20 URLs a call, web pages, PDF, Word and Excel, $0.80 per 1,000 pages, a page with no text is free). Pass `{ format: "text" }` for plain text instead of markdown.

## Drive a real browser

```ts
export const readInBrowser = action({
  args: { url: v.string() },
  handler: async (ctx, args) => {
    const session = await specstream.openBrowser(ctx, { timeoutSeconds: 120 });
    try {
      await specstream.browserStep(ctx, session.sessionId, "browser_navigate", { url: args.url });
      return await specstream.browserStep(ctx, session.sessionId, "browser_read");
    } finally {
      await specstream.closeBrowser(ctx, session.sessionId);
    }
  },
});
```

`openBrowser` opens a real browser that SpecStream runs (`POST /v1/browser/sessions`, $0.10 an hour, charged by the second). `browserStep` runs one step at $0.001: `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type` and the other Playwright MCP tools, or `browser_read` for the page's text. The browser ends by itself after `timeoutSeconds` (60 to 3600, default 300); `closeBrowser` ends it sooner. Pass `{ includeConnectUrl: true }` to drive it with Playwright or Puppeteer from a Node action over `connect_url`, and keep that address on the server.

## Find a list

Call the component from your own actions. Authentication, authorization and rate limiting belong in your app: components can't see `ctx.auth`. The [example app](example/convex/example.ts) shows the full pattern, with a `requireUser` gate on every spending endpoint and an app-owned list to user table checked before any list can be read, canceled or deleted.

```ts
// convex/lists.ts
import { v } from "convex/values";
import { SpecStreamClient } from "@specstream/convex";
import { action } from "./_generated/server";
import { components } from "./_generated/api";

const specstream = new SpecStreamClient(components.specstream);

export const findRepositories = action({
  args: {},
  handler: async (ctx) => {
    const result = await specstream.findList(ctx, {
      request: "open-source vector databases on GitHub with more than 5,000 stars, with their license",
      rows: 100,
      maxPriceUsd: 15,
    });
    if (result.status === "needs_edit") return result.message; // add the place, or what every row must meet
    if (result.status === "over_maximum") return result.message; // nothing ran
    return result.listId; // subscribe to this
  },
});
```

`findList` returns one of three things:

- `started`: the list is running. `listId` is its id in your database, `link` opens it in the SpecStream workspace.
- `needs_edit`: SpecStream couldn't price the request as written. `readAs` is what it understood, so you can show what was missing. Nothing ran.
- `over_maximum`: the most the list can cost is above `maxPriceUsd`. Nothing ran.

Your request can name its own row count ("50 open-source vector databases on GitHub"). `rows` is the count you are pricing for, from 1 to 1000.

### Show the price first

When a person should see the price before anything runs, use the two steps. `quote` reads the request and prices it. `approve` starts the list, and `confirmMaxCents` has to equal the quote's own maximum, so the amount approved is always the amount shown.

```ts
const quote = await specstream.quote(ctx, {
  request: "dentists in Lisbon that take new patients",
  rows: 50,
});
if (quote.status === "quoted") {
  // Show quote.maximumCents, then, when the person says yes:
  await specstream.approve(ctx, {
    quoteId: quote.quoteId,
    confirmMaxCents: quote.maximumCents,
    idempotencyKey: `${userId}-${quote.quoteId}`, // a double click starts one list
  });
}
```

The maximum is a ceiling. You pay for each row delivered. Approving the same quote twice starts one list, and an expired quote runs nothing.

## Read the rows

```ts
// convex/lists.ts
export const rows = query({
  args: { listId: v.string(), paginationOpts: paginationOptsValidator },
  handler: async (ctx, args) => {
    // Check that the caller owns this list first.
    return await specstream.listRows(ctx, args);
  },
});
```

```tsx
// React
const { results, status, loadMore } = usePaginatedQuery(
  api.lists.rows,
  { listId },
  { initialNumItems: 50 },
);
```

The count climbs as rows arrive. Each row looks like this:

```ts
{
  entityId: "...",            // SpecStream's id for the thing the row describes
  ordinal: 26,
  sourceUrl: "https://www.sec.gov/Archives/edgar/data/2052031/000205203126000006/primary_doc.xml",
  observedAt: "2026-10-14T19:56:02.016693Z",
  cells: [
    { columnId: "organization", label: "Organization", display: "RapidCanvas Inc", sourceUrl: "https://www.sec.gov/...", observedAt: "..." },
    { columnId: "amount_sold", label: "Amount sold (USD)", display: "28999988", sourceUrl: "https://www.sec.gov/...", observedAt: "..." },
  ],
}
```

A fact a source doesn't publish has an empty `display` and an `absence` such as "Not published". It is never guessed. `flattenRow(row)` gives one field per column label, ready for a table or a prompt:

```ts
import { flattenRow } from "@specstream/convex";

flattenRow(row);
// { entityId, position: 26, Organization: "RapidCanvas Inc", "Amount sold (USD)": "28999988",
//   sourceUrl: "https://www.sec.gov/...", checkedAt: "2026-10-14T19:56:02Z" }
```

Other reads: `getList` (status and progress), `listLists`, `getRow`, `getListBySpecstreamId` and `getQuote`.

## When a list finishes

Pass an `onComplete` mutation and it runs once when the list reaches a final state: `completed`, `partial` (SpecStream finished with the rows it found, fewer than you asked for), `failed`, `canceled` or `expired`.

```ts
import type { ListCompletePayload } from "@specstream/convex";

export const onFinished = internalMutation({
  args: {
    listId: v.string(),
    specstreamListId: v.string(),
    status: v.string(),
    rowCount: v.number(),
    requestedCount: v.number(),
    error: v.optional(v.string()),
    context: v.optional(v.any()),
  },
  handler: async (ctx, args) => {
    // Mail the person, enrich the rows, mark the report ready.
  },
});
```

Whatever you passed as `context` comes back untouched.

## Webhook mode

By default the component checks each list every few seconds, backing off to fifteen. If you mount the HTTP route, SpecStream tells your deployment the moment a list finishes, and the component checks only slowly as a safety net. Webhooks belong to your SpecStream account, so register one once:

```ts
// npx convex run example:registerWebhook '{"siteUrl":"https://your-name.convex.site"}'
const { hookId, secret } = await specstream.registerWebhook(
  ctx,
  "https://your-name.convex.site/specstream/webhook",
);
```

```sh
npx convex env set SPECSTREAM_WEBHOOK_SECRET <the secret it returned>
```

Pass `mode: "webhook"` to `findList` or `approve` for lists you expect the webhook to finish. With the secret set, every delivery must carry a valid `Specstream-Signature` (signed over `<timestamp>.<body>`, refused after five minutes). Either way a delivery only wakes a list the component already tracks: rows always come from the SpecStream API with your key, never from the delivery.

SpecStream delivers webhooks only to public `https://` addresses on port 443, so a deployment on localhost uses the default checks.

## Use it for

- **Data inside your own app.** A user types a request in plain words and watches rows fill in, with the source URL and read time on every value.
- **A tool for your agent.** Wrap `findList` in a tool for your Convex agent. It picks the request and the row count, and your code owns the maximum.
- **A directory that fills itself.** Start a list per city or category from a scheduled function, store the rows, and render them from your own tables.
- **Market maps and research dashboards.** Rows ready for a table or a chart, with the page behind every value.

## Good to know

- **The component never spends on its own.** Every list starts from a quote, and the amount you approve must equal the quote's maximum. A mismatch, an expired quote or an account SpecStream can't authorize runs nothing.
- **Your app owns who may do what.** The component doesn't know about users. Keep an owner table like the example's and check it on every list-scoped call.
- **Errors are `ConvexError`s** with `data: { code, message, status? }`. Codes the component raises: `specstream_missing_api_key`, `specstream_empty_request`, `specstream_bad_rows`, `specstream_bad_maximum`, `specstream_unknown_quote`, `specstream_quote_expired`, `specstream_quote_not_approvable`, `specstream_approval_mismatch`, `specstream_bad_idempotency_key` and `specstream_request_failed`. SpecStream's own error codes arrive as `specstream_<code>`. A rate limit or a server error is retried three times first.
- **Tracking can stop.** After a key stops working, or after 400 status checks, the list is marked `failed` with a message starting "Stopped tracking this list". The list may still be running at SpecStream. Fix the key and call `resume`.
- **Convex's 1MB document limit.** Rows are small. A row that would exceed the limit loses its full detail set first, then its raw values, and keeps its displayed text and its page.
- **Reading is free.** `refresh` reads the latest status and rows now. Re-reading a list never duplicates rows.
- **Another base URL.** Set `SPECSTREAM_API_URL` to point the component at a different host, such as the mock in the example.

## Testing

Register the component with [`convex-test`](https://www.npmjs.com/package/convex-test), then stub `fetch` for `api.specstream.ai`:

```ts
import { convexTest } from "convex-test";
import specstream from "@specstream/convex/test";
import schema from "./schema";

const t = convexTest(schema, import.meta.glob("./**/*.*s"));
specstream.register(t);
```

The example app's [`setup.test.ts`](example/convex/setup.test.ts) and [`example.test.ts`](example/convex/example.test.ts) show a full run: quote, approve, rows, the completion callback, and one person unable to read another's list.

## Try it locally

[`example/mock-specstream.mjs`](example/mock-specstream.mjs) implements the calls the component makes and fills a list in at one row a second, so you can watch rows arrive without spending anything. From this folder:

```sh
npm install

# terminal 1: the stand-in for SpecStream
SPECSTREAM_WEBHOOK_SECRET=whsec-mock npm run dev:mock

# terminal 2: point the component at it, then start Convex
npx convex env set SPECSTREAM_API_KEY ss_mock_key
npx convex env set SPECSTREAM_API_URL http://127.0.0.1:4343
# The CLI calls functions without signing in. This lets the walkthrough run.
# Local deployments only: never set it on anything reachable from the internet.
npx convex env set DEMO_ALLOW_ANONYMOUS true
npm run dev
```

Then, from a third terminal:

```sh
npx convex run example:quoteList '{"request":"open-source vector databases on GitHub","rows":10}'
npx convex run example:approveList '{"quoteId":"<quoteId from above>","confirmMaxCents":150}'
npx convex run example:myLists
```

To use the real service, remove `SPECSTREAM_API_URL` and set a real key. See the [example README](example/README.md).

## FAQ

**What does a list cost?** The quote shows the maximum before anything runs. You pay for each row delivered, and a search that finds nothing costs nothing. Rates are on the [pricing page](https://specstream.ai/pricing).

**Can the model or the browser raise the price?** No. The maximum is an argument in your server code. `confirmMaxCents` has to match the quote the component saved.

**What if my deployment restarts mid-list?** The list keeps running at SpecStream and the component's scheduled checks continue from the database. Rows already stored stay stored.

**Where do I see the list outside Convex?** Every list has a `link` that opens it in your SpecStream workspace, where it can be sent to Sheets or a CRM.

**Which requests work?** Anything you can say in a sentence that has a place or a condition every row must meet. A request that is too loose comes back as `needs_edit` with what SpecStream read.

## Development

```sh
npm install        # npm 11 resolves this repo's peer graph; npm 10 may stop with an arborist error
npm run build      # compile to dist/
npm test           # vitest, including the example app
npm run typecheck  # the component, the example, and the example's Convex functions
npm run lint
```

The files under `_generated/` are committed, the way Convex components publish them. After changing a function's arguments or return value, run `npx convex dev` once against a deployment to regenerate them, or edit `src/component/_generated/component.ts` by hand to match.

## License

MIT. See [LICENSE](LICENSE).
