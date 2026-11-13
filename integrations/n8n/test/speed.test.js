"use strict";

// Web Search passes the Search API's speed: fast at $1 per 1,000, the API's default otherwise.
// Needs the build output: `npm test` builds first. No network: every HTTP call is answered here.
const assert = require("assert");
const { Specstream } = require("../dist/nodes/Specstream/Specstream.node.js");

function context(parameters, calls) {
  return {
    getInputData: () => [{ json: {} }],
    getCredentials: async () => ({ apiBase: "https://api.specstream.ai" }),
    getNodeParameter: (name, _index, fallback) => (name in parameters ? parameters[name] : fallback),
    getNode: () => ({ name: "SpecStream", type: "specstream", typeVersion: 1, id: "n1", position: [0, 0], parameters: {} }),
    helpers: {
      httpRequestWithAuthentication: async (_name, options) => {
        calls.push(`${options.method} ${options.url.replace("https://api.specstream.ai", "")}`);
        return { data: { kind: "fact", sources: [] } };
      },
    },
  };
}

const search = (extra) => ({ resource: "web", operation: "webSearch", search_query: "capital of Portugal", ...extra });

(async () => {
  let calls = [];
  await new Specstream().execute.call(context(search({ speed: "fast" }), calls));
  assert.deepStrictEqual(calls, ["GET /v1/web-search?q=capital%20of%20Portugal&speed=fast"]);

  // Default, or a workflow saved before the field existed: no speed is sent, the API's default runs.
  for (const extra of [{ speed: "default" }, {}]) {
    calls = [];
    await new Specstream().execute.call(context(search(extra), calls));
    assert.deepStrictEqual(calls, ["GET /v1/web-search?q=capital%20of%20Portugal"]);
  }

  // An unknown speed is refused before any call.
  calls = [];
  await assert.rejects(new Specstream().execute.call(context(search({ speed: "turbo" }), calls)), /Speed/);
  assert.deepStrictEqual(calls, []);

  const field = new Specstream().description.properties.find((p) => p.name === "speed");
  assert.deepStrictEqual(field.options.map((o) => o.value), ["default", "fast"]);
  assert.ok(field.options.find((o) => o.value === "fast").description.includes("$1 per 1,000"));
  console.log("n8n web search speed ok");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
