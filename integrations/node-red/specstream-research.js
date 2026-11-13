const lib = require("./lib");
module.exports = function (RED) {
  function SpecStreamResearch(config) {
    RED.nodes.createNode(this, config);
    const node = this;
    const cfg = RED.nodes.getNode(config.server);
    node.on("input", async (msg, send, done) => {
      const f = node.fetchImpl || fetch;
      try {
        const key = cfg && cfg.credentials && cfg.credentials.apiKey;
        if (!key) throw new Error("Missing SpecStream API key");
        // msg.reportId reads a report that was started earlier. Reading is free.
        if (msg.reportId) {
          msg.payload = await lib.getResearch(f, key, String(msg.reportId));
          node.status({});
          send(msg);
          done();
          return;
        }
        const question = typeof msg.payload === "string" && msg.payload.trim() ? msg.payload : msg.question || config.question;
        const body = lib.researchBody(question, msg.depth || config.depth);
        const created = await lib.startResearch(f, key, body, lib.idempotencyKey(msg._msgid, node.id));
        if (!created || !created.id) throw new Error("SpecStream started no report");
        msg.reportId = String(created.id);
        const wait = msg.wait === undefined ? config.wait !== false : msg.wait !== false;
        if (!wait) {
          msg.payload = created;
        } else {
          node.status({ fill: "blue", shape: "dot", text: "writing the report" });
          msg.payload = await lib.waitForResearch(f, key, msg.reportId, config.waitMinutes, config.everySeconds, node.sleepImpl);
        }
        node.status({});
        send(msg);
        done();
      } catch (e) {
        node.status({ fill: "red", shape: "ring", text: "no report" });
        done(e);
      }
    });
  }
  RED.nodes.registerType("specstream research", SpecStreamResearch);
};
