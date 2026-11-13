// The specstream command against a scripted API: no network, no key that exists.
"use strict";

const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const path = require("node:path");
const test = require("node:test");

const { main, VERSION } = require("../bin/specstream.js");

/** Runs the command with scripted answers, in call order. Each answer is [status, body]. */
async function run(argv, answers = [], env = { SPECSTREAM_API_KEY: "ss_test_key" }) {
  const calls = [];
  const out = [];
  const err = [];
  const code = await main(argv, {
    env,
    out: (line) => out.push(line),
    err: (line) => err.push(line),
    uuid: () => "fixed-uuid",
    fetch: async (url, init) => {
      calls.push({ url, method: init.method, headers: init.headers, redirect: init.redirect, body: init.body ? JSON.parse(init.body) : undefined });
      const answer = answers.shift();
      if (!answer) throw new Error("no scripted answer for " + url);
      return new Response(typeof answer[1] === "string" ? answer[1] : JSON.stringify(answer[1]), { status: answer[0] });
    },
  });
  return { code, calls, out: out.join("\n"), err: err.join("\n") };
}

const ok = (data) => [200, { data, error: null }];

test("the version is the package's version", () => {
  assert.equal(VERSION, require("../package.json").version);
});

test("search sends the question with the key and prints the answer and its sources", async () => {
  const result = await run(["search", "latest", "PostgreSQL", "release", "--fast", "--num", "5"], [
    ok({
      answer: { value: "PostgreSQL 18", page: "https://www.postgresql.org/" },
      sources: [{ title: "PostgreSQL", url: "https://www.postgresql.org/", snippet: "The world's most\n advanced database" }],
      price_usd: 0.001,
      took_ms: 420,
    }),
  ]);
  assert.equal(result.code, 0);
  const [call] = result.calls;
  assert.equal(call.url, "https://api.specstream.ai/v1/web-search?q=latest+PostgreSQL+release&speed=fast&num=5");
  assert.equal(call.method, "GET");
  assert.equal(call.headers.Authorization, "Bearer ss_test_key");
  assert.equal(call.redirect, "error");
  assert.equal(
    result.out,
    "PostgreSQL 18\n  https://www.postgresql.org/\n\n1. PostgreSQL\n   https://www.postgresql.org/\n   The world's most advanced database",
  );
  assert.match(result.err, /\$0\.001 charged/);
});

test("the default search names no speed, so it is the default tier", async () => {
  const result = await run(["search", "hello"], [ok({ answer: null, sources: [] })]);
  assert.equal(result.calls[0].url, "https://api.specstream.ai/v1/web-search?q=hello");
  assert.match(result.err, /No results/);
});

test("--json prints the API's data as JSON", async () => {
  const data = { answer: null, sources: [{ url: "https://a.example/", title: "A" }] };
  const result = await run(["search", "a", "--json"], [ok(data)]);
  assert.deepEqual(JSON.parse(result.out), data);
});

test("read posts the addresses and prints one page's text alone", async () => {
  const result = await run(["read", "https://a.example/"], [
    ok({ results: [{ url: "https://a.example/", status: "ok", title: "A", text: "# A\nbody" }], price_usd: 0.0008, took_ms: 9 }),
  ]);
  assert.equal(result.code, 0);
  assert.equal(result.calls[0].url, "https://api.specstream.ai/v1/extract");
  assert.deepEqual(result.calls[0].body, { urls: ["https://a.example/"], format: "markdown" });
  assert.equal(result.out, "# A\nbody");
});

test("read names each page when there are several, reports a page it could not read, and fails when none was read", async () => {
  const pages = [
    { url: "https://a.example/", status: "ok", title: "A", text: "one" },
    { url: "https://b.example/", status: "blocked", reason: "robots", title: null, text: "" },
  ];
  const result = await run(["read", "https://a.example/", "https://b.example/", "--format=text"], [ok({ results: pages })]);
  assert.equal(result.code, 0);
  assert.equal(result.calls[0].body.format, "text");
  assert.match(result.out, /^--- https:\/\/a\.example\/ \| A ---\none\n$/);
  assert.match(result.err, /https:\/\/b\.example\/: blocked \(robots\)/);
  const none = await run(["read", "https://b.example/"], [ok({ results: [pages[1]] })]);
  assert.equal(none.code, 1);
});

test("deep reads and prices the request and starts nothing", async () => {
  const result = await run(["deep", "self-hosted signing tools", "--results", "40"], [
    ok({ ast_hash: "h1", read_back: "Self-hosted document-signing tools" }),
    ok({ quote_id: "q_1", quote_hash: "qh", maximum_cents: 600, expires_at: "2026-11-12T12:30:00Z" }),
  ]);
  assert.equal(result.code, 0);
  assert.deepEqual(result.calls.map((call) => call.method + " " + new URL(call.url).pathname), [
    "POST /v1/parse",
    "POST /v1/capacity/quotes",
  ]);
  assert.deepEqual(result.calls[0].body, { q: "self-hosted signing tools", locale: "en-US" });
  assert.deepEqual(result.calls[1].body, { ast_hash: "h1", operation: "find", requested_units: 40 });
  assert.match(result.out, /at most \$6\.00/);
  assert.match(result.out, /Nothing has run/);
  assert.match(result.out, /specstream deep approve q_1 --max-cents 600/);
});

test("deep stops before a price when the request cannot be read", async () => {
  const result = await run(["deep", "hm"], [ok({ ast_hash: null, notice: "Say what to find." })]);
  assert.equal(result.code, 1);
  assert.equal(result.calls.length, 1);
  assert.equal(result.err, "Say what to find.");
});

test("deep approve starts the work only with the quote's own maximum", async () => {
  const quote = { quote_id: "q_1", quote_hash: "qh", maximum_cents: 600 };
  const refused = await run(["deep", "approve", "q_1", "--max-cents", "500"], [ok(quote)]);
  assert.equal(refused.code, 1);
  assert.deepEqual(refused.calls.map((call) => call.method), ["GET"]);
  assert.match(refused.err, /Not started/);

  const started = await run(["deep", "approve", "q_1", "--max-cents", "600"], [
    ok(quote),
    ok({ find_id: "f_9", maximum_cents: 600, state: "running" }),
  ]);
  assert.equal(started.code, 0);
  assert.equal(started.calls[1].url, "https://api.specstream.ai/v1/capacity/executions");
  assert.deepEqual(started.calls[1].body, {
    quote_id: "q_1",
    quote_hash: "qh",
    confirm_max_cents: 600,
    idempotency_key: "cli-fixed-uuid",
  });
  assert.match(started.err, /Request key: cli-fixed-uuid/);
  assert.match(started.out, /Started f_9, at most \$6\.00/);
});

test("deep approve without a maximum calls nothing", async () => {
  const result = await run(["deep", "approve", "q_1"]);
  assert.equal(result.code, 2);
  assert.equal(result.calls.length, 0);
});

test("deep status and rows read a run; --all follows the cursor", async () => {
  const status = await run(["deep", "status", "f_9"], [ok({ find_id: "f_9", status: "running", accepted_count: 3, requested_count: 25 })]);
  assert.equal(status.out, "f_9: running, 3 of 25 results");
  const rows = await run(["deep", "rows", "f_9", "--all"], [
    ok({ flat_rows: [{ name: "a" }], rows: [], next_cursor: "c2" }),
    ok({ flat_rows: [{ name: "b" }], rows: [], next_cursor: null }),
  ]);
  assert.equal(rows.out, '{"name":"a"}\n{"name":"b"}');
  assert.equal(rows.calls[1].url, "https://api.specstream.ai/v1/finds/f_9/rows?limit=100&cursor=c2");
  const first = await run(["deep", "rows", "f_9"], [ok({ flat_rows: [{ name: "a" }], next_cursor: "c2" })]);
  assert.equal(first.calls.length, 1);
  assert.match(first.err, /--all/);
});

test("without a key nothing is called and the message says where to make one", async () => {
  const result = await run(["search", "x"], [], {});
  assert.equal(result.code, 2);
  assert.equal(result.calls.length, 0);
  assert.match(result.err, /SPECSTREAM_API_KEY/);
  assert.match(result.err, /specstream\.ai\/workspace/);
});

test("an API error prints its words and never the key", async () => {
  const result = await run(["search", "x"], [[402, { data: null, error: { code: "payment_required", message: "The balance is empty" } }]]);
  assert.equal(result.code, 1);
  assert.match(result.err, /HTTP 402: payment_required: The balance is empty/);
  assert.doesNotMatch(result.err + result.out, /ss_test_key/);
  const html = await run(["search", "x"], [[502, "<html>bad gateway</html>"]]);
  assert.equal(html.code, 1);
  assert.match(html.err, /HTTP 502/);
});

test("the address and the key can come from options and the environment", async () => {
  const result = await run(["search", "x", "--api-key", "k2", "--base-url", "http://127.0.0.1:9/"], [ok({ sources: [] })], {});
  assert.equal(result.calls[0].url, "http://127.0.0.1:9/v1/web-search?q=x");
  assert.equal(result.calls[0].headers.Authorization, "Bearer k2");
  const env = await run(["search", "x"], [ok({ sources: [] })], { SPECSTREAM_API_KEY: "k3", SPECSTREAM_BASE_URL: "http://127.0.0.1:9" });
  assert.equal(env.calls[0].url, "http://127.0.0.1:9/v1/web-search?q=x");
});

test("an unknown command or option is a usage error", async () => {
  assert.equal((await run(["serach", "x"])).code, 2);
  assert.equal((await run(["search", "x", "--quick"])).code, 2);
  assert.equal((await run(["search", "x", "--num", "ten"])).code, 2);
});

test("the file runs as a program: --help names the three products and needs no key", () => {
  const help = execFileSync(process.execPath, [path.join(__dirname, "..", "bin", "specstream.js"), "--help"], {
    env: { PATH: process.env.PATH },
    encoding: "utf8",
  });
  for (const word of ["specstream search", "specstream read", "specstream deep", "SPECSTREAM_API_KEY"]) assert.ok(help.includes(word), word);
});
