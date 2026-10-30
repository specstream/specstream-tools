"use strict";

const assert = require("assert");
const { flatRowsById, flattenRow, resolveBase, runKey } = require("../lib/specstream");

// Credentials go only to https://api.specstream.ai.
assert.strictEqual(resolveBase(""), "https://api.specstream.ai");
assert.strictEqual(resolveBase("https://api.specstream.ai/"), "https://api.specstream.ai");
for (const bad of [
  "http://api.specstream.ai",
  "https://api.specstream.ai.evil.com",
  "https://evil.com",
  "https://api.specstream.ai@evil.com",
  "https://user:pw@api.specstream.ai",
  "https://api.specstream.ai/v1",
  "api.specstream.ai",
]) {
  assert.throws(() => resolveBase(bad), /API Base URL must be/, bad);
}

// The run key is stable for the same request within one UTC hour.
const base = { request: "Roofers in Columbus", count: 25, maxPrice: 5 };
const a = runKey({ ...base, now: new Date("2026-10-15T10:01:00Z") });
assert.strictEqual(a, runKey({ ...base, now: new Date("2026-10-15T10:59:59Z") }));
assert.match(a, /^n8n-[a-f0-9]{32}$/);
assert.notStrictEqual(a, runKey({ ...base, now: new Date("2026-10-15T11:00:00Z") }));
assert.notStrictEqual(a, runKey({ ...base, count: 26, now: new Date("2026-10-15T10:30:00Z") }));
assert.notStrictEqual(a, runKey({ ...base, request: "Plumbers", now: new Date("2026-10-15T10:30:00Z") }));
assert.notStrictEqual(a, runKey({ ...base, maxPrice: 6, now: new Date("2026-10-15T10:30:00Z") }));
assert.strictEqual(runKey({ ...base, override: " my-own-key-1 " }), "my-own-key-1");

// Columns named like built-in fields never overwrite them. The pages come from the API's flat row:
// the filing that put the row in the list, not the first value's page.
const cell = (label, display, provenance) => ({ label, display, provenance });
const flat = {
  id: "fnd_1:e1",
  name: "Acme",
  name_source: "https://a.example/p",
  rating: "4.6",
  rating_source: "https://maps.example/acme",
  lead_source: "Referral",
  source_url: "https://www.sec.gov/filing",
  checked_at: "2026-10-16T00:00:00Z",
};
const row = flattenRow("fnd_1", {
  entity_id: "e1",
  ordinal: 3,
  cells: [
    cell("rating_source", "x"),
    cell("id", "col-id", { source_url: "https://a.example/p", observed_at: "2026-10-15T00:00:00Z" }),
    cell("list_id", "x"),
    cell("list_link", "x"),
    cell("position", "x"),
    cell("source_url", "col-src"),
    cell("checked_at", "x"),
    cell("list_status", "x"),
    cell("id (column)", "second"),
    cell("Name", "Acme"),
    cell("Name", "Acme again"),
  ],
}, flatRowsById([flat]).get("fnd_1:e1"));
assert.strictEqual(row.id, "fnd_1:e1");
assert.strictEqual(row.list_id, "fnd_1");
assert.strictEqual(row.list_link, "https://specstream.ai/workspace/collections/fnd_1");
assert.strictEqual(row.position, 3);
assert.strictEqual(row.source_url, "https://www.sec.gov/filing");
assert.strictEqual(row.checked_at, "2026-10-16T00:00:00Z");
assert.deepStrictEqual([row.name_source, row.rating_source], ["https://a.example/p", "https://maps.example/acme"]);
assert.strictEqual(row["rating_source (column)"], "x");
assert.strictEqual(row.lead_source, undefined);
assert.strictEqual(row["id (column)"], "col-id");
assert.strictEqual(row["id (column) (column)"], "second");
assert.strictEqual(row["source_url (column)"], "col-src");
assert.strictEqual(row["list_status (column)"], "x");
assert.strictEqual(row.Name, "Acme");
assert.strictEqual(row["Name (column)"], "Acme again");

console.log("n8n specstream helpers ok");
