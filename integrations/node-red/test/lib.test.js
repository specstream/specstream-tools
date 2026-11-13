const test = require("node:test");
const assert = require("node:assert");
const lib = require("../lib");

const ok = (body) => async (url, opts) => {
  ok.last = { url, opts };
  return { ok: true, status: 200, text: async () => JSON.stringify(body) };
};

test("search calls GET /v1/web-search with bearer key", async () => {
  const f = ok({ results: [] });
  const out = await lib.search(f, "k", "acme funding", 5);
  assert.deepStrictEqual(out, { results: [] });
  assert.match(ok.last.url, /^https:\/\/api\.specstream\.ai\/v1\/web-search\?q=acme\+funding&limit=5$/);
  assert.strictEqual(ok.last.opts.method, "GET");
  assert.strictEqual(ok.last.opts.headers.Authorization, "Bearer k");
  assert.match(ok.last.opts.headers["User-Agent"], /^specstream-node-red\//);
});

test("extract posts at most 20 urls", async () => {
  const f = ok({ pages: [] });
  const urls = Array.from({ length: 25 }, (_, i) => "https://e.com/" + i);
  await lib.extract(f, "k", urls);
  assert.strictEqual(ok.last.opts.method, "POST");
  assert.strictEqual(JSON.parse(ok.last.opts.body).urls.length, 20);
});

test("error status throws", async () => {
  const f = async () => ({ ok: false, status: 401, text: async () => "{}" });
  await assert.rejects(lib.search(f, "bad", "x"), /401/);
});
