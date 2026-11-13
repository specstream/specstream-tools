import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { getToolPluginMetadata } from "openclaw/plugin-sdk/tool-plugin";
import entry from "../src/index.js";
import { BrowserClient, SpecStreamError } from "../src/client.js";
import { effectiveDomains, effectiveTimeout, resolveConfig } from "../src/config.js";

type Call = { method: string; path: string; body: Record<string, any> | null; headers: Record<string, string> };
type Answer = { status?: number; data?: unknown; error?: unknown };
type Tool = { name: string; execute: (id: string, params: any, signal?: AbortSignal) => Promise<any> };

const SESSION = {
  id: "bs_1",
  status: "running",
  ended_reason: null,
  connect_url: "wss://api.specstream.ai/v1/browser/connect/bs_1?token=t",
  live_url: "https://api.specstream.ai/v1/browser/sessions/bs_1/live?token=t",
  expires_at: "2026-11-13T10:05:00Z",
  timeout_s: 300,
  idle_timeout_s: 300,
  allowed_domains: [],
  seconds: 0,
  actions: 0,
  charged_usd: 0,
};

const STEP = { result: [{ type: "text", text: "- link \"More\" [ref=e7]" }], error: null, url: "https://example.com/", title: "Example", took_ms: 40, price_usd: 0.001 };

/** A fetch that answers as the browser-session routes do and records every call. */
function server(step: (call: Call) => Answer | undefined = () => ({ data: STEP })) {
  const calls: Call[] = [];
  const impl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const call: Call = {
      method: init?.method ?? "GET",
      path: url.pathname,
      body: init?.body ? JSON.parse(String(init.body)) : null,
      headers: init?.headers as Record<string, string>,
    };
    calls.push(call);
    let answer: Answer | undefined;
    if (call.method === "POST" && call.path === "/v1/browser/sessions") answer = { status: 201, data: { ...SESSION, ...call.body } };
    else if (call.path.endsWith("/actions")) answer = step(call);
    else if (call.path.endsWith("/release")) answer = { data: { ...SESSION, status: "ended", ended_reason: "released", connect_url: null, live_url: null, seconds: 42, actions: 3, charged_usd: 0.004167 } };
    answer ??= { status: 404, error: { message: "No session with this id on this account." } };
    const status = answer.status ?? 200;
    const payload = status >= 400 ? { error: answer.error ?? { message: "error" } } : { data: answer.data };
    return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", impl);
  return calls;
}

/** Registers the plugin against a stand-in API and returns the tools it registered. */
function load(pluginConfig: Record<string, unknown>): Record<string, Tool> {
  const tools: Record<string, Tool> = {};
  const add = (tool: Tool) => {
    tools[tool.name] = tool;
  };
  (entry as any).register({
    pluginConfig,
    // A factory tool is registered as a function of the tool context; a plain tool as the tool itself.
    registerTool: (tool: Tool | ((context: unknown) => Tool | Tool[] | null)) => {
      const made = typeof tool === "function" ? tool({}) : tool;
      for (const one of Array.isArray(made) ? made : made ? [made] : []) add(one);
    },
  });
  return tools;
}

const details = (answer: any) => answer.details ?? answer;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("manifest", () => {
  const read = (name: string) => JSON.parse(readFileSync(new URL(`../${name}`, import.meta.url), "utf8"));
  const names = ["specstream_browser_open", "specstream_browser_step", "specstream_browser_read", "specstream_browser_close"];

  it("declares the four browser tools, in the plugin and in the manifest ClawHub reads", () => {
    expect(getToolPluginMetadata(entry)?.tools.map((tool) => tool.name)).toEqual(names);
    expect(read("openclaw.plugin.json").contracts.tools).toEqual(names);
    expect(read("openclaw.plugin.json").id).toBe("specstream-browser");
  });

  it("gives the package, the manifest and the lock one version", () => {
    const pkg = read("package.json");
    const lock = read("package-lock.json");
    expect(read("openclaw.plugin.json").version).toBe(pkg.version);
    expect(lock.version).toBe(pkg.version);
    expect(lock.packages[""].version).toBe(pkg.version);
    expect(lock.name).toBe(pkg.name);
  });

  it("tags every specstream.ai link in the README with the ClawHub source", () => {
    const text = readFileSync(new URL("../README.md", import.meta.url), "utf8");
    const links = text.match(/https:\/\/specstream\.ai[^\s)"`]*/g) ?? [];
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) expect(link).toContain("utm_source=clawhub");
  });
});

describe("config", () => {
  it("reads the key from the environment and fails clearly without one", () => {
    expect(resolveConfig({}, { SPECSTREAM_API_KEY: " ss_live_env " } as NodeJS.ProcessEnv)).toMatchObject({ apiKey: "ss_live_env", timeoutSeconds: 300, idleTimeoutSeconds: 300 });
    expect(() => resolveConfig({}, {} as NodeJS.ProcessEnv)).toThrow("SPECSTREAM_API_KEY");
  });

  it("lets a call shorten the session and never lengthen it", () => {
    expect(effectiveTimeout(300, 120)).toBe(120);
    expect(effectiveTimeout(300, 3600)).toBe(300);
    expect(effectiveTimeout(300, undefined)).toBe(300);
    expect(effectiveTimeout(300, 5)).toBe(60);
  });

  it("lets a call narrow the configured hosts and never add one", () => {
    expect(effectiveDomains([], ["Example.com"])).toEqual(["example.com"]);
    expect(effectiveDomains(["example.com", "*.shop.test"], undefined)).toEqual(["example.com", "*.shop.test"]);
    expect(effectiveDomains(["example.com", "*.shop.test"], ["a.shop.test"])).toEqual(["a.shop.test"]);
    expect(() => effectiveDomains(["example.com"], ["example.com", "evil.test"])).toThrow("evil.test");
    expect(() => effectiveDomains(["*.shop.test"], ["notshop.test"])).toThrow("notshop.test");
  });
});

describe("tools", () => {
  it("open starts a kept-alive session within the configured length, then opens the page", async () => {
    const calls = server();
    const tools = load({ apiKey: "ss_live_cfg", timeoutSeconds: 120, allowedDomains: ["example.com"] });
    const answer = details(await tools.specstream_browser_open.execute("c1", { url: "https://example.com", timeout_s: 900 }));

    expect(calls[0]).toMatchObject({ method: "POST", path: "/v1/browser/sessions" });
    expect(calls[0].body).toMatchObject({ timeout_s: 120, idle_timeout_s: 300, keep_alive: true, allowed_domains: ["example.com"] });
    expect(calls[0].headers.Authorization).toBe("Bearer ss_live_cfg");
    expect(calls[0].headers["User-Agent"]).toContain("@specstream/openclaw-browser-plugin/");
    expect(calls[1]).toMatchObject({ path: "/v1/browser/sessions/bs_1/actions", body: { tool: "browser_navigate", arguments: { url: "https://example.com" } } });
    expect(answer).toMatchObject({ session_id: "bs_1", status: "running", live_url: SESSION.live_url, page: { url: "https://example.com/", title: "Example" } });
  });

  it("open still returns the session when its first page fails, so that it can be closed", async () => {
    server(() => ({ status: 502, error: { message: "The browser did not answer." } }));
    const answer = details(await load({ apiKey: "k" }).specstream_browser_open.execute("c1", { url: "https://example.com" }));
    expect(answer.session_id).toBe("bs_1");
    expect(answer.page.error.message).toContain("The browser did not answer.");
  });

  it("step sends the Playwright tool call as given and returns its text, page and price", async () => {
    const calls = server();
    const answer = await load({ apiKey: "k" }).specstream_browser_step.execute("c1", { session_id: "bs_1", tool: "browser_click", arguments: { element: "More", ref: "e7" } });
    expect(calls[0]).toMatchObject({ path: "/v1/browser/sessions/bs_1/actions", body: { tool: "browser_click", arguments: { element: "More", ref: "e7" } } });
    expect(answer.details).toMatchObject({ text: '- link "More" [ref=e7]', images: 0, error: null, url: "https://example.com/", price_usd: 0.001 });
    expect(answer.content).toHaveLength(1);
    expect(JSON.parse(answer.content[0].text).title).toBe("Example");
  });

  it("step returns a screenshot as an image and keeps its bytes out of the text", async () => {
    server(() => ({ data: { ...STEP, result: [{ type: "text", text: "Took the screenshot" }, { type: "image", data: "aGVsbG8=", mime_type: "image/jpeg" }] } }));
    const answer = await load({ apiKey: "k" }).specstream_browser_step.execute("c1", { session_id: "bs_1", tool: "browser_take_screenshot" });
    expect(answer.content[1]).toEqual({ type: "image", data: "aGVsbG8=", mimeType: "image/jpeg" });
    expect(answer.content[0].text).not.toContain("aGVsbG8=");
    expect(answer.details.images).toBe(1);
  });

  it("step passes a refused page on as an error the model can read", async () => {
    server(() => ({ data: { ...STEP, result: [], error: { code: "blocked", reason: "private_address", message: "This address is private." } } }));
    const answer = await load({ apiKey: "k" }).specstream_browser_step.execute("c1", { session_id: "bs_1", tool: "browser_navigate", arguments: { url: "http://10.0.0.1" } });
    expect(answer.details.error).toMatchObject({ code: "blocked", reason: "private_address" });
  });

  it("read asks for the page's text in markdown by default", async () => {
    const calls = server(() => ({ data: { ...STEP, result: [{ type: "text", text: "# Example" }], read_at: "2026-11-13T10:00:00Z" } }));
    const answer = details(await load({ apiKey: "k" }).specstream_browser_read.execute("c1", { session_id: "bs_1" }));
    expect(calls[0].body).toEqual({ tool: "browser_read", arguments: { format: "markdown" } });
    expect(answer).toMatchObject({ text: "# Example", read_at: "2026-11-13T10:00:00Z" });
  });

  it("close releases the session and reports what it cost", async () => {
    const calls = server();
    const answer = details(await load({ apiKey: "k" }).specstream_browser_close.execute("c1", { session_id: "bs_1" }));
    expect(calls[0]).toMatchObject({ method: "POST", path: "/v1/browser/sessions/bs_1/release" });
    expect(answer).toMatchObject({ status: "ended", ended_reason: "released", seconds: 42, steps: 3, charged_usd: 0.004167 });
  });
});

describe("client", () => {
  it("turns a refusal into an error with the API's own words", async () => {
    server();
    const client = new BrowserClient({ apiKey: "k" });
    await expect(client.get("bs_missing")).rejects.toThrow("SpecStream answered 404: No session with this id on this account.");
    await expect(client.act(" ", "browser_snapshot")).rejects.toBeInstanceOf(SpecStreamError);
  });

  it("does not send the key anywhere but the Authorization header", async () => {
    const calls = server();
    await new BrowserClient({ apiKey: "ss_live_secret" }).open({ timeoutSeconds: 60, idleTimeoutSeconds: 60 });
    expect(JSON.stringify(calls[0].body)).not.toContain("ss_live_secret");
    expect(calls[0].path).not.toContain("ss_live_secret");
  });
});
