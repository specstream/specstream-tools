import { describe, expect, it } from "vitest";
import { SpecStreamClient, flattenRow } from "../src/client.js";
import { cell, listServer, mockFetch } from "./mock.js";

const options = { maxResults: 25, maxPriceUsd: 5, pollIntervalSeconds: 0 };
const client = (fetch: typeof globalThis.fetch, extra: Record<string, unknown> = {}) =>
  new SpecStreamClient({ apiKey: "ss_live_test", fetch, sleep: async () => {}, now: () => Date.parse("2026-10-15T10:30:00Z"), ...extra });

describe("flattenRow", () => {
  it("takes the pages from the API's flat row and renames columns that collide with row fields", () => {
    const flat = {
      id: "fnd_1:e1",
      name: "Acme",
      name_source: "https://acme.example/about",
      lead_source: "Referral",
      source_url: "https://www.sec.gov/filing",
      checked_at: "2026-10-16T00:00:00Z",
    };
    const row = flattenRow("fnd_1", {
      ordinal: 3,
      details: [cell("source_url", "x"), cell("name_source", "y"), cell("Name", "Acme", "https://acme.example/about"), { label: "Phone", absence: "not_found" }],
    }, flat);
    expect(row.lead_source).toBeUndefined();
    expect(row).toMatchObject({
      list_id: "fnd_1",
      position: 3,
      Name: "Acme",
      Phone: "",
      "source_url (column)": "x",
      "name_source (column)": "y",
      name_source: "https://acme.example/about",
      source_url: "https://www.sec.gov/filing",
      checked_at: "2026-10-16T00:00:00Z",
      list_link: "https://specstream.ai/workspace/collections/fnd_1",
    });
  });
});

describe("findList", () => {
  it("prices the request, runs it within the ceiling and returns rows with their sources", async () => {
    const server = listServer({ maximumCents: 250 });
    const result = await client(server.fetch).findList("dental clinics in Lisbon", options);

    expect(result).toMatchObject({ state: "completed", list_id: "fnd_new", row_count: 1, maximum_price_usd: 2.5 });
    if (!("rows" in result)) throw new Error("expected rows");
    expect(result.rows[0]).toMatchObject({ Name: "Acme Dental", name_source: "https://example.org/a", source_url: "https://example.org/filing" });

    const paths = server.calls.map((call) => `${call.method} ${call.path.split("?")[0]}`);
    expect(paths.filter((p) => p.startsWith("POST"))).toEqual(["POST /v1/parse", "POST /v1/capacity/quotes", "POST /v1/capacity/executions"]);
    const quote = server.calls.find((call) => call.path === "/v1/capacity/quotes");
    expect(quote?.body).toMatchObject({ ast_hash: "a".repeat(64), operation: "find", requested_units: 25 });
    const execution = server.calls.find((call) => call.path === "/v1/capacity/executions");
    expect(execution?.body).toMatchObject({ quote_id: "q1", confirm_max_cents: 250 });
    expect(execution?.headers.Authorization).toBe("Bearer ss_live_test");
  });

  it("starts nothing when the quoted maximum is above the ceiling", async () => {
    const server = listServer({ maximumCents: 900 });
    const result = await client(server.fetch).findList("dental clinics in Lisbon", { ...options, maxPriceUsd: 5 });

    expect(result).toMatchObject({ state: "over_maximum", maximum_price_usd: 9 });
    expect(server.calls.some((call) => call.path === "/v1/capacity/executions")).toBe(false);
  });

  it("runs a list that costs exactly the ceiling", async () => {
    const server = listServer({ maximumCents: 500 });
    const result = await client(server.fetch).findList("dental clinics in Lisbon", { ...options, maxPriceUsd: 5 });
    expect(result.state).toBe("completed");
  });

  it("asks for a clearer request when the reading is not runnable", async () => {
    const server = listServer({ runnable: false });
    const result = await client(server.fetch).findList("things", options);

    expect(result.state).toBe("needs_edit");
    expect(server.calls.some((call) => call.path === "/v1/capacity/quotes")).toBe(false);
  });

  it("sends the same idempotency key for a retry and a different one for different limits", async () => {
    const keyOf = async (request: string, extra: Partial<typeof options>) => {
      const server = listServer();
      await client(server.fetch).findList(request, { ...options, ...extra });
      return server.calls.find((call) => call.path === "/v1/capacity/executions")?.body?.idempotency_key;
    };
    const first = await keyOf("dental clinics in Lisbon", {});
    expect(first).toMatch(/^openclaw-[0-9a-f]{32}$/);
    expect(await keyOf("dental clinics in Lisbon", {})).toBe(first);
    expect(await keyOf("dental clinics in Lisbon", { maxResults: 50 })).not.toBe(first);
    expect(await keyOf("dental clinics in Porto", {})).not.toBe(first);
  });

  it("reaches the run it already started instead of buying the list again", async () => {
    const server = listServer({ existing: true });
    const result = await client(server.fetch).findList("dental clinics in Lisbon", options);

    expect(result).toMatchObject({ list_id: "fnd_old", maximum_price_usd: 2 });
    expect(server.calls.filter((call) => call.method === "POST")).toEqual([]);
  });

  it("finds a run started in the previous hour", async () => {
    const seen: string[] = [];
    const server = mockFetch((call) => {
      if (call.path.startsWith("/v1/capacity/requests/")) {
        seen.push(call.path);
        return seen.length === 2 ? { data: { find_id: "fnd_prev", maximum_cents: 100 } } : undefined;
      }
      if (call.path.startsWith("/v1/finds/")) return { data: { status: "completed", rows: [] } };
      return undefined;
    });
    const result = await client(server.fetch).findList("dental clinics in Lisbon", options);

    expect(result).toMatchObject({ list_id: "fnd_prev" });
    expect(new Set(seen).size).toBe(2);
  });

  it("returns the rows so far with a pointer to the free read when the list is still running", async () => {
    const server = listServer({ status: "running" });
    let time = Date.parse("2026-10-15T10:30:00Z");
    const result = await client(server.fetch, { now: () => (time += 100_000) }).findList("dental clinics in Lisbon", {
      ...options,
      waitSeconds: 200,
    });

    expect(result.state).toBe("running");
    expect("message" in result && result.message).toContain("specstream_get_list_rows");
  });

  it("explains an API refusal", async () => {
    const server = mockFetch((call) =>
      call.path === "/v1/parse" ? { status: 401, error: { message: "Invalid API key" } } : undefined,
    );
    await expect(client(server.fetch).findList("dental clinics in Lisbon", options)).rejects.toThrow(
      "SpecStream answered 401: Invalid API key",
    );
  });

  it("rejects limits it cannot honor before any call", async () => {
    const server = listServer();
    await expect(client(server.fetch).findList("x", { ...options, maxResults: 0 })).rejects.toThrow("max_results");
    await expect(client(server.fetch).findList("x", { ...options, maxPriceUsd: 0 })).rejects.toThrow("ceiling");
    await expect(client(server.fetch).findList("  ", options)).rejects.toThrow("Describe the list");
    expect(server.calls).toEqual([]);
  });
});

describe("results", () => {
  it("follows the pages and reads for free", async () => {
    const server = mockFetch((call) => {
      const first = !call.path.includes("cursor=");
      return {
        data: {
          status: "completed",
          rows: [{ ordinal: first ? 1 : 2, details: [cell("Name", first ? "A" : "B")] }],
          next_cursor: first ? "c2" : null,
        },
      };
    });
    const list = await client(server.fetch).results("fnd_9");

    expect(list.rows.map((row) => row.Name)).toEqual(["A", "B"]);
    expect(list).toMatchObject({ state: "completed", row_count: 2 });
    expect(server.calls.every((call) => call.method === "GET")).toBe(true);
  });
});

describe("webSearch and extractPages", () => {
  it("calls GET /v1/web-search with q and optional passages", async () => {
    const server = mockFetch((call) =>
      call.path.startsWith("/v1/web-search?")
        ? { data: { kind: "fact", answer: { value: "Paris", page: "https://example.org", seen_at: "2026-11-05T12:00:00Z" }, rows: [], sources: [] } }
        : undefined,
    );
    const res = await client(server.fetch).webSearch("capital of France", { passages: true });
    expect(res).toMatchObject({ kind: "fact", answer: { value: "Paris" } });
    expect(server.calls[0]).toMatchObject({ method: "GET", path: "/v1/web-search?q=capital+of+France&passages=true" });
  });

  it("calls POST /v1/extract with urls and format", async () => {
    const server = mockFetch((call) =>
      call.path === "/v1/extract"
        ? { data: { request_id: "r1", results: [{ url: "https://example.org", status: "ok", text: "Hello", title: "Example" }], price_usd: 0.0008 } }
        : undefined,
    );
    const res = await client(server.fetch).extractPages([" https://example.org "], { format: "markdown" });
    expect(res).toMatchObject({ request_id: "r1", price_usd: 0.0008 });
    expect(server.calls[0]).toMatchObject({ method: "POST", path: "/v1/extract", body: { urls: ["https://example.org"], format: "markdown" } });
  });
});
