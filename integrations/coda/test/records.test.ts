import { strict as assert } from "node:assert";
import { test } from "node:test";
import { codaRow, columnKey, columnsOf, listIdOf, readRecord, runKey, shownColumns, withCount } from "../records";

const found = {
  ordinal: 3,
  entity_id: "ent_1",
  cells: [
    { column_id: "identity", label: "Business", display: "Ace Roofing", provenance: { source_url: "https://ace.example/" } },
    { column_id: "maps.phone", label: "Phone", display: "+1 512 555 0100", provenance: { source_url: "https://maps.example/ace" } },
    { column_id: "web.email", label: "Email", absence: "not_published", display: "Not published" },
    { column_id: "open", label: "Open", display: "Open" },
  ],
};

test("found records keep each value with its page, and a value not found stays empty", () => {
  const columns = columnsOf([found]);
  assert.deepEqual(columns.map((c) => c.key), ["identity", "maps_phone", "web_email"]);
  const row = codaRow(readRecord(found), columns);
  assert.equal(row.record_id, "3");
  assert.equal(row.entity_id, "ent_1");
  assert.equal(row.maps_phone, "+1 512 555 0100");
  assert.equal(row.maps_phone_source, "https://maps.example/ace");
  assert.equal(row.web_email, null);
  assert.equal(row.open, undefined);
});

test("a new table shows each value beside its page and hides columns no record has", () => {
  const columns = columnsOf([found]);
  assert.deepEqual(shownColumns([readRecord(found)], columns), ["identity", "identity_source", "maps_phone", "maps_phone_source"]);
  const imported = readRecord({ id: "r1", provided: { Company: "Acme", Employees: 40 } });
  assert.deepEqual(shownColumns([imported], columnsOf([{ id: "r1", provided: { Company: "Acme", Employees: 40 } }])), ["Company", "Employees"]);
  assert.deepEqual(shownColumns([readRecord(found)], columns, 1), ["identity", "identity_source"]);
});

test("imported and combined rows read like found ones", () => {
  const imported = readRecord({ id: "r1", provided: { Company: "Acme", Employees: 40 } });
  assert.equal(imported.recordId, "r1");
  assert.equal(imported.cells.get("Employees")!.value, "40");
  const combined = readRecord({
    id: "r2",
    sources: [{ row: { entity_id: "ent_9" } }],
    field_values: { "maps.phone": [{ label: "Phone", display: "555", provenance: { source_url: "https://p.example" } }], matches: [{}] },
  });
  assert.equal(combined.entityId, "ent_9");
  assert.equal(combined.cells.get("maps.phone")!.source, "https://p.example");
  assert.equal(combined.cells.has("matches"), false);
});

test("keys, list IDs and run keys", () => {
  assert.equal(columnKey("job.location_countries"), "job_location_countries");
  assert.equal(columnKey("1st"), "column_1st");
  assert.equal(listIdOf("https://specstream.ai/workspace/collections/fnd_abc123"), "fnd_abc123");
  assert.throws(() => listIdOf("https://example.com/"));
  const hour = new Date("2026-10-16T07:10:00Z");
  assert.equal(runKey("roofers in Austin", 25, 500, hour), runKey("roofers in Austin", 25, 500, new Date("2026-10-16T07:59:00Z")));
  assert.notEqual(runKey("roofers in Austin", 25, 500, hour), runKey("roofers in Austin", 26, 500, hour));
  assert.match(runKey("café", 1, 1, hour), /^coda-[0-9a-f]{16}$/);
});

test("the reading names the number being priced", () => {
  assert.equal(withCount("25 roofers in Austin, Texas, US. Each with its phone.", 10), "10 roofers in Austin, Texas, US. Each with its phone.");
  assert.equal(withCount("Roofers in Austin", 10), "Roofers in Austin");
});
