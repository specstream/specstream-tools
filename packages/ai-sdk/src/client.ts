/** The SpecStream REST calls the tools share: read a request, price it, start it within a maximum, read its rows. */

export const DEFAULT_BASE_URL = "https://api.specstream.ai";
export const USER_AGENT = "@specstream/ai-sdk/0.2.1";
/** A list runs for up to about five minutes, so the tools wait a little longer than that by default. */
export const DEFAULT_WAIT_SECONDS = 420;
export const DEFAULT_POLL_INTERVAL_SECONDS = 3;
export const DEFAULT_LOCALE = "en-US";
export const MAX_RESULTS = 1000;
const REQUEST_TIMEOUT_MS = 150_000;
const FINISHED = new Set(["completed", "partial"]);
const STOPPED = new Set(["failed", "cancelled", "canceled", "expired"]);
/** Fields every row carries; a column with the same name is renamed so it can't overwrite them. */
const RESERVED = new Set(["list_id", "list_link", "position", "source_url", "checked_at"]);

export const MISSING_KEY_MESSAGE =
  "Set SPECSTREAM_API_KEY or pass apiKey. Create a key under Agents & API in your SpecStream workspace.";

/** SpecStream refused a call or answered with something this package can't read. */
export class SpecStreamError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SpecStreamError";
  }
}

/** One row as flat fields: the list's own columns, then where the row was read. */
export type ListRow = {
  list_id: string;
  position: number | null;
  source_url: string;
  checked_at: string;
  list_link: string;
  [column: string]: unknown;
};

export type ListResults = {
  list_id: string;
  status: string;
  list_link: string;
  row_count: number;
  rows: ListRow[];
};

export type FoundList = ListResults & {
  request: string;
  maximum_price_usd: number;
  /** Set when the list was still running at the end of the wait. */
  message?: string;
};

export type NeedsEdit = {
  status: "needs_edit";
  request: string;
  message: string;
};

export type OverMaximum = {
  status: "over_maximum";
  request: string;
  maximum_price_usd: number;
  message: string;
};

export type FindListResult = FoundList | NeedsEdit | OverMaximum;

export type FindListOptions = {
  /** How many rows to find. Held to 1 through 1000. */
  maxResults: number;
  /** The most one list may cost, in US dollars. Above it, nothing runs. */
  maxPriceUsd: number;
  waitSeconds?: number;
  pollIntervalSeconds?: number;
  locale?: string;
  /** Stops waiting for the list. The list itself keeps running and can be read later. */
  abortSignal?: AbortSignal;
};

export type SpecStreamClientOptions = {
  /** A SpecStream API key. Defaults to the SPECSTREAM_API_KEY environment variable. */
  apiKey?: string;
  baseUrl?: string;
  /** Replaces the global fetch, for tests or a proxy. */
  fetch?: typeof fetch;
  /** Replaces the wait between polls, for tests. Receives milliseconds. */
  sleep?: (ms: number) => Promise<void>;
  /** Replaces the clock, for tests. Returns epoch milliseconds. */
  now?: () => number;
  /** Starts every idempotency key. Defaults to "aisdk". */
  keyPrefix?: string;
};

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

function envKey(): string {
  return (typeof process !== "undefined" && process.env?.SPECSTREAM_API_KEY) || "";
}

function dollars(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

export function listLink(findId: string): string {
  return `https://specstream.ai/workspace/collections/${encodeURIComponent(findId)}`;
}

type Cell = {
  label?: unknown;
  column_id?: unknown;
  absence?: unknown;
  display?: unknown;
  value?: unknown;
  provenance?: { source_url?: unknown; observed_at?: unknown } | null;
};

type RawRecord = { entity_id?: unknown; ordinal?: number | null; details?: Cell[] | null; cells?: Cell[] | null };
/** The API's flat row for a record: its fields with each value's page and the row's source page. */
type FlatRow = Record<string, unknown>;

/** Each value's page in the API's flat row: <field>_source beside the <field> it belongs to. */
function sourcesOf(flat: FlatRow | undefined): Record<string, unknown> {
  const sources: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(flat ?? {})) {
    if (key.endsWith("_source") && Object.prototype.hasOwnProperty.call(flat, key.slice(0, -7))) sources[key] = value;
  }
  return sources;
}

/**
 * One row as flat fields: each column's label holds what the list shows. The page of each value (<field>_source)
 * and of the fact that put the row in the list (source_url, checked_at) come from the API's flat row, so every
 * tool shows the same pages.
 */
export function flattenRow(findId: string, record: RawRecord, flat?: FlatRow): ListRow {
  const row: Record<string, unknown> = { list_id: findId, position: record.ordinal ?? null };
  const sources = sourcesOf(flat);
  const cells = record.details?.length ? record.details : (record.cells ?? []);
  for (const cell of cells) {
    let label = String(cell.label || cell.column_id || "").trim();
    if (!label) continue;
    if (RESERVED.has(label) || label in sources) label = `${label} (column)`;
    let value: unknown;
    if (cell.absence) value = "";
    else if (cell.display != null) value = cell.display;
    else value = cell.value ?? "";
    row[label] = value;
  }
  Object.assign(row, sources);
  row.source_url = flat?.source_url ?? "";
  row.checked_at = flat?.checked_at ?? "";
  row.list_link = listLink(findId);
  return row as ListRow;
}

async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  if (globalThis.crypto?.subtle) {
    const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  }
  const { createHash } = await import("node:crypto");
  return createHash("sha256").update(text).digest("hex");
}

/** The low-level client the tools are built on. Use it directly when you want the calls without a model. */
export class SpecStreamClient {
  readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly fetchImpl: typeof fetch;
  private readonly sleep: (ms: number) => Promise<void>;
  private readonly now: () => number;
  private readonly keyPrefix: string;

  constructor(options: SpecStreamClientOptions = {}) {
    this.apiKey = (options.apiKey ?? envKey()).trim();
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.fetchImpl = options.fetch ?? ((input, init) => globalThis.fetch(input, init));
    this.sleep = options.sleep ?? wait;
    this.now = options.now ?? Date.now;
    this.keyPrefix = options.keyPrefix ?? "aisdk";
  }

  get hasKey(): boolean {
    return this.apiKey.length > 0;
  }

  private async request(
    method: "GET" | "POST",
    path: string,
    body?: Record<string, unknown>,
    options: { allow404?: boolean; abortSignal?: AbortSignal } = {},
  ): Promise<Record<string, unknown> | null> {
    if (!this.apiKey) throw new SpecStreamError(MISSING_KEY_MESSAGE);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(new Error("timed out")), REQUEST_TIMEOUT_MS);
    const outer = options.abortSignal;
    const onAbort = () => controller.abort(outer?.reason);
    if (outer?.aborted) onAbort();
    else outer?.addEventListener("abort", onAbort, { once: true });
    let response: Response;
    let raw: string;
    try {
      response = await this.fetchImpl(this.baseUrl + path, {
        method,
        body: body === undefined ? undefined : JSON.stringify(body),
        headers: {
          Authorization: /^bearer /i.test(this.apiKey) ? this.apiKey : `Bearer ${this.apiKey}`,
          Accept: "application/json",
          "Content-Type": "application/json",
          "User-Agent": USER_AGENT,
        },
        signal: controller.signal,
      });
      raw = await response.text();
    } catch (error) {
      if (outer?.aborted) throw error;
      const reason = error instanceof Error ? (error.cause instanceof Error ? error.cause.message : error.message) : String(error);
      throw new SpecStreamError(`Couldn't reach SpecStream: ${reason}`);
    } finally {
      clearTimeout(timer);
      outer?.removeEventListener("abort", onAbort);
    }
    if (!response.ok) {
      if (options.allow404 && response.status === 404) return null;
      throw new SpecStreamError(errorMessage(response, raw));
    }
    let payload: unknown;
    try {
      payload = JSON.parse(raw || "{}");
    } catch {
      payload = null;
    }
    const data = isObject(payload) ? payload.data : undefined;
    if (!isObject(data)) throw new SpecStreamError("SpecStream returned a response this package couldn't read.");
    return data;
  }

  /** Search the live web with GET /v1/web-search ($5 per 1,000 searches, no quote needed). */
  async webSearch(query: string, options: { passages?: boolean; abortSignal?: AbortSignal } = {}): Promise<Record<string, unknown>> {
    const q = (query ?? "").trim();
    if (!q || q.length > 2000) throw new Error("q must be between 1 and 2,000 characters.");
    const params = new URLSearchParams({ q });
    if (options.passages) params.set("passages", "true");
    return (await this.request("GET", `/v1/web-search?${params}`, undefined, { abortSignal: options.abortSignal })) ?? {};
  }

  /** Extract the main text of 1 to 20 URLs live with POST /v1/extract ($0.80 per 1,000 pages, empty pages free). */
  async extractPages(urls: string[], options: { format?: "markdown" | "text"; abortSignal?: AbortSignal } = {}): Promise<Record<string, unknown>> {
    const cleaned = (Array.isArray(urls) ? urls : []).map((u) => String(u ?? "").trim()).filter(Boolean);
    if (cleaned.length < 1 || cleaned.length > 20) throw new Error("Provide 1 to 20 http or https URLs in urls.");
    const format = options.format === "text" ? "text" : "markdown";
    return (await this.request("POST", "/v1/extract", { urls: cleaned, format }, { abortSignal: options.abortSignal })) ?? {};
  }

  /** Every row found so far for a list, following the pages. Reading is free. */
  async results(findId: string, abortSignal?: AbortSignal): Promise<ListResults> {
    const rows: ListRow[] = [];
    let cursor: string | null = null;
    let status = "running";
    for (;;) {
      const query = new URLSearchParams({ limit: "100", ...(cursor ? { cursor } : {}) });
      const page: Record<string, unknown> =
        (await this.request("GET", `/v1/finds/${encodeURIComponent(findId)}/rows?${query}`, undefined, { abortSignal })) ?? {};
      status = typeof page.status === "string" && page.status ? page.status : status;
      const flat = new Map((Array.isArray(page.flat_rows) ? (page.flat_rows as FlatRow[]) : []).map((item) => [String(item.id), item]));
      for (const record of Array.isArray(page.rows) ? (page.rows as RawRecord[]) : []) {
        rows.push(flattenRow(findId, record, flat.get(`${findId}:${String(record.entity_id)}`)));
      }
      const next: string | null = typeof page.next_cursor === "string" && page.next_cursor ? page.next_cursor : null;
      if (!next || next === cursor) break;
      cursor = next;
    }
    return { list_id: findId, status, list_link: listLink(findId), row_count: rows.length, rows };
  }

  /** Reads the request, prices it, and runs it only if the most it can cost is within `maxPriceUsd`. */
  async findList(request: string, options: FindListOptions): Promise<FindListResult> {
    const q = (request ?? "").trim();
    if (!q) throw new Error("Describe the list to find.");
    const maxResults = options.maxResults;
    if (!Number.isInteger(maxResults) || maxResults < 1) throw new Error("maxResults must be 1 or more.");
    const maxCents = Math.round(Number(options.maxPriceUsd) * 100);
    if (!(maxCents > 0)) throw new Error("maxPriceUsd must be greater than 0.");
    const { abortSignal } = options;

    // The same request with the same limits gets the run it already started in this hour or the one before,
    // so a retried agent step never buys the list twice, even across the turn of the hour.
    const keyFor = async (at: number) => {
      const hour = new Date(at).toISOString().slice(0, 13);
      return `${this.keyPrefix}-${(await sha256Hex(`${q}|${maxResults}|${maxCents}|${hour}`)).slice(0, 32)}`;
    };

    const at = this.now();
    const requestKey = await keyFor(at);
    let existing: Record<string, unknown> | null = null;
    for (const candidate of [requestKey, await keyFor(at - 3_600_000)]) {
      existing = await this.request("GET", `/v1/capacity/requests/${encodeURIComponent(candidate)}`, undefined, {
        allow404: true,
        abortSignal,
      });
      if (existing?.find_id) break;
    }

    let findId: string;
    let maximumCents: number;
    if (existing?.find_id) {
      findId = String(existing.find_id);
      maximumCents = Math.trunc(Number(existing.maximum_cents)) || maxCents;
    } else {
      const reading = (await this.request("POST", "/v1/parse", { q, locale: options.locale ?? DEFAULT_LOCALE }, { abortSignal })) ?? {};
      if (reading.status !== "runnable") {
        const readAs = reading.canonical_sentence || q;
        return {
          status: "needs_edit",
          request: q,
          message: `SpecStream needs a clearer request before it can price it. It read: "${readAs}". Add the place or what every row must meet.`,
        };
      }
      const quote =
        (await this.request(
          "POST",
          "/v1/capacity/quotes",
          { ast_hash: reading.ast_hash, operation: "find", requested_units: maxResults },
          { abortSignal },
        )) ?? {};
      maximumCents = Math.trunc(Number(quote.maximum_cents)) || 0;
      if (maximumCents > maxCents) {
        return {
          status: "over_maximum",
          request: q,
          maximum_price_usd: maximumCents / 100,
          message: `Nothing ran: this list can cost up to ${dollars(maximumCents)}, above the maximum of ${dollars(maxCents)}. Ask for fewer results or raise maxPriceUsd.`,
        };
      }
      const run =
        (await this.request(
          "POST",
          "/v1/capacity/executions",
          { quote_id: quote.quote_id, quote_hash: quote.quote_hash, confirm_max_cents: maximumCents, idempotency_key: requestKey },
          { abortSignal },
        )) ?? {};
      if (!run.find_id) throw new SpecStreamError("SpecStream returned a response this package couldn't read.");
      findId = String(run.find_id);
    }

    const waitMs = Math.max(0, options.waitSeconds ?? DEFAULT_WAIT_SECONDS) * 1000;
    const pollMs = Math.max(0, options.pollIntervalSeconds ?? DEFAULT_POLL_INTERVAL_SECONDS) * 1000;
    const deadline = this.now() + waitMs;
    let result: ListResults;
    for (;;) {
      result = await this.results(findId, abortSignal);
      if (FINISHED.has(result.status) || STOPPED.has(result.status) || this.now() >= deadline) break;
      if (abortSignal?.aborted) throw abortSignal.reason ?? new Error("aborted");
      await this.sleep(pollMs);
    }
    const found: FoundList = { ...result, request: q, maximum_price_usd: maximumCents / 100 };
    if (!FINISHED.has(result.status) && !STOPPED.has(result.status)) {
      found.message = "Still running. Call specstream_get_list_results with this list_id for the rest.";
    }
    return found;
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function errorMessage(response: Response, raw: string): string {
  let payload: unknown = {};
  try {
    payload = JSON.parse(raw || "{}");
  } catch {
    payload = {};
  }
  const detail = isObject(payload) ? payload.error : undefined;
  const message = isObject(detail) ? detail.message : typeof detail === "string" ? detail : undefined;
  return `SpecStream answered ${response.status}: ${message || response.statusText}`;
}
