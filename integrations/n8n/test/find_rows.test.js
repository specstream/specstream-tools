"use strict";

// Find Rows: the rows of a list that hold a value in a column. Needs the build output (`npm test` builds first).
// No network: every HTTP call is answered here.
const assert = require("assert");
const { Specstream } = require("../dist/nodes/Specstream/Specstream.node.js");
const { listIdOf, rowMatches } = require("../lib/specstream");

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

const record = (n, name, website) => ({
  entity_id: `e${n}`,
  ordinal: n,
  cells: [
    { label: "Name", display: name },
    { label: "Website", display: website },
  ],
});

// Two pages of a list; the second page ends it.
const pages = {
  "": {
    find_id: "fnd_1",
    status: "complete",
    rows: [record(1, "Acme Roofing", "acme.com"), record(2, "Best Roofs", "bestroofs.com"), record(3, "Acme Gutters", "acmegutters.com")],
    flat_rows: [{ id: "fnd_1:e1", source_url: "https://acme.com/about", checked_at: "2026-11-12T10:00:00Z", Website: "acme.com", Website_source: "https://acme.com" }],
    next_cursor: "c2",
  },
  c2: { find_id: "fnd_1", status: "complete", rows: [record(4, "Columbus Acme", "colacme.com")], flat_rows: [], next_cursor: null },
};
const answer = (call) => {
  const cursor = /cursor=([^&]+)/.exec(call);
  return { data: pages[cursor ? cursor[1] : ""] };
};
const run = async (parameters) => {
  const calls = [];
  const out = await new Specstream().execute.call(context({ resource: "list", operation: "findRows", ...parameters }, answer, calls));
  return { calls, rows: out[0].map((item) => item.json) };
};

(async () => {
  // The operation sits under List, beside Find a List and Get List Results.
  const listOps = new Specstream().description.properties.find((p) => p.name === "operation" && p.displayOptions.show.resource[0] === "list");
  assert.deepStrictEqual(listOps.options.map((o) => o.value), ["findList", "findRows", "getListRows"]);

  // The helpers: a list link or a bare ID; a column match by name, any column, case aside.
  assert.strictEqual(listIdOf("https://specstream.ai/workspace/collections/fnd_9?tab=rows"), "fnd_9");
  assert.strictEqual(listIdOf("  fnd_9 "), "fnd_9");
  const row = { id: "fnd_1:e1", list_id: "fnd_1", source_url: "https://acme.example", Name: "Acme", "Name (column)": "Other", Website_source: "x" };
  assert.strictEqual(rowMatches(row, "name", "ACME"), true);
  assert.strictEqual(rowMatches(row, "", "other"), true);
  assert.strictEqual(rowMatches(row, "Website", "acme"), false);
  assert.strictEqual(rowMatches(row, "", "acme.example"), false, "a built-in field is not a column");
  assert.strictEqual(rowMatches(row, "Name", ""), true);

  // A value in one column, read over every page, full pages, the source pages kept.
  let { calls, rows } = await run({ list_id: "fnd_1", column: "Name", value: "acme", returnAll: true });
  assert.deepStrictEqual(calls, ["GET /v1/finds/fnd_1/rows?limit=100", "GET /v1/finds/fnd_1/rows?limit=100&cursor=c2"]);
  assert.deepStrictEqual(rows.map((r) => r.Name), ["Acme Roofing", "Acme Gutters", "Columbus Acme"]);
  assert.strictEqual(rows[0].source_url, "https://acme.com/about");
  assert.strictEqual(rows[0].Website_source, "https://acme.com");
  assert.strictEqual(rows[0].list_status, "complete");

  // The limit stops the read once enough rows match; the list link works as the ID.
  ({ calls, rows } = await run({ list_id: "https://specstream.ai/workspace/collections/fnd_1", column: "", value: "ACME", returnAll: false, limit: 2 }));
  assert.deepStrictEqual(calls, ["GET /v1/finds/fnd_1/rows?limit=100"]);
  assert.deepStrictEqual(rows.map((r) => r.position), [1, 3]);

  // A column with no match returns nothing; a missing ID stops before any call.
  ({ calls, rows } = await run({ list_id: "fnd_1", column: "Website", value: "nowhere", returnAll: true }));
  assert.strictEqual(rows.length, 0);
  assert.strictEqual(calls.length, 2);
  await assert.rejects(run({ list_id: " ", value: "acme", returnAll: true }), /List ID/);

  // A cursor that repeats ends the read instead of looping.
  const loopCalls = [];
  await new Specstream().execute.call(
    context({ operation: "findRows", list_id: "fnd_1", value: "x", returnAll: true }, () => ({ data: { ...pages[""], next_cursor: "same" } }), loopCalls),
  );
  assert.ok(loopCalls.length <= 2);

  console.log("n8n find rows ok");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
