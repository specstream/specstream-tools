import assert from "node:assert/strict";
import { test } from "node:test";
import { tableOf } from "../frontend/core/records";
import type { AcceptedRow } from "../frontend/core/specstream";
import { batches, cellFor, cellsFor, ID_KEY, planFields, READ_ON_KEY, SOURCE_KEY } from "../frontend/plan";

const ROWS: AcceptedRow[] = [
	{
		entity_id: "ent_a",
		cells: [
			{ column_id: "name", label: "Name", value: "Cuvée Coffee", provenance: { source_url: "https://cuvee.example/", observed_at: "2026-10-17T09:00:00Z" } },
			{ column_id: "rating", label: "Rating", value: 4.6, display: "4.6" },
			{ column_id: "website", label: "Website", value: "https://cuvee.example" },
			{ column_id: "open_now", label: "Open now", value: true, display: "Yes" },
		],
	},
];

test("a new table gets one field per column, plus source, read date and SpecStream ID", () => {
	const plan = planFields(tableOf(ROWS), []);
	assert.deepEqual(
		plan.targets.map((target) => [target.create?.name, target.create?.type]),
		[
			["Name", "singleLineText"],
			["Rating", "number"],
			["Website", "url"],
			["Open now", "checkbox"],
			["Source", "url"],
			["Read on", "date"],
			["SpecStream ID", "singleLineText"],
		],
	);
	assert.deepEqual(plan.targets[1]?.create?.options, { precision: 1 });
});

test("existing fields are reused when they can hold the values, never overwritten when they can't", () => {
	const existing = [
		{ id: "fld_primary", name: "Shop", type: "singleLineText", computed: false },
		{ id: "fld_rating", name: "rating", type: "formula", computed: true },
		{ id: "fld_web", name: "Website", type: "url", computed: false },
		{ id: "fld_src", name: "Source", type: "singleLineText", computed: false },
	];
	const plan = planFields(tableOf(ROWS), existing, { primary: existing[0] });
	const byKey = new Map(plan.targets.map((target) => [target.key, target]));
	assert.equal(byKey.get("name")?.field?.id, "fld_primary");
	assert.equal(byKey.get("rating")?.field, null);
	assert.equal(byKey.get("rating")?.create?.name, "Rating (SpecStream)");
	assert.equal(byKey.get("website")?.field?.id, "fld_web");
	assert.equal(byKey.get(SOURCE_KEY)?.field?.id, "fld_src");
	assert.equal(byKey.get(ID_KEY)?.create?.name, "SpecStream ID");
});

test("cell values follow the target field's type", () => {
	const value = (raw: unknown, shown: string) => ({ raw, shown, source: null });
	assert.equal(cellFor("singleLineText", value("a\nb", "a\nb")), "a b");
	assert.equal(cellFor("multilineText", value("a\nb", "a\nb")), "a\nb");
	assert.equal(cellFor("number", value("1,204", "1,204")), 1204);
	assert.equal(cellFor("number", value("n/a", "n/a")), undefined);
	assert.equal(cellFor("checkbox", value(true, "Yes")), true);
	assert.equal(cellFor("date", value("2026-10-17T09:00:00Z", "Oct 17")), "2026-10-17");
	assert.equal(cellFor("url", value("https://x.example", "https://x.example")), "https://x.example");
	assert.equal(cellFor("url", null), undefined);
});

test("a record's cells go to field IDs, with its source, read date and ID", () => {
	const [record] = tableOf(ROWS).records;
	assert.ok(record);
	const fields = cellsFor(record, [
		{ key: "name", fieldId: "f1", type: "singleLineText" },
		{ key: "rating", fieldId: "f2", type: "number" },
		{ key: SOURCE_KEY, fieldId: "f3", type: "url" },
		{ key: READ_ON_KEY, fieldId: "f4", type: "date" },
		{ key: ID_KEY, fieldId: "f5", type: "singleLineText" },
	]);
	assert.deepEqual(fields, { f1: "Cuvée Coffee", f2: 4.6, f3: "https://cuvee.example/", f4: "2026-10-17", f5: "ent_a" });
});

test("writes go in batches of 50", () => {
	const sizes = batches(Array.from({ length: 120 }, (_, i) => i)).map((batch) => batch.length);
	assert.deepEqual(sizes, [50, 50, 20]);
});
