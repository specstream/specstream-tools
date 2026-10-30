import type { AcceptedRow, RowCell } from "./specstream";

export type Kind = "text" | "longText" | "number" | "boolean" | "date" | "url" | "email" | "phone";

export type Column = {
	id: string;
	label: string;
	kind: Kind;
	/** Digits after the decimal point, for number columns. */
	precision: number;
};

export type Value = { raw: unknown; shown: string; source: string | null };

export type FoundRecord = {
	/** SpecStream's stable ID for the result, the same on every refresh. */
	id: string;
	values: Map<string, Value>;
	/** The page the record's first value was read from. */
	source: string | null;
	readAt: string | null;
};

export type ResultTable = { columns: Column[]; records: FoundRecord[] };

// Row controls in the workspace, not data.
const CONTROLS = new Set(["matches", "open"]);

/** The workspace's controls, the line naming where a place was read (its link names it), and the site check
 * whose "custom" says only that the business runs its own site: none of them is a fact for a field. */
function skipped(cell: RowCell, key: string): boolean {
	if (CONTROLS.has(key) || key.endsWith(".attribution")) return true;
	const shown = typeof cell.display === "string" ? cell.display : typeof cell.value === "string" ? cell.value : "";
	return key === "site" && shown.trim().toLowerCase() === "custom";
}
const MAPS_LISTING = "https://www.google.com/maps/place/";
const MAPS_FETCHES = ["www.google.com/search?tbm=map", "www.google.com/maps/preview/"];
const SEARCH_PAGES = ["html.duckduckgo.com/", "duckduckgo.com/html", "search.yahoo.com/", "www.google.com/search", "www.bing.com/search"];
const PLACE_ID = /!1s0x[0-9a-f]+:0x([0-9a-f]+)/i;
const DATA_FILE = /\.(?:json|parquet|csv|zst|zstd|gz)$/i;
// The workspace shows a place's rating and review count together, as "4.6 · 22".
const RATED = /^(\d(?:\.\d+)?) · \d[\d,]*$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;
const MOMENT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$/;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PHONE = /^[+(]?[\d][\d\s().-]{5,}$/;
const LONG_TEXT = 255;

function plain(raw: unknown): string | null {
	if (raw === null || raw === undefined) return null;
	if (typeof raw === "string") return raw;
	if (typeof raw === "boolean") return raw ? "Yes" : "No";
	if (typeof raw === "number") return Number.isFinite(raw) ? String(raw) : null;
	if (Array.isArray(raw) && raw.every((item) => typeof item === "string")) return raw.join(", ");
	return JSON.stringify(raw);
}

/** A page a person can open: a Maps fetch becomes the place's own listing, and a search page is no source. */
export function openable(url: unknown, listing: string | null = null): string | null {
	if (typeof url !== "string" || !/^https?:\/\//.test(url)) return null;
	if (MAPS_FETCHES.some((fetch) => url.includes(fetch))) {
		if (listing) return listing;
		let decoded = url;
		try {
			decoded = decodeURIComponent(url);
		} catch {
			decoded = url;
		}
		const place = PLACE_ID.exec(decoded);
		return place ? `https://www.google.com/maps?cid=${BigInt(`0x${place[1]}`).toString()}` : null;
	}
	if (SEARCH_PAGES.some((search) => url.includes(search))) return null;
	let parsed: URL;
	try {
		parsed = new URL(url);
	} catch {
		return null;
	}
	const host = parsed.hostname.toLowerCase();
	// A data file or an API answer is where a value came from, but not a page a person reads.
	if (DATA_FILE.test(parsed.pathname) || host.startsWith("api.") || host.includes(".s3.") || parsed.pathname.includes("/api/")) {
		return null;
	}
	return parsed.href;
}

function listingOf(cells: RowCell[]): string | null {
	for (const cell of cells) {
		if (typeof cell.value === "string" && cell.value.startsWith(MAPS_LISTING)) return cell.value;
	}
	return null;
}

function valueOf(cell: RowCell, listing: string | null): Value | null {
	if (cell.absence || cell.value === null || cell.value === undefined) return null;
	const display = typeof cell.display === "string" && cell.display.trim() ? cell.display : null;
	const shown = display ?? plain(cell.value);
	if (!shown || !shown.trim()) return null;
	return { raw: cell.value, shown: shown.trim(), source: openable(cell.provenance?.source_url, listing) };
}

function isNumber(raw: unknown): raw is number {
	return typeof raw === "number" && Number.isFinite(raw);
}

function isUrl(text: string): boolean {
	return /^https?:\/\/\S+$/i.test(text);
}

function kindOf(id: string, label: string, values: Value[]): Kind {
	const raws = values.map((value) => value.raw);
	const shown = values.map((value) => value.shown);
	if (raws.every((raw) => typeof raw === "boolean")) return "boolean";
	if (raws.every(isNumber)) return "number";
	if (raws.every((raw) => typeof raw === "string" && (DAY.test(raw) || MOMENT.test(raw)))) return "date";
	if (raws.every((raw) => typeof raw === "string" && isUrl(raw))) return "url";
	if (shown.every((item) => EMAIL.test(item))) return "email";
	const named = `${id} ${label}`.toLowerCase();
	if (/phone|tel\b|telephone/.test(named) && shown.every((item) => PHONE.test(item))) return "phone";
	if (shown.some((item) => item.length > LONG_TEXT || /[\r\n]/.test(item))) return "longText";
	return "text";
}

function precisionOf(values: Value[]): number {
	let digits = 0;
	for (const value of values) {
		if (!isNumber(value.raw)) continue;
		const decimals = String(value.raw).split(".")[1];
		if (decimals) digits = Math.max(digits, decimals.length);
	}
	return Math.min(digits, 8);
}

/**
 * The results as typed columns and records. A column empty in every record, or one that repeats
 * an earlier column value for value, adds nothing and is left out.
 */
export function tableOf(rows: AcceptedRow[]): ResultTable {
	const labels = new Map<string, string>();
	const records: FoundRecord[] = [];
	for (const row of rows) {
		const cells = [...(row.cells ?? []), ...(row.details ?? [])];
		const listing = listingOf(cells);
		const values = new Map<string, Value>();
		let source: string | null = null;
		let readAt: string | null = null;
		for (const cell of cells) {
			const key = cell.column_id;
			if (typeof key !== "string" || !key || values.has(key) || skipped(cell, key)) continue;
			if (!labels.has(key)) labels.set(key, (cell.label || key).trim() || key);
			const value = valueOf(cell, listing);
			if (!value) continue;
			values.set(key, value);
			if (!source && value.source) source = value.source;
			const observed = cell.provenance?.observed_at;
			if (!readAt && typeof observed === "string" && observed) readAt = observed;
		}
		records.push({ id: row.entity_id, values, source, readAt });
	}

	const columns: Column[] = [];
	const seen = new Set<string>();
	for (const [id, label] of labels) {
		const values = records.map((record) => record.values.get(id)).filter((value): value is Value => value !== undefined);
		if (!values.length) continue;
		const fingerprint = JSON.stringify(records.map((record) => record.values.get(id)?.shown ?? null));
		if (seen.has(fingerprint)) continue;
		seen.add(fingerprint);
		const kind = kindOf(id, label, values);
		if (kind === "number" && values.some((value) => RATED.test(value.shown))) {
			for (const record of records) {
				const rated = RATED.exec(record.values.get(id)?.shown ?? "");
				const reviews = record.values.get(id);
				if (rated && reviews) record.values.set(`${id}:rating`, { raw: Number(rated[1]), shown: rated[1] ?? "", source: reviews.source });
			}
			// A rating column of its own later on repeats this one value for value, and is left out.
			const rating = JSON.stringify(records.map((record) => record.values.get(`${id}:rating`)?.shown ?? null));
			if (!seen.has(rating)) {
				seen.add(rating);
				columns.push({ id: `${id}:rating`, label: "Rating", kind: "number", precision: 1 });
			}
		}
		columns.push({ id, label, kind, precision: kind === "number" ? precisionOf(values) : 0 });
	}
	return { columns, records };
}

/** The column that names each record, for a primary field or a slug: the first text column. */
export function nameColumn(table: ResultTable): Column | null {
	return table.columns.find((column) => column.kind === "text") ?? table.columns.find((column) => column.kind === "longText") ?? null;
}

/** `name`, or `name (2)`, `name (3)`... until it is free, compared without case. */
export function uniqueName(name: string, taken: Set<string>): string {
	const base = name.trim() || "Field";
	let candidate = base;
	for (let n = 2; taken.has(candidate.toLowerCase()); n += 1) candidate = `${base} (${n})`;
	taken.add(candidate.toLowerCase());
	return candidate;
}

/** The value as plain text on one line, for fields that hold a single line. */
export function oneLine(text: string): string {
	return text.replace(/\s+/g, " ").trim();
}

/** A calendar day for a date field, from a day or a moment. */
export function dayOf(raw: unknown): string | null {
	if (typeof raw !== "string") return null;
	if (DAY.test(raw)) return raw;
	if (MOMENT.test(raw)) {
		const time = Date.parse(raw);
		return Number.isNaN(time) ? null : new Date(time).toISOString().slice(0, 10);
	}
	return null;
}

export function numberOf(value: Value): number | null {
	if (isNumber(value.raw)) return value.raw;
	const parsed = Number(value.shown.replace(/[,\s]/g, ""));
	return Number.isFinite(parsed) && /\d/.test(value.shown) ? parsed : null;
}
