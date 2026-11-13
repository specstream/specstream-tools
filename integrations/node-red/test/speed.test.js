const test = require("node:test");
const assert = require("node:assert");
const lib = require("../lib");

// The search passes the Search API's speed: fast at $1 per 1,000, the API's default when left out.

function recorder() {
  const urls = [];
  const f = async (url) => {
    urls.push(new URL(url));
    return { ok: true, status: 200, text: async () => "{}" };
  };
  return { urls, f };
}

test("a fast search sends speed=fast; without one no speed is sent", async () => {
  const { urls, f } = recorder();
  await lib.search(f, "k", "acme funding", undefined, "fast");
  await lib.search(f, "k", "acme funding");
  assert.deepStrictEqual(urls.map((u) => u.searchParams.get("speed")), ["fast", null]);
});

test("an unknown speed is refused before any call", async () => {
  const { urls, f } = recorder();
  await assert.rejects(lib.search(f, "k", "x", undefined, "turbo"), /speed/);
  assert.strictEqual(urls.length, 0);
});

test("msg.speed reaches the search through the node", async () => {
  const { urls, f } = recorder();
  let handler;
  const RED = {
    nodes: {
      createNode: (node) => {
        node.on = (_event, fn) => (handler = fn);
      },
      getNode: () => ({ credentials: { apiKey: "k" } }),
      registerType: () => {},
    },
  };
  const register = require("../specstream-search");
  register(RED);
  const node = new register.SpecStreamSearch({ server: "s", speed: "" });
  node.fetchImpl = f;
  await new Promise((resolve, reject) => handler({ payload: "acme", speed: "fast" }, () => {}, (e) => (e ? reject(e) : resolve())));
  assert.strictEqual(urls[0].searchParams.get("speed"), "fast");
});
