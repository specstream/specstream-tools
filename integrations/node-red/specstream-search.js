const lib = require("./lib");
module.exports = function (RED) {
  function SpecStreamSearch(config) {
    RED.nodes.createNode(this, config);
    const node = this;
    const cfg = RED.nodes.getNode(config.server);
    node.on("input", async (msg, send, done) => {
      try {
        const key = cfg && cfg.credentials && cfg.credentials.apiKey;
        if (!key) throw new Error("Missing SpecStream API key");
        const query = msg.payload && typeof msg.payload === "string" ? msg.payload : msg.query || config.query;
        if (!query) throw new Error("No query: set msg.payload or the Query field");
        const limit = msg.limit || config.limit;
        msg.payload = await lib.search(node.fetchImpl || fetch, key, query, limit);
        send(msg);
        done();
      } catch (e) {
        done(e);
      }
    });
  }
  RED.nodes.registerType("specstream search", SpecStreamSearch);
  module.exports.SpecStreamSearch = SpecStreamSearch;
};
