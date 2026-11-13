#!/usr/bin/env node
// The SpecStream command: Search API, Extract API and Deep Search with one key.
// One file with no dependencies, so the npm package and the single binary (Node SEA) run the same code.
"use strict";

const VERSION = "0.1.0";
const DEFAULT_BASE_URL = "https://api.specstream.ai";
const KEY_HELP =
  "Set SPECSTREAM_API_KEY (or pass --api-key). Create a key under Agents & API at https://specstream.ai/workspace";

const HELP = `specstream ${VERSION}: web search, page reading and Deep Search with one key

Usage:
  specstream search <question or keywords>   Search API: an answer and its sources from the live web
      --fast            the fast search ($1 per 1,000 searches; the default search is $5 per 1,000)
      --num <n>         how many results (default 10)
      --news            news results
      --country <cc>    two-letter country      --language <xx>  two-letter language
  specstream read <url> [<url> ...]          Extract API: the main text of up to 20 pages, PDF, Word or Excel
      --format <markdown|text>   (default markdown)
  specstream deep <request in plain words>   Deep Search: reads the request and prints the most it can cost.
      --results <n>     how many results to price (default 25)        Nothing runs and nothing is charged.
  specstream deep approve <quote_id> --max-cents <n>   start the priced work; <n> is the maximum you approve
      --key <text>      your own request key; a retry with the same key never pays twice
  specstream deep status <find_id>           progress of a run
  specstream deep rows <find_id> [--all]     the results, one JSON object per line

Options for every command:
  --json                print the API's JSON instead of text
  --api-key <key>       default: the SPECSTREAM_API_KEY environment variable
  --base-url <url>      default: ${DEFAULT_BASE_URL} (or SPECSTREAM_BASE_URL)
  --version, --help

${KEY_HELP}
`;

// Flags that take a value. Every other flag is a switch.
const VALUE_FLAGS = new Set([
  "num", "country", "language", "format", "results", "max-cents", "key", "api-key", "base-url", "limit",
]);
const SWITCHES = new Set(["fast", "news", "json", "all", "help", "version"]);

class Usage extends Error {}
class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function parseArgs(argv) {
  const flags = {};
  const words = [];
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--") {
      words.push(...argv.slice(i + 1));
      break;
    }
    if (arg === "-h") flags.help = true;
    else if (arg === "-v" || arg === "-V") flags.version = true;
    else if (arg.startsWith("--")) {
      const eq = arg.indexOf("=");
      const name = eq === -1 ? arg.slice(2) : arg.slice(2, eq);
      if (SWITCHES.has(name)) {
        if (eq !== -1) throw new Usage(`--${name} takes no value`);
        flags[name] = true;
      } else if (VALUE_FLAGS.has(name)) {
        const value = eq === -1 ? argv[(i += 1)] : arg.slice(eq + 1);
        if (value === undefined || value === "") throw new Usage(`--${name} needs a value`);
        flags[name] = value;
      } else throw new Usage(`Unknown option --${name}`);
    } else words.push(arg);
  }
  return { flags, words };
}

function wholeNumber(flags, name, fallback, min, max) {
  if (flags[name] === undefined) return fallback;
  const value = Number(flags[name]);
  if (!/^\d+$/.test(flags[name]) || !Number.isSafeInteger(value) || value < min || value > max)
    throw new Usage(`--${name} must be a whole number from ${min} to ${max}`);
  return value;
}

function errorText(status, parsed) {
  const error = parsed && typeof parsed === "object" ? parsed.error ?? parsed.detail ?? parsed : null;
  let said = "";
  if (typeof error === "string") said = error;
  else if (error && typeof error === "object") {
    said = [error.code, error.message].filter((part) => typeof part === "string" && part).join(": ");
    if (!said) said = JSON.stringify(error).slice(0, 400);
  }
  let hint = "";
  if (status === 401 || status === 403) hint = " " + KEY_HELP;
  if (status === 402) hint = " Add credit at https://specstream.ai/workspace";
  return `SpecStream answered HTTP ${status}${said ? ": " + said : ""}.${hint}`;
}

function makeApi({ apiKey, baseUrl, fetchFn }) {
  const base = baseUrl.replace(/\/+$/, "");
  const token = apiKey.toLowerCase().startsWith("bearer ") ? apiKey : `Bearer ${apiKey}`;
  return async function call(method, path, body) {
    let response;
    let text;
    try {
      response = await fetchFn(base + path, {
        method,
        headers: {
          Authorization: token,
          Accept: "application/json",
          "Content-Type": "application/json",
          "User-Agent": `specstream-cli/${VERSION}`,
        },
        // A redirect would carry the key to another address.
        redirect: "error",
        signal: AbortSignal.timeout(150_000),
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      text = await response.text();
    } catch (error) {
      throw new ApiError(`Could not reach ${base}: ${(error && error.message) || error}`, null);
    }
    let parsed = null;
    try {
      parsed = JSON.parse(text);
    } catch {
      if (response.ok) throw new ApiError(`${method} ${path} did not answer JSON`, response.status);
    }
    if (!response.ok) throw new ApiError(errorText(response.status, parsed), response.status);
    const data = parsed && typeof parsed === "object" ? parsed.data : null;
    if (!parsed || parsed.error != null || !data || typeof data !== "object")
      throw new ApiError(`${method} ${path} answered without data`, response.status);
    return data;
  };
}

function dollars(cents) {
  return "$" + (cents / 100).toFixed(2);
}

async function search(ctx, words, flags) {
  const q = words.join(" ").trim();
  if (!q) throw new Usage('Give the search: specstream search "latest stable release of PostgreSQL"');
  const query = new URLSearchParams({ q });
  if (flags.fast) query.set("speed", "fast");
  if (flags.num !== undefined) query.set("num", String(wholeNumber(flags, "num", 10, 1, 100)));
  if (flags.news) query.set("news", "true");
  if (flags.country) query.set("country", flags.country);
  if (flags.language) query.set("language", flags.language);
  const data = await ctx.api("GET", "/v1/web-search?" + query);
  if (flags.json) return ctx.json(data);
  if (data.answer && data.answer.value) {
    ctx.out(String(data.answer.value));
    if (data.answer.page) ctx.out("  " + data.answer.page);
    ctx.out("");
  }
  const sources = Array.isArray(data.sources) ? data.sources : [];
  sources.forEach((source, index) => {
    ctx.out(`${index + 1}. ${source.title || source.url}`);
    ctx.out(`   ${source.url}`);
    if (source.snippet) ctx.out(`   ${String(source.snippet).replace(/\s+/g, " ").trim()}`);
  });
  if (!sources.length && !(data.answer && data.answer.value)) ctx.err("No results.");
  if (typeof data.price_usd === "number") ctx.err(`$${data.price_usd} charged, ${data.took_ms} ms`);
  return 0;
}

async function read(ctx, words, flags) {
  if (!words.length) throw new Usage("Give at least one address: specstream read https://example.com");
  if (words.length > 20) throw new Usage("One call reads up to 20 addresses");
  const format = flags.format || "markdown";
  if (format !== "markdown" && format !== "text") throw new Usage("--format is markdown or text");
  const data = await ctx.api("POST", "/v1/extract", { urls: words, format });
  if (flags.json) return ctx.json(data);
  const results = Array.isArray(data.results) ? data.results : [];
  let ok = 0;
  for (const page of results) {
    if (page.status !== "ok") {
      ctx.err(`${page.url}: ${page.status}${page.reason ? " (" + page.reason + ")" : ""}`);
      continue;
    }
    ok += 1;
    // One page prints as its text alone, so it pipes into a file or another tool.
    if (words.length > 1) ctx.out(`--- ${page.url}${page.title ? " | " + page.title : ""} ---`);
    ctx.out(page.text);
    if (words.length > 1) ctx.out("");
  }
  if (typeof data.price_usd === "number") ctx.err(`$${data.price_usd} charged, ${data.took_ms} ms`);
  return ok ? 0 : 1;
}

function findId(words, what) {
  if (words.length !== 1) throw new Usage(`Give the run: specstream deep ${what} <find_id>`);
  return encodeURIComponent(words[0]);
}

async function deep(ctx, words, flags) {
  const sub = words[0];
  if (sub === "approve") return deepApprove(ctx, words.slice(1), flags);
  if (sub === "status") {
    const data = await ctx.api("GET", "/v1/finds/" + findId(words.slice(1), "status"));
    if (flags.json) return ctx.json(data);
    ctx.out(`${data.find_id}: ${data.status}, ${data.accepted_count} of ${data.requested_count} results`);
    if (data.stop_reason) ctx.out(`stopped: ${data.stop_reason}`);
    return 0;
  }
  if (sub === "rows") {
    const id = findId(words.slice(1), "rows");
    const limit = wholeNumber(flags, "limit", 100, 1, 100);
    let cursor = null;
    do {
      const query = new URLSearchParams({ limit: String(limit) });
      if (cursor) query.set("cursor", cursor);
      const page = await ctx.api("GET", `/v1/finds/${id}/rows?${query}`);
      const rows = Array.isArray(page.flat_rows) && page.flat_rows.length ? page.flat_rows : page.rows || [];
      for (const row of rows) ctx.out(JSON.stringify(row));
      cursor = page.next_cursor || null;
      if (cursor && !flags.all) ctx.err("More results: add --all");
    } while (cursor && flags.all);
    return 0;
  }
  const q = words.join(" ").trim();
  if (!q) throw new Usage('Give the request: specstream deep "open-source document-signing tools I can self-host"');
  const units = wholeNumber(flags, "results", 25, 1, 100000);
  const spec = await ctx.api("POST", "/v1/parse", { q, locale: "en-US" });
  if (!spec.ast_hash) {
    if (flags.json) ctx.json({ spec });
    ctx.err(spec.notice || "SpecStream could not read this request as a list. Say what to find and which facts to bring back.");
    return 1;
  }
  const quote = await ctx.api("POST", "/v1/capacity/quotes", {
    ast_hash: spec.ast_hash,
    operation: "find",
    requested_units: units,
  });
  if (flags.json) return ctx.json({ spec, quote });
  const reading = spec.read_back || spec.canonical_sentence || spec.label;
  if (reading) ctx.out(`Reading: ${reading}`);
  ctx.out(`Up to ${units} results cost at most ${dollars(quote.maximum_cents)}. You pay only for results delivered.`);
  ctx.out(`The price holds until ${quote.expires_at}. Nothing has run.`);
  ctx.out("To start it:");
  ctx.out(`  specstream deep approve ${quote.quote_id} --max-cents ${quote.maximum_cents}`);
  return 0;
}

async function deepApprove(ctx, words, flags) {
  if (words.length !== 1 || flags["max-cents"] === undefined)
    throw new Usage("Give the quote and the maximum you approve: specstream deep approve <quote_id> --max-cents <n>");
  const approved = wholeNumber(flags, "max-cents", 0, 1, 100000000);
  const quote = await ctx.api("GET", "/v1/capacity/quotes/" + encodeURIComponent(words[0]));
  if (quote.maximum_cents !== approved) {
    ctx.err(
      `Not started: this quote's maximum is ${quote.maximum_cents} cents and you approved ${approved}. ` +
        "Approve the quote's own maximum, or price the request again.",
    );
    return 1;
  }
  const key = flags.key || "cli-" + ctx.uuid();
  // Shown before the call: if the answer is lost, the same key starts nothing twice.
  ctx.err(`Request key: ${key}`);
  const run = await ctx.api("POST", "/v1/capacity/executions", {
    quote_id: quote.quote_id,
    quote_hash: quote.quote_hash,
    confirm_max_cents: approved,
    idempotency_key: key,
  });
  if (flags.json) return ctx.json(run);
  if (!run.find_id) {
    ctx.err(`The work was not started (${run.state}). Run the same command again with --key ${key}`);
    return 1;
  }
  ctx.out(`Started ${run.find_id}, at most ${dollars(run.maximum_cents)}.`);
  ctx.out(`  specstream deep status ${run.find_id}`);
  ctx.out(`  specstream deep rows ${run.find_id} --all`);
  return 0;
}

const COMMANDS = { search, read, extract: read, deep };

/** Runs one command and returns the exit code. Everything outside (network, streams, key) comes in by `io`. */
async function main(argv, io = {}) {
  const env = io.env || process.env;
  const out = io.out || ((line) => process.stdout.write(line + "\n"));
  const err = io.err || ((line) => process.stderr.write(line + "\n"));
  try {
    const { flags, words } = parseArgs(argv);
    if (flags.version) return out(VERSION), 0;
    const name = words[0];
    if (flags.help || !name || name === "help") return out(HELP), 0;
    const command = COMMANDS[name];
    if (!command) throw new Usage(`Unknown command "${name}"`);
    const apiKey = (flags["api-key"] || env.SPECSTREAM_API_KEY || "").trim();
    if (!apiKey) throw new Usage("No API key. " + KEY_HELP);
    const ctx = {
      out,
      err,
      json: (data) => (out(JSON.stringify(data, null, 2)), 0),
      uuid: io.uuid || (() => require("node:crypto").randomUUID()),
      api: makeApi({
        apiKey,
        baseUrl: flags["base-url"] || env.SPECSTREAM_BASE_URL || DEFAULT_BASE_URL,
        fetchFn: io.fetch || fetch,
      }),
    };
    return await command(ctx, words.slice(1), flags);
  } catch (error) {
    if (error instanceof Usage) return err(error.message), err("See: specstream --help"), 2;
    if (error instanceof ApiError) return err(error.message), 1;
    throw error;
  }
}

function isBinary() {
  try {
    return require("node:sea").isSea();
  } catch {
    return false;
  }
}

if (require.main === module || isBinary()) {
  main(process.argv.slice(2)).then(
    (code) => {
      process.exitCode = code;
    },
    (error) => {
      process.stderr.write(String((error && error.stack) || error) + "\n");
      process.exitCode = 1;
    },
  );
}

module.exports = { main, VERSION };
