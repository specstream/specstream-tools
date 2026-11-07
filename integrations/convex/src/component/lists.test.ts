/// <reference types="vite/client" />
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { api, internal } from "./_generated/api.js";
import {
  TEST_API_KEY,
  TEST_WEBHOOK_SECRET,
  executionReply,
  fakeSpecStream,
  findReply,
  initConvexTest,
  parseReply,
  quoteReply,
  rowOf,
  rowsReply,
} from "./setup.test.js";
import { sign } from "./signature.js";

const houston = rowOf(
  "ent_1",
  1,
  "Houston Food Bank",
  "https://houstonfoodbank.org/about",
);
const austin = rowOf(
  "ent_2",
  2,
  "Central Texas Food Bank",
  "https://centraltexasfoodbank.org",
);

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  delete process.env.SPECSTREAM_WEBHOOK_SECRET;
});

const happyRoutes = () => ({
  "POST /v1/parse": parseReply(),
  "POST /v1/capacity/quotes": quoteReply(),
  "POST /v1/capacity/executions": executionReply(),
});

describe("read", () => {
  test("reads a request and reports the stated row count", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({ "POST /v1/parse": parseReply() });

    const reading = await t.action(api.lib.read, {
      request: "food banks in Texas, 100 of them",
    });

    expect(reading).toEqual({
      status: "runnable",
      astHash: "a".repeat(64),
      canonicalSentence: "Food banks in Texas",
      statedRows: 100,
      rowsInferred: false,
    });
    expect(calls[0].url).toBe("https://api.specstream.ai/v1/parse");
    expect(calls[0].headers.Authorization).toBe(`Bearer ${TEST_API_KEY}`);
    expect(calls[0].body).toEqual({
      q: "food banks in Texas, 100 of them",
      locale: "en-US",
    });
  });

  test("an empty request is refused before any call", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({});
    await expect(t.action(api.lib.read, { request: "  " })).rejects.toThrow();
    expect(calls).toHaveLength(0);
  });

  test("a revoked key reads as a plain message", async () => {
    const t = initConvexTest();
    fakeSpecStream({
      "POST /v1/parse": {
        status: 401,
        body: { error: { code: "unauthorized", message: "no" } },
      },
    });
    await expect(
      t.action(api.lib.read, { request: "food banks in Texas" }),
    ).rejects.toThrow(/did not accept the API key/);
  });

  test("retries a rate limit, then succeeds", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({
      "POST /v1/parse": (_call, index) =>
        index === 0
          ? { status: 429, body: { error: { code: "rate" } } }
          : parseReply(),
    });
    const reading = await t.action(api.lib.read, {
      request: "food banks in Texas",
    });
    expect(reading.status).toBe("runnable");
    expect(calls).toHaveLength(2);
  });
});

describe("webSearch and extractPages", () => {
  test("search sends the question and passes the data through", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({
      "GET /v1/web-search": { body: { data: { answer: "42", sources: [] } } },
    });
    const out = await t.action(api.lib.webSearch, { q: " height of K2 ", passages: true });
    expect(out.answer).toBe("42");
    expect(calls[0].url).toContain("q=height+of+K2");
    expect(calls[0].url).toContain("passages=true");
    await expect(t.action(api.lib.webSearch, { q: "  " })).rejects.toThrow(/between 1 and 2,000/);
  });

  test("extract posts 1 to 20 trimmed URLs", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({
      "POST /v1/extract": { body: { data: { pages: [{ url: "https://a.test" }] } } },
    });
    const out = await t.action(api.lib.extractPages, {
      urls: [" https://a.test ", ""],
      format: "text",
    });
    expect(out.pages).toHaveLength(1);
    expect(calls[0].body).toEqual({ urls: ["https://a.test"], format: "text" });
    await expect(t.action(api.lib.extractPages, { urls: [] })).rejects.toThrow(/1 to 20/);
    const many = Array.from({ length: 21 }, (_, i) => `https://x${i}.test`);
    await expect(t.action(api.lib.extractPages, { urls: many })).rejects.toThrow(/1 to 20/);
  });
});

describe("account", () => {
  test("returns the email and the balance", async () => {
    const t = initConvexTest();
    fakeSpecStream({
      "GET /v1/me": {
        body: { data: { email: "dev@example.com", guest: false } },
      },
      "GET /v1/capacity/balance": { body: { data: { available_cents: 4200 } } },
    });
    expect(await t.action(api.lib.account, {})).toEqual({
      email: "dev@example.com",
      availableCents: 4200,
    });
  });
});

describe("registerWebhook", () => {
  test("registers find.completed and returns the secret", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({
      "POST /v1/account/webhooks": {
        body: {
          data: {
            hook_id: "hook_1",
            event_name: "find.completed",
            events: ["find.completed"],
            secret: "whsec_x",
          },
        },
      },
    });
    const hook = await t.action(api.lib.registerWebhook, {
      url: "https://app.convex.site/specstream/webhook",
    });
    expect(hook).toEqual({ hookId: "hook_1", secret: "whsec_x" });
    expect(calls[0].body).toEqual({
      url: "https://app.convex.site/specstream/webhook",
      events: ["find.completed"],
    });
  });
});

describe("quote and approve", () => {
  test("a request that can't be priced says what SpecStream read, and prices nothing", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({
      "POST /v1/parse": parseReply({
        status: "needs_edit",
        ast_hash: null,
        canonical_sentence: "Food banks",
      }),
    });
    const result = await t.action(api.lists.quote, {
      request: "food banks",
      rows: 50,
    });
    expect(result).toMatchObject({
      status: "needs_edit",
      readAs: "Food banks",
    });
    expect(calls.map((c) => c.path)).toEqual(["/v1/parse"]);
  });

  test("a quote keeps the price and hides SpecStream's signature", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream(happyRoutes());
    const result = await t.action(api.lists.quote, {
      request: "food banks in Texas",
      rows: 100,
    });
    if (result.status !== "quoted") throw new Error("expected a quote");
    expect(result).toMatchObject({
      maximumCents: 1500,
      unitCents: 15,
      currency: "USD",
      rows: 100,
      canAuthorize: true,
    });
    expect(calls[1].body).toEqual({
      ast_hash: "a".repeat(64),
      operation: "find",
      requested_units: 100,
    });
    const saved = await t.query(api.lists.getQuote, {
      quoteId: result.quoteId,
    });
    expect(saved).toMatchObject({ maximumCents: 1500 });
    expect(saved).not.toHaveProperty("quoteHash");
    expect(saved).not.toHaveProperty("astHash");
  });

  test("rows outside 1 to 1000 are refused", async () => {
    const t = initConvexTest();
    fakeSpecStream(happyRoutes());
    await expect(
      t.action(api.lists.quote, { request: "x", rows: 0 }),
    ).rejects.toThrow(/1 to 1000/);
    await expect(
      t.action(api.lists.quote, { request: "x", rows: 1001 }),
    ).rejects.toThrow(/1 to 1000/);
  });

  test("approving a different maximum runs nothing", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream(happyRoutes());
    const result = await t.action(api.lists.quote, {
      request: "food banks in Texas",
      rows: 100,
    });
    if (result.status !== "quoted") throw new Error("expected a quote");

    await expect(
      t.action(api.lists.approve, {
        quoteId: result.quoteId,
        confirmMaxCents: 9999,
      }),
    ).rejects.toThrow(/must equal the quoted maximum/);
    expect(calls.some((c) => c.path === "/v1/capacity/executions")).toBe(false);
  });

  test("an expired price runs nothing", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({
      ...happyRoutes(),
      "POST /v1/capacity/quotes": quoteReply({
        expires_at: new Date(Date.now() - 1000).toISOString(),
      }),
    });
    const result = await t.action(api.lists.quote, {
      request: "food banks in Texas",
      rows: 100,
    });
    if (result.status !== "quoted") throw new Error("expected a quote");
    await expect(
      t.action(api.lists.approve, {
        quoteId: result.quoteId,
        confirmMaxCents: 1500,
      }),
    ).rejects.toThrow(/expired/);
    expect(calls.some((c) => c.path === "/v1/capacity/executions")).toBe(false);
  });

  test("a quote SpecStream won't authorize runs nothing", async () => {
    const t = initConvexTest();
    fakeSpecStream({
      ...happyRoutes(),
      "POST /v1/capacity/quotes": quoteReply({ can_authorize: false }),
    });
    const result = await t.action(api.lists.quote, {
      request: "food banks in Texas",
      rows: 100,
    });
    if (result.status !== "quoted") throw new Error("expected a quote");
    await expect(
      t.action(api.lists.approve, {
        quoteId: result.quoteId,
        confirmMaxCents: 1500,
      }),
    ).rejects.toThrow(/can't start/);
  });

  test("approving sends the exact quote and maximum, and approving twice starts one list", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({
      ...happyRoutes(),
      "GET /v1/finds/fnd_1": findReply("running", 0),
    });
    const result = await t.action(api.lists.quote, {
      request: "food banks in Texas",
      rows: 100,
    });
    if (result.status !== "quoted") throw new Error("expected a quote");

    const first = await t.action(api.lists.approve, {
      quoteId: result.quoteId,
      confirmMaxCents: 1500,
    });
    const second = await t.action(api.lists.approve, {
      quoteId: result.quoteId,
      confirmMaxCents: 1500,
    });

    expect(first).toMatchObject({
      status: "started",
      specstreamListId: "fnd_1",
      link: "https://specstream.ai/workspace/collections/fnd_1",
      maximumCents: 1500,
    });
    expect(second.listId).toBe(first.listId);
    const executions = calls.filter(
      (c) => c.path === "/v1/capacity/executions",
    );
    expect(executions).toHaveLength(1);
    expect(executions[0].body).toEqual({
      quote_id: "qte_1",
      quote_hash: "a".repeat(64),
      confirm_max_cents: 1500,
      idempotency_key: "convex-qte_1",
    });
  });

  test("findList stops above the maximum and spends nothing", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream(happyRoutes());
    const result = await t.action(api.lists.findList, {
      request: "food banks in Texas",
      rows: 100,
      maxCents: 1000,
    });
    expect(result).toMatchObject({
      status: "over_maximum",
      maximumCents: 1500,
    });
    expect(calls.some((c) => c.path === "/v1/capacity/executions")).toBe(false);
  });

  test("findList within the maximum starts the list with the caller's key", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({
      ...happyRoutes(),
      "GET /v1/finds/fnd_1": findReply("running", 0),
    });
    const result = await t.action(api.lists.findList, {
      request: "food banks in Texas",
      rows: 100,
      maxCents: 2000,
      idempotencyKey: "report-42",
    });
    expect(result).toMatchObject({
      status: "started",
      specstreamListId: "fnd_1",
    });
    const execution = calls.find((c) => c.path === "/v1/capacity/executions")!;
    expect(execution.body.idempotency_key).toBe("convex-report-42");
    expect(execution.body.confirm_max_cents).toBe(1500);
  });
});

describe("following a list", () => {
  async function start(
    t: ReturnType<typeof initConvexTest>,
    mode?: "poll" | "webhook",
  ) {
    const result = await t.action(api.lists.findList, {
      request: "food banks in Texas",
      rows: 100,
      maxCents: 2000,
      mode,
    });
    if (result.status !== "started") throw new Error("expected start");
    return result.listId;
  }

  test("stores rows as they arrive and finishes with the page behind each row", async () => {
    const t = initConvexTest();
    fakeSpecStream({
      ...happyRoutes(),
      "GET /v1/finds/fnd_1": (_call, index) =>
        index === 0 ? findReply("running", 1) : findReply("completed", 2),
      "GET /v1/finds/fnd_1/rows": (_call, index) =>
        index === 0
          ? rowsReply([houston], "running")
          : rowsReply([houston, austin]),
    });

    const listId = await start(t);
    await t.finishAllScheduledFunctions(vi.runAllTimers);

    const list = await t.query(api.lists.get, { listId });
    expect(list).toMatchObject({
      status: "completed",
      finalized: true,
      acceptedCount: 2,
      rowCount: 2,
      requestedCount: 100,
    });
    const page = await t.query(api.lists.listRows, {
      listId,
      paginationOpts: { numItems: 10, cursor: null },
    });
    expect(page.page.map((row: any) => row.entityId)).toEqual([
      "ent_1",
      "ent_2",
    ]);
    expect(page.page[0].sourceUrl).toBe("https://houstonfoodbank.org/about");
    expect(page.page[0].cells[0].display).toBe("Houston Food Bank");
    const row = await t.query(api.lists.getRow, { listId, entityId: "ent_2" });
    expect(row?.ordinal).toBe(2);
  });

  test("reading rows again never duplicates them", async () => {
    const t = initConvexTest();
    fakeSpecStream({
      ...happyRoutes(),
      "GET /v1/finds/fnd_1": (_call, index) =>
        index < 2 ? findReply("running", index + 1) : findReply("completed", 2),
      "GET /v1/finds/fnd_1/rows": () => rowsReply([houston, austin]),
    });
    const listId = await start(t);
    await t.finishAllScheduledFunctions(vi.runAllTimers);
    const stored = await t.run(
      async (ctx: any) => await ctx.db.query("rows").collect(),
    );
    expect(stored).toHaveLength(2);
    expect(await t.query(api.lists.get, { listId })).toMatchObject({
      rowCount: 2,
    });
  });

  test("a partial list keeps the rows it found", async () => {
    const t = initConvexTest();
    fakeSpecStream({
      ...happyRoutes(),
      "GET /v1/finds/fnd_1": findReply("partial", 1),
      "GET /v1/finds/fnd_1/rows": rowsReply([houston], "partial"),
    });
    const listId = await start(t);
    await t.finishAllScheduledFunctions(vi.runAllTimers);
    expect(await t.query(api.lists.get, { listId })).toMatchObject({
      status: "partial",
      finalized: true,
      rowCount: 1,
    });
  });

  test("follows the cursor through every page of rows", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({
      ...happyRoutes(),
      "GET /v1/finds/fnd_1": findReply("completed", 2),
      "GET /v1/finds/fnd_1/rows": (call) =>
        call.url.includes("cursor=c2")
          ? {
              body: {
                data: {
                  find_id: "fnd_1",
                  status: "completed",
                  accepted_count: 2,
                  rows: [austin],
                  next_cursor: null,
                },
              },
            }
          : {
              body: {
                data: {
                  find_id: "fnd_1",
                  status: "completed",
                  accepted_count: 2,
                  rows: [houston],
                  next_cursor: "c2",
                },
              },
            },
    });
    const listId = await start(t);
    await t.finishAllScheduledFunctions(vi.runAllTimers);
    expect(await t.query(api.lists.get, { listId })).toMatchObject({
      rowCount: 2,
    });
    const rowCalls = calls.filter((c) => c.path.endsWith("/rows"));
    expect(rowCalls[0].url).toContain("limit=100");
    expect(rowCalls[1].url).toContain("cursor=c2");
  });

  test("a failed list is final", async () => {
    const t = initConvexTest();
    fakeSpecStream({
      ...happyRoutes(),
      "GET /v1/finds/fnd_1": findReply("failed", 0),
      "GET /v1/finds/fnd_1/rows": rowsReply([], "failed"),
    });
    const listId = await start(t);
    await t.finishAllScheduledFunctions(vi.runAllTimers);
    expect(await t.query(api.lists.get, { listId })).toMatchObject({
      status: "failed",
      finalized: true,
    });
  });

  test("a transient status error is retried and the list still finishes", async () => {
    const t = initConvexTest();
    fakeSpecStream({
      ...happyRoutes(),
      "GET /v1/finds/fnd_1": (_call, index) =>
        index < 5
          ? { status: 500, body: { error: { message: "boom" } } }
          : findReply("completed", 1),
      "GET /v1/finds/fnd_1/rows": rowsReply([houston]),
    });
    const listId = await start(t);
    await t.finishAllScheduledFunctions(vi.runAllTimers);
    expect(await t.query(api.lists.get, { listId })).toMatchObject({
      status: "completed",
      rowCount: 1,
    });
  });

  test("a revoked key stops tracking, and resume picks it back up", async () => {
    const t = initConvexTest();
    let revoked = true;
    fakeSpecStream({
      ...happyRoutes(),
      "GET /v1/finds/fnd_1": () =>
        revoked
          ? { status: 401, body: { error: { code: "unauthorized" } } }
          : findReply("completed", 1),
      "GET /v1/finds/fnd_1/rows": rowsReply([houston]),
    });
    const listId = await start(t);
    await t.finishAllScheduledFunctions(vi.runAllTimers);
    const stopped = await t.query(api.lists.get, { listId });
    expect(stopped).toMatchObject({ status: "failed", finalized: true });
    expect(stopped!.error).toMatch(/Stopped tracking/);

    revoked = false;
    expect(await t.mutation(api.lists.resume, { listId })).toBe(true);
    await t.finishAllScheduledFunctions(vi.runAllTimers);
    expect(await t.query(api.lists.get, { listId })).toMatchObject({
      status: "completed",
      rowCount: 1,
    });
    expect(await t.mutation(api.lists.resume, { listId })).toBe(false);
  });

  test("cancel asks SpecStream to stop and keeps the rows found", async () => {
    const t = initConvexTest();
    let canceled = false;
    const { calls } = fakeSpecStream({
      ...happyRoutes(),
      "POST /v1/finds/fnd_1/cancel": () => {
        canceled = true;
        return { body: { data: { find_id: "fnd_1", status: "canceled" } } };
      },
      "GET /v1/finds/fnd_1": () =>
        canceled ? findReply("canceled", 1) : findReply("running", 0),
      "GET /v1/finds/fnd_1/rows": rowsReply([houston], "canceled"),
    });
    const listId = await start(t);
    await t.action(api.lists.cancel, { listId });
    expect(calls.some((c) => c.path === "/v1/finds/fnd_1/cancel")).toBe(true);
    expect(await t.query(api.lists.get, { listId })).toMatchObject({
      status: "canceled",
      finalized: true,
      rowCount: 1,
    });
  });

  test("hides internal bookkeeping from the public list", async () => {
    const t = initConvexTest();
    fakeSpecStream({
      ...happyRoutes(),
      "GET /v1/finds/fnd_1": findReply("running", 0),
    });
    const listId = await start(t);
    const list = await t.query(api.lists.get, { listId });
    expect(list).not.toHaveProperty("onComplete");
    expect(list).not.toHaveProperty("pollAttempt");
    expect(list).not.toHaveProperty("syncedAcceptedCount");
  });

  test("list, getBySpecstreamListId and deleteList", async () => {
    const t = initConvexTest();
    fakeSpecStream({
      ...happyRoutes(),
      "GET /v1/finds/fnd_1": findReply("completed", 2),
      "GET /v1/finds/fnd_1/rows": rowsReply([houston, austin]),
    });
    const listId = await start(t);
    await t.finishAllScheduledFunctions(vi.runAllTimers);

    expect(await t.query(api.lists.list, {})).toHaveLength(1);
    expect(await t.query(api.lists.list, { status: "failed" })).toHaveLength(0);
    expect(
      (
        await t.query(api.lists.getBySpecstreamListId, {
          specstreamListId: "fnd_1",
        })
      )?._id,
    ).toBe(listId);

    await t.mutation(api.lists.deleteList, { listId });
    await t.finishAllScheduledFunctions(vi.runAllTimers);
    expect(await t.query(api.lists.get, { listId })).toBeNull();
    expect(
      await t.run(async (ctx: any) => await ctx.db.query("rows").collect()),
    ).toHaveLength(0);
  });

  test("an unknown id reads as null, not an error", async () => {
    const t = initConvexTest();
    expect(await t.query(api.lists.get, { listId: "nope" })).toBeNull();
    expect(await t.query(api.lists.getQuote, { quoteId: "nope" })).toBeNull();
    const page = await t.query(api.lists.listRows, {
      listId: "nope",
      paginationOpts: { numItems: 5, cursor: null },
    });
    expect(page.page).toEqual([]);
  });
});

describe("webhook", () => {
  const body = JSON.stringify({
    id: "dlv_1",
    event: "find.completed",
    find_id: "fnd_1",
    records: [],
  });

  async function signed(secret: string, payload = body) {
    const stamp = String(Math.floor(Date.now() / 1000));
    return `t=${stamp},v1=${await sign(secret, stamp, payload)}`;
  }

  async function startWebhookList(t: ReturnType<typeof initConvexTest>) {
    const result = await t.action(api.lists.findList, {
      request: "food banks in Texas",
      rows: 100,
      maxCents: 2000,
      mode: "webhook",
    });
    if (result.status !== "started") throw new Error("expected start");
    return result.listId;
  }

  test("a signed delivery wakes the list up now instead of waiting for the next check", async () => {
    process.env.SPECSTREAM_WEBHOOK_SECRET = TEST_WEBHOOK_SECRET;
    const t = initConvexTest();
    let done = false;
    const { calls } = fakeSpecStream({
      ...happyRoutes(),
      "GET /v1/finds/fnd_1": () =>
        done ? findReply("completed", 1) : findReply("running", 0),
      "GET /v1/finds/fnd_1/rows": rowsReply([houston]),
    });
    const listId = await startWebhookList(t);
    // Let the first check run, and not the slow one behind it.
    await vi.advanceTimersByTimeAsync(1_000);
    await t.finishInProgressScheduledFunctions();
    const checks = () =>
      calls.filter((c) => c.path === "/v1/finds/fnd_1").length;
    expect(checks()).toBe(1);
    expect(await t.query(api.lists.get, { listId })).toMatchObject({
      status: "running",
    });

    done = true;
    const response = await t.fetch("/webhook", {
      method: "POST",
      body,
      headers: { "Specstream-Signature": await signed(TEST_WEBHOOK_SECRET) },
    });
    expect(response.status).toBe(200);
    await vi.advanceTimersByTimeAsync(1_000);
    await t.finishInProgressScheduledFunctions();
    expect(checks()).toBe(2);
    expect(await t.query(api.lists.get, { listId })).toMatchObject({
      status: "completed",
      rowCount: 1,
      finalized: true,
    });
  });

  test("a bad signature is refused", async () => {
    process.env.SPECSTREAM_WEBHOOK_SECRET = TEST_WEBHOOK_SECRET;
    const t = initConvexTest();
    const response = await t.fetch("/webhook", {
      method: "POST",
      body,
      headers: { "Specstream-Signature": await signed("another-secret") },
    });
    expect(response.status).toBe(401);
  });

  test("a delivery for a list this app didn't start is accepted and ignored", async () => {
    process.env.SPECSTREAM_WEBHOOK_SECRET = TEST_WEBHOOK_SECRET;
    const t = initConvexTest();
    const other = JSON.stringify({
      event: "find.completed",
      find_id: "fnd_other",
    });
    const response = await t.fetch("/webhook", {
      method: "POST",
      body: other,
      headers: {
        "Specstream-Signature": await signed(TEST_WEBHOOK_SECRET, other),
      },
    });
    expect(response.status).toBe(200);
  });

  test("other events and unreadable bodies don't start any work", async () => {
    const t = initConvexTest();
    const found = JSON.stringify({ event: "monitor.found", find_id: "fnd_1" });
    expect(
      (await t.fetch("/webhook", { method: "POST", body: found })).status,
    ).toBe(200);
    expect(
      (await t.fetch("/webhook", { method: "POST", body: "not json" })).status,
    ).toBe(400);
    expect(
      await t.mutation(internal.lists.handleWebhook, {
        event: "find.completed",
      }),
    ).toMatchObject({ accepted: true });
  });
});
