import assert from "node:assert/strict";
import { test } from "node:test";
import { nameColumn, openable, tableOf, uniqueName } from "../src/core/records";
import type { AcceptedRow } from "../src/core/specstream";

const MAPS_FETCH = "https://www.google.com/maps/preview/place?authuser=0&pb=%211m14%211s0xa5cede46c5afd729%3A0xbaa68e991ed8c454";

function cell(column_id: string, label: string, value: unknown, extra: Record<string, unknown> = {}) {
	return { column_id, label, value, display: typeof value === "string" ? value : undefined, provenance: { source_url: "https://example.com/shop", observed_at: "2026-10-17T09:00:00Z" }, ...extra };
}

const ROWS: AcceptedRow[] = [
	{
		entity_id: "ent_a",
		cells: [
			cell("business", "Business", "Cuvée Coffee"),
			cell("reviews", "Reviews", 812, { display: "4.6 · 812", provenance: { source_url: MAPS_FETCH } }),
			cell("website", "Website", "https://cuveecoffee.com"),
			cell("phone", "Phone", "(512) 555-0134"),
			cell("site", "Site", null, { display: "Couldn't check", absence: "Couldn't check" }),
			cell("matches", "Matches", true, { display: "Why it matches" }),
			cell("open", "Open", "https://cuveecoffee.com", { display: "Open" }),
			cell("copy", "Copy", "Cuvée Coffee"),
		],
		details: [cell("opened", "Opened", "2012-05-01"), cell("about", "About", "Roaster.\nCafe.")],
	},
	{
		entity_id: "ent_b",
		cells: [
			cell("business", "Business", "Merit Coffee"),
			cell("reviews", "Reviews", 95, { display: "4.8 · 95", provenance: { source_url: MAPS_FETCH } }),
			cell("website", "Website", "https://meritcoffee.com"),
			cell("phone", "Phone", "+1 512 555 0188"),
			cell("copy", "Copy", "Merit Coffee"),
		],
		details: [cell("opened", "Opened", "2009-03-14")],
	},
];

test("columns are typed, controls and empty or repeated columns are left out", () => {
	const table = tableOf(ROWS);
	assert.deepEqual(
		table.columns.map((column) => [column.label, column.kind]),
		[
			["Business", "text"],
			["Rating", "number"],
			["Reviews", "number"],
			["Website", "url"],
			["Phone", "phone"],
			["Opened", "date"],
			["About", "longText"],
		],
	);
	assert.equal(table.records.length, 2);
	assert.equal(table.records[0]?.values.get("reviews:rating")?.raw, 4.6);
	assert.equal(table.records[1]?.values.get("reviews:rating")?.raw, 4.8);
	assert.equal(nameColumn(table)?.label, "Business");
});

test("each record keeps its stable ID, its first source page and when it was read", () => {
	const [first] = tableOf(ROWS).records;
	assert.equal(first?.id, "ent_a");
	assert.equal(first?.source, "https://example.com/shop");
	assert.equal(first?.readAt, "2026-10-17T09:00:00Z");
});

test("a Maps fetch becomes the place's listing and search pages are no source", () => {
	assert.equal(openable(MAPS_FETCH), `https://www.google.com/maps?cid=${BigInt("0xbaa68e991ed8c454").toString()}`);
	assert.equal(openable(MAPS_FETCH, "https://www.google.com/maps/place/Merit"), "https://www.google.com/maps/place/Merit");
	assert.equal(openable("https://www.google.com/search?q=coffee"), null);
	assert.equal(openable("https://api.example.com/v2/items"), null);
	assert.equal(openable("https://data.example.org/export.csv"), null);
	assert.equal(openable("javascript:alert(1)"), null);
	assert.equal(openable("https://cuveecoffee.com/about"), "https://cuveecoffee.com/about");
});

test("names stay unique without regard to case", () => {
	const taken = new Set(["name", "source"]);
	assert.equal(uniqueName("Name", taken), "Name (2)");
	assert.equal(uniqueName("Source", taken), "Source (2)");
	assert.equal(uniqueName("Website", taken), "Website");
	assert.equal(uniqueName("website", taken), "website (2)");
});
