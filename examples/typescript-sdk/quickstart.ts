// Read a request, show the price, ask, run it, and print the first results.
//
//   export SPECSTREAM_API_KEY="ss_live_..."
//   npm install
//   npm start -- "Open-source vector databases on GitHub with more than 5,000 stars, with their license."
//
// Nothing runs until you type yes. The request key is derived from the quote, so
// running this twice on the same quote never pays twice.
import { createInterface } from "node:readline/promises";
import { Client } from "@specstream/sdk";

const request = process.argv[2];
if (!request) {
  console.error('usage: npm start -- "what you need, in your own words"');
  process.exit(2);
}

const client = new Client({
  apiKey: process.env.SPECSTREAM_API_KEY ?? "",
  baseUrl: process.env.SPECSTREAM_BASE_URL ?? "https://api.specstream.ai",
});

const read = await client.compile(request);
const quote = await client.quoteCapacityWork({
  ast_hash: String(read.ast_hash),
  operation: "find",
  requested_units: (read.ast as { limit: { max: number } }).limit.max,
});
console.log(`Up to ${(quote.maximum_cents / 100).toFixed(2)} ${quote.currency ?? "USD"}. The price is good until ${quote.expires_at}.`);

const prompt = createInterface({ input: process.stdin, output: process.stdout });
const answer = await prompt.question("Run it? Type yes to approve that maximum: ");
prompt.close();
if (answer.trim().toLowerCase() !== "yes") {
  console.log("Nothing was run.");
  process.exit(0);
}

const run = await client.authorizeCapacityWork({
  quote_id: quote.quote_id,
  quote_hash: quote.quote_hash,
  confirm_max_cents: quote.maximum_cents,
  idempotency_key: `quickstart-${quote.quote_id}`,
});
if (!run.find_id) throw new Error("The work was not started. Run again to recover it with the same key.");
const findId = run.find_id;

for (;;) {
  const state = await client.getFind(findId);
  if (state.status === "completed" || state.status === "partial") break;
  if (state.status === "failed" || state.status === "canceled" || state.status === "expired") {
    console.error(`The run ended as ${state.status}. What it found is kept.`);
    process.exit(1);
  }
  await new Promise((resolve) => setTimeout(resolve, 3000));
}

let shown = 0;
let cursor: string | null = null;
while (shown < 5) {
  const page = await client.rows(findId, cursor);
  for (const row of page.rows.slice(0, 5 - shown)) {
    console.log(JSON.stringify(row).slice(0, 400));
    shown += 1;
  }
  cursor = page.next_cursor ?? null;
  if (!cursor) break;
}
console.log(`Run ${findId}: open it in the workspace to see the source behind each fact.`);
