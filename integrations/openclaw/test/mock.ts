import { vi } from "vitest";

export type Call = { method: string; path: string; body: Record<string, any> | null; headers: Record<string, string> };

type Handler = (call: Call) => { status?: number; data?: unknown; error?: unknown } | undefined;

/** A fetch that answers from `handler` and records every call it receives. */
export function mockFetch(handler: Handler) {
  const calls: Call[] = [];
  const impl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const call: Call = {
      method: init?.method ?? "GET",
      path: url.pathname + url.search,
      body: init?.body ? JSON.parse(String(init.body)) : null,
      headers: init?.headers as Record<string, string>,
    };
    calls.push(call);
    const answer = handler(call) ?? { status: 404, error: { message: "not found" } };
    const status = answer.status ?? 200;
    const payload = status >= 400 ? { error: answer.error ?? { message: "error" } } : { data: answer.data };
    return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
  });
  return { fetch: impl as unknown as typeof fetch, calls };
}

export const cell = (label: string, display: unknown, url = "https://example.org/a") => ({
  label,
  display,
  provenance: { source_url: url, observed_at: "2026-10-15T10:00:00Z" },
});

/** A server that prices a find at `maximumCents` and returns `pages` of rows for it. */
export function listServer(options: { maximumCents?: number; status?: string; existing?: boolean; runnable?: boolean } = {}) {
  const { maximumCents = 250, status = "completed", existing = false, runnable = true } = options;
  return mockFetch((call) => {
    if (call.path.startsWith("/v1/capacity/requests/")) {
      return existing ? { data: { find_id: "fnd_old", maximum_cents: 200 } } : undefined;
    }
    if (call.path === "/v1/parse") {
      return { data: runnable ? { status: "runnable", ast_hash: "a".repeat(64) } : { status: "needs_input", canonical_sentence: "things" } };
    }
    if (call.path === "/v1/capacity/quotes") return { data: { quote_id: "q1", quote_hash: "b".repeat(64), maximum_cents: maximumCents } };
    if (call.path === "/v1/capacity/executions") return { data: { find_id: "fnd_new" } };
    if (call.path.startsWith("/v1/finds/")) {
      const rows = [{ entity_id: "e1", ordinal: 1, details: [cell("Name", "Acme Dental"), cell("Phone", "")] }];
      // The API's flat rows carry the page of each value and of the fact that put the row in the list.
      const flat_rows = [{ id: "fnd_new:e1", name: "Acme Dental", name_source: "https://example.org/a", source_url: "https://example.org/filing", checked_at: "2026-10-15T10:00:00Z" }];
      return { data: { status, rows, flat_rows, next_cursor: null } };
    }
    return undefined;
  });
}
