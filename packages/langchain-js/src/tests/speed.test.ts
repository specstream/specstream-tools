import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { SpecStreamSearch } from "../index.js";

// The search tool passes the Search API's speed: fast at $1 per 1,000, the API's default when left out.

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockImplementation(async () => new Response(JSON.stringify({ data: { kind: "fact", sources: [] } }), { status: 200 }));
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

const sentSpeed = () => new URL(fetchMock.mock.calls[0][0]).searchParams.get("speed");

describe("speed", () => {
  test("a fast tool sends speed=fast", async () => {
    await new SpecStreamSearch({ specstreamApiKey: "ss_test", speed: "fast" }).invoke({ query: "a question" });
    expect(sentSpeed()).toBe("fast");
  });

  test("without a speed the API's default runs", async () => {
    await new SpecStreamSearch({ specstreamApiKey: "ss_test" }).invoke({ query: "a question" });
    expect(sentSpeed()).toBeNull();
  });

  test("an unknown speed is refused", () => {
    expect(() => new SpecStreamSearch({ specstreamApiKey: "ss_test", speed: "turbo" as any })).toThrow(/speed/);
  });
});
