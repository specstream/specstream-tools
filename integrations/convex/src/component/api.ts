import { ConvexError } from "convex/values";
import { env } from "./_generated/server.js";

const DEFAULT_API_URL = "https://api.specstream.ai";

/** Sent as the User-Agent so SpecStream can tell this component's traffic apart. */
export const USER_AGENT = "@specstream/convex/0.1.0";

/** Where a list opens in the SpecStream workspace. */
export function listLink(specstreamListId: string): string {
  return `https://specstream.ai/workspace/collections/${encodeURIComponent(specstreamListId)}`;
}

/**
 * Retry policy for transient SpecStream failures. Exported as a mutable object
 * so tests can zero out the delays.
 */
export const RETRY = { attempts: 3, baseDelayMs: 500, maxDelayMs: 8_000 };

const RETRYABLE_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);

export function apiBase(): string {
  return (env.SPECSTREAM_API_URL ?? DEFAULT_API_URL).replace(/\/+$/, "");
}

function apiKey(): string {
  const key = (env.SPECSTREAM_API_KEY ?? "").trim();
  if (!key) {
    throw new ConvexError({
      code: "specstream_missing_api_key",
      message:
        "SPECSTREAM_API_KEY is not set for the SpecStream component. Pass it in `app.use(specstream, { env: { SPECSTREAM_API_KEY: ... } })`.",
    });
  }
  return key;
}

function fail(
  path: string,
  status: number,
  message: string,
  code?: string,
): never {
  throw new ConvexError({
    code: code ?? "specstream_request_failed",
    status,
    path,
    message,
  });
}

function plainError(
  status: number,
  detailCode: string | null,
  detailMessage: string | null,
): string {
  if (status === 401) {
    return "SpecStream did not accept the API key. Create a new one under Agents & API in your workspace and set SPECSTREAM_API_KEY.";
  }
  if (status === 402) {
    return "The SpecStream balance can't cover this. Add funds in the workspace, then try again.";
  }
  if (status === 429) {
    return "SpecStream is asking for a short pause. Try again in a minute.";
  }
  if (detailMessage) return detailMessage;
  return detailCode
    ? `SpecStream could not do that (${detailCode}).`
    : `SpecStream answered with an error (HTTP ${status}).`;
}

async function sleep(ms: number): Promise<void> {
  if (ms <= 0) return;
  await new Promise((resolve) => setTimeout(resolve, ms));
}

function retryDelayMs(attempt: number, retryAfter: string | null): number {
  if (retryAfter) {
    const seconds = Number(retryAfter);
    if (Number.isFinite(seconds) && seconds >= 0) {
      return Math.min(seconds * 1000, RETRY.maxDelayMs);
    }
  }
  return Math.min(RETRY.baseDelayMs * 2 ** attempt, RETRY.maxDelayMs);
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function asString(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined;
}

export function asCount(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.trunc(value)
    : 0;
}

export type RequestInitLike = {
  method?: "GET" | "POST" | "DELETE";
  body?: Record<string, unknown>;
  /** Extra headers, such as an Idempotency-Key that makes a retried POST safe. */
  headers?: Record<string, string>;
};

/**
 * Call the SpecStream API, retrying transient failures, and return the `data`
 * object of the response envelope.
 */
export async function specstreamRequest(
  path: string,
  init: RequestInitLike = {},
): Promise<Record<string, any>> {
  const method = init.method ?? "GET";
  const key = apiKey();
  const headers: Record<string, string> = {
    Authorization: /^bearer /i.test(key) ? key : `Bearer ${key}`,
    Accept: "application/json",
    "User-Agent": USER_AGENT,
    ...(init.headers ?? {}),
  };
  let payload: string | undefined;
  if (init.body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(init.body);
  }
  const url = `${apiBase()}${path}`;

  let lastError = "";
  for (let attempt = 0; attempt <= RETRY.attempts; attempt++) {
    let response: Response;
    try {
      response = await fetch(url, { method, headers, body: payload });
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
      if (attempt === RETRY.attempts) {
        fail(path, 0, `Could not reach SpecStream: ${lastError}`);
      }
      await sleep(retryDelayMs(attempt, null));
      continue;
    }

    const text = await response.text();
    let body: unknown = null;
    if (text.length > 0) {
      try {
        body = JSON.parse(text);
      } catch {
        body = null;
      }
    }

    if (response.ok) {
      const data = isObject(body) ? body.data : undefined;
      if (isObject(data)) return data;
      fail(
        path,
        response.status,
        "SpecStream returned something this component could not read.",
      );
    }

    const detail = isObject(body) && isObject(body.error) ? body.error : {};
    const detailCode = asString(detail.code) ?? null;
    const message = plainError(
      response.status,
      detailCode,
      asString(detail.message) ?? null,
    );
    const retryable = RETRYABLE_STATUS.has(response.status);
    if (!retryable || attempt === RETRY.attempts) {
      fail(
        path,
        response.status,
        message,
        detailCode ? `specstream_${detailCode}` : undefined,
      );
    }
    lastError = message;
    await sleep(retryDelayMs(attempt, response.headers.get("retry-after")));
  }

  fail(path, 0, lastError || "exhausted retries");
}

export const _test = { retryDelayMs, plainError };
