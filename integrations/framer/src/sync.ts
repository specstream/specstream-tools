import { type Column, dayOf, type FoundRecord, nameColumn, numberOf, oneLine, type ResultTable, uniqueName } from "./core/records";

export type FramerFieldType = "string" | "number" | "boolean" | "date" | "link";

export type FieldInput = { id: string; name: string; type: FramerFieldType };

export type FieldEntry =
	| { type: "string"; value: string }
	| { type: "number"; value: number | null }
	| { type: "boolean"; value: boolean }
	| { type: "date"; value: string | null }
	| { type: "link"; value: string | null };

export type ItemInput = { id: string; slug: string; draft: boolean; fieldData: Record<string, FieldEntry> };

export const SOURCE_FIELD_ID = "specstream-source";
export const READ_ON_FIELD_ID = "specstream-read-on";
// Framer allows 30 fields in a managed collection; two are kept for the source page and read date.
export const MAX_COLUMNS = 28;
const MAX_ID = 64;
const MAX_SLUG = 64;

export const PLUGIN_KEYS = {
	FIND_ID: "specstreamFindId",
	REQUEST: "specstreamRequest",
	SLUG_COLUMN: "specstreamSlugColumn",
	IGNORED: "specstreamIgnored",
} as const;

function typeFor(column: Column): FramerFieldType {
	switch (column.kind) {
		case "number":
			return "number";
		case "boolean":
			return "boolean";
		case "date":
			return "date";
		case "url":
			return "link";
		default:
			return "string";
	}
}

/** A field ID that stays the same on every sync, so canvas bindings survive a refresh. */
export function fieldId(columnId: string): string {
	return `col-${columnId}`.replace(/[^A-Za-z0-9_.:-]/g, "-").slice(0, MAX_ID);
}

export type FieldChoice = { column: Column | null; field: FieldInput };

/** Every column as a Framer field, then the source page and the date it was read. */
export function fieldsFor(table: ResultTable): { choices: FieldChoice[]; dropped: string[] } {
	const taken = new Set<string>();
	const ids = new Set<string>();
	const choices: FieldChoice[] = [];
	const dropped: string[] = [];
	for (const column of table.columns) {
		if (choices.length >= MAX_COLUMNS) {
			dropped.push(column.label);
			continue;
		}
		let id = fieldId(column.id);
		for (let n = 2; ids.has(id); n += 1) id = `${fieldId(column.id).slice(0, MAX_ID - 4)}-${n}`;
		ids.add(id);
		choices.push({ column, field: { id, name: uniqueName(column.label, taken), type: typeFor(column) } });
	}
	choices.push({ column: null, field: { id: SOURCE_FIELD_ID, name: uniqueName("Source", taken), type: "link" } });
	choices.push({ column: null, field: { id: READ_ON_FIELD_ID, name: uniqueName("Read on", taken), type: "date" } });
	return { choices, dropped };
}

/** Keeps a field's name if the person renamed it in an earlier sync. */
export function keepNames(fields: FieldInput[], existing: Array<{ id: string; name: string }>): FieldInput[] {
	const names = new Map(existing.map((field) => [field.id, field.name]));
	return fields.map((field) => ({ ...field, name: names.get(field.id) ?? field.name }));
}

export function slugify(text: string): string {
	return text
		.normalize("NFKD")
		.replace(/[\u0300-\u036f]/g, "")
		.replace(/\u00df/g, "ss")
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, "-")
		.replace(/^-+|-+$/g, "")
		.slice(0, MAX_SLUG)
		.replace(/-+$/g, "");
}

function entry(field: FieldInput, record: FoundRecord, column: Column | null): FieldEntry | null {
	if (field.id === SOURCE_FIELD_ID) return { type: "link", value: record.source };
	if (field.id === READ_ON_FIELD_ID) return { type: "date", value: dayOf(record.readAt) };
	if (!column) return null;
	const value = record.values.get(column.id);
	switch (field.type) {
		case "number":
			return { type: "number", value: value ? numberOf(value) : null };
		case "boolean":
			return { type: "boolean", value: value?.raw === true };
		case "date":
			return { type: "date", value: value ? dayOf(value.raw) : null };
		case "link":
			return { type: "link", value: value ? oneLine(value.shown) : null };
		default:
			return { type: "string", value: value ? value.shown : "" };
	}
}

/**
 * One item per result. The item ID is SpecStream's ID for the result, so syncing again updates
 * the same items. Slugs come from the chosen column and stay unique.
 */
export function itemsFor(table: ResultTable, choices: FieldChoice[], slugColumnId: string | null): ItemInput[] {
	const slugColumn = table.columns.find((column) => column.id === slugColumnId) ?? nameColumn(table);
	const slugs = new Set<string>();
	return table.records.map((record) => {
		const base = slugify(slugColumn ? (record.values.get(slugColumn.id)?.shown ?? "") : "") || slugify(record.id) || "item";
		let slug = base;
		for (let n = 2; slugs.has(slug); n += 1) slug = `${base.slice(0, MAX_SLUG - 6)}-${n}`;
		slugs.add(slug);
		const fieldData: Record<string, FieldEntry> = {};
		for (const choice of choices) {
			const value = entry(choice.field, record, choice.column);
			// Framer rejects null in number, date and link fields; an item without the value leaves the field empty.
			if (value && value.value !== null) fieldData[choice.field.id] = value;
		}
		return { id: record.id, slug, draft: false, fieldData };
	});
}

/** Items a previous sync added that the results no longer carry. */
export function staleItems(existingIds: string[], items: ItemInput[]): string[] {
	const current = new Set(items.map((item) => item.id));
	return existingIds.filter((id) => !current.has(id));
}
