"use strict";

// Needs the build output: `npm test` builds first. No network: every HTTP call is answered here.
const assert = require("assert");
const { Specstream } = require("../dist/nodes/Specstream/Specstream.node.js");
const { isNotFound } = require("../lib/specstream");

const httpError = (status) => Object.assign(new Error(`Request failed with status code ${status}`), { httpCode: String(status) });

function context(parameters, answer, calls) {
  return {
    getInputData: () => [{ json: {} }],
    getCredentials: async () => ({ apiBase: "https://api.specstream.ai" }),
    getNodeParameter: (name, _index, fallback) => (name in parameters ? parameters[name] : fallback),
    getNode: () => ({ name: "SpecStream", type: "specstream", typeVersion: 1, id: "n1", position: [0, 0], parameters: {} }),
    helpers: {
      httpRequestWithAuthentication: async (_name, options) => {
        const call = `${options.method} ${options.url.replace("https://api.specstream.ai", "")}`;
        calls.push(call);
        return answer(call, options);
      },
    },
  };
}

const find = { resource: "list", operation: "findList", request: "Roofers in Columbus", count: 2, max_price_usd: 1, findOptions: { run_key: "run-key-0001" } };

(async () => {
  // The description: three resources, each operation value under exactly one of them.
  const properties = new Specstream().description.properties;
  const resource = properties.find((p) => p.name === "resource");
  assert.deepStrictEqual(resource.options.map((o) => o.value), ["list", "quote", "web"]);
  const values = properties.filter((p) => p.name === "operation").flatMap((p) => p.options.map((o) => o.value));
  assert.deepStrictEqual([...values].sort(), ["compile", "confirmAndRun", "extractPages", "findList", "getListRows", "quoteWork", "webSearch"]);
  assert.strictEqual(new Set(values).size, values.length);
  for (const p of properties.filter((p) => p.name === "operation")) {
    assert.ok(p.options.length <= 5 && p.displayOptions.show.resource.length === 1);
  }

  assert.strictEqual(isNotFound(httpError(404)), true);
  assert.strictEqual(isNotFound({ cause: { response: { status: 404 } } }), true);
  for (const other of [httpError(401), httpError(500), new Error("socket hang up"), undefined]) {
    assert.strictEqual(isNotFound(other), false);
  }

  // Nothing has run for the key (404): the list is read, priced and started.
  let calls = [];
  let out = await new Specstream().execute.call(
    context(find, (call) => {
      if (call.startsWith("GET /v1/capacity/requests/")) throw httpError(404);
      if (call === "POST /v1/parse") return { data: { status: "runnable", ast_hash: "h", read_back: "Roofers in Columbus" } };
      if (call === "POST /v1/capacity/quotes") return { data: { quote_id: "cqt_1", quote_hash: "q", maximum_cents: 30 } };
      return { data: { find_id: "fnd_1", state: "running" } };
    }, calls),
  );
  assert.deepStrictEqual(calls, ["GET /v1/capacity/requests/run-key-0001", "POST /v1/parse", "POST /v1/capacity/quotes", "POST /v1/capacity/executions"]);
  assert.strictEqual(out[0][0].json.list_id, "fnd_1");

  // The key already started a run: it is returned and nothing is bought.
  calls = [];
  out = await new Specstream().execute.call(context(find, () => ({ data: { find_id: "fnd_0", state: "running", maximum_cents: 30 } }), calls));
  assert.deepStrictEqual(calls, ["GET /v1/capacity/requests/run-key-0001"]);
  assert.strictEqual(out[0][0].json.list_id, "fnd_0");

  // A refused key, a server fault or a network fault on the lookup stops the step: nothing is priced or bought.
  for (const failure of [httpError(401), httpError(500), new Error("socket hang up")]) {
    calls = [];
    await assert.rejects(
      new Specstream().execute.call(context(find, () => { throw failure; }, calls)),
      (error) => error.constructor.name === "NodeApiError",
    );
    assert.deepStrictEqual(calls, ["GET /v1/capacity/requests/run-key-0001"]);
  }

  // A workflow saved before resources existed carries only the operation and still runs.
  calls = [];
  out = await new Specstream().execute.call(
    context({ operation: "webSearch", search_query: "who owns acme" }, () => ({ data: { results: [] } }), calls),
  );
  assert.deepStrictEqual(calls, ["GET /v1/web-search?q=who%20owns%20acme"]);
  assert.deepStrictEqual(out[0][0].json, { results: [] });

  console.log("n8n specstream node ok");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
