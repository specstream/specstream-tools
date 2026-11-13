module.exports = function (RED) {
  function SpecStreamConfig(n) {
    RED.nodes.createNode(this, n);
  }
  RED.nodes.registerType("specstream-config", SpecStreamConfig, {
    credentials: { apiKey: { type: "password" } },
  });
};
