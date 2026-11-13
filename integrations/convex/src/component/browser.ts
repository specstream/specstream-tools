import { v } from "convex/values";
import { action } from "./_generated/server.js";
import { specstreamRequest } from "./api.js";
import { fail } from "./helpers.js";

// Browser sessions: a real browser that SpecStream runs (POST /v1/browser/sessions).
// Time costs $0.10 an hour, charged by the second while it is open, and each step
// costs $0.001. The browser ends by itself after `timeoutSeconds`.

export const DEFAULT_TIMEOUT_SECONDS = 300;
export const DEFAULT_IDLE_SECONDS = 120;
const TOOL_NAME = /^browser_[a-z][a-z0-9_]{0,62}$/;
const SESSION_KEYS = [
  "status",
  "ended_reason",
  "live_url",
  "expires_at",
  "timeout_s",
  "seconds",
  "actions",
  "charged_usd",
  "price",
] as const;

function isObject(value: unknown): value is Record<string, any> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function sessionId(id: string): string {
  const trimmed = (id ?? "").trim();
  if (!trimmed) {
    fail("specstream_invalid_session", "Pass the sessionId that openBrowser returned.");
  }
  return encodeURIComponent(trimmed);
}

/** A session without its connect address, which carries the session's token. */
export function sessionView(
  session: Record<string, any>,
  includeConnectUrl = false,
): Record<string, any> {
  const out: Record<string, any> = { sessionId: String(session.id ?? "") };
  for (const key of SESSION_KEYS) {
    if (session[key] !== undefined && session[key] !== null) out[key] = session[key];
  }
  if (includeConnectUrl && typeof session.connect_url === "string") {
    out.connect_url = session.connect_url;
  }
  return out;
}

/** One step: its text joined, image data left out, where the page is and what it cost. */
export function stepView(id: string, step: Record<string, any>): Record<string, any> {
  const out: Record<string, any> = { sessionId: id };
  const texts: string[] = [];
  const images: { mime_type: string | null; base64_chars: number }[] = [];
  for (const part of Array.isArray(step.result) ? step.result : []) {
    if (!isObject(part)) continue;
    if (part.type === "text" && typeof part.text === "string" && part.text) {
      texts.push(part.text);
    } else if (part.type === "image") {
      images.push({
        mime_type: typeof part.mime_type === "string" ? part.mime_type : null,
        base64_chars: typeof part.data === "string" ? part.data.length : 0,
      });
    }
  }
  if (texts.length) out.text = texts.join("\n\n");
  if (images.length) out.images = images;
  for (const key of ["url", "title", "read_at", "price_usd"]) {
    if (step[key] !== undefined && step[key] !== null) out[key] = step[key];
  }
  if (isObject(step.error)) out.error = step.error;
  return out;
}

/**
 * Open a real browser (`POST /v1/browser/sessions`, $0.10 an hour by the second).
 * Steps hold no connection, so the session is kept alive between them. Set
 * `includeConnectUrl` to drive it with Playwright or Puppeteer from a Node action
 * over its `connect_url`; keep that address on the server, it carries a token.
 */
export const openBrowser = action({
  args: {
    timeoutSeconds: v.optional(v.number()),
    idleTimeoutSeconds: v.optional(v.number()),
    allowedDomains: v.optional(v.array(v.string())),
    blockMedia: v.optional(v.boolean()),
    headless: v.optional(v.boolean()),
    metadata: v.optional(v.record(v.string(), v.union(v.string(), v.number(), v.boolean()))),
    includeConnectUrl: v.optional(v.boolean()),
    idempotencyKey: v.optional(v.string()),
  },
  returns: v.any(),
  handler: async (_ctx, args) => {
    const timeout = args.timeoutSeconds ?? DEFAULT_TIMEOUT_SECONDS;
    if (!Number.isInteger(timeout) || timeout < 60 || timeout > 3600) {
      fail("specstream_invalid_timeout", "timeoutSeconds must be a whole number from 60 to 3600.");
    }
    const idle = args.idleTimeoutSeconds ?? DEFAULT_IDLE_SECONDS;
    if (!Number.isInteger(idle) || idle < 10 || idle > 600) {
      fail("specstream_invalid_timeout", "idleTimeoutSeconds must be a whole number from 10 to 600.");
    }
    const body: Record<string, unknown> = {
      timeout_s: timeout,
      idle_timeout_s: idle,
      keep_alive: true,
    };
    if (args.allowedDomains?.length) body.allowed_domains = args.allowedDomains;
    if (args.blockMedia) body.block_media = true;
    if (args.headless === false) body.headless = false;
    if (args.metadata && Object.keys(args.metadata).length) body.metadata = args.metadata;
    // The same key on a retried call returns the session the first call opened.
    const key = (args.idempotencyKey ?? "").trim() || crypto.randomUUID();
    const session = await specstreamRequest("/v1/browser/sessions", {
      method: "POST",
      body,
      headers: { "Idempotency-Key": key.slice(0, 128) },
    });
    return sessionView(session, args.includeConnectUrl === true);
  },
});

/**
 * Run one step in the session's browser (`POST /v1/browser/sessions/{id}/actions`,
 * $0.001 a step). `tool` is a Playwright MCP tool name (browser_navigate,
 * browser_snapshot, browser_click, browser_type and the others) or browser_read for
 * the page's text. A page the site refuses comes back in `error`, not as an exception.
 */
export const browserStep = action({
  args: {
    sessionId: v.string(),
    tool: v.string(),
    arguments: v.optional(v.record(v.string(), v.any())),
  },
  returns: v.any(),
  handler: async (_ctx, args) => {
    const id = sessionId(args.sessionId);
    if (!TOOL_NAME.test(args.tool ?? "")) {
      fail(
        "specstream_invalid_tool",
        "tool must be a browser step name such as browser_navigate or browser_click.",
      );
    }
    const cleaned = Object.fromEntries(
      Object.entries(args.arguments ?? {}).filter(([, value]) => value !== undefined && value !== null),
    );
    const step = await specstreamRequest(`/v1/browser/sessions/${id}/actions`, {
      method: "POST",
      body: { tool: args.tool, arguments: cleaned },
    });
    return stepView(args.sessionId.trim(), step);
  },
});

/** A session's state, seconds, steps and charge so far (`GET /v1/browser/sessions/{id}`). Free. */
export const browserSession = action({
  args: { sessionId: v.string() },
  returns: v.any(),
  handler: async (_ctx, args) =>
    sessionView(await specstreamRequest(`/v1/browser/sessions/${sessionId(args.sessionId)}`)),
});

/** End the session (`POST /v1/browser/sessions/{id}/release`), so its time stops being charged. */
export const closeBrowser = action({
  args: { sessionId: v.string() },
  returns: v.any(),
  handler: async (_ctx, args) =>
    sessionView(
      await specstreamRequest(`/v1/browser/sessions/${sessionId(args.sessionId)}/release`, {
        method: "POST",
      }),
    ),
});
