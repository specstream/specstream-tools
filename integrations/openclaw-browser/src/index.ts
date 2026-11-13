import { Type } from "typebox";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";
import { BrowserClient, IDLE_MAX_S, IDLE_MIN_S, TIMEOUT_MAX_S, TIMEOUT_MIN_S, type ActionResult, type BrowserSession } from "./client.js";
import {
  DEFAULT_IDLE_TIMEOUT_SECONDS,
  DEFAULT_TIMEOUT_SECONDS,
  effectiveDomains,
  effectiveTimeout,
  resolveConfig,
  type PluginConfig,
} from "./config.js";

const PRICE = "$0.10 an hour charged by the second, and $1 per 1,000 steps";

const configSchema = Type.Object(
  {
    apiKey: Type.Optional(
      Type.Union([Type.String(), Type.Record(Type.String(), Type.Unknown())], {
        description: "SpecStream API key, or a SecretRef. Falls back to the SPECSTREAM_API_KEY environment variable.",
      }),
    ),
    timeoutSeconds: Type.Optional(
      Type.Integer({
        minimum: TIMEOUT_MIN_S,
        maximum: TIMEOUT_MAX_S,
        description: `The most seconds one browser session runs. Defaults to ${DEFAULT_TIMEOUT_SECONDS}. The model can ask for less per session and never more.`,
      }),
    ),
    idleTimeoutSeconds: Type.Optional(
      Type.Integer({
        minimum: IDLE_MIN_S,
        maximum: IDLE_MAX_S,
        description: `A session ends after this many seconds without a step. Defaults to ${DEFAULT_IDLE_TIMEOUT_SECONDS}.`,
      }),
    ),
    allowedDomains: Type.Optional(
      Type.Array(Type.String(), {
        maxItems: 100,
        description: "Hosts the browser may open, such as example.com or *.example.com. Empty allows every public host. The model can narrow the list per session and never add a host.",
      }),
    ),
    blockMedia: Type.Optional(
      Type.Boolean({ description: "true skips images, video, audio and fonts, so pages load faster. Screenshots then show no pictures." }),
    ),
  },
  { additionalProperties: false },
);

const sessionId = Type.String({ minLength: 1, description: "The session_id that specstream_browser_open returned." });

/** What the model needs of a session: its id, its state, where a person can watch it, and what it has cost. */
function sessionView(session: BrowserSession): Record<string, unknown> {
  return {
    session_id: session.id,
    status: session.status,
    ended_reason: session.ended_reason ?? null,
    live_url: session.live_url ?? null,
    expires_at: session.expires_at ?? null,
    timeout_s: session.timeout_s ?? null,
    idle_timeout_s: session.idle_timeout_s ?? null,
    allowed_domains: session.allowed_domains ?? [],
    seconds: session.seconds ?? 0,
    steps: session.actions ?? 0,
    charged_usd: session.charged_usd ?? 0,
  };
}

/** One step without its pictures: the text the tool returned, the page after it and what the step cost. */
function stepView(answer: ActionResult): Record<string, unknown> {
  const text = answer.result
    .filter((part) => part.type === "text" && typeof part.text === "string")
    .map((part) => part.text)
    .join("\n");
  return {
    text,
    images: answer.result.filter((part) => part.type === "image").length,
    error: answer.error ?? null,
    url: answer.url ?? null,
    title: answer.title ?? null,
    took_ms: answer.took_ms ?? null,
    price_usd: answer.price_usd ?? null,
    ...(answer.read_at ? { read_at: answer.read_at } : {}),
  };
}

type Content = { type: "text"; text: string } | { type: "image"; data: string; mimeType: string };

/** The step as the agent receives it: its JSON as text, then each picture (a screenshot) as an image. */
export function stepContent(answer: ActionResult): { content: Content[]; details: Record<string, unknown> } {
  const details = stepView(answer);
  const content: Content[] = [{ type: "text", text: JSON.stringify(details, null, 2) }];
  for (const part of answer.result) {
    if (part.type === "image" && typeof part.data === "string" && part.data) {
      content.push({ type: "image", data: part.data, mimeType: part.mime_type || "image/png" });
    }
  }
  return { content, details };
}

const stepParameters = Type.Object({
  session_id: sessionId,
  tool: Type.String({
    pattern: "^browser_[a-z][a-z0-9_]{0,62}$",
    description:
      "A Playwright MCP tool name: browser_navigate, browser_snapshot, browser_click, browser_type, browser_press_key, browser_select_option, browser_wait_for, browser_take_screenshot and the others.",
  }),
  arguments: Type.Optional(
    Type.Record(Type.String(), Type.Unknown(), {
      description:
        'The tool\'s arguments, as Playwright MCP names them. Examples: {"url": "https://example.com"} for browser_navigate; {"element": "Sign in button", "ref": "e12"} for browser_click, with ref taken from the last browser_snapshot.',
    }),
  ),
});

const entry = defineToolPlugin({
  id: "specstream-browser",
  name: "SpecStream Browser",
  description:
    "A real Chromium browser in the cloud for your agent: open pages, click, type, read and take screenshots, with no browser to install. " +
    `Sessions cost ${PRICE}.`,
  activation: { onStartup: false },
  configSchema,
  tools: (tool) => [
    tool({
      name: "specstream_browser_open",
      label: "Open a cloud browser",
      description: [
        `Open a real Chromium browser in the cloud with SpecStream browser sessions (POST /v1/browser/sessions, ${PRICE}).`,
        "Use it for a page that needs a real browser: one that renders with JavaScript, needs clicks, typing or scrolling, or refuses a plain read.",
        "Pass url to open a page at once. Returns JSON with session_id for the other specstream_browser tools, live_url (a page where a person watches the screen), expires_at and, with url, the first page.",
        "The session ends at its timeout, after the idle wait without a step, or with specstream_browser_close. Close it when the work is done, so that its time stops being charged.",
      ].join(" "),
      parameters: Type.Object({
        url: Type.Optional(Type.String({ minLength: 1, description: "An http or https page to open first." })),
        timeout_s: Type.Optional(
          Type.Integer({
            minimum: TIMEOUT_MIN_S,
            maximum: TIMEOUT_MAX_S,
            description: "The most seconds the session runs. It can be lower than the configured length and never higher.",
          }),
        ),
        allowed_domains: Type.Optional(
          Type.Array(Type.String(), {
            maxItems: 100,
            description: "Hosts the browser may open, such as example.com or *.example.com, with no scheme or path. Leave it out to allow every host the configuration allows.",
          }),
        ),
      }),
      execute: async ({ url, timeout_s, allowed_domains }, config, { signal }) => {
        const settings = resolveConfig(config as PluginConfig);
        const client = new BrowserClient({ apiKey: settings.apiKey });
        const session = await client.open({
          timeoutSeconds: effectiveTimeout(settings.timeoutSeconds, timeout_s),
          idleTimeoutSeconds: settings.idleTimeoutSeconds,
          allowedDomains: effectiveDomains(settings.allowedDomains, allowed_domains),
          blockMedia: settings.blockMedia,
          abortSignal: signal,
        });
        const view = sessionView(session);
        if (!url) return view;
        try {
          return { ...view, page: stepView(await client.act(session.id, "browser_navigate", { url }, signal)) };
        } catch (error) {
          // The session is open and charged by the second, so the model must learn its id even when the page failed.
          return { ...view, page: { error: { code: "tool_failed", message: error instanceof Error ? error.message : String(error) } } };
        }
      },
    }),
    tool({
      name: "specstream_browser_step",
      label: "Do one browser step",
      description: [
        "Do one step in an open SpecStream browser session: a Playwright MCP tool call ($1 per 1,000 steps).",
        "Typical order: browser_navigate to a page, browser_snapshot to get the page's elements with their ref ids, then browser_click or browser_type with a ref, and browser_snapshot again to see the result.",
        "browser_take_screenshot returns the picture as an image.",
        "Returns JSON with text (the tool's answer), error (code blocked when the page is refused, tool_failed when the step failed), the page's url and title after the step, and price_usd.",
      ].join(" "),
      parameters: stepParameters,
      factory: ({ config }) => ({
        name: "specstream_browser_step",
        label: "Do one browser step",
        description: "Do one step in an open SpecStream browser session: a Playwright MCP tool call.",
        parameters: stepParameters,
        execute: async (_toolCallId: string, params: { session_id: string; tool: string; arguments?: Record<string, unknown> }, signal?: AbortSignal) => {
          signal?.throwIfAborted();
          const settings = resolveConfig(config as PluginConfig);
          const client = new BrowserClient({ apiKey: settings.apiKey });
          return stepContent(await client.act(params.session_id, params.tool, params.arguments ?? {}, signal));
        },
      }),
    }),
    tool({
      name: "specstream_browser_read",
      label: "Read the open page",
      description: [
        "Read the main text of the page that is open in a SpecStream browser session, as the browser shows it now (one step, $1 per 1,000 steps).",
        "Use it after the clicks and typing that bring the content up. Returns JSON with text, the page's url and title, read_at and price_usd.",
      ].join(" "),
      parameters: Type.Object({
        session_id: sessionId,
        format: Type.Optional(
          Type.Union([Type.Literal("markdown"), Type.Literal("text")], {
            description: 'Output format: "markdown" (default, keeps headings, lists and links) or "text".',
          }),
        ),
      }),
      execute: async ({ session_id, format }, config, { signal }) => {
        const settings = resolveConfig(config as PluginConfig);
        const client = new BrowserClient({ apiKey: settings.apiKey });
        return stepView(await client.act(session_id, "browser_read", { format: format ?? "markdown" }, signal));
      },
    }),
    tool({
      name: "specstream_browser_close",
      label: "Close the cloud browser",
      description:
        "End a SpecStream browser session, so that its time stops being charged. Returns JSON with status, the seconds it ran, its steps and charged_usd. Closing a session that already ended is not an error.",
      parameters: Type.Object({ session_id: sessionId }),
      execute: async ({ session_id }, config, { signal }) => {
        const settings = resolveConfig(config as PluginConfig);
        const client = new BrowserClient({ apiKey: settings.apiKey });
        return sessionView(await client.release(session_id, signal));
      },
    }),
  ],
});

export default entry;
