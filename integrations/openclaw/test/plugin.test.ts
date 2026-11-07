import { afterEach, describe, expect, it, vi } from "vitest";
import { getToolPluginMetadata } from "openclaw/plugin-sdk/tool-plugin";
import entry from "../src/index.js";
import { effectiveCeiling, resolveConfig } from "../src/config.js";
import { listServer } from "./mock.js";

type Tool = { name: string; parameters: { required?: string[] }; execute: (id: string, params: any, signal?: AbortSignal) => Promise<any> };

/** Registers the plugin against a stand-in API and returns the tools it registered. */
function load(pluginConfig: Record<string, unknown>): Record<string, Tool> {
  const tools: Record<string, Tool> = {};
  (entry as any).register({
    pluginConfig,
    registerTool: (tool: Tool) => {
      tools[tool.name] = tool;
    },
  });
  return tools;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("manifest metadata", () => {
  it("declares the four tools", () => {
    expect(getToolPluginMetadata(entry)?.tools.map((tool) => tool.name)).toEqual([
      "specstream_web_search",
      "specstream_extract_pages",
      "specstream_find_list",
      "specstream_get_list_rows",
    ]);
  });
});

describe("config", () => {
  it("reads the key from the environment when the config has none", () => {
    expect(resolveConfig({}, { SPECSTREAM_API_KEY: " ss_live_env " } as NodeJS.ProcessEnv)).toMatchObject({ apiKey: "ss_live_env", maxPriceUsd: 5 });
  });

  it("prefers the configured key and fails clearly without any key", () => {
    expect(resolveConfig({ apiKey: "ss_live_cfg", maxPriceUsd: 2 }, {} as NodeJS.ProcessEnv)).toMatchObject({ apiKey: "ss_live_cfg", maxPriceUsd: 2 });
    expect(() => resolveConfig({}, {} as NodeJS.ProcessEnv)).toThrow("SPECSTREAM_API_KEY");
  });

  it("lets a call lower the ceiling and never raise it", () => {
    expect(effectiveCeiling(5, 2)).toBe(2);
    expect(effectiveCeiling(5, 50)).toBe(5);
    expect(effectiveCeiling(5, undefined)).toBe(5);
    expect(effectiveCeiling(5, -1)).toBe(5);
  });
});

describe("tools", () => {
  it("find_list runs a list within the configured ceiling and returns its rows", async () => {
    const server = listServer({ maximumCents: 400 });
    vi.stubGlobal("fetch", server.fetch);
    const tools = load({ apiKey: "ss_live_cfg", maxPriceUsd: 5, waitSeconds: 10 });

    const result = await tools.specstream_find_list.execute("call-1", { request: "dental clinics in Lisbon", max_results: 10 });

    expect(result.details).toMatchObject({ state: "completed", list_id: "fnd_new" });
    expect(result.details.rows[0].source_url).toBe("https://example.org/filing");
    expect(server.calls.find((call) => call.path === "/v1/capacity/quotes")?.body?.requested_units).toBe(10);
  });

  it("find_list does not run when the model asks for a lower ceiling than the quote", async () => {
    const server = listServer({ maximumCents: 400 });
    vi.stubGlobal("fetch", server.fetch);
    const tools = load({ apiKey: "ss_live_cfg", maxPriceUsd: 5 });

    const result = await tools.specstream_find_list.execute("call-1", { request: "dental clinics in Lisbon", max_price_usd: 3 });

    expect(result.details.state).toBe("over_maximum");
    expect(server.calls.some((call) => call.path === "/v1/capacity/executions")).toBe(false);
  });

  it("find_list ignores a model ceiling above the configured one", async () => {
    const server = listServer({ maximumCents: 800 });
    vi.stubGlobal("fetch", server.fetch);
    const tools = load({ apiKey: "ss_live_cfg", maxPriceUsd: 5 });

    const result = await tools.specstream_find_list.execute("call-1", { request: "dental clinics in Lisbon", max_price_usd: 100 });

    expect(result.details.state).toBe("over_maximum");
    expect(server.calls.some((call) => call.path === "/v1/capacity/executions")).toBe(false);
  });

  it("uses the environment key when the config has none", async () => {
    const server = listServer();
    vi.stubGlobal("fetch", server.fetch);
    vi.stubEnv("SPECSTREAM_API_KEY", "ss_live_env");
    const tools = load({});

    await tools.specstream_find_list.execute("call-1", { request: "dental clinics in Lisbon" });

    expect(server.calls[0].headers.Authorization).toBe("Bearer ss_live_env");
  });

  it("refuses to call SpecStream without a key", async () => {
    const server = listServer();
    vi.stubGlobal("fetch", server.fetch);
    vi.stubEnv("SPECSTREAM_API_KEY", "");
    const tools = load({});

    await expect(tools.specstream_find_list.execute("call-1", { request: "x" })).rejects.toThrow("no API key");
    expect(server.calls).toEqual([]);
  });

  it("get_list_rows reads a list without any POST", async () => {
    const server = listServer();
    vi.stubGlobal("fetch", server.fetch);
    const tools = load({ apiKey: "ss_live_cfg" });

    const result = await tools.specstream_get_list_rows.execute("call-2", { list_id: " fnd_new " });

    expect(result.details).toMatchObject({ list_id: "fnd_new", row_count: 1, state: "completed" });
    expect(server.calls.map((call) => call.method)).toEqual(["GET"]);
    expect(server.calls[0].path).toContain("/v1/finds/fnd_new/rows");
  });

  it("runs web_search and extract_pages tools and registers web search and fetch providers", async () => {
    const server = listServer();
    vi.stubGlobal("fetch", server.fetch);
    let searchProvider: Record<string, unknown> | undefined;
    let fetchProvider: Record<string, unknown> | undefined;
    const tools: Record<string, Tool> = {};
    entry.register({
      pluginConfig: { apiKey: "ss_live_cfg" },
      registerTool: (tool: Tool) => {
        tools[tool.name] = tool;
      },
      registerWebSearchProvider: (p: Record<string, unknown>) => {
        searchProvider = p;
      },
      registerWebFetchProvider: (p: Record<string, unknown>) => {
        fetchProvider = p;
      },
    } as Parameters<typeof entry.register>[0]);

    expect(searchProvider).toMatchObject({ id: "specstream", label: "SpecStream Search" });
    expect(fetchProvider).toMatchObject({ id: "specstream", label: "SpecStream Extract" });
    expect(Object.keys(tools)).toEqual([
      "specstream_web_search",
      "specstream_extract_pages",
      "specstream_find_list",
      "specstream_get_list_rows",
    ]);
  });
});
