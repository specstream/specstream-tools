import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { SpecStreamExtract, SpecStreamExtractAPIWrapper, SpecStreamSearch } from "../index.js";

const search = {
  kind: "fact",
  answer: { value: "42", page: "https://a.example", seen_at: "2026-11-07T00:00:00Z" },
  rows: [],
  sources: [{ url: "https://a.example", title: "A", cited: true }],
};
const extract = { results: [{ url: "https://a.example", status: "ok", text: "page" }], price_usd: 0.0008 };

const fetchMock = vi.fn();

function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(body), { status }));
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("SPECSTREAM_API_KEY", "");
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("SpecStreamSearch", () => {
  test("calls GET /v1/web-search with the key and returns the data", async () => {
    reply(200, { data: search });
    const tool = new SpecStreamSearch({ specstreamApiKey: "ss_test", passages: true });
    const result = await tool.invoke({ query: " a question " });
    expect(result).toEqual(search);
    const [url, init] = fetchMock.mock.calls[0];
    const parsed = new URL(url);
    expect(parsed.origin + parsed.pathname).toBe("https://api.specstream.ai/v1/web-search");
    expect(parsed.searchParams.get("q")).toBe("a question");
    expect(parsed.searchParams.get("passages")).toBe("true");
    expect(init.method).toBe("GET");
    expect(init.headers.Authorization).toBe("Bearer ss_test");
  });

  test("reads the key from the environment and returns an API error as data", async () => {
    vi.stubEnv("SPECSTREAM_API_KEY", "ss_env");
    reply(402, { error: { message: "Balance is empty." } });
    const result = await new SpecStreamSearch().invoke({ query: "x" });
    expect(result).toEqual({ error: "Error 402: Balance is empty." });
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer ss_env");
  });

  test("throws at construction when there is no key", () => {
    expect(() => new SpecStreamSearch()).toThrow(/SPECSTREAM_API_KEY/);
  });

  test("keeps a custom name and description", () => {
    const tool = new SpecStreamSearch({ specstreamApiKey: "k", name: "web", description: "d" });
    expect([tool.name, tool.description]).toEqual(["web", "d"]);
    expect(new SpecStreamSearch({ specstreamApiKey: "k" }).name).toBe("specstream_search");
  });
});

describe("SpecStreamExtract", () => {
  test("posts at most 20 URLs to /v1/extract", async () => {
    reply(200, { data: extract });
    const tool = new SpecStreamExtract({ specstreamApiKey: "ss_test", apiBaseUrl: "https://example.test/" });
    const urls = Array.from({ length: 20 }, (_, i) => `https://a.example/${i}`);
    expect(await tool.invoke({ urls, format: "text" })).toEqual(extract);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://example.test/v1/extract");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ urls, format: "text" });
  });

  test("the constructor format wins and the wrapper trims the list to 20", async () => {
    reply(200, { data: extract });
    reply(200, { data: extract });
    await new SpecStreamExtract({ specstreamApiKey: "k", format: "markdown" }).invoke({ urls: ["https://a.example"], format: "text" });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).format).toBe("markdown");
    const wrapper = new SpecStreamExtractAPIWrapper({ specstreamApiKey: "k" });
    await wrapper.rawResults({ urls: Array.from({ length: 25 }, (_, i) => `https://a.example/${i}`) });
    expect(JSON.parse(fetchMock.mock.calls[1][1].body).urls).toHaveLength(20);
  });

  test("returns the error message when the call fails", async () => {
    fetchMock.mockResolvedValueOnce(new Response("busy", { status: 503 }));
    const result = await new SpecStreamExtract({ specstreamApiKey: "k" }).invoke({ urls: ["https://a.example"] });
    expect(result).toEqual({ error: "Error 503: Unknown error" });
  });
});
