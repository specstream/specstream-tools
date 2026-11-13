const lib = require("./lib");
module.exports = function (RED) {
  function SpecStreamExtract(config) {
    RED.nodes.createNode(this, config);
    const node = this;
    const cfg = RED.nodes.getNode(config.server);
    node.on("input", async (msg, send, done) => {
      try {
        const key = cfg && cfg.credentials && cfg.credentials.apiKey;
        if (!key) throw new Error("Missing SpecStream API key");
        let urls = msg.urls || msg.payload;
        if (typeof urls === "string") urls = [urls];
        if (!Array.isArray(urls) || !urls.length) throw new Error("No URLs: set msg.payload to a URL or an array of URLs");
        msg.payload = await lib.extract(node.fetchImpl || fetch, key, urls);
        send(msg);
        done();
      } catch (e) {
        done(e);
      }
    });
  }
  RED.nodes.registerType("specstream extract", SpecStreamExtract);
};
