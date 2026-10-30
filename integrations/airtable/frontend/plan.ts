import { type Column, dayOf, type FoundRecord, type Kind, numberOf, oneLine, type ResultTable, uniqueName, type Value } from "./core/records";

/** Airtable field type names, as the Blocks SDK's FieldType enum spells them. */
export type AirtableType =
	| "singleLineText"
	| "multilineText"
	| "richText"
	| "number"
	| "percent"
	| "currency"
	| "checkbox"
	| "date"
	| "dateTime"
	| "url"
	| "email"
	| "phoneNumber";

export type ExistingField = { id: string; name: string; type: string; computed: boolean };

/** Where one column's values go: an existing field, or a new one to create first. */
export type Target = {
	key: string;
	label: string;
	field: { id: string; name: string; type: AirtableType } | null;
	create: { name: string; type: AirtableType; options: Record<string, unknown> | null } | null;
};

export type Plan = { targets: Target[]; skipped: string[] };

export const ID_FIELD = "SpecStream ID";
export const SOURCE_FIELD = "Source";
export const READ_ON_FIELD = "Read on";
export const ID_KEY = "specstream:id";
export const SOURCE_KEY = "specstream:source";
export const READ_ON_KEY = "specstream:read_on";

const WRITABLE = new Set<string>([
	"singleLineText",
	"multilineText",
	"richText",
	"number",
	"percent",
	"currency",
	"checkbox",
	"date",
	"dateTime",
	"url",
	"email",
	"phoneNumber",
]);

const TEXT = new Set<string>(["singleLineText", "multilineText", "richText"]);

function typeFor(kind: Kind, precision: number): { type: AirtableType; options: Record<string, unknown> | null } {
	switch (kind) {
		case "number":
			return { type: "number", options: { precision } };
		case "boolean":
			return { type: "checkbox", options: { icon: "check", color: "greenBright" } };
		case "date":
			return { type: "date", options: { dateFormat: { name: "iso" } } };
		case "url":
			return { type: "url", options: null };
		case "email":
			return { type: "email", options: null };
		case "phone":
			return { type: "phoneNumber", options: null };
		case "longText":
			return { type: "multilineText", options: null };
		default:
			return { type: "singleLineText", options: null };
	}
}

// A field can take a column when Airtable can store its values without losing them.
function fits(fieldType: string, kind: Kind): boolean {
	if (!WRITABLE.has(fieldType)) return false;
	if (fieldType === "singleLineText" || fieldType === "multilineText" || fieldType === "richText") return true;
	if (fieldType === "number" || fieldType === "percent" || fieldType === "currency") return kind === "number";
	if (fieldType === "checkbox") return kind === "boolean";
	if (fieldType === "date" || fieldType === "dateTime") return kind === "date";
	if (fieldType === "url") return kind === "url";
	if (fieldType === "email") return kind === "email";
	if (fieldType === "phoneNumber") return kind === "phone";
	return false;
}

/**
 * Matches each column to a field of the same name, or plans a new field. A same-named field that
 * can't hold the column's values (a formula, or a number field for text) is left alone and the
 * column gets its own field instead, so nothing the base already computes is overwritten.
 */
export function planFields(table: ResultTable, existing: ExistingField[], options: { primary?: ExistingField | null } = {}): Plan {
	const byName = new Map(existing.map((field) => [field.name.trim().toLowerCase(), field]));
	const taken = new Set(existing.map((field) => field.name.trim().toLowerCase()));
	const targets: Target[] = [];
	const skipped: string[] = [];

	const columns: Array<{ key: string; label: string; kind: Kind; precision: number }> = [
		...table.columns.map((column: Column) => ({ key: column.id, label: column.label, kind: column.kind, precision: column.precision })),
		{ key: SOURCE_KEY, label: SOURCE_FIELD, kind: "url" as Kind, precision: 0 },
		{ key: READ_ON_KEY, label: READ_ON_FIELD, kind: "date" as Kind, precision: 0 },
		{ key: ID_KEY, label: ID_FIELD, kind: "text" as Kind, precision: 0 },
	];

	const primary = options.primary ?? null;
	const nameKey = table.columns.find((column) => column.kind === "text")?.id ?? null;

	for (const column of columns) {
		// Each record's name goes in the table's primary field, unless a field already carries the column's name.
		if (primary && column.key === nameKey && !byName.has(column.label.trim().toLowerCase()) && TEXT.has(primary.type)) {
			targets.push({ key: column.key, label: column.label, field: { id: primary.id, name: primary.name, type: primary.type as AirtableType }, create: null });
			continue;
		}
		const match = byName.get(column.label.trim().toLowerCase());
		if (match && !match.computed && fits(match.type, column.kind)) {
			targets.push({ key: column.key, label: column.label, field: { id: match.id, name: match.name, type: match.type as AirtableType }, create: null });
			continue;
		}
		const name = uniqueName(match ? `${column.label} (SpecStream)` : column.label, taken);
		const { type, options: fieldOptions } = typeFor(column.kind, column.precision);
		targets.push({ key: column.key, label: column.label, field: null, create: { name, type, options: fieldOptions } });
	}
	if (!table.columns.length) skipped.push("This result has no values to add.");
	return { targets, skipped };
}

/** The cell value Airtable expects for this field type, or undefined to leave the cell empty. */
export function cellFor(type: AirtableType, value: Value | null | undefined): unknown {
	if (!value) return undefined;
	switch (type) {
		case "singleLineText":
			return oneLine(value.shown).slice(0, 10000);
		case "multilineText":
		case "richText":
			return value.shown.slice(0, 100000);
		case "number":
		case "percent":
		case "currency": {
			const number = numberOf(value);
			return number === null ? undefined : number;
		}
		case "checkbox":
			return typeof value.raw === "boolean" ? value.raw : undefined;
		case "date":
			return dayOf(value.raw) ?? undefined;
		case "dateTime":
			return typeof value.raw === "string" && !Number.isNaN(Date.parse(value.raw)) ? new Date(value.raw).toISOString() : undefined;
		case "url":
		case "email":
		case "phoneNumber":
			return oneLine(value.shown);
		default:
			return undefined;
	}
}

/** Every value a record carries, keyed by the field ID it goes to. */
export function cellsFor(record: FoundRecord, targets: Array<{ key: string; fieldId: string; type: AirtableType }>): Record<string, unknown> {
	const fields: Record<string, unknown> = {};
	for (const target of targets) {
		let value: Value | null | undefined;
		if (target.key === SOURCE_KEY) value = record.source ? { raw: record.source, shown: record.source, source: null } : null;
		else if (target.key === READ_ON_KEY) value = record.readAt ? { raw: record.readAt, shown: record.readAt, source: null } : null;
		else if (target.key === ID_KEY) value = { raw: record.id, shown: record.id, source: null };
		else value = record.values.get(target.key);
		const cell = cellFor(target.type, value);
		if (cell !== undefined) fields[target.fieldId] = cell;
	}
	return fields;
}

/** Splits work into Airtable's write batches of 50 records. */
export function batches<T>(items: T[], size = 50): T[][] {
	const out: T[][] = [];
	for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
	return out;
}
