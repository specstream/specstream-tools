/** OpenAPI-aligned SPECSTREAM SDK: compile, quote capacity work, explicitly authorize, receive a Delivery. */
import type { Schemas } from "./work-types.js";
import { requireWorkAuthorization } from "./authorization.js";
export type { Schemas } from "./work-types.js";

export const FAMILIES = [
  "local_business",
  "creator",
  "organization",
  "storefront_product",
  "app_listing",
  "job_posting",
  "scholarly_work",
  "tender",
  "grant",
  "software_repository",
  "software_package",
  "dataset",
  "clinical_trial",
  "regulatory_document",
  "vulnerability",
  "book",
  "podcast",
  "web_page",
  "knowledge_entity",
  "person",
] as const;

/** A record kind the service names today. FAMILIES lists them; they are examples, not a limit. */
export type KnownEntityType = (typeof FAMILIES)[number];

/** A record kind is an open string: any kind name a reading gives is valid. */
export type EntityType = KnownEntityType | (string & {});

export const DEFAULT_BASE_URL = "https://api.specstream.ai";

export class SpecstreamError extends Error {
  readonly status: number | null;
  readonly body: unknown;
  readonly code: string | null;
  readonly details: Record<string, unknown>;
  constructor(message: string, status: number | null = null, body: unknown = null) {
    super(message);
    this.name = "SpecstreamError";
    this.status = status;
    this.body = body;
    let parsed = body;
    if (typeof parsed === "string") {
      try { parsed = JSON.parse(parsed); } catch { parsed = null; }
    }
    const candidate = parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>).error : null;
    const error = candidate && typeof candidate === "object" && !Array.isArray(candidate)
      ? candidate as Record<string, unknown> : {};
    this.code = typeof error.code === "string" ? error.code : null;
    this.details = error.details && typeof error.details === "object" && !Array.isArray(error.details)
      ? { ...error.details as Record<string, unknown> } : {};
  }
}

export function assertFamily(entityType: string): EntityType {
  if (typeof entityType !== "string" || !entityType.trim()) {
    throw new Error("entity_type must be a non-empty string");
  }
  return entityType;
}

export type FetchFn = (input: string, init?: RequestInit) => Promise<Response>;

const RETRY_AFTER_MAX_MS = 10_000;

/** Milliseconds to wait before the one retry of a 503 that names its Retry-After, or null. */
function retryAfterMs(response: Response): number | null {
  if (response.status !== 503) return null;
  const value = (response.headers?.get("retry-after") || "").trim();
  if (!value) return null;
  const ms = /^\d+(\.\d+)?$/.test(value) ? Number(value) * 1000 : Date.parse(value) - Date.now();
  return Number.isFinite(ms) && ms >= 0 && ms <= RETRY_AFTER_MAX_MS ? ms : null;
}

export type ClientOptions = {
  apiKey: string;
  baseUrl?: string;
  fetch?: FetchFn;
  exportOrigin?: string;
  timeoutMs?: number;
};

export type JsonMap = Record<string, unknown>;

export class Client {
  readonly apiKey: string;
  readonly baseUrl: string;
  private readonly fetchFn: FetchFn;
  private readonly exportOrigin?: string;
  private readonly timeoutMs: number;

  constructor(options: ClientOptions) {
    const key = (options.apiKey || "").trim();
    if (!key) {
      throw new SpecstreamError("SPECSTREAM_API_KEY is required");
    }
    this.apiKey = key;
    this.baseUrl = (options.baseUrl || DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.fetchFn = options.fetch ?? fetch;
    this.exportOrigin = options.exportOrigin;
    this.timeoutMs = options.timeoutMs ?? 150_000;
    if (!Number.isSafeInteger(this.timeoutMs) || this.timeoutMs <= 0 || this.timeoutMs > 2_147_483_647) {
      throw new SpecstreamError("timeoutMs must be a positive integer up to 2147483647");
    }
  }

  families(): readonly KnownEntityType[] {
    return FAMILIES;
  }

  compile(q: string, locale = "en-US"): Promise<JsonMap> {
    return this.request("POST", "/v1/parse", { q, locale });
  }

  editSpec(ast: JsonMap, operations: JsonMap[] = []): Promise<JsonMap> {
    return this.request("POST", "/v1/parse/from-chips", { ast, operations });
  }

  specOptions(target: string): Promise<JsonMap> {
    return this.request("GET", "/v1/spec-options/" + encodeURIComponent(target));
  }

  getFind(findId: string): Promise<JsonMap> {
    return this.request("GET", `/v1/finds/${encodeURIComponent(findId)}`);
  }

  revisit(findId: string, after = "", limit = 100): Promise<JsonMap> {
    const query = new URLSearchParams({ after, limit: String(limit) });
    return this.request("GET", `/v1/finds/${encodeURIComponent(findId)}/revisit?${query}`);
  }

  rows(findId: string, cursor: string | null = null, limit = 100): Promise<Schemas["FindRowsPage"]> {
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) throw new Error("Row page limit must be an integer from 1 to 100");
    if (cursor !== null && (typeof cursor !== "string" || !cursor || cursor.length > 2048)) throw new Error("Use the opaque next_cursor returned by this Delivery");
    const query = new URLSearchParams({limit: String(limit)});
    if (cursor !== null) query.set("cursor", cursor);
    return this.request("GET", "/v1/finds/" + encodeURIComponent(findId) + "/rows?" + query) as Promise<Schemas["FindRowsPage"]>;
  }

  export(findId: string, format = "csv"): Promise<JsonMap> {
    return this.request("POST", "/v1/finds/" + encodeURIComponent(findId) + "/export", { format });
  }

  /** Fetch a fresh one-use export. Account credentials never accompany its capability. */
  async downloadExport(
    findId: string, format: "xlsx" | "csv" | "json" | "html" = "xlsx",
    maxBytes = 64 * 1024 * 1024,
  ): Promise<Uint8Array> {
    if (!Number.isSafeInteger(maxBytes) || maxBytes <= 0) {
      throw new SpecstreamError("maxBytes must be a positive integer");
    }
    const exported = await this.export(findId, format);
    const location = exported.download_url;
    if (typeof location !== "string" || /[\x00-\x20\\]/.test(location) ||
        /^https?:\/\/[^/]*@/i.test(location)) {
      throw new SpecstreamError("Export returned an invalid download location");
    }
    let url: URL;
    try {
      url = new URL(location);
      const base = new URL(this.baseUrl);
      const allowed = new Set([base.origin]);
      if (this.exportOrigin !== undefined) {
        const declared = new URL(this.exportOrigin);
        if (!['http:', 'https:'].includes(declared.protocol) || declared.username ||
            declared.password || declared.search || declared.hash || declared.pathname !== '/') {
          throw new Error("invalid export origin");
        }
        allowed.add(declared.origin);
      } else if (base.origin === "https://api.specstream.ai") {
        allowed.add("https://specstream.ai");
      }
      if (!allowed.has(url.origin) || !['http:', 'https:'].includes(url.protocol) ||
          url.username || url.password || url.search || url.hash ||
          !/^\/export\/[A-Za-z0-9_-]+$/.test(url.pathname)) {
        throw new Error("untrusted download location");
      }
    } catch {
      throw new SpecstreamError("Export returned an untrusted download location");
    }
    try {
      const response = await this.fetchFn(url.href, {
        method: "GET", redirect: "error", credentials: "omit",
        signal: AbortSignal.timeout(this.timeoutMs),
        headers: { Accept: "*/*", "Accept-Encoding": "identity" },
      });
      if (response.status !== 200) {
        await response.body?.cancel();
        throw new SpecstreamError("Export download failed", response.status);
      }
      const reader = response.body?.getReader();
      if (!reader) throw new SpecstreamError("Export download returned no body", response.status);
      const chunks: Uint8Array[] = [];
      let size = 0;
      try {
        for (;;) {
          const {done, value} = await reader.read();
          if (done) break;
          size += value.length;
          if (size > maxBytes) {
            await reader.cancel();
            throw new SpecstreamError("Export exceeds maxBytes", response.status);
          }
          chunks.push(value);
        }
      } finally {
        reader.releaseLock();
      }
      if (!size) throw new SpecstreamError("Export download returned no body", response.status);
      const bytes = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
      return bytes;
    } catch (error) {
      if (error instanceof SpecstreamError) throw error;
      throw new SpecstreamError("Export download transport failed");
    }
  }

  // BEGIN GENERATED LIFECYCLE
  getVocabulary(): Promise<Schemas["VocabularyData"]> {
    let path = `/v1/vocabulary`;
    return this.request("GET", path) as Promise<Schemas["VocabularyData"]>;
  }

  workspaceListAuditEvents(query: { "project_id"?: string; "actor_account_id"?: string; "cursor"?: string; "kind"?: "Sign-in" | "Access" | "Spending" | "Exports" | "Automation" | "Lists"; "limit"?: number; } = {}): Promise<Schemas["WorkspaceAuditPage"]> {
    let path = `/v1/workspace/audit`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["WorkspaceAuditPage"]>;
  }

  understandLive(request: Schemas["LiveUnderstandingRequest"]): Promise<Schemas["LiveUnderstandingResult"]> {
    let path = `/v1/understand`;
    return this.request("POST", path, request) as Promise<Schemas["LiveUnderstandingResult"]>;
  }

  workspaceSearch(query: { "q": string; "limit"?: number; "cursor"?: string; }): Promise<Schemas["WorkspaceSearchPage"]> {
    let path = `/v1/search`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["WorkspaceSearchPage"]>;
  }

  webSearch(query: { "q": string; "passages"?: boolean; }): Promise<Schemas["WebSearchPage"]> {
    let path = `/v1/web-search`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["WebSearchPage"]>;
  }

  extractPages(request: Schemas["ExtractRequest"]): Promise<Schemas["ExtractPage"]> {
    let path = `/v1/extract`;
    return this.request("POST", path, request) as Promise<Schemas["ExtractPage"]>;
  }

  webSearchAnswers(query: { "q"?: string; "limit"?: number; "cursor"?: string; } = {}): Promise<Schemas["WebSearchAnswerPage"]> {
    let path = `/v1/web-search/answers`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["WebSearchAnswerPage"]>;
  }

  webSearchAnswer(answerId: string): Promise<Schemas["WebSearchAnswer"]> {
    let path = `/v1/web-search/answers/${encodeURIComponent(answerId)}`;
    return this.request("GET", path) as Promise<Schemas["WebSearchAnswer"]>;
  }

  workspaceListNotifications(query: { "tab"?: "all" | "unread" | "archived"; "limit"?: number; "cursor"?: string; } = {}): Promise<Schemas["WorkspaceNotificationPage"]> {
    let path = `/v1/workspace/notifications`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["WorkspaceNotificationPage"]>;
  }

  workspaceUpdateNotification(identifier: string, request: Schemas["NotificationPatch"]): Promise<Schemas["WorkspaceNotification"]> {
    let path = `/v1/workspace/notifications/${encodeURIComponent(identifier)}`;
    return this.request("PATCH", path, request) as Promise<Schemas["WorkspaceNotification"]>;
  }

  workspaceReadNotifications(request: Schemas["NotificationRead"]): Promise<Schemas["WorkspaceNotifications"]> {
    let path = `/v1/workspace/notifications/read`;
    return this.request("POST", path, request) as Promise<Schemas["WorkspaceNotifications"]>;
  }

  getMe(): Promise<Schemas["MeData"]> {
    let path = `/v1/me`;
    return this.request("GET", path) as Promise<Schemas["MeData"]>;
  }

  getAccount(): Promise<Schemas["AccountData"]> {
    let path = `/v1/account`;
    return this.request("GET", path) as Promise<Schemas["AccountData"]>;
  }

  listAccountKeys(): Promise<{ "keys": Array<Schemas["KeyListItem"]>; }> {
    let path = `/v1/account/keys`;
    return this.request("GET", path) as Promise<{ "keys": Array<Schemas["KeyListItem"]>; }>;
  }

  createAccountKey(request: Schemas["KeyCreateRequest"]): Promise<Schemas["KeyCreateData"]> {
    let path = `/v1/account/keys`;
    return this.request("POST", path, request) as Promise<Schemas["KeyCreateData"]>;
  }

  updateAccountSpend(request: Schemas["AccountSpendRequest"]): Promise<Schemas["AccountSpendData"]> {
    let path = `/v1/account/spend`;
    return this.request("PATCH", path, request) as Promise<Schemas["AccountSpendData"]>;
  }

  revokeAccountKey(keyId: string): Promise<{ "revoked": true; }> {
    let path = `/v1/account/keys/${encodeURIComponent(keyId)}`;
    return this.request("DELETE", path) as Promise<{ "revoked": true; }>;
  }

  getFindCommerce(findId: string): Promise<Schemas["CommerceData"]> {
    let path = `/v1/finds/${encodeURIComponent(findId)}/commerce`;
    return this.request("GET", path) as Promise<Schemas["CommerceData"]>;
  }

  reconcileFindCommerce(findId: string): Promise<Schemas["CommerceData"]> {
    let path = `/v1/finds/${encodeURIComponent(findId)}/reconcile`;
    return this.request("POST", path) as Promise<Schemas["CommerceData"]>;
  }

  cancelFind(findId: string): Promise<Schemas["CancelData"]> {
    let path = `/v1/finds/${encodeURIComponent(findId)}/cancel`;
    return this.request("POST", path) as Promise<Schemas["CancelData"]>;
  }

  shareFind(findId: string, request: Schemas["ShareCreateRequest"]): Promise<Schemas["ShareData"]> {
    let path = `/v1/finds/${encodeURIComponent(findId)}/share`;
    return this.request("POST", path, request) as Promise<Schemas["ShareData"]>;
  }

  revokeShare(shareId: string, request?: Schemas["ShareRevokeRequest"]): Promise<{ "share_id": string; "revoked": true; }> {
    let path = `/v1/share/${encodeURIComponent(shareId)}/revoke`;
    return this.request("POST", path, request) as Promise<{ "share_id": string; "revoked": true; }>;
  }

  createSpec(request: Schemas["SpecCreateRequest"]): Promise<Schemas["SavedSpec"]> {
    let path = `/v1/specs`;
    return this.request("POST", path, request) as Promise<Schemas["SavedSpec"]>;
  }

  listSpecs(query: { "limit"?: number; "cursor"?: string; "project_id"?: string; "archived"?: boolean; } = {}): Promise<Schemas["SpecPage"]> {
    let path = `/v1/specs`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["SpecPage"]>;
  }

  getSpec(specId: string): Promise<Schemas["SavedSpec"]> {
    let path = `/v1/specs/${encodeURIComponent(specId)}`;
    return this.request("GET", path) as Promise<Schemas["SavedSpec"]>;
  }

  reviseSpec(specId: string, request: Schemas["SpecRevisionRequest"]): Promise<Schemas["SavedSpec"]> {
    let path = `/v1/specs/${encodeURIComponent(specId)}/revisions`;
    return this.request("POST", path, request) as Promise<Schemas["SavedSpec"]>;
  }

  listSpecRevisions(specId: string, query: { "limit"?: number; "cursor"?: string; } = {}): Promise<Schemas["RevisionPage"]> {
    let path = `/v1/specs/${encodeURIComponent(specId)}/revisions`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["RevisionPage"]>;
  }

  getSpecRevision(specId: string, revisionId: string): Promise<Schemas["SpecRevision"]> {
    let path = `/v1/specs/${encodeURIComponent(specId)}/revisions/${encodeURIComponent(revisionId)}`;
    return this.request("GET", path) as Promise<Schemas["SpecRevision"]>;
  }

  archiveSpec(specId: string, request: Schemas["SpecArchiveRequest"]): Promise<Schemas["SavedSpec"]> {
    let path = `/v1/specs/${encodeURIComponent(specId)}`;
    return this.request("PATCH", path, request) as Promise<Schemas["SavedSpec"]>;
  }

  listSpecFinds(specId: string, query: { "limit"?: number; "cursor"?: string; } = {}): Promise<Schemas["LineagePage"]> {
    let path = `/v1/specs/${encodeURIComponent(specId)}/finds`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["LineagePage"]>;
  }

  getFindLineage(findId: string): Promise<Schemas["FindLineage"]> {
    let path = `/v1/finds/${encodeURIComponent(findId)}/lineage`;
    return this.request("GET", path) as Promise<Schemas["FindLineage"]>;
  }

  getDelivery(findId: string): Promise<Schemas["DeliveryProjection"]> {
    let path = `/v1/finds/${encodeURIComponent(findId)}/delivery`;
    return this.request("GET", path) as Promise<Schemas["DeliveryProjection"]>;
  }

  getFindDecisions(findId: string, query: { "limit"?: number; "cursor"?: string; } = {}): Promise<Schemas["DecisionPage"]> {
    let path = `/v1/finds/${encodeURIComponent(findId)}/decisions`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["DecisionPage"]>;
  }

  createProject(request: Schemas["ProjectCreateRequest"]): Promise<Schemas["Project"]> {
    let path = `/v1/projects`;
    return this.request("POST", path, request) as Promise<Schemas["Project"]>;
  }

  listProjects(query: { "limit"?: number; "cursor"?: string; } = {}): Promise<Schemas["ProjectPage"]> {
    let path = `/v1/projects`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["ProjectPage"]>;
  }

  getProject(projectId: string): Promise<Schemas["Project"]> {
    let path = `/v1/projects/${encodeURIComponent(projectId)}`;
    return this.request("GET", path) as Promise<Schemas["Project"]>;
  }

  updateProject(projectId: string, request: Schemas["ProjectPatchRequest"]): Promise<Schemas["Project"]> {
    let path = `/v1/projects/${encodeURIComponent(projectId)}`;
    return this.request("PATCH", path, request) as Promise<Schemas["Project"]>;
  }

  putProjectMember(projectId: string, request: Schemas["ProjectMemberRequest"]): Promise<Schemas["ProjectMember"]> {
    let path = `/v1/projects/${encodeURIComponent(projectId)}/members`;
    return this.request("POST", path, request) as Promise<Schemas["ProjectMember"]>;
  }

  listProjectMembers(projectId: string, query: { "limit"?: number; "cursor"?: string; } = {}): Promise<Schemas["MemberPage"]> {
    let path = `/v1/projects/${encodeURIComponent(projectId)}/members`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["MemberPage"]>;
  }

  revokeProjectMember(projectId: string, accountId: string): Promise<Schemas["MemberRevokeData"]> {
    let path = `/v1/projects/${encodeURIComponent(projectId)}/members/${encodeURIComponent(accountId)}`;
    return this.request("DELETE", path) as Promise<Schemas["MemberRevokeData"]>;
  }

  listCustomerWebhooks(): Promise<Schemas["CustomerWebhookListData"]> {
    let path = `/v1/account/webhooks`;
    return this.request("GET", path) as Promise<Schemas["CustomerWebhookListData"]>;
  }

  createCustomerWebhook(request: Schemas["CustomerWebhookRequest"]): Promise<Schemas["CustomerWebhookData"]> {
    let path = `/v1/account/webhooks`;
    return this.request("POST", path, request) as Promise<Schemas["CustomerWebhookData"]>;
  }

  revokeCustomerWebhook(hookId: string): Promise<{ "revoked": boolean; }> {
    let path = `/v1/account/webhooks/${encodeURIComponent(hookId)}`;
    return this.request("DELETE", path) as Promise<{ "revoked": boolean; }>;
  }

  getCapacityCatalog(): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/catalog`;
    return this.request("GET", path) as Promise<{ [key: string]: unknown; }>;
  }

  getCapacityBalance(query: { "project_id"?: string; } = {}): Promise<Schemas["CapacityBalanceData"]> {
    let path = `/v1/capacity/balance`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["CapacityBalanceData"]>;
  }

  getCapacityEntitlements(query: { "project_id"?: string; } = {}): Promise<Schemas["CapacityEntitlementsData"]> {
    let path = `/v1/capacity/entitlements`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["CapacityEntitlementsData"]>;
  }

  getCapacityReferral(): Promise<Schemas["CapacityReferralData"]> {
    let path = `/v1/capacity/referral`;
    return this.request("GET", path) as Promise<Schemas["CapacityReferralData"]>;
  }

  captureCapacityReferral(request: Schemas["CapacityReferralVisitRequest"]): Promise<Schemas["CapacityReferralVisitData"]> {
    let path = `/v1/capacity/referral/visit`;
    return this.request("POST", path, request) as Promise<Schemas["CapacityReferralVisitData"]>;
  }

  getCapacityHistory(): Promise<Schemas["CapacityHistoryData"]> {
    let path = `/v1/capacity/history`;
    return this.request("GET", path) as Promise<Schemas["CapacityHistoryData"]>;
  }

  claimFreeCapacity(): Promise<Schemas["CapacityBalanceData"]> {
    let path = `/v1/capacity/free`;
    return this.request("POST", path) as Promise<Schemas["CapacityBalanceData"]>;
  }

  setCapacityBudget(request: Schemas["CapacityBalanceLimitRequest"]): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/budget`;
    return this.request("PATCH", path, request) as Promise<{ [key: string]: unknown; }>;
  }

  quoteCapacityWork(request: Schemas["CapacityQuoteRequest"]): Promise<Schemas["CapacityQuoteData"]> {
    let path = `/v1/capacity/quotes`;
    return this.request("POST", path, request) as Promise<Schemas["CapacityQuoteData"]>;
  }

  getCapacityQuote(quoteId: string): Promise<Schemas["CapacityQuoteData"]> {
    let path = `/v1/capacity/quotes/${encodeURIComponent(quoteId)}`;
    return this.request("GET", path) as Promise<Schemas["CapacityQuoteData"]>;
  }

  authorizeCapacityWork(request: Schemas["CapacityAuthorizeRequest"]): Promise<Schemas["CapacityExecutionData"]> {
    let path = `/v1/capacity/executions`;
    requireWorkAuthorization(request);
    return this.request("POST", path, request) as Promise<Schemas["CapacityExecutionData"]>;
  }

  startCapacityRequest(request: Schemas["CapacityStartRequest"]): Promise<Schemas["CapacityStartData"]> {
    let path = `/v1/capacity/requests`;
    return this.request("POST", path, request) as Promise<Schemas["CapacityStartData"]>;
  }

  getCapacityRequest(requestKey: string, query: { "project_id"?: string; } = {}): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/requests/${encodeURIComponent(requestKey)}`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<{ [key: string]: unknown; }>;
  }

  getCapacityRequestRows(requestKey: string, query: { "project_id"?: string; "cursor"?: string; "limit"?: number; "format"?: "json" | "markdown" | "csv"; } = {}): Promise<({ [key: string]: unknown; } | { "format": "markdown" | "csv"; "columns": Array<{ "column_id": string; "label": string; }>; "table": string; "find_id"?: (string | null); "accepted_count"?: number; "next_cursor"?: (string | null); })> {
    let path = `/v1/capacity/requests/${encodeURIComponent(requestKey)}/rows`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<({ [key: string]: unknown; } | { "format": "markdown" | "csv"; "columns": Array<{ "column_id": string; "label": string; }>; "table": string; "find_id"?: (string | null); "accepted_count"?: number; "next_cursor"?: (string | null); })>;
  }

  getCapacityExecution(findId: string): Promise<Schemas["CommerceData"]> {
    let path = `/v1/capacity/executions/${encodeURIComponent(findId)}`;
    return this.request("GET", path) as Promise<Schemas["CommerceData"]>;
  }

  createCapacityFunding(request: Schemas["CapacityFundingRequest"]): Promise<Schemas["CapacityFundingData"]> {
    let path = `/v1/capacity/funding`;
    return this.request("POST", path, request) as Promise<Schemas["CapacityFundingData"]>;
  }

  getCapacityFunding(fundingId: string): Promise<Schemas["CapacityFundingData"]> {
    let path = `/v1/capacity/funding/${encodeURIComponent(fundingId)}`;
    return this.request("GET", path) as Promise<Schemas["CapacityFundingData"]>;
  }

  cancelCapacityFunding(fundingId: string): Promise<Schemas["CapacityFundingData"]> {
    let path = `/v1/capacity/funding/${encodeURIComponent(fundingId)}`;
    return this.request("DELETE", path) as Promise<Schemas["CapacityFundingData"]>;
  }

  getCapacityMembership(): Promise<Schemas["CapacityMembershipStatusData"]> {
    let path = `/v1/capacity/membership`;
    return this.request("GET", path) as Promise<Schemas["CapacityMembershipStatusData"]>;
  }

  changeCapacityMembership(request: Schemas["CapacityMembershipRequest"]): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/membership`;
    return this.request("POST", path, request) as Promise<{ [key: string]: unknown; }>;
  }

  createCapacityAuthority(request: Schemas["CapacityAuthorityRequest"]): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/authorities`;
    return this.request("POST", path, request) as Promise<{ [key: string]: unknown; }>;
  }

  revokeCapacityAuthority(authorityId: string): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/authorities/${encodeURIComponent(authorityId)}`;
    return this.request("DELETE", path) as Promise<{ [key: string]: unknown; }>;
  }

  createCapacitySchedule(request: Schemas["CapacityScheduleRequest"]): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/schedules`;
    return this.request("POST", path, request) as Promise<{ [key: string]: unknown; }>;
  }

  listCapacitySchedules(query: { "project_id"?: string; "after"?: string; "limit"?: number; } = {}): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/schedules`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<{ [key: string]: unknown; }>;
  }

  updateCapacitySchedule(scheduleId: string, request: Schemas["CapacitySchedulePatch"]): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/schedules/${encodeURIComponent(scheduleId)}`;
    return this.request("PATCH", path, request) as Promise<{ [key: string]: unknown; }>;
  }

  listCapacityOccurrences(scheduleId: string, query: { "before"?: string; "limit"?: number; } = {}): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/schedules/${encodeURIComponent(scheduleId)}/occurrences`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<{ [key: string]: unknown; }>;
  }

  runCapacityScheduleNow(scheduleId: string): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/schedules/${encodeURIComponent(scheduleId)}/run`;
    return this.request("POST", path) as Promise<{ [key: string]: unknown; }>;
  }

  createCapacityRefundClaim(request: Schemas["CapacityRefundRequest"]): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/refund-claims`;
    return this.request("POST", path, request) as Promise<{ [key: string]: unknown; }>;
  }

  listCapacityRefundClaims(): Promise<Schemas["CapacityRefundClaimsData"]> {
    let path = `/v1/capacity/refund-claims`;
    return this.request("GET", path) as Promise<Schemas["CapacityRefundClaimsData"]>;
  }

  getCapacityRefundClaim(claimId: string): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/refund-claims/${encodeURIComponent(claimId)}`;
    return this.request("GET", path) as Promise<{ [key: string]: unknown; }>;
  }

  requestCapacityCustomPlan(request: Schemas["CapacityCustomRequest"]): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/enterprise`;
    return this.request("POST", path, request) as Promise<{ [key: string]: unknown; }>;
  }

  getCapacityStoreConfig(): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/stores/config`;
    return this.request("GET", path) as Promise<{ [key: string]: unknown; }>;
  }

  verifyCapacityStorePurchase(request: Schemas["StorePurchaseRequest"]): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/stores/purchases`;
    return this.request("POST", path, request) as Promise<{ [key: string]: unknown; }>;
  }

  restoreCapacityStorePurchases(request: Schemas["StoreRestoreRequest"]): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/stores/restore`;
    return this.request("POST", path, request) as Promise<{ [key: string]: unknown; }>;
  }

  transferCapacityStoreToCard(request: Schemas["StoreCardTransferRequest"]): Promise<{ [key: string]: unknown; }> {
    let path = `/v1/capacity/stores/card-transfer`;
    return this.request("POST", path, request) as Promise<{ [key: string]: unknown; }>;
  }

  createSpecLink(specId: string, request: Schemas["SpecLinkRequest"]): Promise<Schemas["SpecLinkData"]> {
    let path = `/v1/specs/${encodeURIComponent(specId)}/links`;
    return this.request("POST", path, request) as Promise<Schemas["SpecLinkData"]>;
  }

  getSharedSpec(token: string): Promise<Schemas["SharedSpec"]> {
    let path = `/v1/shared-specs/${encodeURIComponent(token)}`;
    return this.request("GET", path) as Promise<Schemas["SharedSpec"]>;
  }

  revokeSpecLink(specId: string, linkId: string): Promise<Schemas["SpecLinkRevoked"]> {
    let path = `/v1/specs/${encodeURIComponent(specId)}/links/${encodeURIComponent(linkId)}/revoke`;
    return this.request("POST", path) as Promise<Schemas["SpecLinkRevoked"]>;
  }

  workspaceResearchInput(findId: string): Promise<Schemas["WorkspaceResearchInput"]> {
    let path = `/v1/workspace/collections/${encodeURIComponent(findId)}/input`;
    return this.request("GET", path) as Promise<Schemas["WorkspaceResearchInput"]>;
  }

  workspaceSetScheduleDelivery(scheduleId: string, request: Schemas["ScheduleDeliveryInput"]): Promise<Schemas["ScheduleDeliveryData"]> {
    let path = `/v1/workspace/schedules/${encodeURIComponent(scheduleId)}/delivery`;
    return this.request("PATCH", path, request) as Promise<Schemas["ScheduleDeliveryData"]>;
  }

  workspaceListCollections(query: { "project_id"?: string; "after"?: string; "limit"?: number; "sort"?: "id" | "recent"; } = {}): Promise<Schemas["WorkspaceCollectionPage"]> {
    let path = `/v1/workspace/collections`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["WorkspaceCollectionPage"]>;
  }

  workspaceReadCollection(collectionId: string): Promise<Schemas["WorkspaceCollection"]> {
    let path = `/v1/workspace/collections/${encodeURIComponent(collectionId)}`;
    return this.request("GET", path) as Promise<Schemas["WorkspaceCollection"]>;
  }

  workspaceCombineCollections(request: Schemas["CombineCollectionsInput"]): Promise<Schemas["WorkspaceCollection"]> {
    let path = `/v1/workspace/collections/combine`;
    return this.request("POST", path, request) as Promise<Schemas["WorkspaceCollection"]>;
  }

  workspaceCopyCollection(collectionId: string, request: Schemas["CopyCollectionInput"]): Promise<Schemas["WorkspaceCollection"]> {
    let path = `/v1/workspace/collections/${encodeURIComponent(collectionId)}/copy`;
    return this.request("POST", path, request) as Promise<Schemas["WorkspaceCollection"]>;
  }

  workspaceFilterCollection(collectionId: string, request: Schemas["CollectionFilter"]): Promise<Schemas["WorkspaceCollection"]> {
    let path = `/v1/workspace/collections/${encodeURIComponent(collectionId)}/filter`;
    return this.request("POST", path, request) as Promise<Schemas["WorkspaceCollection"]>;
  }

  workspaceListViews(collectionId: string): Promise<Schemas["WorkspaceViewList"]> {
    let path = `/v1/workspace/views/${encodeURIComponent(collectionId)}`;
    return this.request("GET", path) as Promise<Schemas["WorkspaceViewList"]>;
  }

  workspaceSaveView(collectionId: string, request: Schemas["WorkspaceViewSave"]): Promise<Schemas["WorkspaceViewList"]> {
    let path = `/v1/workspace/views/${encodeURIComponent(collectionId)}`;
    return this.request("PUT", path, request) as Promise<Schemas["WorkspaceViewList"]>;
  }

  workspaceListStars(): Promise<Schemas["WorkspaceStarList"]> {
    let path = `/v1/workspace/stars`;
    return this.request("GET", path) as Promise<Schemas["WorkspaceStarList"]>;
  }

  workspaceStarItem(request: Schemas["WorkspaceStarWrite"]): Promise<Schemas["WorkspaceStarList"]> {
    let path = `/v1/workspace/stars`;
    return this.request("PUT", path, request) as Promise<Schemas["WorkspaceStarList"]>;
  }

  workspaceListNotes(query: { "project_id"?: string; "collection_id"?: string; "record_id"?: string; } = {}): Promise<Schemas["WorkspaceNotes"]> {
    let path = `/v1/workspace/notes`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["WorkspaceNotes"]>;
  }

  workspaceAddNote(request: Schemas["WorkspaceNoteAdd"]): Promise<Schemas["WorkspaceNotes"]> {
    let path = `/v1/workspace/notes`;
    return this.request("POST", path, request) as Promise<Schemas["WorkspaceNotes"]>;
  }

  workspaceResolveNote(noteId: string, request: Schemas["WorkspaceNoteResolve"]): Promise<Schemas["WorkspaceNotes"]> {
    let path = `/v1/workspace/notes/${encodeURIComponent(noteId)}`;
    return this.request("PATCH", path, request) as Promise<Schemas["WorkspaceNotes"]>;
  }

  workspaceEditNote(noteId: string, request: Schemas["WorkspaceNoteEdit"]): Promise<Schemas["WorkspaceNotes"]> {
    let path = `/v1/workspace/notes/${encodeURIComponent(noteId)}`;
    return this.request("PUT", path, request) as Promise<Schemas["WorkspaceNotes"]>;
  }

  workspaceDeleteNote(noteId: string, request: Schemas["WorkspaceNoteDelete"]): Promise<Schemas["WorkspaceNotes"]> {
    let path = `/v1/workspace/notes/${encodeURIComponent(noteId)}`;
    return this.request("DELETE", path, request) as Promise<Schemas["WorkspaceNotes"]>;
  }

  workspaceRegisterWebPushSubscription(request: Schemas["WebPushSubscriptionInput"]): Promise<Schemas["PushDevice"]> {
    let path = `/v1/workspace/push/subscriptions`;
    return this.request("POST", path, request) as Promise<Schemas["PushDevice"]>;
  }

  workspacePushCapabilities(): Promise<Schemas["PushCapabilities"]> {
    let path = `/v1/workspace/push/capabilities`;
    return this.request("GET", path) as Promise<Schemas["PushCapabilities"]>;
  }

  workspaceListPushDevices(): Promise<Schemas["PushDevicePage"]> {
    let path = `/v1/workspace/push/devices`;
    return this.request("GET", path) as Promise<Schemas["PushDevicePage"]>;
  }

  workspaceRegisterPushDevice(request: Schemas["PushDeviceInput"]): Promise<Schemas["PushDevice"]> {
    let path = `/v1/workspace/push/devices`;
    return this.request("POST", path, request) as Promise<Schemas["PushDevice"]>;
  }

  workspaceRevokePushDevice(deviceId: string): Promise<Schemas["PushDeviceRevoked"]> {
    let path = `/v1/workspace/push/devices/${encodeURIComponent(deviceId)}`;
    return this.request("DELETE", path) as Promise<Schemas["PushDeviceRevoked"]>;
  }

  workspaceListYourFields(collectionId: string): Promise<Schemas["YourFields"]> {
    let path = `/v1/workspace/collections/${encodeURIComponent(collectionId)}/fields`;
    return this.request("GET", path) as Promise<Schemas["YourFields"]>;
  }

  workspaceSaveYourFields(collectionId: string, request: Schemas["YourFieldsSave"]): Promise<Schemas["YourFields"]> {
    let path = `/v1/workspace/collections/${encodeURIComponent(collectionId)}/fields`;
    return this.request("PUT", path, request) as Promise<Schemas["YourFields"]>;
  }

  workspaceSetYourFieldValue(collectionId: string, request: Schemas["YourFieldValue"]): Promise<Schemas["YourFields"]> {
    let path = `/v1/workspace/collections/${encodeURIComponent(collectionId)}/fields/values`;
    return this.request("PUT", path, request) as Promise<Schemas["YourFields"]>;
  }

  beginConnectionAuthorization(provider: string): Promise<Schemas["ConnectedToolData"]> {
    let path = `/v1/connections/${encodeURIComponent(provider)}/authorize`;
    return this.request("POST", path) as Promise<Schemas["ConnectedToolData"]>;
  }

  disconnectConnection(connectionId: string): Promise<Schemas["ConnectedToolData"]> {
    let path = `/v1/connections/${encodeURIComponent(connectionId)}`;
    return this.request("DELETE", path) as Promise<Schemas["ConnectedToolData"]>;
  }

  listCloudImports(): Promise<Schemas["ConnectedToolData"]> {
    let path = `/v1/imports/cloud`;
    return this.request("GET", path) as Promise<Schemas["ConnectedToolData"]>;
  }

  listConnectedTools(): Promise<Schemas["ConnectedToolData"]> {
    let path = `/v1/connections/catalog`;
    return this.request("GET", path) as Promise<Schemas["ConnectedToolData"]>;
  }

  listConnections(): Promise<Schemas["ConnectedToolData"]> {
    let path = `/v1/connections`;
    return this.request("GET", path) as Promise<Schemas["ConnectedToolData"]>;
  }

  listConnectionDestinations(connectionId: string, query: { "base_id"?: string; "cursor"?: string; } = {}): Promise<Schemas["ConnectedToolData"]> {
    let path = `/v1/connections/${encodeURIComponent(connectionId)}/destinations`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["ConnectedToolData"]>;
  }

  getConnectionColumns(connectionId: string, request: Schemas["DestinationRequest"]): Promise<Schemas["ConnectedToolData"]> {
    let path = `/v1/connections/${encodeURIComponent(connectionId)}/columns`;
    return this.request("POST", path, request) as Promise<Schemas["ConnectedToolData"]>;
  }

  saveConnectionDestination(connectionId: string, request: Schemas["DestinationRequest"]): Promise<Schemas["ConnectedToolData"]> {
    let path = `/v1/connections/${encodeURIComponent(connectionId)}/destination`;
    return this.request("POST", path, request) as Promise<Schemas["ConnectedToolData"]>;
  }

  sendToDestination(connectionId: string, request: Schemas["SendToDestinationInput"]): Promise<Schemas["ConnectedToolData"]> {
    let path = `/v1/connections/${encodeURIComponent(connectionId)}/send`;
    return this.request("POST", path, request) as Promise<Schemas["ConnectedToolData"]>;
  }

  reconcileDestinationExport(connectionId: string, exportId: string): Promise<Schemas["ConnectedToolData"]> {
    let path = `/v1/connections/${encodeURIComponent(connectionId)}/exports/${encodeURIComponent(exportId)}/reconcile`;
    return this.request("POST", path) as Promise<Schemas["ConnectedToolData"]>;
  }

  listDestinationExports(): Promise<Schemas["ConnectedToolData"]> {
    let path = `/v1/connections/exports`;
    return this.request("GET", path) as Promise<Schemas["ConnectedToolData"]>;
  }

  createDestinationSync(request: Schemas["DestinationSyncInput"]): Promise<Schemas["ConnectedToolData"]> {
    let path = `/v1/destination-syncs`;
    return this.request("POST", path, request) as Promise<Schemas["ConnectedToolData"]>;
  }

  updateDestinationSync(syncId: string, request: Schemas["DestinationSyncUpdate"]): Promise<Schemas["ConnectedToolData"]> {
    let path = `/v1/destination-syncs/${encodeURIComponent(syncId)}`;
    return this.request("PATCH", path, request) as Promise<Schemas["ConnectedToolData"]>;
  }

  listDestinationSyncs(): Promise<Schemas["ConnectedToolData"]> {
    let path = `/v1/destination-syncs`;
    return this.request("GET", path) as Promise<Schemas["ConnectedToolData"]>;
  }

  previewCloudList(request: Schemas["CloudImportPreview"]): Promise<Schemas["ConnectedToolData"]> {
    let path = `/v1/imports/cloud/preview`;
    return this.request("POST", path, request) as Promise<Schemas["ConnectedToolData"]>;
  }

  importCloudList(request: Schemas["CloudImportInput"]): Promise<Schemas["ConnectedToolData"]> {
    let path = `/v1/imports/cloud`;
    return this.request("POST", path, request) as Promise<Schemas["ConnectedToolData"]>;
  }

  updateCloudImport(importId: string, request: Schemas["CloudImportUpdate"]): Promise<Schemas["ConnectedToolData"]> {
    let path = `/v1/imports/cloud/${encodeURIComponent(importId)}`;
    return this.request("PATCH", path, request) as Promise<Schemas["ConnectedToolData"]>;
  }

  workspaceInviteMember(request: Schemas["InvitationInput"]): Promise<Schemas["InvitationData"]> {
    let path = `/v1/workspace/invitations`;
    return this.request("POST", path, request) as Promise<Schemas["InvitationData"]>;
  }

  importFileCommand(request: Schemas["FileImportCommand"]): Promise<Schemas["WorkspaceImportData"]> {
    let path = `/v1/imports/file`;
    return this.request("POST", path, request) as Promise<Schemas["WorkspaceImportData"]>;
  }

  workspaceActivity(query: { "project_id"?: string; "cursor"?: string; "limit"?: number; } = {}): Promise<Schemas["ActivityPage"]> {
    let path = `/v1/activity`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["ActivityPage"]>;
  }

  workspaceRelationships(collectionId: string, query: { "field_id"?: string; } = {}): Promise<Schemas["RelationshipData"]> {
    let path = `/v1/workspace/collections/${encodeURIComponent(collectionId)}/relationships`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["RelationshipData"]>;
  }

  workspaceSaveRelationships(collectionId: string, request: Schemas["RelationshipSelection"]): Promise<Schemas["RelationshipData"]> {
    let path = `/v1/workspace/collections/${encodeURIComponent(collectionId)}/relationships`;
    return this.request("PUT", path, request) as Promise<Schemas["RelationshipData"]>;
  }

  workspaceShareCollection(collectionId: string, request: Schemas["CollectionShareInput"]): Promise<Schemas["CollectionShareData"]> {
    let path = `/v1/workspace/collections/${encodeURIComponent(collectionId)}/share`;
    return this.request("POST", path, request) as Promise<Schemas["CollectionShareData"]>;
  }

  workspaceReportResult(collectionId: string, request: Schemas["ResultReportInput"]): Promise<Schemas["ResultReportData"]> {
    let path = `/v1/workspace/collections/${encodeURIComponent(collectionId)}/reports`;
    return this.request("POST", path, request) as Promise<Schemas["ResultReportData"]>;
  }

  listRequestTemplates(query: { "record_type"?: string; } = {}): Promise<Schemas["RequestTemplateList"]> {
    let path = `/v1/request-templates`;
    const queryString = new URLSearchParams();
    for (const [key, value] of Object.entries(query))
      if (value !== undefined && value !== null) queryString.set(key, String(value));
    if (queryString.size) path += "?" + queryString.toString();
    return this.request("GET", path) as Promise<Schemas["RequestTemplateList"]>;
  }

  workspaceCollectionChanges(collectionId: string): Promise<Schemas["WorkspaceCollectionChanges"]> {
    let path = `/v1/workspace/collections/${encodeURIComponent(collectionId)}/changes`;
    return this.request("GET", path) as Promise<Schemas["WorkspaceCollectionChanges"]>;
  }

  workspaceListPasskeys(): Promise<Schemas["PasskeyList"]> {
    let path = `/v1/workspace/security/passkeys`;
    return this.request("GET", path) as Promise<Schemas["PasskeyList"]>;
  }

  workspaceRegisterPasskeyOptions(): Promise<Schemas["SecurityChallenge"]> {
    let path = `/v1/workspace/security/passkeys/options`;
    return this.request("POST", path) as Promise<Schemas["SecurityChallenge"]>;
  }

  workspaceRegisterPasskey(request: Schemas["PasskeyRegistration"]): Promise<Schemas["PasskeyData"]> {
    let path = `/v1/workspace/security/passkeys`;
    return this.request("POST", path, request) as Promise<Schemas["PasskeyData"]>;
  }

  workspaceNamePasskey(credentialId: string, request: Schemas["PasskeyLabel"]): Promise<Schemas["PasskeyData"]> {
    let path = `/v1/workspace/security/passkeys/${encodeURIComponent(credentialId)}`;
    return this.request("PATCH", path, request) as Promise<Schemas["PasskeyData"]>;
  }

  workspaceDeletePasskey(credentialId: string): Promise<Schemas["SecuritySuccess"]> {
    let path = `/v1/workspace/security/passkeys/${encodeURIComponent(credentialId)}`;
    return this.request("DELETE", path) as Promise<Schemas["SecuritySuccess"]>;
  }

  workspacePasskeySignInOptions(): Promise<Schemas["SecurityChallenge"]> {
    let path = `/v1/workspace/auth/passkey/options`;
    return this.request("POST", path) as Promise<Schemas["SecurityChallenge"]>;
  }

  workspacePasskeySignIn(request: Schemas["PasskeyComplete"]): Promise<Schemas["SecuritySuccess"]> {
    let path = `/v1/workspace/auth/passkey/verify`;
    return this.request("POST", path, request) as Promise<Schemas["SecuritySuccess"]>;
  }

  workspaceListSSODomains(): Promise<Schemas["SSODomains"]> {
    let path = `/v1/workspace/security/sso`;
    return this.request("GET", path) as Promise<Schemas["SSODomains"]>;
  }

  workspaceAddSSODomain(request: Schemas["SSODomainInput"]): Promise<Schemas["SSODomain"]> {
    let path = `/v1/workspace/security/sso`;
    return this.request("POST", path, request) as Promise<Schemas["SSODomain"]>;
  }

  workspaceVerifySSODomain(domainId: string): Promise<Schemas["SSODomain"]> {
    let path = `/v1/workspace/security/sso/${encodeURIComponent(domainId)}/verify`;
    return this.request("POST", path) as Promise<Schemas["SSODomain"]>;
  }

  workspaceConfigureSSO(domainId: string, request: Schemas["SSOConfigInput"]): Promise<Schemas["SSODomain"]> {
    let path = `/v1/workspace/security/sso/${encodeURIComponent(domainId)}/provider`;
    return this.request("PUT", path, request) as Promise<Schemas["SSODomain"]>;
  }

  workspaceSetSSOPolicy(domainId: string, request: Schemas["SSOPolicyInput"]): Promise<Schemas["SSODomain"]> {
    let path = `/v1/workspace/security/sso/${encodeURIComponent(domainId)}`;
    return this.request("PATCH", path, request) as Promise<Schemas["SSODomain"]>;
  }

  workspaceStartSSO(request: Schemas["SSOStartInput"]): Promise<Schemas["SSOStartData"]> {
    let path = `/v1/workspace/auth/sso/start`;
    return this.request("POST", path, request) as Promise<Schemas["SSOStartData"]>;
  }

  workspaceRotateSCIMToken(domainId: string): Promise<Schemas["SCIMCredential"]> {
    let path = `/v1/workspace/security/sso/${encodeURIComponent(domainId)}/scim/token`;
    return this.request("POST", path) as Promise<Schemas["SCIMCredential"]>;
  }

  workspaceRevokeSCIMToken(domainId: string): Promise<Schemas["SecuritySuccess"]> {
    let path = `/v1/workspace/security/sso/${encodeURIComponent(domainId)}/scim/token`;
    return this.request("DELETE", path) as Promise<Schemas["SecuritySuccess"]>;
  }

  workspaceReadSCIMMappings(domainId: string): Promise<Schemas["SCIMProvisioning"]> {
    let path = `/v1/workspace/security/sso/${encodeURIComponent(domainId)}/scim/mappings`;
    return this.request("GET", path) as Promise<Schemas["SCIMProvisioning"]>;
  }

  workspaceSetSCIMMappings(domainId: string, request: Schemas["SCIMMappings"]): Promise<Schemas["SCIMMappings"]> {
    let path = `/v1/workspace/security/sso/${encodeURIComponent(domainId)}/scim/mappings`;
    return this.request("PUT", path, request) as Promise<Schemas["SCIMMappings"]>;
  }

  workspaceReadPhoto(): Promise<Schemas["AccountPhotoData"]> {
    let path = `/v1/workspace/profile/photo`;
    return this.request("GET", path) as Promise<Schemas["AccountPhotoData"]>;
  }

  workspaceDeletePhoto(): Promise<Schemas["AccountPhotoData"]> {
    let path = `/v1/workspace/profile/photo`;
    return this.request("DELETE", path) as Promise<Schemas["AccountPhotoData"]>;
  }

  workspaceStartNativeProvider(request: Schemas["NativeAuthStart"]): Promise<Schemas["NativeAuthStartData"]> {
    let path = `/v1/workspace/auth/native/start`;
    return this.request("POST", path, request) as Promise<Schemas["NativeAuthStartData"]>;
  }

  workspaceRedeemNativeProvider(request: Schemas["NativeAuthRedeem"]): Promise<Schemas["NativeAuthRedeemData"]> {
    let path = `/v1/workspace/auth/native/redeem`;
    return this.request("POST", path, request) as Promise<Schemas["NativeAuthRedeemData"]>;
  }

  workspacePlacementAllowance(): Promise<Schemas["PlacementMonthlyData"]> {
    let path = `/v1/workspace/placement/allowance`;
    return this.request("GET", path) as Promise<Schemas["PlacementMonthlyData"]>;
  }

  workspaceQuotePlacement(importId: string): Promise<Schemas["PlacementQuoteData"]> {
    let path = `/v1/workspace/imports/${encodeURIComponent(importId)}/placement/quote`;
    return this.request("POST", path) as Promise<Schemas["PlacementQuoteData"]>;
  }

  workspaceStartPlacement(importId: string, request: Schemas["PlacementStartInput"]): Promise<Schemas["PlacementStatusData"]> {
    let path = `/v1/workspace/imports/${encodeURIComponent(importId)}/placement`;
    return this.request("POST", path, request) as Promise<Schemas["PlacementStatusData"]>;
  }

  workspacePlacementStatus(importId: string, placementId: string): Promise<Schemas["PlacementStatusData"]> {
    let path = `/v1/workspace/imports/${encodeURIComponent(importId)}/placement/${encodeURIComponent(placementId)}`;
    return this.request("GET", path) as Promise<Schemas["PlacementStatusData"]>;
  }

  teachWebSource(request: Schemas["TeachWebSource"]): Promise<Schemas["WebSourcePreview"]> {
    let path = `/v1/imports/web/sources`;
    return this.request("POST", path, request) as Promise<Schemas["WebSourcePreview"]>;
  }

  listWebSources(): Promise<Schemas["WebSourceList"]> {
    let path = `/v1/imports/web/sources`;
    return this.request("GET", path) as Promise<Schemas["WebSourceList"]>;
  }

  getWebSource(sourceId: string): Promise<Schemas["WebSourceInfo"]> {
    let path = `/v1/imports/web/sources/${encodeURIComponent(sourceId)}`;
    return this.request("GET", path) as Promise<Schemas["WebSourceInfo"]>;
  }

  previewWebSource(sourceId: string): Promise<Schemas["WebSourcePreview"]> {
    let path = `/v1/imports/web/sources/${encodeURIComponent(sourceId)}/previews`;
    return this.request("POST", path) as Promise<Schemas["WebSourcePreview"]>;
  }

  getWebSourcePreview(previewId: string): Promise<Schemas["WebSourcePreview"]> {
    let path = `/v1/imports/web/previews/${encodeURIComponent(previewId)}`;
    return this.request("GET", path) as Promise<Schemas["WebSourcePreview"]>;
  }

  saveWebSourceList(request: Schemas["SaveWebSourceList"]): Promise<Schemas["WorkspaceImportData"]> {
    let path = `/v1/imports/web/lists`;
    return this.request("POST", path, request) as Promise<Schemas["WorkspaceImportData"]>;
  }

  getReconciliationFields(collectionId: string): Promise<Schemas["ReconciliationFields"]> {
    let path = `/v1/reconciliation/collections/${encodeURIComponent(collectionId)}/fields`;
    return this.request("GET", path) as Promise<Schemas["ReconciliationFields"]>;
  }

  listReconciliations(collectionId: string): Promise<Schemas["ReconciliationHistory"]> {
    let path = `/v1/reconciliation/collections/${encodeURIComponent(collectionId)}/comparisons`;
    return this.request("GET", path) as Promise<Schemas["ReconciliationHistory"]>;
  }

  prepareReconciliation(request: Schemas["ReconciliationPrepare"]): Promise<Schemas["ReconciliationView"]> {
    let path = `/v1/reconciliation/comparisons`;
    return this.request("POST", path, request) as Promise<Schemas["ReconciliationView"]>;
  }

  getReconciliation(comparisonId: string): Promise<Schemas["ReconciliationView"]> {
    let path = `/v1/reconciliation/comparisons/${encodeURIComponent(comparisonId)}`;
    return this.request("GET", path) as Promise<Schemas["ReconciliationView"]>;
  }

  applyReconciliation(comparisonId: string, request: Schemas["ReconciliationApply"]): Promise<Schemas["WorkspaceImportData"]> {
    let path = `/v1/reconciliation/comparisons/${encodeURIComponent(comparisonId)}/apply`;
    return this.request("POST", path, request) as Promise<Schemas["WorkspaceImportData"]>;
  }

  getReconciledInput(importId: string): Promise<Schemas["ReconciliationReceipt"]> {
    let path = `/v1/reconciliation/imports/${encodeURIComponent(importId)}`;
    return this.request("GET", path) as Promise<Schemas["ReconciliationReceipt"]>;
  }
  // END GENERATED LIFECYCLE

  private headers(): Record<string, string> {
    const token = this.apiKey.toLowerCase().startsWith("bearer ")
      ? this.apiKey
      : `Bearer ${this.apiKey}`;
    return {
      Authorization: token,
      Accept: "application/json",
      "Content-Type": "application/json",
      "User-Agent": "specstream-typescript/1.3.3",
    };
  }

  private async request(method: string, path: string, body?: JsonMap): Promise<JsonMap> {
    const url = this.baseUrl + path;
    const send = () => this.fetchFn(url, {
      method,
      headers: this.headers(),
      redirect: "error",
      signal: AbortSignal.timeout(this.timeoutMs),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let response: Response;
    let text: string;
    try {
      response = await send();
      const wait = retryAfterMs(response);
      if (wait !== null) {
        // The server did nothing and names when to ask again: ask once more.
        await response.body?.cancel();
        await new Promise((resolve) => setTimeout(resolve, wait));
        response = await send();
      }
      text = await response.text();
    } catch (error) {
      throw new SpecstreamError(method + " " + path + " transport failed", null, error);
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw new SpecstreamError(method + " " + path + " returned invalid JSON", response.status, text);
    }
    if (!response.ok) {
      throw new SpecstreamError(method + " " + path + " failed with HTTP " + response.status, response.status, parsed);
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new SpecstreamError(method + " " + path + " returned non-object JSON", response.status, parsed);
    }
    const envelope = parsed as JsonMap;
    if (envelope.error != null || !envelope.data || typeof envelope.data !== "object" || Array.isArray(envelope.data)) {
      throw new SpecstreamError(method + " " + path + " returned an invalid success envelope", response.status, parsed);
    }
    return envelope.data as JsonMap;
  }
}

export default Client;
