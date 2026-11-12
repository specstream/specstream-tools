import { describe, expect, it } from "vitest";
import { asSchema } from "ai";
import { SpecStreamClient, SpecStreamError, specstreamTools } from "../src/index.js";

const KEY = "ss_live_test_key";
const NOW = Date.parse("2026-11-12T10:20:00Z");

type Call = { method: string; path: string; query: URLSearchParams; body: any };

function schedule(overrides: Record<string, unknown> = {}) {
  return {
    schedule_id: "csc_1",
    scope: { ast_hash: "a".repeat(64), operation: "refresh", parent_find_id: "fnd_1", requested_units: 40 },
    cadence_seconds: 86_400,
    next_due_at: "2026-11-13T10:00:00+00:00",
    per_run_cents: 300,
    period_cents: 9_300,
    monthly_maximum_cents: 9_300,
    valid_until: "2027-11-13T10:00:00+00:00",
    state: "active",
    last_reason: null,
    last_occurrence_at: null,
    last_find_id: null,
    version: 1,
    ...overrides,
  };
}

/** Answers like the SpecStream API's list, quote and schedule calls. */
class FakeSpecStream {
  calls: Call[] = [];
  schedules = [schedule(), schedule({ schedule_id: "csc_2", version: 4 })];
  constructor(public maximumCents = 250) {}

  fetch = async (input: string | URL | Request, init?: RequestInit): Promise<Response> => {
    const url = new URL(String(input));
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    this.calls.push({ method, path: url.pathname, query: url.searchParams, body });
    const reply = (data: unknown) => new Response(JSON.stringify({ data }), { status: 200 });
    if (url.pathname === "/v1/finds/fnd_1") return reply({ find_id: "fnd_1", ast_hash: "a".repeat(64), requested_count: 40, status: "completed" });
    if (url.pathname === "/v1/capacity/quotes") return reply({ quote_id: "cqt_1", quote_hash: "b".repeat(64), maximum_cents: this.maximumCents });
    if (url.pathname === "/v1/capacity/schedules" && method === "POST") return reply(schedule({ per_run_cents: body.per_run_cents }));
    if (url.pathname === "/v1/capacity/schedules" && method === "GET") {
      const after = url.searchParams.get("after");
      return after
        ? reply({ schedules: this.schedules.slice(1), next_after: null })
        : reply({ schedules: this.schedules.slice(0, 1), next_after: "csc_1" });
    }
    if (url.pathname === "/v1/capacity/schedules/csc_2" && method === "PATCH") return reply(schedule({ schedule_id: "csc_2", state: body.state, version: 5 }));
    if (url.pathname === "/v1/capacity/schedules/csc_1/run") return reply({ schedule_id: "csc_1", find_id: "fnd_9", started_at: "2026-11-12T10:20:00+00:00" });
    if (url.pathname === "/v1/capacity/schedules/csc_1/occurrences") {
      return reply({ occurrences: [{ due_at: "2026-11-12T10:00:00+00:00", status: "blocked", reason: "budget_exceeded", find_id: null }], next_before: null });
    }
    throw new Error(`unexpected call ${method} ${url.pathname}`);
  };

  find(method: string, path: string) {
    return this.calls.find((call) => call.method === method && call.path === path);
  }
}

const client = (api: FakeSpecStream) => new SpecStreamClient({ apiKey: KEY, fetch: api.fetch, now: () => NOW });

describe("monitorList", () => {
  it("prices one refresh of the list and saves a schedule within the limits", async () => {
    const api = new FakeSpecStream(250);
    const monitor = await client(api).monitorList("fnd_1", { every: "day", maxPricePerRunUsd: 3 });

    const scope = { ast_hash: "a".repeat(64), operation: "refresh", parent_find_id: "fnd_1", requested_units: 40 };
    expect(api.find("POST", "/v1/capacity/quotes")?.body).toEqual(scope);
    const saved = api.find("POST", "/v1/capacity/schedules")?.body;
    expect(saved).toMatchObject({
      scope,
      cadence_seconds: 86_400,
      first_due_at: "2026-11-13T10:00:00.000Z",
      per_run_cents: 300,
      period_cents: 300 * 31,
      valid_until: "2027-11-13T10:00:00.000Z",
    });
    expect(saved.idempotency_key).toMatch(/^aisdk-monitor-[0-9a-f]{32}$/);
    expect(monitor).toMatchObject({ status: "saved", monitor_id: "csc_1", list_id: "fnd_1", state: "active", max_price_per_run_usd: 3, max_price_per_month_usd: 93 });
    expect(monitor.status === "saved" && monitor.list_link).toBe("https://specstream.ai/workspace/collections/fnd_1");
  });

  it("checks a list in a project inside that project", async () => {
    const api = new FakeSpecStream();
    const plain = api.fetch;
    api.fetch = async (input, init) =>
      new URL(String(input)).pathname === "/v1/finds/fnd_1"
        ? new Response(JSON.stringify({ data: { ast_hash: "a".repeat(64), requested_count: 40, project_id: "prj_7" } }), { status: 200 })
        : plain(input, init);
    await client(api).monitorList("fnd_1", { maxPricePerRunUsd: 3 });
    expect(api.find("POST", "/v1/capacity/schedules")?.body.scope.project_id).toBe("prj_7");
  });

  it("saves nothing when one check costs more than the maximum per check", async () => {
    const api = new FakeSpecStream(450);
    const result = await client(api).monitorList("fnd_1", { maxPricePerRunUsd: 3 });
    expect(result).toMatchObject({ status: "over_maximum", list_id: "fnd_1", maximum_price_usd: 4.5 });
    expect(api.find("POST", "/v1/capacity/schedules")).toBeUndefined();
  });

  it("sends the same schedule and key when a step is retried within the hour", async () => {
    const api = new FakeSpecStream();
    await new SpecStreamClient({ apiKey: KEY, fetch: api.fetch, now: () => NOW }).monitorList("fnd_1", { maxPricePerRunUsd: 3 });
    await new SpecStreamClient({ apiKey: KEY, fetch: api.fetch, now: () => NOW + 30 * 60_000 }).monitorList("fnd_1", { maxPricePerRunUsd: 3 });
    const bodies = api.calls.filter((call) => call.method === "POST" && call.path === "/v1/capacity/schedules").map((call) => call.body);
    expect(bodies).toHaveLength(2);
    expect(bodies[1]).toEqual(bodies[0]);
  });

  it.each([
    [{ maxPricePerRunUsd: 0 }, "maxPricePerRunUsd"],
    [{ maxPricePerRunUsd: 3, maxPricePerMonthUsd: 2 }, "maxPricePerMonthUsd"],
    [{ maxPricePerRunUsd: 3, every: "minute" as never }, "every"],
    [{ maxPricePerRunUsd: 3, firstRunAt: new Date(NOW + 7_200_000), until: new Date(NOW) }, "until"],
  ])("refuses limits that can't hold before calling anything (%#)", async (options, word) => {
    const api = new FakeSpecStream();
    await expect(client(api).monitorList("fnd_1", options)).rejects.toThrow(word);
    expect(api.calls).toHaveLength(0);
  });
});

describe("the other monitor calls", () => {
  it("lists every monitor across pages", async () => {
    const monitors = await client(new FakeSpecStream()).monitors();
    expect(monitors.map((monitor) => monitor.monitor_id)).toEqual(["csc_1", "csc_2"]);
  });

  it("pauses with the version it just read", async () => {
    const api = new FakeSpecStream();
    const paused = await client(api).pauseMonitor("csc_2");
    expect(api.find("PATCH", "/v1/capacity/schedules/csc_2")?.body).toEqual({ expected_version: 4, state: "paused" });
    expect(paused).toMatchObject({ monitor_id: "csc_2", state: "paused", version: 5 });
  });

  it("names a monitor the account doesn't have", async () => {
    await expect(client(new FakeSpecStream()).deleteMonitor("csc_404")).rejects.toThrow(SpecStreamError);
  });

  it("runs a check now and reads the checks", async () => {
    const api = new FakeSpecStream();
    expect(await client(api).runMonitorNow("csc_1")).toEqual({ monitor_id: "csc_1", list_id: "fnd_9", started_at: "2026-11-12T10:20:00+00:00" });
    expect(await client(api).monitorRuns("csc_1")).toEqual([{ due_at: "2026-11-12T10:00:00+00:00", status: "blocked", reason: "budget_exceeded", list_id: null }]);
  });
});

describe("the monitor tools", () => {
  it("are only there when the code sets a maximum per check, and the model can't set a price", async () => {
    const api = new FakeSpecStream();
    expect(Object.keys(specstreamTools({ maxPriceUsd: 5, apiKey: KEY, fetch: api.fetch }))).not.toContain("specstream_monitor_list");
    const tools = specstreamTools({ maxPriceUsd: 5, apiKey: KEY, fetch: api.fetch, monitorMaxPricePerRunUsd: 3 });
    expect(Object.keys(tools)).toContain("specstream_list_monitors");
    const input = (await asSchema(tools.specstream_monitor_list.inputSchema).jsonSchema) as { properties: Record<string, unknown> };
    expect(Object.keys(input.properties).sort()).toEqual(["every", "listId"]);

    const saved = await (tools.specstream_monitor_list.execute as any)({ listId: "fnd_1", every: "week" }, { toolCallId: "t1", messages: [], context: {} });
    expect(saved).toMatchObject({ status: "saved", monitor_id: "csc_1" });
    expect(api.find("POST", "/v1/capacity/schedules")?.body).toMatchObject({ cadence_seconds: 604_800, per_run_cents: 300, period_cents: 1_500 });
  });

  it("refuses a maximum per check that isn't above zero", () => {
    expect(() => specstreamTools({ maxPriceUsd: 5, apiKey: KEY, monitorMaxPricePerRunUsd: 0 })).toThrow("monitorMaxPricePerRunUsd");
  });
});
