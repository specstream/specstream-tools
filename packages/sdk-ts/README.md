# @specstream/sdk

TypeScript client for [SpecStream](https://specstream.ai), the live web data engine for teams and agents. Describe the list you need in plain words; SpecStream reads the web where those things live, hands back only the matches, each with the page it came from, and you pay for each result delivered.

The client has no runtime dependencies and needs Node 22 or newer. It uses the same account, permissions, projects and balance as the workspace.

```sh
npm install @specstream/sdk
```

Create an API key under **Agents & API** in your SpecStream workspace and keep it in the environment: `SPECSTREAM_API_KEY`.

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

New accounts start with $10 of work for 30 days, no card. A delivered result costs 10 cents, 30 cents or $1 depending on how many facts it carries. No result, no charge. See [pricing](https://specstream.ai/pricing).

## Links

- [SDK docs](https://specstream.ai/docs/sdk) and [API docs](https://specstream.ai/docs/api)
- [Source and issues](https://github.com/specstream/specstream-tools)
- [Python client](https://pypi.org/project/specstream-client/)
- Support: support@specstream.ai

MIT license.
