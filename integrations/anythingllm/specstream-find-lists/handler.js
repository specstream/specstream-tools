// SpecStream: find a list. AnythingLLM custom agent skill (MIT).
// https://github.com/specstream/specstream-tools/tree/main/integrations/anythingllm
//
// One call does the whole job: read the request, get the price, ask the person to approve it,
// start the list, and hand back every row with the page it came from. Pass list_id to read a
// list that is already started.

const crypto = require("crypto");

const BASE_URL = "https://api.specstream.ai";
const LIST_URL = "https://specstream.ai/workspace/collections/";
const FINISHED = ["completed", "partial", "failed", "canceled", "expired"];
// The most one list can ever be quoted for through this skill, whatever MAX_PRICE_USD says.
const HARD_CEILING_CENTS = 50000;

class SpecStreamError extends Error {}

async function send(apiKey, method, path, body) {
  let response;
  try {
    response = await fetch(BASE_URL + path, {
      method,
      redirect: "error",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
        "User-Agent": "specstream-anythingllm/1.0.0",
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(60000),
    });
  } catch (_) {
    throw new SpecStreamError("Could not reach SpecStream. Try again in a moment.");
  }
  let payload = null;
  try {
    payload = await response.json();
  } catch (_) {
    payload = null;
  }
  if (!response.ok) {
    const message = payload?.error?.message || `SpecStream answered HTTP ${response.status}.`;
    if (
      response.status === 401 ||
      response.status === 403 ||
      (response.status === 404 && message === "This page isn't available.")
    ) {
      throw new SpecStreamError(
        "SpecStream did not accept this API key. Check the key in the skill's settings."
      );
    }
    throw new SpecStreamError(message);
  }
  if (!payload || typeof payload.data !== "object" || payload.data === null) {
    throw new SpecStreamError("SpecStream returned an unexpected answer.");
  }
  return payload.data;
}

const dollars = (cents) => (Number(cents || 0) / 100).toFixed(2);
const wholeNumber = (value, fallback, min, max) => {
  const n = Math.round(Number(value));
  return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback;
};
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Columns the workspace shows as buttons (open the site, open why it matches), not facts.
const SCREEN_ONLY = new Set(["matches", "open"]);

function describeRow(record) {
  const values = [];
  const pages = [];
  for (const cell of record.cells || []) {
    const label = String(cell.label || cell.column_id || "").trim();
    if (!label || SCREEN_ONLY.has(cell.column_id)) continue;
    const shown = cell.display ?? cell.value;
    values.push(`${label}: ${shown === null || shown === undefined || shown === "" ? "-" : shown}`);
    const url = cell.provenance?.source_url;
    if (url && !pages.includes(url)) pages.push(url);
  }
  const checked = (record.cells || []).map((c) => c.provenance?.observed_at).find(Boolean);
  return (
    `${(record.ordinal ?? 0) + 1}. ${values.join("; ")}` +
    (pages.length ? `\n   Pages: ${pages.slice(0, 3).join(" ")}` : "") +
    (checked ? `\n   Checked: ${checked}` : "")
  );
}

async function readRows(ctx, apiKey, listId, waitSeconds, cursor) {
  const limit = wholeNumber(ctx.runtimeArgs?.MAX_ROWS, 25, 1, 100);
  let path = `/v1/finds/${encodeURIComponent(listId)}/rows?limit=${limit}`;
  if (cursor) path += `&cursor=${encodeURIComponent(cursor)}`;
  let page = await send(apiKey, "GET", path);
  const deadline = Date.now() + waitSeconds * 1000;
  while (!FINISHED.includes(page.status) && Date.now() < deadline) {
    ctx.introspect(`Reading the web: ${page.accepted_count || 0} rows so far.`);
    await sleep(5000);
    page = await send(apiKey, "GET", path);
  }
  const rows = (page.rows || []).map(describeRow);
  const finished = FINISHED.includes(page.status);
  const lines = [
    `List ${listId}: ${page.accepted_count || 0} rows found (${page.status}). Open it in SpecStream: ${LIST_URL}${listId}`,
  ];
  if (finished && page.commerce?.amount_captured_cents !== undefined) {
    lines.push(`Charged: $${dollars(page.commerce.amount_captured_cents)}.`);
  }
  lines.push(rows.length ? rows.join("\n") : "No rows yet.");
  if (page.next_cursor) {
    lines.push(`More rows: call this skill again with list_id "${listId}" and cursor "${page.next_cursor}".`);
  }
  if (!finished) {
    lines.push(
      `The list is still being built and keeps going. Call this skill again later with list_id "${listId}" for the rest.`
    );
  }
  return lines.join("\n");
}

async function findList(ctx, apiKey, request, count) {
  const args = ctx.runtimeArgs || {};
  const capCents = Math.min(
    HARD_CEILING_CENTS,
    Math.round((Number.parseFloat(args.MAX_PRICE_USD) || 5) * 100)
  );
  const wait = wholeNumber(args.WAIT_SECONDS, 90, 0, 150);

  ctx.introspect("Reading your request.");
  const reading = await send(apiKey, "POST", "/v1/parse", { q: request, locale: "en-US" });
  // The reading starts with the engine's default count; say the count this request asks for.
  const readAs = String(reading.read_back || reading.canonical_sentence || request).replace(/^\d[\d,]*(?=\s)/, String(count));
  if (reading.status !== "runnable" || !reading.ast_hash) {
    return `SpecStream needs a clearer request before it can price it. It read: "${readAs}". Ask the person to add the place, the kind of thing, or what every row must meet, then call this skill again.`;
  }

  ctx.introspect("Getting the price.");
  const quote = await send(apiKey, "POST", "/v1/capacity/quotes", {
    ast_hash: reading.ast_hash,
    operation: "find",
    requested_units: count,
  });
  const maximum = Number(quote.maximum_cents);
  if (maximum > capCents) {
    return `The most this list can cost is $${dollars(maximum)}, above the cap of $${dollars(capCents)} set for this skill, so it did not start and nothing was charged. Offer fewer rows, or tell the person the cap is MAX_PRICE_USD in the skill settings.`;
  }
  if (quote.can_authorize === false) {
    return "SpecStream cannot start this list yet (balance or plan). Nothing was charged. Tell the person to check their balance at https://specstream.ai.";
  }

  const requestKey =
    "anythingllm-" + crypto.createHash("sha256").update(String(quote.quote_id)).digest("hex").slice(0, 32);
  let started = null;
  try {
    started = await send(apiKey, "GET", `/v1/capacity/requests/${encodeURIComponent(requestKey)}`);
  } catch (_) {
    started = null;
  }

  if (!started?.find_id) {
    if (String(args.APPROVAL || "ask").trim().toLowerCase() !== "within_cap") {
      const answer = await ctx.requestToolApproval({
        payload: { list: readAs, rows_asked_for: count, most_it_can_cost_usd: dollars(maximum) },
        description: `Read the web for this list: "${readAs}". It can cost at most $${dollars(maximum)}, and you pay for each result delivered.`,
      });
      if (!answer?.approved) {
        return answer?.message || "The person did not approve the price. Nothing ran and nothing was charged.";
      }
    }
    ctx.introspect("Starting the list.");
    started = await send(apiKey, "POST", "/v1/capacity/executions", {
      quote_id: quote.quote_id,
      quote_hash: quote.quote_hash,
      confirm_max_cents: maximum,
      idempotency_key: requestKey,
    });
  }
  if (!started?.find_id) return "SpecStream did not return a list ID. Nothing was charged.";

  const text = await readRows(ctx, apiKey, started.find_id, wait);
  return `${text}\nThe most it could have cost was $${dollars(maximum)}.`;
}

module.exports.runtime = {
  handler: async function ({ request = "", count = 25, list_id = "", cursor = "" }) {
    try {
      const apiKey = String(this.runtimeArgs?.SPECSTREAM_API_KEY || "").trim();
      if (!apiKey) {
        return "No SpecStream API key is set. Add one in this skill's settings (create it under Agents & API at https://specstream.ai).";
      }
      const listId = String(list_id || "").trim();
      if (listId) {
        if (!listId.startsWith("fnd_")) return "Pass the list ID from an earlier run. It starts with fnd_.";
        return await readRows(this, apiKey, listId, 0, String(cursor || "").trim());
      }
      const asked = String(request || "").trim();
      if (!asked) return "Describe the list to find, for example: roofing companies in Columbus, Ohio with their phone number.";
      return await findList(this, apiKey, asked, wholeNumber(count, 25, 1, 10000));
    } catch (error) {
      this.logger(`SpecStream skill error: ${error.message}`);
      return error instanceof SpecStreamError
        ? error.message
        : "SpecStream could not finish this request. Nothing more was charged. Try again in a moment.";
    }
  },
};
