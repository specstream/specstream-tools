"use strict";

const assert = require("assert");
const { resolveBase } = require("../lib/base.js");

// The key is sent only to the SpecStream API over https.
assert.strictEqual(resolveBase(""), "https://api.specstream.ai");
assert.strictEqual(resolveBase("https://api.specstream.ai/"), "https://api.specstream.ai");
for (const bad of [
  "http://api.specstream.ai",
  "https://api.specstream.ai.evil.example",
  "https://user:pass@api.specstream.ai",
  "https://api.specstream.ai/v1",
  "https://api.specstream.ai?x=1",
  "not a url",
]) {
  assert.throws(() => resolveBase(bad), /API Base URL must be/, bad);
}

console.log("base.test.js passed");
