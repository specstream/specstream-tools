import { afterEach, describe, expect, it, vi } from "vitest";
import { asSchema } from "ai";
import { SpecStreamClient, SpecStreamError, specstreamTools, flattenRow } from "../src/index.js";

const KEY = "ss_live_test_key";

function cell(label: string, value: unknown, source?: string) {
  return {
    label,
    value,
    display: value,
    absence: null,
    provenance: source ? { source_url: source, observed_at: "2026-10-14T08:00:00Z" } : null,
  };
}

const ROWS = [
  { entity_id: "e1", ordinal: 1, cells: [cell("Organization", "Clínica Sorriso", "https://sorriso.pt/marcacoes"), cell("Website", "https://sorriso.pt")] },
  { entity_id: "e2", ordinal: 2, cells: [cell("Organization", "Dentes de Lisboa", "https://dentesdelisboa.pt"), { ...cell("Website", null), absence: "Not published" }] },
];

/** The API's flat rows: the page of each value, and of the fact that put the row in the list. */
const FLAT: Record<string, Record<string, unknown>> = {
  e1: { id: "fnd_1:e1", name: "Clínica Sorriso", name_source: "https://sorriso.pt/marcacoes", source_url: "https://filings.example/e1", checked_at: "2026-10-15T09:00:00Z" },
  e2: { id: "fnd_1:e2", name: "Dentes de Lisboa", name_source: "https://dentesdelisboa.pt", source_url: "https://filings.example/e2", checked_at: "2026-10-15T09:00:00Z" },
};
const withFlat = (data: { status: string; rows: typeof ROWS; next_cursor: string | null }) => ({
  ...data,
  flat_rows: data.rows.map((row) => FLAT[row.entity_id]),
});

type Call = { method: string; path: string; body: any; headers: Record<string, string> };

/** Answers like the SpecStream API: the request, its quote, the run, then rows over two polls and two pages. */
class FakeSpecStream {
  calls: Call[] = [];
  polls = 0;
  misses = 0;
  constructor(
    public opts: { maximumCents?: number; runnable?: boolean; existing?: Record<string, unknown> | null } = {},
  ) {}

  fetch = async (input: string | URL | Request, init?: RequestInit): Promise<Response> => {
    const url = new URL(String(input));
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    this.calls.push({ method: init?.method ?? "GET", path: url.pathname, body, headers: init?.headers as Record<string, string> });
    const reply = (data: unknown) => new Response(JSON.stringify({ data }), { status: 200 });
    const notFound = () => new Response("{}", { status: 404, statusText: "Not Found" });
    if (url.pathname.startsWith("/v1/capacity/requests/")) {
      if (this.misses > 0) {
        this.misses -= 1;
        return notFound();
      }
      return this.opts.existing ? reply(this.opts.existing) : notFound();
    }
    if (url.pathname === "/v1/parse") {
      return reply({
        status: this.opts.runnable === false ? "needs_input" : "runnable",
        ast_hash: "a".repeat(64),
        canonical_sentence: "25 dental clinics in Lisbon",
      });
    }
    if (url.pathname === "/v1/capacity/quotes") return reply({ quote_id: "cqt_1", quote_hash: "b".repeat(64), maximum_cents: this.opts.maximumCents ?? 250 });
    if (url.pathname === "/v1/capacity/executions") return reply({ find_id: "fnd_1", state: "running" });
    if (url.pathname === "/v1/finds/fnd_1/rows") {
      if (url.searchParams.get("cursor") === "page-2") return reply(withFlat({ status: "completed", rows: ROWS.slice(1), next_cursor: null }));
      this.polls += 1;
      if (this.polls === 1) return reply(withFlat({ status: "running", rows: [], next_cursor: null }));
      return reply(withFlat({ status: "completed", rows: ROWS.slice(0, 1), next_cursor: "page-2" }));
    }
    throw new Error(`unexpected call ${init?.method} ${url.pathname}`);
  };

  paths() {
    return this.calls.map((call) => call.path);
  }
  body(path: string) {
    return this.calls.find((call) => call.path === path)?.body;
  }
}

function setup(fake: FakeSpecStream, extra: Record<string, unknown> = {}) {
  const tools = specstreamTools({
    apiKey: KEY,
    maxPriceUsd: 5,
    pollIntervalSeconds: 0,
    fetch: fake.fetch as typeof fetch,
    ...extra,
  });
  const run = (name: "specstream_find_list" | "specstream_get_list_results", input: unknown) =>
    (tools[name].execute as any)(input, { toolCallId: "call_1", messages: [], context: {} });
  return { tools, find: (input: unknown) => run("specstream_find_list", input), read: (input: unknown) => run("specstream_get_list_results", input) };
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.useRealTimers();
});

describe("specstream_find_list", () => {
  it("finds a list within the maximum and returns every row", async () => {
    const fake = new FakeSpecStream();
    const result = await setup(fake).find({ request: "Dental clinics in Lisbon with online booking", maxResults: 25 });

    expect(result.status).toBe("completed");
    expect(result.row_count).toBe(2);
    expect(result.list_link).toBe("https://specstream.ai/workspace/collections/fnd_1");
    expect(result.maximum_price_usd).toBe(2.5);
    const [first, second] = result.rows;
    expect(first.Organization).toBe("Clínica Sorriso");
    expect(first.source_url).toBe("https://filings.example/e1");
    expect(first.checked_at).toBe("2026-10-15T09:00:00Z");
    expect(first.name_source).toBe("https://sorriso.pt/marcacoes");
    expect(second.Website).toBe("");
    const run = fake.body("/v1/capacity/executions");
    expect(run.confirm_max_cents).toBe(250);
    expect(run.idempotency_key).toMatch(/^aisdk-[0-9a-f]{32}$/);
    expect(fake.body("/v1/capacity/quotes")).toEqual({ ast_hash: "a".repeat(64), operation: "find", requested_units: 25 });
    expect(fake.body("/v1/parse")).toEqual({ q: "Dental clinics in Lisbon with online booking", locale: "en-US" });
  });

  it("runs nothing when the price is above the maximum", async () => {
    const fake = new FakeSpecStream({ maximumCents: 900 });
    const result = await setup(fake).find({ request: "Dental clinics in Lisbon", maxResults: 25 });

    expect(result.status).toBe("over_maximum");
    expect(result.maximum_price_usd).toBe(9);
    expect(result.message).toContain("$9.00");
    expect(result.message).toContain("$5.00");
    expect(fake.paths()).not.toContain("/v1/capacity/executions");
    expect(fake.paths().some((path) => path.startsWith("/v1/finds/"))).toBe(false);
  });

  it("returns how an unclear request was read, and prices nothing", async () => {
    const fake = new FakeSpecStream({ runnable: false });
    const result = await setup(fake).find({ request: "clinics", maxResults: 25 });

    expect(result.status).toBe("needs_edit");
    expect(result.message).toContain('It read: "25 dental clinics in Lisbon".');
    expect(fake.paths()).not.toContain("/v1/capacity/quotes");
  });

  it("clamps maxResults to 1 through 1000", async () => {
    const high = new FakeSpecStream();
    await setup(high).find({ request: "Dental clinics in Lisbon", maxResults: 50000 });
    expect(high.body("/v1/capacity/quotes").requested_units).toBe(1000);

    const low = new FakeSpecStream();
    await setup(low).find({ request: "Dental clinics in Lisbon", maxResults: -4 });
    expect(low.body("/v1/capacity/quotes").requested_units).toBe(1);

    const unset = new FakeSpecStream();
    await setup(unset).find({ request: "Dental clinics in Lisbon" });
    expect(unset.body("/v1/capacity/quotes").requested_units).toBe(25);
  });

  it("reuses the run a retried step already started", async () => {
    const fake = new FakeSpecStream({ existing: { find_id: "fnd_1", maximum_cents: 250 } });
    const result = await setup(fake).find({ request: "Dental clinics in Lisbon", maxResults: 25 });

    expect(result.row_count).toBe(2);
    expect(fake.paths()).not.toContain("/v1/parse");
    expect(fake.paths()).not.toContain("/v1/capacity/executions");
  });

  it("reuses the previous hour's run after the turn of the hour", async () => {
    const fake = new FakeSpecStream({ existing: { find_id: "fnd_1", maximum_cents: 250 } });
    fake.misses = 1;
    const result = await setup(fake).find({ request: "Dental clinics in Lisbon", maxResults: 25 });

    const lookups = fake.paths().filter((path) => path.startsWith("/v1/capacity/requests/"));
    expect(lookups).toHaveLength(2);
    expect(lookups[0]).not.toBe(lookups[1]);
    expect(result.row_count).toBe(2);
    expect(fake.paths()).not.toContain("/v1/capacity/executions");
  });

  it("derives the run key from the request, the limits and the UTC hour", async () => {
    const at = Date.UTC(2026, 9, 14, 23, 59, 30);
    const make = (now: number) => {
      const fake = new FakeSpecStream();
      const client = new SpecStreamClient({ apiKey: KEY, fetch: fake.fetch as typeof fetch, now: () => now, sleep: async () => {} });
      return { fake, client };
    };
    const a = make(at);
    await a.client.findList("Dental clinics in Lisbon", { maxResults: 25, maxPriceUsd: 5, pollIntervalSeconds: 0 });
    const keyA = a.fake.body("/v1/capacity/executions").idempotency_key;

    const sameHour = make(at - 1000);
    await sameHour.client.findList("Dental clinics in Lisbon", { maxResults: 25, maxPriceUsd: 5, pollIntervalSeconds: 0 });
    expect(sameHour.fake.body("/v1/capacity/executions").idempotency_key).toBe(keyA);

    const nextHour = make(at + 60_000);
    await nextHour.client.findList("Dental clinics in Lisbon", { maxResults: 25, maxPriceUsd: 5, pollIntervalSeconds: 0 });
    expect(nextHour.fake.body("/v1/capacity/executions").idempotency_key).not.toBe(keyA);
    // The retry in the new hour looks up the old hour's key second.
    const lookups = nextHour.fake.calls.filter((call) => call.path.startsWith("/v1/capacity/requests/")).map((call) => call.path);
    expect(lookups[1]).toBe(`/v1/capacity/requests/${keyA}`);

    const otherLimit = make(at);
    await otherLimit.client.findList("Dental clinics in Lisbon", { maxResults: 26, maxPriceUsd: 5, pollIntervalSeconds: 0 });
    expect(otherLimit.fake.body("/v1/capacity/executions").idempotency_key).not.toBe(keyA);
  });

  it("says the list is still running when the wait ends", async () => {
    let clock = 0;
    let polls = 0;
    const fake = new FakeSpecStream();
    const base = fake.fetch;
    fake.fetch = async (input, init) => {
      const url = new URL(String(input));
      if (url.pathname === "/v1/finds/fnd_1/rows") polls += 1;
      if (url.pathname === "/v1/finds/fnd_1/rows") return new Response(JSON.stringify({ data: { status: "running", rows: [], next_cursor: null } }));
      return base(input, init);
    };
    const client = new SpecStreamClient({
      apiKey: KEY,
      fetch: fake.fetch as typeof fetch,
      now: () => clock,
      sleep: async (ms) => {
        clock += ms;
      },
    });
    const result = (await client.findList("Dental clinics in Lisbon", { maxResults: 25, maxPriceUsd: 5, waitSeconds: 9, pollIntervalSeconds: 3 })) as any;
    expect(result.status).toBe("running");
    expect(result.message).toBe("Still running. Call specstream_get_list_results with this list_id for the rest.");
    expect(result.list_id).toBe("fnd_1");
    expect(polls).toBe(4);
  });

  it("stops waiting on a list that failed", async () => {
    const fake = new FakeSpecStream();
    const base = fake.fetch;
    fake.fetch = async (input, init) => {
      const url = new URL(String(input));
      if (url.pathname === "/v1/finds/fnd_1/rows") return new Response(JSON.stringify({ data: { status: "failed", rows: [] } }));
      return base(input, init);
    };
    const result = await setup(fake).find({ request: "Dental clinics in Lisbon", maxResults: 25 });
    expect(result.status).toBe("failed");
    expect(result.message).toBeUndefined();
  });
});

describe("specstream_get_list_results", () => {
  it("follows every page", async () => {
    const fake = new FakeSpecStream();
    fake.polls = 1;
    const result = await setup(fake).read({ listId: " fnd_1 " });

    expect(result.rows.map((row: any) => row.position)).toEqual([1, 2]);
    const pages = fake.calls.filter((call) => call.path === "/v1/finds/fnd_1/rows");
    expect(pages).toHaveLength(2);
  });
});

describe("the model's view of the tools", () => {
  it("sees four tools and cannot set the price", async () => {
    const { tools } = setup(new FakeSpecStream());
    expect(Object.keys(tools)).toEqual(["specstream_web_search", "specstream_extract_pages", "specstream_find_list", "specstream_get_list_results"]);

    const find: any = await asSchema(tools.specstream_find_list.inputSchema).jsonSchema;
    expect(Object.keys(find.properties).sort()).toEqual(["maxResults", "request"]);
    expect(find.required).toEqual(["request"]);
    expect(find.properties.maxResults).toMatchObject({ type: "integer", minimum: 1, maximum: 1000, default: 25 });
    expect(find.properties.request.description).toContain("Dental clinics in Lisbon");

    const read: any = await asSchema(tools.specstream_get_list_results.inputSchema).jsonSchema;
    expect(Object.keys(read.properties)).toEqual(["listId"]);

    expect(tools.specstream_find_list.description).toContain("live web");
    expect(tools.specstream_find_list.description).toContain("over_maximum");
    expect(tools.specstream_find_list.description).toContain("needs_edit");
    expect(tools.specstream_find_list.description).toContain("specstream_get_list_results");
  });

  it("rejects an input that tries to carry a price", async () => {
    const { tools } = setup(new FakeSpecStream());
    const schema = asSchema(tools.specstream_find_list.inputSchema);
    const parsed = await schema.validate!({ request: "Dental clinics", maxResults: 5, maxPriceUsd: 1000 });
    // Unknown keys are dropped, so a model-supplied price never reaches execute.
    expect(parsed.success && "maxPriceUsd" in (parsed.value as object)).toBe(false);
  });
});

describe("the key", () => {
  it("goes in the Authorization header and never into the output", async () => {
    const fake = new FakeSpecStream();
    const result = await setup(fake).find({ request: "Dental clinics in Lisbon", maxResults: 25 });

    expect(fake.calls.length).toBeGreaterThan(0);
    for (const call of fake.calls) {
      expect(call.headers.Authorization).toBe(`Bearer ${KEY}`);
      expect(call.headers["User-Agent"]).toBe("@specstream/ai-sdk/0.4.0");
    }
    expect(JSON.stringify(result)).not.toContain(KEY);
  });

  it("says where to get one when missing", () => {
    vi.stubEnv("SPECSTREAM_API_KEY", "");
    expect(() => specstreamTools({ maxPriceUsd: 5 })).toThrow(/SPECSTREAM_API_KEY.*Agents & API/);
  });

  it("can come from the environment", async () => {
    vi.stubEnv("SPECSTREAM_API_KEY", "ss_live_from_env");
    const fake = new FakeSpecStream();
    const tools = specstreamTools({ maxPriceUsd: 5, pollIntervalSeconds: 0, fetch: fake.fetch as typeof fetch });
    await (tools.specstream_get_list_results.execute as any)({ listId: "fnd_1" }, { toolCallId: "1", messages: [], context: {} });
    expect(fake.calls[0].headers.Authorization).toBe("Bearer ss_live_from_env");
  });

  it("requires a price cap above zero", () => {
    expect(() => specstreamTools({ apiKey: KEY, maxPriceUsd: 0 })).toThrow(/maxPriceUsd/);
    expect(() => specstreamTools({ apiKey: KEY, maxPriceUsd: Number.NaN })).toThrow(/maxPriceUsd/);
  });
});

describe("errors", () => {
  it("names the status and the message the API gave", async () => {
    const client = new SpecStreamClient({
      apiKey: KEY,
      fetch: (async () => new Response(JSON.stringify({ error: { message: "Invalid API key" } }), { status: 401, statusText: "Unauthorized" })) as typeof fetch,
    });
    await expect(client.results("fnd_1")).rejects.toThrow("SpecStream answered 401: Invalid API key");
  });

  it("says when SpecStream can't be reached", async () => {
    const client = new SpecStreamClient({
      apiKey: KEY,
      fetch: (async () => {
        throw new TypeError("fetch failed");
      }) as typeof fetch,
    });
    await expect(client.results("fnd_1")).rejects.toThrow("Couldn't reach SpecStream: fetch failed");
  });

  it("says when the response isn't one it can read", async () => {
    const client = new SpecStreamClient({ apiKey: KEY, fetch: (async () => new Response("<html>")) as typeof fetch });
    await expect(client.results("fnd_1")).rejects.toBeInstanceOf(SpecStreamError);
    await expect(client.results("fnd_1")).rejects.toThrow("SpecStream returned a response this package couldn't read.");
  });

  it("asks for a request and a positive price before calling anything", async () => {
    const fake = new FakeSpecStream();
    const client = new SpecStreamClient({ apiKey: KEY, fetch: fake.fetch as typeof fetch });
    await expect(client.findList("  ", { maxResults: 5, maxPriceUsd: 5 })).rejects.toThrow("Describe the list to find.");
    await expect(client.findList("x", { maxResults: 0, maxPriceUsd: 5 })).rejects.toThrow("maxResults must be 1 or more.");
    await expect(client.findList("x", { maxResults: 5, maxPriceUsd: 0 })).rejects.toThrow("maxPriceUsd must be greater than 0.");
    expect(fake.calls).toHaveLength(0);
  });
});

describe("flattenRow", () => {
  it("renames a column that would overwrite a field every row carries, and takes the pages from the flat row", () => {
    const flat = { id: "fnd_9:e1", title: "Head of sales", title_source: "https://example.com/team", lead_source: "Referral", source_url: "https://example.com/team" };
    const row = flattenRow("fnd_9", {
      ordinal: 3,
      details: [cell("position", "Head of sales", "https://example.com/team"), cell("source_url", "https://other.example"), cell("title_source", "x")],
    }, flat);
    expect(row["position (column)"]).toBe("Head of sales");
    expect(row["source_url (column)"]).toBe("https://other.example");
    expect(row["title_source (column)"]).toBe("x");
    expect(row.title_source).toBe("https://example.com/team");
    expect(row.lead_source).toBeUndefined();
    expect(row.position).toBe(3);
    expect(row.source_url).toBe("https://example.com/team");
    expect(row.list_link).toBe("https://specstream.ai/workspace/collections/fnd_9");
  });

  it("uses details before cells, display before value, and the column id when there is no label", () => {
    const row = flattenRow("fnd_9", {
      ordinal: 1,
      details: [{ column_id: "amount", display: "$28,999,988", value: 28999988, provenance: { source_url: "ftp://nope" } }],
      cells: [cell("ignored", "x")],
    });
    expect(row.amount).toBe("$28,999,988");
    expect(row.ignored).toBeUndefined();
    expect(row.source_url).toBe("");
    expect(row.checked_at).toBe("");
  });
});
