"use strict";

// Needs the build output: `npm test` builds first. No call leaves the machine: the HTTP helper is scripted.
const assert = require("assert");
const { SpecstreamResearch } = require("../dist/nodes/SpecstreamResearch/SpecstreamResearch.node.js");
const { endedWithoutReport, idempotencyKey, reportBody } = require("../lib/report.js");
const packageJson = require("../package.json");

const NODE = { name: "SpecStream Research", type: "specstreamResearch", typeVersion: 1, id: "node-1", position: [0, 0], parameters: {} };
const RUNNING = { id: "rs_1", status: "running", stage: "reading" };
const DONE = {
  id: "rs_1",
  status: "completed",
  stage: "done",
  report: { title: "T", content: "A fact [1].", citations: [{ n: 1, url: "https://example.com/a" }] },
  usage: { charged_usd: 0.1 },
};

// answers: a function of (line, request) that returns the scripted reply or throws.
function context(parameters, answers, extra = {}) {
  const calls = [];
  const self = {
    calls,
    getInputData: () => extra.items || [{ json: {} }],
    getCredentials: async (name) => {
      assert.strictEqual(name, "specstreamResearchApi");
      return { apiBase: extra.apiBase || "https://api.specstream.ai" };
    },
    getNode: () => NODE,
    getExecutionId: () => "exec 42",
    getNodeParameter: (name, _index, fallback) => (name in parameters ? parameters[name] : fallback),
    continueOnFail: () => Boolean(extra.continueOnFail),
    helpers: {
      httpRequestWithAuthentication: async function (name, request) {
        assert.strictEqual(this, self, "the helper is called on the node's own context");
        assert.strictEqual(name, "specstreamResearchApi");
        assert.ok(request.url.startsWith("https://api.specstream.ai/"), request.url);
        assert.strictEqual(request.disableFollowRedirect, true);
        const line = `${request.method} ${request.url.replace("https://api.specstream.ai", "")}`;
        calls.push({ line, body: request.body, qs: request.qs, headers: request.headers });
        return answers(line, request, calls.length);
      },
    },
  };
  return self;
}

const run = (ctx) => new SpecstreamResearch().execute.call(ctx);

async function main() {
  // The body: only what the person set is sent, in the API's own field names.
  assert.deepStrictEqual(reportBody("  Why?  ", "quick", {}), { input: "Why?", depth: "quick" });
  assert.deepStrictEqual(
    reportBody("Why?", "deep", {
      length: "long",
      language: " fr ",
      includeDomains: "Example.com, example.org",
      excludeDomains: "bad.example",
      afterDate: "2026-01-31T00:00:00.000Z",
      jsonSchema: '{"type":"object","properties":{"answer":{"type":"string"}}}',
      waitMinutes: 3,
    }),
    {
      input: "Why?",
      depth: "deep",
      length: "long",
      language: "fr",
      include_domains: ["example.com", "example.org"],
      exclude_domains: ["bad.example"],
      after_date: "2026-01-31",
      output: { type: "json", schema: { type: "object", properties: { answer: { type: "string" } } } },
    },
  );
  assert.deepStrictEqual(reportBody("Why?", "quick", { jsonSchema: "{}", includeDomains: " " }), { input: "Why?", depth: "quick" });
  assert.throws(() => reportBody("   ", "quick", {}), /Write the question/);
  assert.throws(() => reportBody("x".repeat(15001), "quick", {}), /15001 characters. The most is 15000/);
  assert.throws(() => reportBody("Why?", "huge", {}), /Depth must be one of/);
  assert.throws(() => reportBody("Why?", "quick", { jsonSchema: "{not json" }), /not valid JSON/);
  assert.throws(() => reportBody("Why?", "quick", { jsonSchema: "[1]" }), /must be a JSON object/);
  assert.throws(() => reportBody("Why?", "quick", { afterDate: "last week" }), /must be a date/);

  // The key: the same for a retry of one step, different per item, and never longer than the API takes.
  assert.strictEqual(idempotencyKey("exec 42", "node-1", 0), "n8n-exec_42-node-1-0");
  assert.notStrictEqual(idempotencyKey("e", "n", 0), idempotencyKey("e", "n", 1));
  assert.strictEqual(idempotencyKey("e".repeat(300), "n", 0).length, 128);

  assert.match(endedWithoutReport({ id: "rs_1", status: "payment_required" }), /balance does not hold the price of report rs_1/);
  assert.match(endedWithoutReport({ id: "rs_1", status: "cancelled" }), /not charged/);
  assert.strictEqual(endedWithoutReport({ id: "rs_1", status: "failed", error: { message: "No page answered." } }), "Report rs_1 failed. No page answered.");

  // Write a Report waits: one POST with the key, then reads until the report is completed.
  let ctx = context({ operation: "write", input: "Why?", depth: "quick", options: { everySeconds: 1 } }, (line, _request, n) => {
    if (line === "POST /v1/research") return { id: "rs_1", status: "queued", depth: "quick", price_usd: 0.1 };
    return n < 3 ? RUNNING : DONE;
  });
  let result = await run(ctx);
  assert.deepStrictEqual(ctx.calls.map((call) => call.line), ["POST /v1/research", "GET /v1/research/rs_1", "GET /v1/research/rs_1"]);
  assert.deepStrictEqual(ctx.calls[0].body, { input: "Why?", depth: "quick" });
  assert.strictEqual(ctx.calls[0].headers["Idempotency-Key"], "n8n-exec_42-node-1-0");
  assert.deepStrictEqual(result, [[{ json: DONE, pairedItem: { item: 0 } }]]);

  // With the wait off, the step returns what the POST answered and reads nothing.
  ctx = context({ operation: "write", input: "Why?", depth: "deep", wait: false }, () => ({ id: "rs_2", status: "queued", price_usd: 1 }));
  result = await run(ctx);
  assert.deepStrictEqual(ctx.calls.map((call) => call.line), ["POST /v1/research"]);
  assert.deepStrictEqual(result[0][0].json, { id: "rs_2", status: "queued", price_usd: 1 });

  // Each item gets a key of its own.
  ctx = context({ operation: "write", input: "Why?", depth: "quick", wait: false }, () => ({ id: "rs_3" }), { items: [{ json: {} }, { json: {} }] });
  await run(ctx);
  assert.deepStrictEqual(ctx.calls.map((call) => call.headers["Idempotency-Key"]), ["n8n-exec_42-node-1-0", "n8n-exec_42-node-1-1"]);

  // A report that ends without its text stops the step with the reason.
  ctx = context({ operation: "write", input: "Why?", depth: "quick" }, (line) =>
    line === "POST /v1/research" ? { id: "rs_1" } : { id: "rs_1", status: "payment_required" },
  );
  await assert.rejects(run(ctx), /balance does not hold the price of report rs_1/);
  ctx = context({ operation: "write", input: "Why?", depth: "quick" }, (line) =>
    line === "POST /v1/research" ? { id: "rs_1" } : { id: "rs_1", status: "failed", error: { code: "no_sources", message: "No page answered." } },
  );
  await assert.rejects(run(ctx), /Report rs_1 failed. No page answered./);

  // The wait is bounded: a report still running when it is over stops the step, and the message names the ID.
  ctx = context({ operation: "write", input: "Why?", depth: "quick", options: { waitMinutes: 1, everySeconds: 61 } }, (line) =>
    line === "POST /v1/research" ? { id: "rs_1" } : RUNNING,
  );
  await assert.rejects(run(ctx), /Report rs_1 is still being written after 1 minutes. Read it later with the Get a Report operation/);
  assert.strictEqual(ctx.calls.length, 2);

  // A wrong field never reaches the API.
  ctx = context({ operation: "write", input: " ", depth: "quick" }, () => assert.fail("no call expected"));
  await assert.rejects(run(ctx), /Write the question/);
  assert.strictEqual(ctx.calls.length, 0);

  // An API error (402, 422, 429) stops the step; with Continue On Fail it becomes an item.
  const refuse = () => {
    throw Object.assign(new Error("402 - the balance does not hold the report's price"), { httpCode: "402" });
  };
  await assert.rejects(run(context({ operation: "write", input: "Why?", depth: "quick" }, refuse)));
  result = await run(context({ operation: "write", input: "Why?", depth: "quick" }, refuse, { continueOnFail: true }));
  assert.strictEqual(result[0].length, 1);
  assert.ok(result[0][0].json.error);

  // Get, cancel and list.
  ctx = context({ operation: "get", reportId: " rs/1 " }, () => DONE);
  result = await run(ctx);
  assert.deepStrictEqual(ctx.calls.map((call) => call.line), ["GET /v1/research/rs%2F1"]);
  assert.deepStrictEqual(result[0][0].json, DONE);
  await assert.rejects(run(context({ operation: "get", reportId: "" }, () => assert.fail("no call expected"))), /Enter the report ID/);

  ctx = context({ operation: "cancel", reportId: "rs_1" }, () => ({ id: "rs_1", status: "cancelled" }));
  result = await run(ctx);
  assert.deepStrictEqual(ctx.calls.map((call) => call.line), ["POST /v1/research/rs_1/cancel"]);
  assert.strictEqual(result[0][0].json.status, "cancelled");

  ctx = context({ operation: "getMany", limit: 500 }, () => ({ data: [{ id: "rs_2" }, { id: "rs_1" }], has_more: false }));
  result = await run(ctx);
  assert.deepStrictEqual(ctx.calls[0].qs, { limit: 100 });
  assert.deepStrictEqual(result[0].map((item) => item.json.id), ["rs_2", "rs_1"]);

  // The key goes only to the SpecStream API.
  await assert.rejects(
    run(context({ operation: "get", reportId: "rs_1" }, () => assert.fail("no call expected"), { apiBase: "http://api.specstream.ai" })),
    /API Base URL must be/,
  );

  // The node as n8n lists it: names of its own, usable by an AI agent, the prices on the depth choices.
  const description = new SpecstreamResearch().description;
  assert.strictEqual(description.name, "specstreamResearch");
  assert.strictEqual(description.usableAsTool, true);
  const depth = description.properties.find((property) => property.name === "depth");
  assert.deepStrictEqual(depth.options.map((option) => option.value), ["quick", "standard", "deep"]);
  assert.deepStrictEqual(depth.options.map((option) => /\$(\d\.\d\d)/.exec(option.name)[1]), ["0.10", "0.30", "1.00"]);
  assert.strictEqual(depth.default, "standard");
  assert.deepStrictEqual(packageJson.n8n.nodes, ["dist/nodes/SpecstreamResearch/SpecstreamResearch.node.js"]);

  console.log("research.test.js passed");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
