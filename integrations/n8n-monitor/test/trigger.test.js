"use strict";

// Needs the build output: `npm test` builds first.
const assert = require("assert");
const { createHmac } = require("node:crypto");
const { SpecstreamMonitorTrigger } = require("../dist/nodes/SpecstreamMonitor/SpecstreamMonitorTrigger.node.js");
const packageJson = require("../package.json");

const NODE = { name: "SpecStream Monitor Trigger", type: "specstreamMonitorTrigger", typeVersion: 1, id: "n1", position: [0, 0], parameters: {} };

function hookContext(staticData, calls, options = {}) {
  return {
    getWorkflowStaticData: () => staticData,
    getCredentials: async (name) => {
      assert.strictEqual(name, "specstreamMonitorApi");
      return { apiBase: options.apiBase || "https://api.specstream.ai" };
    },
    getNodeWebhookUrl: () => "https://n8n.example/webhook/specstream-monitor",
    getNode: () => NODE,
    helpers: {
      httpRequestWithAuthentication: async (name, request) => {
        assert.strictEqual(name, "specstreamMonitorApi");
        calls.push({ line: `${request.method} ${request.url.replace("https://api.specstream.ai", "")}`, body: request.body });
        if (request.method === "DELETE" && options.failDelete) {
          throw Object.assign(new Error(options.failDelete), { httpCode: options.failDelete.slice(0, 3) });
        }
        if (request.method === "POST") return { data: options.created || { hook_id: "hk_new", secret: "s_new" } };
        if (request.method === "GET") return { data: { webhooks: options.hooks || [] } };
        return { data: { ok: true } };
      },
    },
  };
}

function sign(secret, raw, at = Math.floor(Date.now() / 1000)) {
  const digest = createHmac("sha256", secret).update(at + ".").update(raw).digest("hex");
  return `t=${at},v1=${digest}`;
}

function webhookContext({ body, secret = "s_new", parameters = {}, signature, raw }) {
  const text = raw === undefined ? JSON.stringify(body) : raw;
  return {
    getWorkflowStaticData: () => ({ hook_id: "hk_new", secret }),
    getHeaderData: () => ({ "specstream-signature": signature === undefined ? sign("s_new", text) : signature }),
    getRequestObject: () => ({ rawBody: text === null ? undefined : Buffer.from(text) }),
    getNodeParameter: (name, fallback) => (name in parameters ? parameters[name] : fallback),
    getNode: () => NODE,
  };
}

const EVENT = {
  id: "evt_1",
  event: "monitor.found",
  find_id: "fnd_2",
  previous_find_id: "fnd_1",
  schedule_id: "sch_1",
  new_ids: ["e1"],
  changed_ids: ["e2"],
  records: [
    { entity_id: "e1", name: "Acme" },
    { entity_id: "e2", name: "Bolt" },
  ],
};

(async () => {
  const node = new SpecstreamMonitorTrigger();
  const methods = node.webhookMethods.default;

  // The package holds one node and one credential, and both carry names of their own.
  assert.deepStrictEqual(packageJson.n8n.nodes, ["dist/nodes/SpecstreamMonitor/SpecstreamMonitorTrigger.node.js"]);
  assert.deepStrictEqual(packageJson.n8n.credentials, ["dist/credentials/SpecstreamMonitorApi.credentials.js"]);
  assert.strictEqual(node.description.name, "specstreamMonitorTrigger");
  assert.deepStrictEqual(node.description.credentials, [{ name: "specstreamMonitorApi", required: true }]);
  assert.deepStrictEqual(node.description.inputs, []);

  // Activating registers one hook, for monitor.found only, and keeps its id and secret.
  let calls = [];
  let data = {};
  assert.strictEqual(await methods.create.call(hookContext(data, calls)), true);
  assert.deepStrictEqual(calls, [
    {
      line: "POST /v1/account/webhooks",
      body: { url: "https://n8n.example/webhook/specstream-monitor", events: ["monitor.found"] },
    },
  ]);
  assert.deepStrictEqual(data, { hook_id: "hk_new", secret: "s_new" });

  // Activating again removes the hook stored last time before registering a new one.
  calls = [];
  data = { hook_id: "hk_old", secret: "s_old" };
  await methods.create.call(hookContext(data, calls));
  assert.deepStrictEqual(calls.map((call) => call.line), ["DELETE /v1/account/webhooks/hk_old", "POST /v1/account/webhooks"]);
  assert.strictEqual(data.hook_id, "hk_new");

  // The old hook is already gone: the new one is still registered.
  data = { hook_id: "hk_old", secret: "s_old" };
  await methods.create.call(hookContext(data, [], { failDelete: "404 not found" }));
  assert.strictEqual(data.hook_id, "hk_new");

  // Any other failure of the removal stops the step.
  data = { hook_id: "hk_old", secret: "s_old" };
  await assert.rejects(methods.create.call(hookContext(data, [], { failDelete: "500 server error" })));
  assert.strictEqual(data.hook_id, "hk_old");

  // A registration without a secret is not taken as done.
  data = {};
  await assert.rejects(methods.create.call(hookContext(data, [], { created: { hook_id: "hk_new" } })), /not confirmed/);
  assert.deepStrictEqual(data, {});

  // A key is never sent to another address.
  await assert.rejects(methods.create.call(hookContext({}, [], { apiBase: "http://api.specstream.ai" })), /API Base URL must be/);

  // checkExists: nothing stored, a live hook, a revoked hook.
  calls = [];
  assert.strictEqual(await methods.checkExists.call(hookContext({}, calls)), false);
  assert.deepStrictEqual(calls, []);
  data = { hook_id: "hk_new", secret: "s_new" };
  assert.strictEqual(await methods.checkExists.call(hookContext(data, [], { hooks: [{ hook_id: "hk_new", revoked_at: null }] })), true);
  assert.strictEqual(await methods.checkExists.call(hookContext(data, [], { hooks: [{ hook_id: "hk_new", revoked_at: "2026-11-12T00:00:00Z" }] })), false);
  assert.strictEqual(await methods.checkExists.call(hookContext(data, [], { hooks: [{ hook_id: "hk_other" }] })), false);

  // Deactivating removes the hook and clears everything create wrote.
  calls = [];
  data = { hook_id: "hk_new", secret: "s_new" };
  assert.strictEqual(await methods.delete.call(hookContext(data, calls)), true);
  assert.deepStrictEqual(calls.map((call) => call.line), ["DELETE /v1/account/webhooks/hk_new"]);
  assert.deepStrictEqual(data, {});

  // A signed event gives one item per record, marked new or changed.
  let result = await node.webhook.call(webhookContext({ body: EVENT }));
  assert.deepStrictEqual(
    result.workflowData[0].map((item) => item.json),
    [
      { change: "new", event_id: "evt_1", monitor_id: "sch_1", run_id: "fnd_2", previous_run_id: "fnd_1", record: { entity_id: "e1", name: "Acme" } },
      { change: "changed", event_id: "evt_1", monitor_id: "sch_1", run_id: "fnd_2", previous_run_id: "fnd_1", record: { entity_id: "e2", name: "Bolt" } },
    ],
  );

  // Whole Event passes the event on as it was sent.
  result = await node.webhook.call(webhookContext({ body: EVENT, parameters: { output: "event" } }));
  assert.deepStrictEqual(result.workflowData, [[{ json: EVENT }]]);

  // Monitor ID: the named monitor starts the workflow, another one starts nothing.
  result = await node.webhook.call(webhookContext({ body: EVENT, parameters: { monitorId: " sch_1 " } }));
  assert.strictEqual(result.workflowData[0].length, 2);
  result = await node.webhook.call(webhookContext({ body: EVENT, parameters: { monitorId: "sch_9" } }));
  assert.strictEqual(result.workflowData, undefined);

  // An event with no records starts nothing.
  result = await node.webhook.call(webhookContext({ body: { ...EVENT, records: [] } }));
  assert.strictEqual(result.workflowData, undefined);

  // Refused: a wrong signature, no signature, an old one, no raw body, no stored secret, another event.
  const text = JSON.stringify(EVENT);
  await assert.rejects(node.webhook.call(webhookContext({ body: EVENT, signature: sign("other", text) })), /Invalid SpecStream signature/);
  await assert.rejects(node.webhook.call(webhookContext({ body: EVENT, signature: "" })), /Unverifiable/);
  await assert.rejects(
    node.webhook.call(webhookContext({ body: EVENT, signature: sign("s_new", text, Math.floor(Date.now() / 1000) - 301) })),
    /Unverifiable/,
  );
  await assert.rejects(node.webhook.call(webhookContext({ body: EVENT, raw: null, signature: sign("s_new", text) })), /Unverifiable/);
  await assert.rejects(node.webhook.call(webhookContext({ body: EVENT, secret: "" })), /Unverifiable/);
  await assert.rejects(node.webhook.call(webhookContext({ body: { ...EVENT, event: "find.completed" } })), /Unexpected SpecStream event/);

  console.log("trigger.test.js passed");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
