import { describe, expect, it } from "vitest";
import { asSchema } from "ai";
import { SpecStreamClient, specstreamBrowserTools, specstreamTools } from "../src/index.js";

// The browser tools open a session at POST /v1/browser/sessions, drive it by steps and release it.
// The fetch is scripted: no test calls SpecStream.

const SESSION = {
  id: "bss_01JX",
  status: "running",
  connect_url: "wss://api.specstream.ai/v1/browser/sessions/bss_01JX/connect?token=secret-token",
  actions_url: "https://api.specstream.ai/v1/browser/sessions/bss_01JX/actions",
  live_url: "https://api.specstream.ai/v1/browser/sessions/bss_01JX/live?token=t",
  expires_at: "2026-11-13T10:05:00Z",
  timeout_s: 300,
  seconds: 0,
  actions: 0,
  charged_usd: 0,
  price: { per_second_usd: 0.0000278, per_action_usd: 0.001 },
};

type Call = { method: string; path: string; body: any; headers: Record<string, string> };

function recorder() {
  const calls: Call[] = [];
  const fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(String(input));
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method: init?.method ?? "GET", path: url.pathname, body, headers: init?.headers as Record<string, string> });
    const reply = (data: unknown, status = 200) => new Response(JSON.stringify({ data }), { status });
    if (url.pathname === "/v1/browser/sessions") return reply(SESSION, 201);
    if (url.pathname.endsWith("/release")) return reply({ ...SESSION, status: "ended", ended_reason: "released", connect_url: null, live_url: null, seconds: 42, actions: 3, charged_usd: 0.0042 });
    if (url.pathname.endsWith("/actions")) {
      if (body.tool === "browser_take_screenshot") return reply({ result: [{ type: "image", data: "QUJD".repeat(100), mime_type: "image/png" }], price_usd: 0.001 });
      if (body.arguments?.url === "https://blocked.example/") {
        return reply({ result: [], error: { code: "blocked", reason: "outside_allowed_domains", message: "The host is outside allowed_domains." }, price_usd: 0 });
      }
      return reply({ result: [{ type: "text", text: "# Example Domain" }], url: "https://example.com/", title: "Example Domain", price_usd: 0.001, read_at: "2026-11-13T10:00:05Z" });
    }
    return reply(SESSION);
  }) as typeof globalThis.fetch;
  return { calls, fetch };
}

const ctx = { toolCallId: "c", messages: [] };
const run = (tool: any, input: unknown) => tool.execute(input, ctx);

describe("specstreamBrowserTools", () => {
  it("gives the eight browser tools, apart from the list tools", () => {
    const tools = specstreamBrowserTools({ apiKey: "ss_live_test_key" });
    expect(Object.keys(tools)).toEqual([
      "specstream_open_browser",
      "specstream_browser_navigate",
      "specstream_browser_read",
      "specstream_browser_snapshot",
      "specstream_browser_click",
      "specstream_browser_type",
      "specstream_browser_action",
      "specstream_close_browser",
    ]);
    expect(Object.keys(specstreamTools({ apiKey: "ss_live_test_key", maxPriceUsd: 5 }))).not.toContain("specstream_open_browser");
  });

  it("opens a session with the limits set in code and hides the connect address", async () => {
    const { calls, fetch } = recorder();
    const tools = specstreamBrowserTools({ apiKey: "ss_live_test_key", fetch, timeoutSeconds: 120, allowedDomains: ["example.com"], blockMedia: true });
    const out = await run(tools.specstream_open_browser, {});
    expect(calls).toHaveLength(1);
    expect(calls[0].method).toBe("POST");
    expect(calls[0].path).toBe("/v1/browser/sessions");
    expect(calls[0].body).toEqual({ timeout_s: 120, idle_timeout_s: 120, keep_alive: true, allowed_domains: ["example.com"], block_media: true });
    expect(calls[0].headers.Authorization).toBe("Bearer ss_live_test_key");
    expect(calls[0].headers["User-Agent"]).toBe("@specstream/ai-sdk/0.4.0");
    expect(out.session_id).toBe("bss_01JX");
    expect(out.message).toContain("specstream_close_browser");
    expect(JSON.stringify(out)).not.toContain("secret-token");
    expect(out).not.toHaveProperty("connect_url");
  });

  it("keeps the time limit out of the model's inputs", async () => {
    const tools = specstreamBrowserTools({ apiKey: "ss_live_test_key" });
    const schema = (await asSchema(tools.specstream_open_browser.inputSchema).jsonSchema) as any;
    expect(Object.keys(schema.properties)).toEqual(["url"]);
  });

  it("opens the first page when the model gives one", async () => {
    const { calls, fetch } = recorder();
    const out = await run(specstreamBrowserTools({ apiKey: "ss_live_test_key", fetch }).specstream_open_browser, { url: " https://example.com/ " });
    expect(calls.map((c) => c.path)).toEqual(["/v1/browser/sessions", "/v1/browser/sessions/bss_01JX/actions"]);
    expect(calls[1].body).toEqual({ tool: "browser_navigate", arguments: { url: "https://example.com/" } });
    expect(out.page.title).toBe("Example Domain");
  });

  it("sends each step as its Playwright MCP tool", async () => {
    const { calls, fetch } = recorder();
    const tools = specstreamBrowserTools({ apiKey: "ss_live_test_key", fetch });
    const read = await run(tools.specstream_browser_read, { session_id: "bss_01JX" });
    await run(tools.specstream_browser_snapshot, { session_id: "bss_01JX" });
    await run(tools.specstream_browser_click, { session_id: "bss_01JX", target: "e12" });
    await run(tools.specstream_browser_type, { session_id: "bss_01JX", target: "e3", text: "lisbon", submit: true });
    await run(tools.specstream_browser_navigate, { session_id: "bss_01JX", url: "https://example.com/" });
    await run(tools.specstream_browser_action, { session_id: "bss_01JX", tool: "browser_press_key", arguments: { key: "Enter" } });
    expect(calls.every((c) => c.method === "POST" && c.path === "/v1/browser/sessions/bss_01JX/actions")).toBe(true);
    expect(calls.map((c) => c.body)).toEqual([
      { tool: "browser_read", arguments: { format: "markdown" } },
      { tool: "browser_snapshot", arguments: {} },
      { tool: "browser_click", arguments: { target: "e12" } },
      { tool: "browser_type", arguments: { target: "e3", text: "lisbon", submit: true } },
      { tool: "browser_navigate", arguments: { url: "https://example.com/" } },
      { tool: "browser_press_key", arguments: { key: "Enter" } },
    ]);
    expect(read).toEqual({
      session_id: "bss_01JX",
      text: "# Example Domain",
      url: "https://example.com/",
      title: "Example Domain",
      read_at: "2026-11-13T10:00:05Z",
      price_usd: 0.001,
    });
  });

  it("returns a refused page as an error the model can read", async () => {
    const { fetch } = recorder();
    const out = await run(specstreamBrowserTools({ apiKey: "ss_live_test_key", fetch }).specstream_browser_navigate, {
      session_id: "bss_01JX",
      url: "https://blocked.example/",
    });
    expect(out.error.code).toBe("blocked");
    expect(out.price_usd).toBe(0);
    expect(out).not.toHaveProperty("text");
  });

  it("leaves a screenshot's bytes out of the answer", async () => {
    const { fetch } = recorder();
    const out = await run(specstreamBrowserTools({ apiKey: "ss_live_test_key", fetch }).specstream_browser_action, {
      session_id: "bss_01JX",
      tool: "browser_take_screenshot",
    });
    expect(out.images).toEqual([{ mime_type: "image/png", base64_chars: 400 }]);
    expect(JSON.stringify(out)).not.toContain("QUJD");
  });

  it("closes the session and returns what it cost", async () => {
    const { calls, fetch } = recorder();
    const out = await run(specstreamBrowserTools({ apiKey: "ss_live_test_key", fetch }).specstream_close_browser, { session_id: "bss_01JX" });
    expect(calls[0].method).toBe("POST");
    expect(calls[0].path).toBe("/v1/browser/sessions/bss_01JX/release");
    expect(out).toMatchObject({ session_id: "bss_01JX", status: "ended", ended_reason: "released", seconds: 42, actions: 3, charged_usd: 0.0042 });
  });

  it("refuses limits outside the API's range, and a missing key, before any call", () => {
    expect(() => specstreamBrowserTools({ apiKey: "ss_live_test_key", timeoutSeconds: 30 })).toThrow(/timeoutSeconds/);
    expect(() => specstreamBrowserTools({ apiKey: "ss_live_test_key", timeoutSeconds: 7200 })).toThrow(/timeoutSeconds/);
    expect(() => specstreamBrowserTools({ apiKey: "ss_live_test_key", idleTimeoutSeconds: 5 })).toThrow(/idleTimeoutSeconds/);
    expect(() => specstreamBrowserTools({ apiKey: "" })).toThrow(/SPECSTREAM_API_KEY/);
  });
});

describe("SpecStreamClient browser calls", () => {
  it("refuses a step name that is not a browser tool, and an empty session, before any call", async () => {
    const { calls, fetch } = recorder();
    const client = new SpecStreamClient({ apiKey: "ss_live_test_key", fetch });
    await expect(client.browserStep("bss_01JX", "rm -rf")).rejects.toThrow(/browser step name/);
    await expect(client.browserStep(" ", "browser_read")).rejects.toThrow(/session_id/);
    await expect(client.closeBrowser("")).rejects.toThrow(/session_id/);
    expect(calls).toHaveLength(0);
  });

  it("reads a session and escapes its id in the path", async () => {
    const { calls, fetch } = recorder();
    const client = new SpecStreamClient({ apiKey: "ss_live_test_key", fetch });
    const session = await client.browserSession("bss/01");
    expect(calls[0].method).toBe("GET");
    expect(calls[0].path).toBe("/v1/browser/sessions/bss%2F01");
    expect(session.status).toBe("running");
  });

  it("opens with the defaults: 300 seconds, kept alive between steps", async () => {
    const { calls, fetch } = recorder();
    await new SpecStreamClient({ apiKey: "ss_live_test_key", fetch }).openBrowser();
    expect(calls[0].body).toEqual({ timeout_s: 300, idle_timeout_s: 120, keep_alive: true });
  });
});
