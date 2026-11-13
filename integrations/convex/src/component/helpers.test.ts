import { describe, expect, test } from "vitest";
import { _test, executionKey, mapStatus } from "./helpers.js";
import { _test as listsTest, STOPPED_TRACKING } from "./lists.js";
import { rowOf } from "./setup.test.js";

describe("mapStatus", () => {
  test("folds the in-flight statuses into running", () => {
    for (const status of ["queued", "planning", "running", "", undefined]) {
      expect(mapStatus(status)).toBe("running");
    }
  });
  test("keeps the final statuses and spells canceled one way", () => {
    expect(mapStatus("completed")).toBe("completed");
    expect(mapStatus("partial")).toBe("partial");
    expect(mapStatus("failed")).toBe("failed");
    expect(mapStatus("expired")).toBe("expired");
    expect(mapStatus("cancelled")).toBe("canceled");
    expect(mapStatus("canceled")).toBe("canceled");
  });
});

describe("toRow", () => {
  test("keeps each cell with its source URL", () => {
    const row = _test.toRow(
      rowOf("ent_1", 3, "Houston Food Bank", "https://hfb.org/about"),
      1,
    );
    expect(row).toMatchObject({
      entityId: "ent_1",
      ordinal: 3,
      sourceUrl: "https://hfb.org/about",
      observedAt: "2026-10-15T10:00:00Z",
    });
    expect(row!.cells[0]).toMatchObject({
      columnId: "name",
      label: "Name",
      display: "Houston Food Bank",
      sourceUrl: "https://hfb.org/about",
    });
  });

  test("skips anything without an entity id or cells", () => {
    expect(_test.toRow({ cells: [] }, 1)).toBeNull();
    expect(_test.toRow({ entity_id: "x" }, 1)).toBeNull();
    expect(_test.toRow("nope", 1)).toBeNull();
  });

  test("keeps absence and ignores non-web provenance", () => {
    const row = _test.toRow(
      {
        entity_id: "e",
        ordinal: 1,
        cells: [
          {
            column_id: "phone",
            label: "Phone",
            value: null,
            display: null,
            absence: "Not published",
            provenance: { source_url: "javascript:alert(1)" },
          },
        ],
      },
      1,
    );
    expect(row!.cells[0].absence).toBe("Not published");
    expect(row!.cells[0].sourceUrl).toBeUndefined();
    expect(row!.sourceUrl).toBeUndefined();
  });

  test("keeps a row under Convex's 1MB document limit", () => {
    const big = (label: string) => ({
      column_id: label,
      label,
      value: "v".repeat(100_000),
      display: "d".repeat(100_000),
    });
    const row = _test.toRow(
      {
        entity_id: "e",
        ordinal: 1,
        cells: Array.from({ length: 6 }, (_, i) => big(`c${i}`)),
        details: Array.from({ length: 6 }, (_, i) => big(`d${i}`)),
      },
      1,
    );
    expect(new TextEncoder().encode(JSON.stringify(row)).length).toBeLessThan(
      1_000_000,
    );
    expect(row!.entityId).toBe("e");
  });
});

describe("clean", () => {
  test("renames keys Convex reserves and drops what it can't store", () => {
    expect(
      _test.clean({ $a: 1, _b: [undefined, Number.NaN], ok: { deep: true } }),
    ).toEqual({ field$a: 1, field_b: [null, null], ok: { deep: true } });
  });
});

describe("executionKey", () => {
  test("is stable for a quote and fits the API's limit", () => {
    expect(executionKey("qte_1")).toBe("convex-qte_1");
    expect(executionKey("qte_1", "report-42")).toBe("convex-report-42");
    expect(executionKey("q".repeat(300)).length).toBe(128);
  });
  test("refuses keys with odd characters", () => {
    expect(() => executionKey("qte_1", "has space")).toThrow();
  });
});

describe("check cadence", () => {
  test("poll mode backs off to 15s, webhook mode to two minutes", () => {
    expect(listsTest.nextDelayMs("poll", 0)).toBe(3_000);
    expect(listsTest.nextDelayMs("poll", 100)).toBe(15_000);
    expect(listsTest.nextDelayMs("webhook", 0)).toBe(30_000);
    expect(listsTest.nextDelayMs("webhook", 100)).toBe(120_000);
    expect(STOPPED_TRACKING.length).toBeGreaterThan(0);
  });
});
