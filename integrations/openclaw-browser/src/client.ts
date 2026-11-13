/** The SpecStream browser-session calls the tools share: open a session, send it one step, end it. */

export const BASE_URL = "https://api.specstream.ai";
export const USER_AGENT = "@specstream/openclaw-browser-plugin/0.1.0";
/** The API's own bounds for a session's length and for its idle wait, in seconds. */
export const TIMEOUT_MIN_S = 60;
export const TIMEOUT_MAX_S = 3600;
export const IDLE_MIN_S = 10;
export const IDLE_MAX_S = 600;
const REQUEST_TIMEOUT_MS = 150_000;

/** SpecStream refused a call or answered with something this plugin cannot read. */
export class SpecStreamError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SpecStreamError";
  }
}

/** A session as the API answers it. Only the fields the tools show are named. */
export type BrowserSession = {
  id: string;
  status: string;
  ended_reason?: string | null;
  connect_url?: string | null;
  live_url?: string | null;
  expires_at?: string;
  timeout_s?: number;
  idle_timeout_s?: number;
  allowed_domains?: string[];
  seconds?: number;
  actions?: number;
  charged_usd?: number;
  [field: string]: unknown;
};

export type ActionContent = { type: "text" | "image"; text?: string | null; data?: string | null; mime_type?: string | null };

/** The answer to one step: what the tool returned, the page after it and what the step cost. */
export type ActionResult = {
  result: ActionContent[];
  error?: { code: string; reason?: string | null; message: string } | null;
  url?: string | null;
  title?: string | null;
  took_ms?: number;
  price_usd?: number;
  read_at?: string | null;
};

export type OpenOptions = {
  timeoutSeconds: number;
  idleTimeoutSeconds: number;
  allowedDomains?: string[];
  blockMedia?: boolean;
  abortSignal?: AbortSignal;
};

export type BrowserClientOptions = {
  apiKey: string;
  baseUrl?: string;
  /** Replaces the global fetch, for tests. */
  fetch?: typeof fetch;
};

export class BrowserClient {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: BrowserClientOptions) {
    this.apiKey = options.apiKey;
    this.baseUrl = (options.baseUrl ?? BASE_URL).replace(/\/+$/, "");
    this.fetchImpl = options.fetch ?? fetch;
  }

  /**
   * Opens a session. keep_alive is true because the tools drive the browser one step at a time, with no client
   * connected between steps: without it the session would end at once. It ends at timeout_s, or after
   * idle_timeout_s without a step, or when it is released.
   */
  async open(options: OpenOptions): Promise<BrowserSession> {
    const body: Record<string, unknown> = {
      timeout_s: options.timeoutSeconds,
      idle_timeout_s: options.idleTimeoutSeconds,
      keep_alive: true,
      metadata: { client: "openclaw" },
    };
    if (options.allowedDomains?.length) body.allowed_domains = options.allowedDomains;
    if (options.blockMedia) body.block_media = true;
    return (await this.request("POST", "/v1/browser/sessions", body, options.abortSignal)) as BrowserSession;
  }

  async get(sessionId: string, abortSignal?: AbortSignal): Promise<BrowserSession> {
    return (await this.request("GET", this.path(sessionId), undefined, abortSignal)) as BrowserSession;
  }

  /** One step: a Playwright MCP tool name with its arguments, or browser_read for the page's text. */
  async act(sessionId: string, tool: string, args: Record<string, unknown> = {}, abortSignal?: AbortSignal): Promise<ActionResult> {
    const data = await this.request("POST", `${this.path(sessionId)}/actions`, { tool, arguments: args }, abortSignal);
    return { ...data, result: Array.isArray(data.result) ? data.result : [] } as ActionResult;
  }

  /** Ends the session, so that its time stops being charged. */
  async release(sessionId: string, abortSignal?: AbortSignal): Promise<BrowserSession> {
    return (await this.request("POST", `${this.path(sessionId)}/release`, {}, abortSignal)) as BrowserSession;
  }

  private path(sessionId: string): string {
    const id = String(sessionId ?? "").trim();
    if (!id) throw new SpecStreamError("session_id is empty. Open a browser with specstream_browser_open first.");
    return `/v1/browser/sessions/${encodeURIComponent(id)}`;
  }

  private async request(
    method: "GET" | "POST",
    path: string,
    body?: Record<string, unknown>,
    abortSignal?: AbortSignal,
  ): Promise<Record<string, unknown>> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(new Error("timed out")), REQUEST_TIMEOUT_MS);
    const onAbort = () => controller.abort(abortSignal?.reason);
    if (abortSignal?.aborted) onAbort();
    else abortSignal?.addEventListener("abort", onAbort, { once: true });
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
      if (abortSignal?.aborted) throw error;
      const reason = error instanceof Error ? (error.cause instanceof Error ? error.cause.message : error.message) : String(error);
      throw new SpecStreamError(`Could not reach SpecStream: ${reason}`);
    } finally {
      clearTimeout(timer);
      abortSignal?.removeEventListener("abort", onAbort);
    }
    let payload: any = null;
    try {
      payload = raw ? JSON.parse(raw) : null;
    } catch {
      payload = null;
    }
    if (!response.ok) {
      const error = payload?.error;
      const message = (typeof error === "string" ? error : error?.message) || payload?.detail || raw.slice(0, 300) || response.statusText;
      throw new SpecStreamError(`SpecStream answered ${response.status}: ${typeof message === "string" ? message : JSON.stringify(message)}`);
    }
    const data = payload?.data;
    if (!data || typeof data !== "object") throw new SpecStreamError("SpecStream answered without data.");
    return data as Record<string, unknown>;
  }
}
