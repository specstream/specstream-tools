export const API_BASE = "https://api.specstream.ai";
export const WORKSPACE_URL = "https://specstream.ai/workspace";
export const API_KEYS_URL = "https://specstream.ai/workspace/agents";
export const PRIVACY_URL = "https://specstream.ai/privacy";
export const PRICING_URL = "https://specstream.ai/pricing";

const FINISHED = new Set(["completed", "partial"]);
const STOPPED = new Set(["failed", "canceled", "cancelled", "expired"]);
// Ten thousand results at 100 per page, the most one request can bring back.
const MAX_ROW_PAGES = 100;

export const isFinished = (status: string): boolean => FINISHED.has(status);
export const isStopped = (status: string): boolean => STOPPED.has(status);

export class SpecStreamError extends Error {
	readonly status: number | null;
	readonly code: string | null;

	constructor(message: string, status: number | null = null, code: string | null = null) {
		super(message);
		this.name = "SpecStreamError";
		this.status = status;
		this.code = code;
	}
}

export type Chip = { category: string; label: string; status: string };

export type Reading = {
	request: string;
	runnable: boolean;
	astHash: string | null;
	sentence: string | null;
	notice: string | null;
	/** The result count written in the request itself, when it names one. */
	statedRows: number | null;
	lookingFor: string[];
	mustMeet: string[];
	bringsBack: string[];
};

export type Quote = {
	quoteId: string;
	quoteHash: string;
	currency: string;
	maximumCents: number;
	unitCents: number | null;
	expiresAt: string;
	canAuthorize: boolean;
	rows: number;
};

export type Run = { findId: string; state: string };

export type Progress = { status: string; requested: number; found: number };

export type Account = { email: string | null; availableCents: number | null };

export type PastResult = { name: string; findId: string; rows: number; createdAt: string };

export type Provenance = { source_url?: string | null; observed_at?: string | null };

export type RowCell = {
	column_id: string;
	label: string;
	value: unknown;
	display?: string | null;
	absence?: string | null;
	provenance?: Provenance | null;
};

export type AcceptedRow = { entity_id: string; ordinal?: number; cells: RowCell[]; details?: RowCell[] };

export type Fetch = (url: string, init: RequestInit) => Promise<Response>;

function isObject(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): string | null {
	return typeof value === "string" && value.trim() ? value : null;
}

function count(value: unknown): number {
	return typeof value === "number" && Number.isFinite(value) ? Math.trunc(value) : 0;
}

function plainError(status: number, code: string | null, message: string | null): string {
	if (status === 401) {
		return "SpecStream didn't accept this API key. Check it in settings, or create a new key under Agents & API in your SpecStream workspace.";
	}
	if (status === 402) return "Your SpecStream balance can't cover this. Add funds in your workspace, then try again.";
	if (status === 403) return message ?? "This API key can't do that. Create a key with full access under Agents & API.";
	if (status === 429) return "SpecStream asked for a short pause. Try again in a minute.";
	if (status >= 500) return "SpecStream couldn't answer right now. Try again in a minute.";
	if (message) return message;
	return code ? `SpecStream couldn't do that (${code}).` : `SpecStream answered with an error (HTTP ${status}).`;
}

function chipLabels(chips: unknown, categories: string[]): string[] {
	if (!Array.isArray(chips)) return [];
	const labels: string[] = [];
	for (const chip of chips) {
		if (!isObject(chip) || !categories.includes(String(chip.category))) continue;
		// Output chips read "Bring back: Google rating"; the list already sits under "Brings back".
		const label = text(chip.label)?.replace(/^Bring back:\s*/i, "") ?? null;
		if (label && !labels.includes(label)) labels.push(label);
	}
	return labels;
}

export function money(cents: number, currency = "USD"): string {
	const symbol = currency === "EUR" ? "€" : currency === "GBP" ? "£" : "$";
	return `${symbol}${(cents / 100).toFixed(2)}`;
}

export function resultLink(findId: string): string {
	return `${WORKSPACE_URL}/collections/${encodeURIComponent(findId)}`;
}

/** The few SpecStream REST calls an app makes. Credentials go only to API_BASE. */
export class SpecStreamClient {
	private readonly authorization: string;
	private readonly fetcher: Fetch;
	private readonly app: string;

	constructor(apiKey: string, options: { app: string; fetch?: Fetch }) {
		const key = apiKey.trim();
		if (!key) throw new SpecStreamError("Add your SpecStream API key in settings first.");
		this.authorization = /^bearer /i.test(key) ? key : `Bearer ${key}`;
		this.fetcher = options.fetch ?? ((url, init) => fetch(url, init));
		this.app = options.app;
	}

	private async request(method: "GET" | "POST", path: string, body?: Record<string, unknown>): Promise<Record<string, unknown>> {
		let response: Response;
		try {
			response = await this.fetcher(API_BASE + path, {
				method,
				headers: {
					Authorization: this.authorization,
					Accept: "application/json",
					...(body === undefined ? {} : { "Content-Type": "application/json" }),
				},
				body: body === undefined ? undefined : JSON.stringify(body),
				credentials: "omit",
			});
		} catch {
			throw new SpecStreamError("Couldn't reach SpecStream. Check your connection and try again.");
		}
		let payload: unknown = null;
		try {
			payload = JSON.parse((await response.text()) || "null");
		} catch {
			payload = null;
		}
		if (response.status < 200 || response.status >= 300) {
			const detail = isObject(payload) && isObject(payload.error) ? payload.error : {};
			throw new SpecStreamError(
				plainError(response.status, text(detail.code), text(detail.message)),
				response.status,
				text(detail.code),
			);
		}
		const data = isObject(payload) ? payload.data : undefined;
		if (!isObject(data)) throw new SpecStreamError("SpecStream sent an answer this app couldn't read.", response.status);
		return data;
	}

	/** How SpecStream reads the request. Free, and nothing runs. */
	async read(request: string): Promise<Reading> {
		const q = request.trim();
		if (!q) throw new SpecStreamError("Describe what you want to find first.");
		const data = await this.request("POST", "/v1/parse", { q, locale: "en-US" });
		const ast = isObject(data.ast) ? data.ast : {};
		const limit = isObject(ast.limit) ? ast.limit : {};
		const max = count(limit.max);
		const astHash = text(data.ast_hash);
		return {
			request: q,
			runnable: data.status === "runnable" && astHash !== null,
			astHash,
			sentence: text(data.canonical_sentence),
			notice: text(data.notice),
			statedRows: limit.inferred === false && max > 0 ? max : null,
			lookingFor: chipLabels(data.chips, ["type", "category", "place"]),
			mustMeet: chipLabels(data.chips, ["predicate"]),
			bringsBack: chipLabels(data.chips, ["output"]),
		};
	}

	/** The most this request can cost. Nothing runs and nothing is charged. */
	async quote(reading: Reading, rows: number): Promise<Quote> {
		if (!reading.runnable || !reading.astHash) {
			throw new SpecStreamError("SpecStream needs a clearer request before it can price it. Add the place, or what every result must meet.");
		}
		const data = await this.request("POST", "/v1/capacity/quotes", {
			ast_hash: reading.astHash,
			operation: "find",
			requested_units: rows,
		});
		const quoteId = text(data.quote_id);
		const quoteHash = text(data.quote_hash);
		if (!quoteId || !quoteHash) throw new SpecStreamError("SpecStream sent a price this app couldn't read.");
		const terms = isObject(data.terms) ? data.terms : {};
		return {
			quoteId,
			quoteHash,
			currency: text(data.currency) ?? "USD",
			maximumCents: count(data.maximum_cents),
			unitCents: typeof terms.unit_cents === "number" ? terms.unit_cents : null,
			expiresAt: text(data.expires_at) ?? "",
			canAuthorize: data.can_authorize !== false,
			rows,
		};
	}

	/**
	 * Approves exactly this quote. Call it only from the person's approve click. The same quote
	 * approved twice reaches the run it already started, so a retry never pays twice.
	 */
	async approve(quote: Quote, maxCents: number): Promise<Run> {
		if (quote.maximumCents > maxCents) {
			throw new SpecStreamError(
				`This can cost up to ${money(quote.maximumCents, quote.currency)}, above your maximum of ${money(maxCents, quote.currency)}. Raise the maximum or ask for fewer results.`,
			);
		}
		if (quote.expiresAt && Date.parse(quote.expiresAt) <= Date.now()) {
			throw new SpecStreamError("That price expired. Get a new price to continue.");
		}
		const data = await this.request("POST", "/v1/capacity/executions", {
			quote_id: quote.quoteId,
			quote_hash: quote.quoteHash,
			confirm_max_cents: quote.maximumCents,
			idempotency_key: `${this.app}-${quote.quoteId}`.slice(0, 128),
		});
		const findId = text(data.find_id);
		if (!findId) throw new SpecStreamError("SpecStream accepted the approval but didn't start the run. Try again.");
		return { findId, state: text(data.state) ?? "running" };
	}

	async progress(findId: string): Promise<Progress> {
		const data = await this.request("GET", `/v1/finds/${encodeURIComponent(findId)}`);
		return {
			status: text(data.status) ?? "running",
			requested: count(data.requested_count),
			found: count(data.accepted_count),
		};
	}

	/** Stops a run. What it found so far is kept and billed for the results delivered. */
	async cancel(findId: string): Promise<void> {
		await this.request("POST", `/v1/finds/${encodeURIComponent(findId)}/cancel`);
	}

	/** Every result of a run, following the pages. Reading results you own is free. */
	async rows(findId: string): Promise<AcceptedRow[]> {
		const rows: AcceptedRow[] = [];
		let cursor: string | null = null;
		for (let page = 0; page < MAX_ROW_PAGES; page += 1) {
			const query = new URLSearchParams({ limit: "100" });
			if (cursor) query.set("cursor", cursor);
			const data = await this.request("GET", `/v1/finds/${encodeURIComponent(findId)}/rows?${query.toString()}`);
			for (const row of Array.isArray(data.rows) ? data.rows : []) {
				if (isObject(row) && typeof row.entity_id === "string" && Array.isArray(row.cells)) {
					rows.push(row as unknown as AcceptedRow);
				}
			}
			const next = text(data.next_cursor);
			if (!next || next === cursor) break;
			cursor = next;
		}
		return rows;
	}

	async account(): Promise<Account> {
		const me = await this.request("GET", "/v1/me");
		// A guest session has no account to bill, so it can't approve a price.
		if (me.guest === true || typeof me.account_id !== "string") {
			throw new SpecStreamError(plainError(401, null, null), 401, "unauthorized");
		}
		let availableCents: number | null = null;
		try {
			const balance = await this.request("GET", "/v1/capacity/balance");
			if (typeof balance.available_cents === "number") availableCents = balance.available_cents;
		} catch {
			availableCents = null;
		}
		return { email: text(me.email), availableCents };
	}

	/** Results this account already has, newest first. Adding them again costs nothing. */
	async pastResults(limit = 30): Promise<PastResult[]> {
		const query = new URLSearchParams({ limit: String(Math.min(Math.max(limit, 1), 100)), sort: "recent" });
		const data = await this.request("GET", `/v1/workspace/collections?${query.toString()}`);
		const found: PastResult[] = [];
		for (const item of Array.isArray(data.collections) ? data.collections : []) {
			if (!isObject(item)) continue;
			const id = text(item.id);
			const findId = text(item.find_id) ?? (id?.startsWith("fnd_") ? id : null);
			if (!findId) continue;
			found.push({
				name: text(item.name) ?? findId,
				findId,
				rows: count(item.row_count ?? item.total),
				createdAt: text(item.created_at) ?? "",
			});
		}
		return found;
	}
}
