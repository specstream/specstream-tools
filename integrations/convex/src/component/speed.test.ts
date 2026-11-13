/// <reference types="vite/client" />
import { afterEach, describe, expect, test, vi } from "vitest";
import { api } from "./_generated/api.js";
import { fakeSpecStream, initConvexTest } from "./setup.test.js";

// webSearch passes the Search API's speed: fast at $1 per 1,000, the API's default when left out.

afterEach(() => {
  vi.unstubAllGlobals();
});

const searchRoute = () => ({
  "GET /v1/web-search": { body: { data: { kind: "fact", sources: [] } } },
});

describe("webSearch speed", () => {
  test("sends speed=fast", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream(searchRoute());
    await t.action(api.lib.webSearch, { q: "capital of Portugal", speed: "fast" });
    expect(new URL(calls[0].url).searchParams.get("speed")).toBe("fast");
  });

  test("leaves speed out so the API's default runs", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream(searchRoute());
    await t.action(api.lib.webSearch, { q: "capital of Portugal" });
    expect(new URL(calls[0].url).searchParams.has("speed")).toBe(false);
  });

  test("refuses an unknown speed", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream(searchRoute());
    await expect(
      t.action(api.lib.webSearch, { q: "q", speed: "turbo" as any }),
    ).rejects.toThrow();
    expect(calls).toHaveLength(0);
  });
});
