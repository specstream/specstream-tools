/// <reference types="vite/client" />
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { api } from "./_generated/api.js";
import { initConvexTest, mockFetch } from "./setup.test.js";

const HASH = "c".repeat(64);
const routes = {
  "POST /v1/parse": {
    data: {
      status: "runnable",
      ast_hash: HASH,
      canonical_sentence: "Food banks in Texas",
      ast: { limit: { max: 50, inferred: false } },
    },
  },
  "POST /v1/capacity/quotes": {
    data: {
      quote_id: "qte_7",
      quote_hash: HASH,
      currency: "USD",
      maximum_cents: 750,
      expires_at: new Date(Date.now() + 3_600_000).toISOString(),
      can_authorize: true,
      terms: { unit_cents: 15 },
    },
  },
  "POST /v1/capacity/executions": {
    data: {
      reservation_id: "res_7",
      find_id: "fnd_7",
      maximum_cents: 750,
      state: "reserved",
      replay: false,
    },
  },
  "GET /v1/finds/fnd_7": {
    data: {
      find_id: "fnd_7",
      status: "completed",
      requested_count: 50,
      accepted_count: 1,
    },
  },
  "GET /v1/finds/fnd_7/rows": {
    data: {
      find_id: "fnd_7",
      status: "completed",
      accepted_count: 1,
      next_cursor: null,
      rows: [
        {
          entity_id: "ent_1",
          ordinal: 1,
          cells: [
            {
              column_id: "name",
              label: "Name",
              value: "Houston Food Bank",
              display: "Houston Food Bank",
              provenance: {
                source_url: "https://houstonfoodbank.org",
                observed_at: "2026-10-15T10:00:00Z",
              },
            },
          ],
        },
      ],
    },
  },
};

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("example app", () => {
  test("every function needs a signed-in caller", async () => {
    const t = initConvexTest();
    mockFetch(routes);
    await expect(
      t.action(api.example.quoteList, {
        request: "food banks in Texas",
        rows: 50,
      }),
    ).rejects.toThrow(/Not signed in/);
  });

  test("quote, approve, read rows, and the callback files a report", async () => {
    const t = initConvexTest();
    mockFetch(routes);
    const alice = t.withIdentity({ subject: "alice" });

    const quote = await alice.action(api.example.quoteList, {
      request: "food banks in Texas",
      rows: 50,
    });
    if (quote.status !== "quoted") throw new Error("expected a quote");
    expect(quote.maximumCents).toBe(750);

    const started = await alice.action(api.example.approveList, {
      quoteId: quote.quoteId,
      confirmMaxCents: quote.maximumCents,
      label: "food banks",
    });
    await t.finishAllScheduledFunctions(vi.runAllTimers);

    const progress = await alice.query(api.example.listProgress, {
      listId: started.listId,
    });
    expect(progress).toMatchObject({ status: "completed", rowCount: 1 });
    const rows = await alice.query(api.example.listRows, {
      listId: started.listId,
      paginationOpts: { numItems: 10, cursor: null },
    });
    expect(rows.page[0]).toMatchObject({
      entityId: "ent_1",
      sourceUrl: "https://houstonfoodbank.org",
    });

    const reports = await alice.query(api.example.reports, {});
    expect(reports).toHaveLength(1);
    expect(reports[0]).toMatchObject({
      userId: "alice",
      label: "food banks",
      status: "completed",
      rowCount: 1,
    });
  });

  test("one person can't read another person's list", async () => {
    const t = initConvexTest();
    mockFetch(routes);
    const alice = t.withIdentity({ subject: "alice" });
    const bob = t.withIdentity({ subject: "bob" });

    const result = await alice.action(api.example.findListUnderBudget, {
      request: "food banks in Texas",
      rows: 50,
    });
    if (result.status !== "started") throw new Error("expected a start");

    await expect(
      bob.query(api.example.listProgress, { listId: result.listId }),
    ).rejects.toThrow(/No such list/);
    await expect(
      bob.mutation(api.example.deleteList, { listId: result.listId }),
    ).rejects.toThrow(/No such list/);
    await expect(
      bob.action(api.example.cancelList, { listId: result.listId }),
    ).rejects.toThrow(/No such list/);
    expect(await bob.query(api.example.myLists, {})).toEqual([]);
  });

  test("reads a page in a browser and closes it", async () => {
    const t = initConvexTest();
    const calls = mockFetch({
      "POST /v1/browser/sessions": { data: { id: "bs_9", status: "running" } },
      "POST /v1/browser/sessions/bs_9/actions": {
        data: {
          result: [{ type: "text", text: "Example Domain" }],
          url: "https://example.com/",
          title: "Example Domain",
        },
      },
      "POST /v1/browser/sessions/bs_9/release": { data: { id: "bs_9", status: "ended" } },
    });
    await expect(
      t.action(api.example.readPageInBrowser, { url: "https://example.com" }),
    ).rejects.toThrow(/Not signed in/);
    const page = await t
      .withIdentity({ subject: "alice" })
      .action(api.example.readPageInBrowser, { url: "https://example.com" });
    expect(page).toMatchObject({ title: "Example Domain", text: "Example Domain" });
    expect(calls).toEqual([
      "POST /v1/browser/sessions",
      "POST /v1/browser/sessions/bs_9/actions",
      "POST /v1/browser/sessions/bs_9/actions",
      "POST /v1/browser/sessions/bs_9/release",
    ]);
  });
});
