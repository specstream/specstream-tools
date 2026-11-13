const test = require("node:test");
const assert = require("node:assert");
const lib = require("../lib");
const register = require("../specstream-research");

// A scripted API: each call takes the next answer, and every call is kept.
function api(answers) {
  const calls = [];
  const f = async (url, opts) => {
    calls.push({ url, opts });
    const next = answers.shift();
    return { ok: (next.status || 200) < 400, status: next.status || 200, text: async () => JSON.stringify(next.body) };
  };
  f.calls = calls;
  return f;
}

// The least of Node-RED the node needs: it registers, takes one message and answers.
function makeNode(config, f, key) {
  let Type;
  const statuses = [];
  const RED = {
    nodes: {
      createNode(node) { node.id = "n1"; node.on = (name, fn) => { node.handler = fn; }; node.status = (s) => statuses.push(s); },
      getNode: () => (key === null ? null : { credentials: { apiKey: key || "k" } }),
      registerType: (name, ctor) => { assert.strictEqual(name, "specstream research"); Type = ctor; },
    },
  };
  register(RED);
  const node = new Type({ server: "s", ...config });
  node.fetchImpl = f;
  node.sleepImpl = async () => {};
  node.statuses = statuses;
  node.run = (msg) => new Promise((resolve) => {
    const sent = [];
    node.handler(msg, (m) => sent.push(m), (err) => resolve({ sent, err }));
  });
  return node;
}

test("research body keeps the question and the default depth", () => {
  assert.deepStrictEqual(lib.researchBody("  Who leads?  "), { input: "Who leads?", depth: "standard" });
  assert.throws(() => lib.researchBody(""), /No question/);
  assert.throws(() => lib.researchBody("x", "huge"), /Depth must be one of/);
  assert.throws(() => lib.researchBody("x".repeat(15001)), /The most is 15000/);
});

test("the node starts a report with one key per message and waits for it", async () => {
  const f = api([
    { body: { id: "res_1", status: "queued" } },
    { body: { id: "res_1", status: "running" } },
    { body: { id: "res_1", status: "completed", report: { content: "Text [1]" } } },
  ]);
  const node = makeNode({ depth: "quick" }, f);
  const { sent, err } = await node.run({ _msgid: "m 1", payload: "Who leads?" });
  assert.strictEqual(err, undefined);
  assert.strictEqual(sent[0].payload.report.content, "Text [1]");
  assert.strictEqual(sent[0].reportId, "res_1");
  assert.strictEqual(f.calls[0].url, "https://api.specstream.ai/v1/research");
  assert.strictEqual(f.calls[0].opts.method, "POST");
  assert.deepStrictEqual(JSON.parse(f.calls[0].opts.body), { input: "Who leads?", depth: "quick" });
  assert.strictEqual(f.calls[0].opts.headers["Idempotency-Key"], "node-red-m_1-n1");
  assert.strictEqual(f.calls[0].opts.headers.Authorization, "Bearer k");
  assert.strictEqual(f.calls[1].url, "https://api.specstream.ai/v1/research/res_1");
  assert.strictEqual(f.calls.length, 3);
});

test("with wait off the node returns the report ID at once", async () => {
  const f = api([{ body: { id: "res_2", status: "queued" } }]);
  const node = makeNode({ wait: false, question: "From the field" }, f);
  const { sent } = await node.run({ _msgid: "m2" });
  assert.strictEqual(sent[0].reportId, "res_2");
  assert.strictEqual(sent[0].payload.status, "queued");
  assert.strictEqual(JSON.parse(f.calls[0].opts.body).input, "From the field");
  assert.strictEqual(f.calls.length, 1);
});

test("msg.reportId reads a report and starts none", async () => {
  const f = api([{ body: { id: "res_3", status: "completed" } }]);
  const node = makeNode({}, f);
  const { sent } = await node.run({ reportId: "res_3", payload: "ignored" });
  assert.strictEqual(sent[0].payload.status, "completed");
  assert.strictEqual(f.calls[0].opts.method, "GET");
  assert.strictEqual(f.calls.length, 1);
});

test("a report that ends without text stops the flow with the reason", async () => {
  const f = api([{ body: { id: "res_4", status: "queued" } }, { body: { id: "res_4", status: "payment_required" } }]);
  const node = makeNode({}, f);
  const { sent, err } = await node.run({ _msgid: "m4", payload: "q" });
  assert.strictEqual(sent.length, 0);
  assert.match(err.message, /balance does not hold the price of report res_4/);
});

test("a report still being written after the wait names its ID", async () => {
  const f = api([{ body: { id: "res_5", status: "running" } }]);
  const err = await lib.waitForResearch(f, "k", "res_5", 1, 61, async () => {}).catch((e) => e);
  assert.strictEqual(err.reportId, "res_5");
  assert.match(err.message, /still being written after 1 minutes/);
});

test("a missing key and an API error stop the flow", async () => {
  const none = await makeNode({}, api([]), null).run({ payload: "q" });
  assert.match(none.err.message, /Missing SpecStream API key/);
  const bad = await makeNode({}, api([{ status: 401, body: {} }])).run({ payload: "q" });
  assert.strictEqual(bad.err.status, 401);
});
