import { createFunctionHandle } from "convex/server";
import type {
  FunctionReference,
  GenericActionCtx,
  GenericDataModel,
  GenericMutationCtx,
  GenericQueryCtx,
  PaginationOptions,
  PaginationResult,
} from "convex/server";
import type { ComponentApi } from "../component/_generated/component.js";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Where a list stands. `partial` means SpecStream finished with the rows it found, fewer than you asked for. */
export type OpenBrowserOptions = {
  /** The most seconds the browser runs, from 60 to 3600. Defaults to 300. */
  timeoutSeconds?: number;
  /** The browser ends after this many seconds with no step, from 10 to 600. Defaults to 120. */
  idleTimeoutSeconds?: number;
  /** Hosts the browser may open, such as example.com or *.example.com. */
  allowedDomains?: string[];
  /** true skips images, video, audio and fonts. */
  blockMedia?: boolean;
  /** false runs the browser with a screen. */
  headless?: boolean;
  /** Your own labels, returned as sent. */
  metadata?: Record<string, string | number | boolean>;
  /** Return `connect_url` for Playwright or Puppeteer. Keep it on the server. */
  includeConnectUrl?: boolean;
  /** The same key on a retried call returns the session the first call opened. */
  idempotencyKey?: string;
};

export type BrowserSession = {
  sessionId: string;
  status?: string;
  ended_reason?: string;
  live_url?: string;
  connect_url?: string;
  expires_at?: string;
  timeout_s?: number;
  seconds?: number;
  actions?: number;
  charged_usd?: number;
  price?: { per_second_usd: number; per_action_usd: number };
};

export type BrowserStep = {
  sessionId: string;
  text?: string;
  images?: { mime_type: string | null; base64_chars: number }[];
  url?: string;
  title?: string;
  read_at?: string;
  price_usd?: number;
  error?: { code: string; reason?: string | null; message: string };
};

export type ListStatus =
  | "running"
  | "completed"
  | "partial"
  | "failed"
  | "canceled"
  | "expired";

/** How progress reaches the component. Webhook mode checks slowly, as a safety net. */
export type TrackMode = "webhook" | "poll";

/** One cell of a row: what SpecStream found, and the page it read it on. */
export type RowCell = {
  columnId: string;
  label: string;
  value?: unknown;
  /** The value as a person would read it. Prefer this for display. */
  display?: string;
  /** Why the cell is empty ("Not published", "Couldn't check"). */
  absence?: string;
  /** The page the value came from. */
  sourceUrl?: string;
  /** When SpecStream read that page. */
  observedAt?: string;
};

export type ListRow = {
  _id: string;
  _creationTime: number;
  listId: string;
  /** SpecStream's stable id for the thing the row describes. */
  entityId: string;
  ordinal: number;
  cells: RowCell[];
  /** The full set of cells, when SpecStream returns more than the table view shows. */
  details?: RowCell[];
  /** The page behind the row: the first page any cell was read on. */
  sourceUrl?: string;
  observedAt?: string;
  locked?: boolean;
};

export type List = {
  _id: string;
  _creationTime: number;
  /** SpecStream's own id for the list (`fnd_...`). */
  specstreamListId: string;
  request: string;
  canonicalSentence?: string;
  quoteId?: string;
  status: ListStatus;
  mode: TrackMode;
  /** Rows you asked for. */
  requestedCount: number;
  /** Rows SpecStream has accepted so far. */
  acceptedCount: number;
  /** Rows stored in Convex. */
  rowCount: number;
  maximumCents?: number;
  currency?: string;
  /** Where to open the list in SpecStream. */
  link: string;
  error?: string;
  context?: unknown;
  finalized: boolean;
  startedAt: number;
  updatedAt: number;
  completedAt?: number;
};

export type Quote = {
  _id: string;
  _creationTime: number;
  request: string;
  canonicalSentence?: string;
  rows: number;
  currency: string;
  /** The most the list can cost, in cents. Rows that are not delivered are not charged. */
  maximumCents: number;
  unitCents?: number;
  expiresAt?: number;
  canAuthorize: boolean;
  listId?: string;
  createdAt: number;
};

/** What SpecStream made of a request, before anything is priced. */
export type Reading = {
  /** `runnable` when the request can be priced. */
  status: string;
  astHash?: string;
  canonicalSentence?: string;
  notice?: string;
  statedRows?: number;
  rowsInferred: boolean;
};

export type NeedsEdit = {
  status: "needs_edit";
  request: string;
  /** The request as SpecStream read it, so you can show what was missing. */
  readAs: string;
  notice?: string;
  message: string;
};

export type Quoted = {
  status: "quoted";
  /** Pass this to `approve`. */
  quoteId: string;
  request: string;
  readAs?: string;
  rows: number;
  currency: string;
  maximumCents: number;
  unitCents?: number;
  expiresAt?: number;
  canAuthorize: boolean;
};

export type Started = {
  status: "started";
  /** The id of the list in your database. Pass it to `getList` and `listRows`. */
  listId: string;
  specstreamListId: string;
  link: string;
  maximumCents: number;
};

export type OverMaximum = {
  status: "over_maximum";
  request: string;
  maximumCents: number;
  message: string;
};

/** Argument shape of the mutation you pass as `onComplete`. */
export type ListCompletePayload = {
  listId: string;
  specstreamListId: string;
  status: Exclude<ListStatus, "running">;
  rowCount: number;
  requestedCount: number;
  error?: string;
  context?: any;
};

export type OnCompleteMutation = FunctionReference<
  "mutation",
  "internal",
  ListCompletePayload,
  null | void
>;

export type StartOptions = {
  /** Pass to make a retried start begin one list, even if the call runs twice. */
  idempotencyKey?: string;
  /**
   * `poll` checks every few seconds. `webhook` checks slowly and relies on the
   * component's HTTP route to hear the list finished.
   */
  mode?: TrackMode;
  /** App mutation to run once, when the list reaches a final state. */
  onComplete?: OnCompleteMutation;
  /** Opaque data handed back to `onComplete`. */
  context?: unknown;
};

export type FindListArgs = StartOptions & {
  /** The list to find, in plain words. */
  request: string;
  /** How many rows to ask for, 1 to 1000. */
  rows: number;
  /** The most one list may cost, in US dollars. Above it, nothing runs. */
  maxPriceUsd: number;
  locale?: string;
};

/** A row as flat fields: the list's columns by label, then the page behind it. */
export type FlatRow = {
  entityId: string;
  position: number;
  sourceUrl: string;
  checkedAt: string;
  [column: string]: unknown;
};

type QueryCtx = Pick<GenericQueryCtx<GenericDataModel>, "runQuery">;
type MutationCtx = Pick<
  GenericMutationCtx<GenericDataModel>,
  "runQuery" | "runMutation"
>;
type ActionCtx = Pick<
  GenericActionCtx<GenericDataModel>,
  "runQuery" | "runMutation" | "runAction"
>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Where a list opens in the SpecStream workspace. */
export function listLink(specstreamListId: string): string {
  return `https://specstream.ai/workspace/collections/${encodeURIComponent(specstreamListId)}`;
}

/** Cents as a dollar amount, for messages. */
export function dollars(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

const RESERVED = new Set(["entityId", "position", "sourceUrl", "checkedAt"]);

/**
 * A row as flat fields, one per column label, ready for a table or a prompt.
 * Empty cells are empty strings, and `sourceUrl` is the page the row was read on.
 */
export function flattenRow(row: ListRow): FlatRow {
  const flat: FlatRow = {
    entityId: row.entityId,
    position: row.ordinal,
    sourceUrl: row.sourceUrl ?? "",
    checkedAt: row.observedAt ?? "",
  };
  for (const cell of row.details?.length ? row.details : row.cells) {
    let label = (cell.label || cell.columnId).trim();
    if (!label) continue;
    if (RESERVED.has(label)) label = `${label} (column)`;
    flat[label] = cell.absence ? "" : (cell.display ?? cell.value ?? "");
  }
  return flat;
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

/**
 * Typed client for the SpecStream component.
 *
 * ```ts
 * const specstream = new SpecStreamClient(components.specstream);
 *
 * export const findRepositories = action({
 *   args: {},
 *   handler: (ctx) =>
 *     specstream.findList(ctx, {
 *       request: "open-source vector databases on GitHub with more than 5,000 stars, with their license",
 *       rows: 100,
 *       maxPriceUsd: 15,
 *     }),
 * });
 * ```
 */
export class SpecStreamClient {
  constructor(public component: ComponentApi) {}

  /** Read a request and say what SpecStream understood. Nothing is priced or charged. */
  async read(
    ctx: ActionCtx,
    request: string,
    options: { locale?: string } = {},
  ): Promise<Reading> {
    return await ctx.runAction(this.component.lib.read, {
      request,
      locale: options.locale,
    });
  }

  /**
   * Search the live web with the Search API (`GET /v1/web-search`, $5 per 1,000
   * searches). No quote is needed. `speed: "fast"` returns the first ranked results
   * in about a second, at $1 per 1,000 searches; left out, the API's default runs.
   */
  async webSearch(
    ctx: ActionCtx,
    q: string,
    options: { passages?: boolean; speed?: "fast" | "default" } = {},
  ): Promise<any> {
    return await ctx.runAction(this.component.lib.webSearch, {
      q,
      passages: options.passages,
      speed: options.speed,
    });
  }

  /**
   * Read 1 to 20 web pages, PDFs, Word or Excel files with the Extract API
   * (`POST /v1/extract`, $0.80 per 1,000 pages; a page with no text is free).
   */
  async extractPages(
    ctx: ActionCtx,
    urls: string[],
    options: { format?: "markdown" | "text" } = {},
  ): Promise<any> {
    return await ctx.runAction(this.component.lib.extractPages, {
      urls,
      format: options.format,
    });
  }

  /**
   * Open a real browser that SpecStream runs (`POST /v1/browser/sessions`, $0.10 an
   * hour, charged by the second). It ends by itself after `timeoutSeconds` (60 to
   * 3600, default 300). Set `includeConnectUrl` to drive it with Playwright or
   * Puppeteer over `connect_url` from a Node action; that address carries a token.
   */
  async openBrowser(ctx: ActionCtx, options: OpenBrowserOptions = {}): Promise<BrowserSession> {
    return await ctx.runAction(this.component.browser.openBrowser, options);
  }

  /**
   * Run one step in the browser (`POST /v1/browser/sessions/{id}/actions`, $0.001 a
   * step): browser_navigate, browser_snapshot, browser_click, browser_type and the
   * other Playwright MCP tools, or browser_read for the page's text.
   */
  async browserStep(
    ctx: ActionCtx,
    sessionId: string,
    tool: string,
    args: Record<string, unknown> = {},
  ): Promise<BrowserStep> {
    return await ctx.runAction(this.component.browser.browserStep, {
      sessionId,
      tool,
      arguments: args,
    });
  }

  /** A session's state, seconds, steps and charge so far. Free. */
  async browserSession(ctx: ActionCtx, sessionId: string): Promise<BrowserSession> {
    return await ctx.runAction(this.component.browser.browserSession, { sessionId });
  }

  /** End the session, so its time stops being charged. */
  async closeBrowser(ctx: ActionCtx, sessionId: string): Promise<BrowserSession> {
    return await ctx.runAction(this.component.browser.closeBrowser, { sessionId });
  }

  /** Who the API key belongs to and what is left to spend. */
  async account(
    ctx: ActionCtx,
  ): Promise<{ email?: string; availableCents: number | null }> {
    return await ctx.runAction(this.component.lib.account, {});
  }

  /**
   * Register your deployment's webhook route so lists finish without waiting for
   * a status check. Do it once per SpecStream account, then store the returned
   * secret as SPECSTREAM_WEBHOOK_SECRET.
   */
  async registerWebhook(
    ctx: ActionCtx,
    url: string,
  ): Promise<{ hookId: string; secret: string }> {
    return await ctx.runAction(this.component.lib.registerWebhook, { url });
  }

  /**
   * Price a request for a number of rows. Nothing runs and nothing is charged
   * until you call `approve` with the quote's own maximum.
   */
  async quote(
    ctx: ActionCtx,
    args: { request: string; rows: number; locale?: string },
  ): Promise<Quoted | NeedsEdit> {
    return await ctx.runAction(this.component.lists.quote, args);
  }

  /**
   * Start the list a quote prices. `confirmMaxCents` must equal the quote's
   * `maximumCents`, so the amount you approve is always the amount you saw.
   */
  async approve(
    ctx: ActionCtx,
    args: { quoteId: string; confirmMaxCents: number } & StartOptions,
  ): Promise<Started> {
    return await ctx.runAction(this.component.lists.approve, {
      quoteId: args.quoteId,
      confirmMaxCents: args.confirmMaxCents,
      idempotencyKey: args.idempotencyKey,
      mode: args.mode,
      onComplete: args.onComplete
        ? await createFunctionHandle(args.onComplete)
        : undefined,
      context: args.context,
    });
  }

  /**
   * Quote and start in one call, only when the most the list can cost is within
   * `maxPriceUsd`. Above it, or when the request needs to be clearer, nothing
   * runs. Rows stream into your database; subscribe to `getList` and `listRows`.
   */
  async findList(
    ctx: ActionCtx,
    args: FindListArgs,
  ): Promise<Started | NeedsEdit | OverMaximum> {
    const maxCents = Math.round(Number(args.maxPriceUsd) * 100);
    if (!(maxCents > 0)) throw new Error("maxPriceUsd must be greater than 0.");
    return await ctx.runAction(this.component.lists.findList, {
      request: args.request,
      rows: args.rows,
      maxCents,
      locale: args.locale,
      idempotencyKey: args.idempotencyKey,
      mode: args.mode,
      onComplete: args.onComplete
        ? await createFunctionHandle(args.onComplete)
        : undefined,
      context: args.context,
    });
  }

  /** A saved quote. */
  async getQuote(ctx: QueryCtx, quoteId: string): Promise<Quote | null> {
    return await ctx.runQuery(this.component.lists.getQuote, { quoteId });
  }

  /** Status and progress of a list. Reactive: subscribe to it from a query. */
  async getList(ctx: QueryCtx, listId: string): Promise<List | null> {
    return (await ctx.runQuery(this.component.lists.get, {
      listId,
    })) as List | null;
  }

  /** Look up a list by SpecStream's own id (`fnd_...`). */
  async getListBySpecstreamId(
    ctx: QueryCtx,
    specstreamListId: string,
  ): Promise<List | null> {
    return (await ctx.runQuery(this.component.lists.getBySpecstreamListId, {
      specstreamListId,
    })) as List | null;
  }

  /** Recent lists, newest first. */
  async listLists(
    ctx: QueryCtx,
    args: { status?: ListStatus; limit?: number } = {},
  ): Promise<List[]> {
    return (await ctx.runQuery(this.component.lists.list, args)) as List[];
  }

  /** A page of a list's rows in SpecStream's order. */
  async listRows(
    ctx: QueryCtx,
    args: { listId: string; paginationOpts: PaginationOptions },
  ): Promise<PaginationResult<ListRow>> {
    return (await ctx.runQuery(
      this.component.lists.listRows,
      args,
    )) as PaginationResult<ListRow>;
  }

  /** One row by SpecStream's id for the thing it describes. */
  async getRow(
    ctx: QueryCtx,
    args: { listId: string; entityId: string },
  ): Promise<ListRow | null> {
    return (await ctx.runQuery(
      this.component.lists.getRow,
      args,
    )) as ListRow | null;
  }

  /** Stop a running list. The rows found so far are kept. */
  async cancel(ctx: ActionCtx, listId: string): Promise<null> {
    return await ctx.runAction(this.component.lists.cancel, { listId });
  }

  /** Read the latest status and rows from SpecStream now, instead of waiting for the next check. */
  async refresh(ctx: ActionCtx, listId: string): Promise<null> {
    return await ctx.runAction(this.component.lists.refresh, { listId });
  }

  /**
   * Pick tracking back up for a list the component stopped watching. Returns
   * false when there was nothing to resume.
   */
  async resume(ctx: MutationCtx, listId: string): Promise<boolean> {
    return await ctx.runMutation(this.component.lists.resume, { listId });
  }

  /** Delete a list and its stored rows. SpecStream keeps the list in your workspace. */
  async deleteList(ctx: MutationCtx, listId: string): Promise<null> {
    return await ctx.runMutation(this.component.lists.deleteList, { listId });
  }
}

export default SpecStreamClient;
