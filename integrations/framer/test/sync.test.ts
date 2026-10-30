import assert from "node:assert/strict";
import { test } from "node:test";
import { tableOf } from "../src/core/records";
import type { AcceptedRow } from "../src/core/specstream";
import { fieldId, fieldsFor, itemsFor, keepNames, MAX_COLUMNS, READ_ON_FIELD_ID, slugify, SOURCE_FIELD_ID, staleItems } from "../src/sync";

const row = (id: string, name: string, rating: number, extra: Record<string, unknown> = {}): AcceptedRow => ({
	entity_id: id,
	cells: [
		{ column_id: "name", label: "Name", value: name, provenance: { source_url: `https://${id}.example/`, observed_at: "2026-10-17T09:00:00Z" } },
		{ column_id: "rating", label: "Rating", value: rating, display: String(rating) },
		{ column_id: "website", label: "Website", value: `https://${id}.example` },
		{ column_id: "open_now", label: "Open now", value: true, display: "Yes" },
		...Object.entries(extra).map(([key, value]) => ({ column_id: key, label: key, value })),
	],
});

const ROWS = [row("ent_a", "Café Olé", 4.6), row("ent_b", "Café Olé", 4.2), row("ent_c", "Merit Coffee", 4.8)];

test("each column becomes a Framer field with a stable ID, then source and read date", () => {
	const { choices, dropped } = fieldsFor(tableOf(ROWS));
	assert.deepEqual(
		choices.map((choice) => [choice.field.id, choice.field.name, choice.field.type]),
		[
			["col-name", "Name", "string"],
			["col-rating", "Rating", "number"],
			["col-website", "Website", "link"],
			["col-open_now", "Open now", "boolean"],
			[SOURCE_FIELD_ID, "Source", "link"],
			[READ_ON_FIELD_ID, "Read on", "date"],
		],
	);
	assert.deepEqual(dropped, []);
});

test("items keep SpecStream's result ID and get unique slugs", () => {
	const table = tableOf(ROWS);
	const { choices } = fieldsFor(table);
	const items = itemsFor(table, choices, "name");
	assert.deepEqual(
		items.map((item) => [item.id, item.slug]),
		[
			["ent_a", "cafe-ole"],
			["ent_b", "cafe-ole-2"],
			["ent_c", "merit-coffee"],
		],
	);
	assert.deepEqual(items[0]?.fieldData["col-rating"], { type: "number", value: 4.6 });
	assert.deepEqual(items[0]?.fieldData["col-open_now"], { type: "boolean", value: true });
	assert.deepEqual(items[0]?.fieldData[SOURCE_FIELD_ID], { type: "link", value: "https://ent_a.example/" });
	assert.deepEqual(items[0]?.fieldData[READ_ON_FIELD_ID], { type: "date", value: "2026-10-17" });
	assert.equal(items[0]?.draft, false);
});

test("Framer's 30 field limit leaves room for source and read date", () => {
	const extra = Object.fromEntries(Array.from({ length: 40 }, (_, i) => [`extra_${i}`, `value ${i}`]));
	const { choices, dropped } = fieldsFor(tableOf([row("ent_a", "A", 4, extra)]));
	assert.equal(choices.length, MAX_COLUMNS + 2);
	assert.equal(dropped.length, 4 + 40 - MAX_COLUMNS);
});

test("syncing again keeps names a person changed and removes results that left", () => {
	assert.deepEqual(keepNames([{ id: "col-name", name: "Name", type: "string" }], [{ id: "col-name", name: "Shop" }]), [
		{ id: "col-name", name: "Shop", type: "string" },
	]);
	const table = tableOf(ROWS);
	const items = itemsFor(table, fieldsFor(table).choices, null);
	assert.deepEqual(staleItems(["ent_a", "ent_gone"], items), ["ent_gone"]);
});

test("slugs and field IDs are safe", () => {
	assert.equal(slugify("  Joe's Pizza & Pasta!! "), "joe-s-pizza-pasta");
	assert.equal(slugify("Zürich Straße"), "zurich-strasse");
	assert.equal(fieldId("maps.url"), "col-maps.url");
	assert.ok(fieldId("x".repeat(100)).length <= 64);
});
