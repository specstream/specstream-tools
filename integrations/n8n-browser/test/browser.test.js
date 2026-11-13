"use strict";

// Needs the build output: `npm test` builds first. No call leaves this file: the API is a scripted function.
const assert = require("assert");
const { SpecstreamBrowser } = require("../dist/nodes/SpecstreamBrowser/SpecstreamBrowser.node.js");
const { SpecstreamBrowserApi } = require("../dist/credentials/SpecstreamBrowserApi.credentials.js");
const packageJson = require("../package.json");

const NODE = { name: "SpecStream Browser", type: "specstreamBrowser", typeVersion: 1, id: "n1", position: [0, 0], parameters: {} };
const SESSION = { id: "bs_1", status: "running", seconds: 0, actions: 0, charged_usd: 0 };

function context(itemParameters, answer, options = {}) {
  const calls = [];
  return {
    calls,
    getInputData: () => itemParameters.map(() => ({ json: {} })),
    getNode: () => NODE,
    continueOnFail: () => Boolean(options.continueOnFail),
    getCredentials: async (name) => {
      assert.strictEqual(name, "specstreamBrowserApi");
      return { apiBase: options.apiBase || "https://api.specstream.ai" };
    },
    getNodeParameter: (name, item, fallback) => {
      const value = itemParameters[item][name];
      return value === undefined ? fallback : value;
    },
    helpers: {
      httpRequestWithAuthentication: async (name, request) => {
        assert.strictEqual(name, "specstreamBrowserApi");
        assert.strictEqual(request.disableFollowRedirect, true);
        const line = `${request.method} ${request.url.replace("https://api.specstream.ai", "")}`;
        calls.push({ line, body: request.body, qs: request.qs });
        return answer(line, request);
      },
      prepareBinaryData: async (buffer, fileName, mimeType) => ({ data: buffer.toString("base64"), fileName, mimeType }),
    },
  };
}

async function run(itemParameters, answer, options) {
  const ctx = context(itemParameters, answer, options);
  const [items] = await new SpecstreamBrowser().execute.call(ctx);
  return { items, calls: ctx.calls };
}

const action = (extra) => ({ data: { result: [{ type: "text", text: "ok" }], error: null, url: "https://example.com/", title: "Example", took_ms: 12, price_usd: 0.001, ...extra } });

(async () => {
  // The package: one node, one credential, names of its own, no dependency.
  assert.strictEqual(packageJson.name, "n8n-nodes-specstream-browser");
  assert.ok(packageJson.keywords.includes("n8n-community-node-package"));
  assert.strictEqual(packageJson.dependencies, undefined);
  const description = new SpecstreamBrowser().description;
  assert.strictEqual(description.name, "specstreamBrowser");
  assert.strictEqual(description.usableAsTool, true);
  assert.deepStrictEqual(description.credentials, [{ name: "specstreamBrowserApi", required: true }]);
  assert.strictEqual(new SpecstreamBrowserApi().name, "specstreamBrowserApi");
  // Two resources, each with its own operations in alphabetical order; no operation value is used twice.
  const [resource, onPage, onSession] = description.properties;
  assert.deepStrictEqual(resource.options.map((option) => option.value), ["page", "session"]);
  assert.deepStrictEqual(onPage.displayOptions, { show: { resource: ["page"] } });
  assert.deepStrictEqual(onSession.displayOptions, { show: { resource: ["session"] } });
  assert.deepStrictEqual(
    onPage.options.map((option) => option.value),
    ["click", "snapshot", "navigate", "readUrl", "read", "tool", "screenshot", "type"],
  );
  assert.deepStrictEqual(onSession.options.map((option) => option.value), ["release", "get", "getAll", "create"]);
  for (const list of [resource, onPage, onSession]) {
    const names = list.options.map((option) => option.name);
    assert.deepStrictEqual(names, [...names].sort((a, b) => a.localeCompare(b)));
  }

  // Open a Session sends only the options that were set, in the API's names.
  let result = await run(
    [{ operation: "create", sessionOptions: { timeoutS: 600, blockMedia: true, allowedDomains: "example.com, *.example.org" } }],
    () => ({ data: SESSION }),
  );
  assert.deepStrictEqual(result.calls, [
    { line: "POST /v1/browser/sessions", body: { timeout_s: 600, block_media: true, allowed_domains: ["example.com", "*.example.org"] }, qs: undefined },
  ]);
  assert.deepStrictEqual(result.items, [{ json: SESSION, pairedItem: { item: 0 } }]);

  // Go to a Page is one browser_navigate step on the session.
  result = await run([{ operation: "navigate", sessionId: " bs_1 ", url: "https://example.com" }], () => action());
  assert.deepStrictEqual(result.calls, [
    { line: "POST /v1/browser/sessions/bs_1/actions", body: { tool: "browser_navigate", arguments: { url: "https://example.com" } }, qs: undefined },
  ]);
  assert.deepStrictEqual(result.items[0].json, {
    tool: "browser_navigate",
    text: "ok",
    url: "https://example.com/",
    title: "Example",
    took_ms: 12,
    price_usd: 0.001,
    session_id: "bs_1",
  });

  // Read the Page joins the text parts and keeps when the page was read.
  result = await run([{ operation: "read", sessionId: "bs_1", format: "text" }], () =>
    action({ result: [{ type: "text", text: "First" }, { type: "text", text: "Second" }], read_at: "2026-11-13T10:00:00Z" }),
  );
  assert.deepStrictEqual(result.calls[0].body, { tool: "browser_read", arguments: { format: "text" } });
  assert.strictEqual(result.items[0].json.text, "First\nSecond");
  assert.strictEqual(result.items[0].json.read_at, "2026-11-13T10:00:00Z");

  // Click and Type send the element and its ref as Playwright MCP names them.
  result = await run(
    [
      { operation: "click", sessionId: "bs_1", element: "Sign in button", ref: "e12" },
      { operation: "type", sessionId: "bs_1", element: "Search field", ref: "e3", text: "boots", submit: true },
      { operation: "snapshot", sessionId: "bs_1" },
    ],
    () => action(),
  );
  assert.deepStrictEqual(result.calls.map((call) => call.body), [
    { tool: "browser_click", arguments: { element: "Sign in button", ref: "e12" } },
    { tool: "browser_type", arguments: { element: "Search field", ref: "e3", text: "boots", submit: true } },
    { tool: "browser_snapshot", arguments: {} },
  ]);
  assert.deepStrictEqual(result.items.map((item) => item.pairedItem), [{ item: 0 }, { item: 1 }, { item: 2 }]);

  // Take a Screenshot gives the picture as a binary file.
  const png = Buffer.from("png-bytes").toString("base64");
  result = await run([{ operation: "screenshot", sessionId: "bs_1", fullPage: true }], () =>
    action({ result: [{ type: "image", data: png, mime_type: "image/png" }] }),
  );
  assert.deepStrictEqual(result.calls[0].body, { tool: "browser_take_screenshot", arguments: { type: "png", fullPage: true } });
  assert.deepStrictEqual(result.items[0].binary, { data: { data: png, fileName: "screenshot.png", mimeType: "image/png" } });

  // Run a Tool takes any Playwright MCP tool and refuses a name or arguments the API would refuse.
  result = await run([{ operation: "tool", sessionId: "bs_1", tool: "browser_press_key", toolArguments: '{"key": "Enter"}' }], () => action());
  assert.deepStrictEqual(result.calls[0].body, { tool: "browser_press_key", arguments: { key: "Enter" } });
  await assert.rejects(run([{ operation: "tool", sessionId: "bs_1", tool: "press_key" }], () => action()), /Playwright MCP tool name/);
  await assert.rejects(
    run([{ operation: "tool", sessionId: "bs_1", tool: "browser_press_key", toolArguments: "[1]" }], () => action()),
    /JSON object/,
  );

  // A step the browser refused stops the node with the API's own words; no call goes out without a session ID.
  const blocked = () => action({ result: [], error: { code: "blocked", reason: "robots", message: "This page asks robots to stay out." } });
  await assert.rejects(run([{ operation: "navigate", sessionId: "bs_1", url: "https://example.com" }], blocked), /robots to stay out\. \(robots\)/);
  result = await run([{ operation: "navigate", sessionId: "bs_1", url: "https://example.com" }], blocked, { continueOnFail: true });
  assert.deepStrictEqual(result.items, [{ json: { error: "This page asks robots to stay out. (robots)" }, pairedItem: { item: 0 } }]);
  const empty = context([{ operation: "get", sessionId: "  " }], () => ({ data: SESSION }));
  await assert.rejects(new SpecstreamBrowser().execute.call(empty), /Session ID is empty/);
  assert.deepStrictEqual(empty.calls, []);

  // Get and Close; a session ID cannot change the path.
  result = await run(
    [
      { operation: "get", sessionId: "bs_1" },
      { operation: "release", sessionId: "bs_1/../../me" },
    ],
    () => ({ data: SESSION }),
  );
  assert.deepStrictEqual(result.calls.map((call) => call.line), [
    "GET /v1/browser/sessions/bs_1",
    "POST /v1/browser/sessions/bs_1%2F..%2F..%2Fme/release",
  ]);

  // Get Many Sessions follows the cursor up to the limit, and stops on a cursor that comes back.
  const pages = {
    undefined: { sessions: [{ id: "a" }, { id: "b" }], next_cursor: "c1" },
    c1: { sessions: [{ id: "c" }, { id: "d" }], next_cursor: "c2" },
    c2: { sessions: [{ id: "e" }], next_cursor: "c1" },
  };
  const paged = (line, request) => ({ data: pages[String(request.qs.cursor)] });
  result = await run([{ operation: "getAll", limit: 3, status: "running" }], paged);
  assert.deepStrictEqual(result.items.map((item) => item.json.id), ["a", "b", "c"]);
  assert.deepStrictEqual(result.calls.map((call) => call.qs), [
    { limit: 3, status: "running" },
    { limit: 1, status: "running", cursor: "c1" },
  ]);
  result = await run([{ operation: "getAll", returnAll: true }], paged);
  assert.deepStrictEqual(result.items.map((item) => item.json.id), ["a", "b", "c", "d", "e"]);
  assert.strictEqual(result.calls.length, 3);

  // Read a Web Page opens, goes, reads and closes, and reports what the session cost.
  const script = (line) => {
    if (line === "POST /v1/browser/sessions") return { data: SESSION };
    if (line.endsWith("/release")) return { data: { ...SESSION, status: "ended", seconds: 4, actions: 2, charged_usd: 0.0021 } };
    return action({ result: [{ type: "text", text: "# Example" }] });
  };
  result = await run([{ operation: "readUrl", url: "https://example.com", sessionOptions: { blockMedia: true } }], script);
  assert.deepStrictEqual(result.calls.map((call) => call.line), [
    "POST /v1/browser/sessions",
    "POST /v1/browser/sessions/bs_1/actions",
    "POST /v1/browser/sessions/bs_1/actions",
    "POST /v1/browser/sessions/bs_1/release",
  ]);
  assert.deepStrictEqual(result.calls[0].body, { block_media: true, keep_alive: true });
  assert.deepStrictEqual(result.calls[2].body, { tool: "browser_read", arguments: { format: "markdown" } });
  assert.strictEqual(result.items[0].json.text, "# Example");
  assert.strictEqual(result.items[0].json.session_id, "bs_1");
  assert.strictEqual(result.items[0].json.charged_usd, 0.0021);

  // A page that fails still closes the browser, so nothing keeps running and charging.
  const failing = context([{ operation: "readUrl", url: "https://example.com" }], (line) => {
    if (line === "POST /v1/browser/sessions") return { data: SESSION };
    if (line.endsWith("/release")) return { data: SESSION };
    return blocked();
  });
  await assert.rejects(new SpecstreamBrowser().execute.call(failing), /robots to stay out/);
  assert.deepStrictEqual(failing.calls.map((call) => call.line), [
    "POST /v1/browser/sessions",
    "POST /v1/browser/sessions/bs_1/actions",
    "POST /v1/browser/sessions/bs_1/release",
  ]);

  // The key goes only to the SpecStream API: another base is refused before any call.
  const elsewhere = context([{ operation: "getAll" }], () => ({ data: {} }), { apiBase: "https://api.specstream.ai.evil.example" });
  await assert.rejects(new SpecstreamBrowser().execute.call(elsewhere), /API Base URL must be/);
  assert.deepStrictEqual(elsewhere.calls, []);

  // An answer without data is an error, not an empty item.
  await assert.rejects(run([{ operation: "get", sessionId: "bs_1" }], () => ({ error: { code: "not_found" } })), /could not read/);

  console.log("browser.test.js passed");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
