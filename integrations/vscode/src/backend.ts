import * as vscode from "vscode";
import { Client } from "@specstream/sdk";

type Json = Record<string, any>;

export interface Reading {
  ok: boolean;
  status: string;
  astHash: string | null;
  sentence: string | null;
}

export interface Quote {
  quoteId: string;
  quoteHash: string;
  maximumCents: number;
  currency: string;
  unitCents: number | null;
  units: number;
  expiresAt: string | null;
}

export interface Match {
  cells: { label: string; text: string }[];
  sourceUrl: string | null;
}

export interface FindState {
  status: string;
  accepted: number;
  chargedCents: number | null;
  currency: string;
}

export const TERMINAL = new Set(["completed", "partial", "failed", "canceled", "expired"]);

/** One call into SpecStream: either through VS Code's MCP tools (signed in with VS Code's own MCP sign-in) or the TypeScript client with an API key. */
type Call = (op: string, args: Json) => Promise<Json>;

export class Backend {
  constructor(private readonly call: Call, readonly via: "mcp" | "key") {}

  async compile(q: string): Promise<Reading> {
    const r = await this.call("compile", { q });
    return {
      ok: r.status === "runnable" && !!r.ast_hash,
      status: String(r.status ?? ""),
      astHash: r.ast_hash ?? null,
      sentence: r.read_back ?? r.canonical_sentence ?? null,
    };
  }

  async quote(astHash: string, units: number): Promise<Quote> {
    const r = await this.call("quote_capacity_work", { ast_hash: astHash, operation: "find", requested_units: units });
    return {
      quoteId: String(r.quote_id),
      quoteHash: String(r.quote_hash),
      maximumCents: Number(r.maximum_cents),
      currency: String(r.currency ?? "USD"),
      unitCents: typeof r.terms?.unit_cents === "number" ? r.terms.unit_cents : null,
      units,
      expiresAt: r.expires_at ?? null,
    };
  }

  /** Starts the run. Only called after the person pressed approve on this exact quote. */
  async authorize(q: Quote): Promise<string> {
    const r = await this.call("authorize_capacity_work", {
      quote_id: q.quoteId,
      quote_hash: q.quoteHash,
      confirm_max_cents: q.maximumCents,
      idempotency_key: `vscode-${q.quoteId}`,
    });
    const findId = r.find_id ?? r.execution?.find_id;
    if (!findId) throw new Error(String(r.message ?? "SpecStream did not start the list."));
    return String(findId);
  }

  async state(findId: string): Promise<FindState> {
    const r = await this.call("get_find", { find_id: findId });
    return {
      status: String(r.status ?? ""),
      accepted: Number(r.accepted_count ?? 0),
      chargedCents: typeof r.commerce?.amount_captured_cents === "number" ? r.commerce.amount_captured_cents : null,
      currency: String(r.commerce?.currency ?? "USD"),
    };
  }

  async matches(findId: string, max: number): Promise<{ matches: Match[]; total: number }> {
    const out: Match[] = [];
    let cursor: string | null = null;
    let total = 0;
    do {
      const args: Json = { find_id: findId, limit: 100 };
      if (cursor) args.cursor = cursor;
      const page = await this.call("list_find_rows", args);
      total = Number(page.accepted_count ?? total);
      for (const row of page.rows ?? []) {
        if (out.length >= max) break;
        out.push(toMatch(row));
      }
      cursor = out.length < max ? page.next_cursor ?? null : null;
    } while (cursor);
    return { matches: out, total: total || out.length };
  }
}

function toMatch(row: Json): Match {
  // A compact row names its main source once and a cell names its own only when it differs.
  let sourceUrl: string | null = row.source_url ?? null;
  const cells = (row.cells ?? []).map((c: Json) => {
    sourceUrl ??= c.source_url ?? c.provenance?.source_url ?? null;
    const value = c.display ?? (c.value === null || c.value === undefined ? "" : typeof c.value === "object" ? JSON.stringify(c.value) : String(c.value));
    return { label: String(c.label ?? c.column_id ?? ""), text: String(value) };
  });
  return { cells, sourceUrl };
}

function parseResult(result: vscode.LanguageModelToolResult): Json {
  const text = result.content
    .filter((p): p is vscode.LanguageModelTextPart => p instanceof vscode.LanguageModelTextPart)
    .map((p) => p.value)
    .join("");
  let parsed: Json;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error(text.trim() || "SpecStream sent back nothing readable.");
  }
  if (parsed.status === "needs" || parsed.status === "unfunded" || parsed.status === "requires_customer_action") {
    throw new Error(String(parsed.message ?? "SpecStream needs something before it can go on."));
  }
  return parsed.data && typeof parsed.data === "object" && !Array.isArray(parsed.data) ? parsed.data : parsed;
}

/** The SpecStream tool VS Code lists for the MCP server, whatever prefix VS Code gave it. */
export function findServerTool(op: string): vscode.LanguageModelToolInformation | undefined {
  return vscode.lm.tools.find((t) => /specstream/i.test(t.name) && (t.name === op || t.name.endsWith(`_${op}`)));
}

export function mcpAvailable(): boolean {
  return ["compile", "quote_capacity_work", "authorize_capacity_work", "get_find", "list_find_rows"].every((op) => !!findServerTool(op));
}

export function viaMcp(token: vscode.ChatParticipantToolToken | undefined, cancel: vscode.CancellationToken): Backend {
  return new Backend(async (op, args) => {
    const tool = findServerTool(op);
    if (!tool) throw new Error("Connect SpecStream first.");
    const result = await vscode.lm.invokeTool(tool.name, { input: args, toolInvocationToken: token }, cancel);
    return parseResult(result);
  }, "mcp");
}

export function viaKey(apiKey: string): Backend {
  const client = new Client({ apiKey });
  return new Backend(async (op, args) => {
    switch (op) {
      case "compile":
        return (await client.compile(args.q)) as Json;
      case "quote_capacity_work":
        return (await client.quoteCapacityWork(args as any)) as Json;
      case "authorize_capacity_work":
        return (await client.authorizeCapacityWork(args as any)) as Json;
      case "get_find":
        return (await client.getFind(args.find_id)) as Json;
      case "list_find_rows":
        return (await client.rows(args.find_id, args.cursor ?? null, args.limit)) as Json;
      default:
        throw new Error(`Unknown call ${op}`);
    }
  }, "key");
}
