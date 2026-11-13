import { describe, expect, it } from "vitest";
import { asSchema } from "ai";
import { SpecStreamClient, specstreamTools } from "../src/index.js";

// The web search tool passes the Search API's speed: fast at $1 per 1,000, the API's default when left out.

function recorder() {
  const queries: URLSearchParams[] = [];
  const fetch = (async (input: string | URL | Request) => {
    const url = new URL(String(input));
    expect(url.pathname).toBe("/v1/web-search");
    queries.push(url.searchParams);
    return new Response(JSON.stringify({ data: { kind: "fact", sources: [] } }), { status: 200 });
  }) as typeof globalThis.fetch;
  return { queries, fetch };
}

describe("speed", () => {
  it("sends speed=fast when the model asks for a fast search", async () => {
    const { queries, fetch } = recorder();
    const tools = specstreamTools({ apiKey: "ss_live_test_key", maxPriceUsd: 5, fetch });
    await (tools.specstream_web_search.execute as any)({ q: "capital of Portugal", speed: "fast" }, { toolCallId: "c", messages: [] });
    expect(queries[0].get("speed")).toBe("fast");
  });

  it("leaves speed out so the API's default runs", async () => {
    const { queries, fetch } = recorder();
    await new SpecStreamClient({ apiKey: "ss_live_test_key", fetch }).webSearch("capital of Portugal");
    expect(queries[0].has("speed")).toBe(false);
  });

  it("refuses an unknown speed before any call", async () => {
    const { queries, fetch } = recorder();
    await expect(new SpecStreamClient({ apiKey: "ss_live_test_key", fetch }).webSearch("q", { speed: "turbo" as any })).rejects.toThrow(/speed/);
    expect(queries).toHaveLength(0);
  });

  it("tells the model what a fast search costs", async () => {
    const tool = specstreamTools({ apiKey: "ss_live_test_key", maxPriceUsd: 5 }).specstream_web_search;
    expect(tool.description).toContain("$1 per 1,000");
    const schema = (await asSchema(tool.inputSchema).jsonSchema) as any;
    expect(schema.properties.speed.enum).toEqual(["fast", "default"]);
  });
});
