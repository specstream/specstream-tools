import * as coda from "@codahq/packs-sdk";
import { codaRow, columnsOf, dollars, listIdOf, readRecord, runKey, shownColumns, withCount } from "./records";

export const pack = coda.newPack();

const API = "https://api.specstream.ai";
const APP = "https://specstream.ai";

pack.addNetworkDomain("specstream.ai");

pack.setUserAuthentication({
  type: coda.AuthenticationType.HeaderBearerToken,
  instructionsUrl: `${APP}/docs/api`,
  getConnectionName: async function (context) {
    const me = await call(context, "GET", "/v1/me");
    return me.email;
  },
});

// Superhuman Go and Go agents reach every SpecStream tool through our MCP server, with the same key.
pack.addMCPServer({
  name: "SpecStream",
  endpointUrl: `${API}/mcp`,
  searchToolNames: ["search_workspace"],
});

// One SpecStream API call. Errors come back with SpecStream's own words, such as a refused key.
async function call(context: coda.ExecutionContext, method: "GET" | "POST", path: string, body?: object, fresh = false) {
  try {
    const response = await context.fetcher.fetch({
      method,
      url: API + path,
      headers: { Accept: "application/json", ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
      cacheTtlSecs: fresh ? 0 : undefined,
    });
    return response.body.data;
  } catch (error: any) {
    const { status, message } = apiError(error);
    if (status && status !== 404 && message) throw new coda.UserVisibleError(message);
    throw error;
  }
}

// The status and SpecStream's message from a failed call. A StatusCodeError carries both; an error that
// lost its fields on the way still says "404 - {...}".
function apiError(error: any): { status?: number; message?: string } {
  let status = error && error.statusCode;
  let body = error && error.body;
  const text = /^(\d{3}) - (.*)$/s.exec(String((error && error.message) || ""));
  if (text) {
    status = status || Number(text[1]);
    try {
      body = body || JSON.parse(text[2]);
    } catch {
      // Not SpecStream's JSON.
    }
  }
  return { status, message: body && body.error && body.error.message };
}

// Every list the connected account can open, newest first.
async function allLists(context: coda.ExecutionContext): Promise<any[]> {
  const lists: any[] = [];
  let after: string | undefined;
  do {
    const page = await call(
      context,
      "GET",
      coda.withQueryParams("/v1/workspace/collections", after ? { limit: 100, sort: "recent", after } : { limit: 100, sort: "recent" }),
      undefined,
      true,
    );
    lists.push(...(page.collections || []));
    after = page.next_after || undefined;
  } while (after && lists.length < 5000);
  return lists;
}

const listLink = (id: string) => `${APP}/workspace/collections/${id}`;

const KINDS: { [kind: string]: string } = {
  find: "Found",
  snapshot: "Found",
  import: "Imported",
  combined: "Combined",
};

const ListSchema = coda.makeObjectSchema({
  properties: {
    name: { type: coda.ValueType.String, description: "The list's name." },
    records: { type: coda.ValueType.Number, fromKey: "row_count", description: "How many records the list has." },
    kind: { type: coda.ValueType.String, description: "Found, Imported or Combined." },
    created: {
      type: coda.ValueType.String,
      codaType: coda.ValueHintType.DateTime,
      fromKey: "created_at",
      description: "When the list was made. A schedule delivers new and changed records as a new list.",
    },
    link: { type: coda.ValueType.String, codaType: coda.ValueHintType.Url, description: "The list in SpecStream." },
    listId: { type: coda.ValueType.String, fromKey: "id", description: "The list's ID." },
  },
  displayProperty: "name",
  idProperty: "listId",
  featuredProperties: ["records", "kind", "created", "link"],
});

pack.addSyncTable({
  name: "Lists",
  description: "Your SpecStream lists: every list you found, imported or combined.",
  identityName: "List",
  schema: ListSchema,
  formula: {
    name: "SyncLists",
    description: "Syncs your SpecStream lists.",
    parameters: [],
    execute: async function ([], context) {
      const lists = await allLists(context);
      return {
        result: lists.map((list) => ({
          ...list,
          row_count: list.row_count ?? list.total ?? null,
          kind: KINDS[list.kind] || (list.imported ? "Imported" : "Found"),
          link: listLink(list.id),
        })),
      };
    },
  },
});

pack.addDynamicSyncTable({
  name: "Records",
  description: "The records of one SpecStream list, each value with the page it was read from.",
  identityName: "Record",
  entityName: "Record",
  listDynamicUrls: async function (context) {
    const lists = await allLists(context);
    return lists.map((list) => ({ display: String(list.name || list.id), value: listLink(list.id) }));
  },
  searchDynamicUrls: async function (context, search) {
    const words = String(search || "").toLowerCase();
    const lists = await allLists(context);
    return lists
      .filter((list) => String(list.name || "").toLowerCase().includes(words))
      .map((list) => ({ display: String(list.name || list.id), value: listLink(list.id) }));
  },
  getName: async function (context) {
    const list = await call(context, "GET", `/v1/workspace/collections/${listIdOf(context.sync.dynamicUrl!)}`);
    return String(list.name || "SpecStream list");
  },
  getDisplayUrl: async function (context) {
    return context.sync.dynamicUrl!;
  },
  getSchema: async function (context) {
    const list = await call(context, "GET", `/v1/workspace/collections/${listIdOf(context.sync.dynamicUrl!)}`, undefined, true);
    const columns = columnsOf(list.rows || []);
    const properties: coda.ObjectSchemaProperties = {
      record_id: { type: coda.ValueType.String, description: "The record's ID within this list." },
      entity_id: {
        type: coda.ValueType.String,
        description: "The same for this company, place, person or posting in every list.",
      },
    };
    for (const column of columns) {
      properties[column.key] = { type: coda.ValueType.String, displayName: column.label };
      properties[`${column.key}_source`] = {
        type: coda.ValueType.String,
        codaType: coda.ValueHintType.Url,
        displayName: `${column.label} source`,
        description: `The page ${column.label.toLowerCase()} was read from.`,
      };
    }
    const shown = shownColumns((list.rows || []).map(readRecord), columns);
    return coda.makeObjectSchema({
      properties,
      idProperty: "record_id",
      displayProperty: shown[0] || "record_id",
      featuredProperties: shown,
      identity: { name: "Record", dynamicUrl: context.sync.dynamicUrl },
    });
  },
  formula: {
    name: "SyncRecords",
    description: "Syncs the records of a SpecStream list.",
    parameters: [],
    execute: async function ([], context) {
      const list = await call(context, "GET", `/v1/workspace/collections/${listIdOf(context.sync.dynamicUrl!)}`, undefined, true);
      const rows = list.rows || [];
      const columns = columnsOf(rows);
      return { result: rows.map((row: any) => codaRow(readRecord(row), columns)) };
    },
  },
});

// Reads a request in plain words; refuses one SpecStream can't price yet.
async function reading(context: coda.ExecutionContext, request: string) {
  const q = request.trim();
  if (!q) throw new coda.UserVisibleError("Describe the list to find, for example: roofers in Austin with their phone.");
  const read = await call(context, "POST", "/v1/parse", { q, locale: "en-US" });
  const said = read.read_back || read.canonical_sentence || q;
  if (read.status !== "runnable" || !read.ast_hash) {
    throw new coda.UserVisibleError(
      `SpecStream needs a clearer request before it can price it. It read: "${said}". Add the place or what every result must meet.`,
    );
  }
  return { read, said };
}

const PriceSchema = coda.makeObjectSchema({
  properties: {
    request: { type: coda.ValueType.String, description: "Your request as SpecStream read it." },
    results: { type: coda.ValueType.Number, description: "The most results this price covers." },
    maximumPrice: {
      type: coda.ValueType.Number,
      codaType: coda.ValueHintType.Currency,
      description: "The most the list can cost. You pay for each result delivered.",
    },
    freeBelow: {
      type: coda.ValueType.Number,
      description: "Below this many matches, the list costs nothing.",
    },
    expires: { type: coda.ValueType.String, codaType: coda.ValueHintType.DateTime },
  },
  displayProperty: "request",
  featuredProperties: ["results", "maximumPrice", "freeBelow"],
});

pack.addFormula({
  name: "Price",
  description:
    "Reads a request in plain words and prices it. Nothing runs and nothing is spent. Example: Price(\"Roofers in Austin with their phone\", 25)",
  parameters: [
    coda.makeParameter({
      type: coda.ParameterType.String,
      name: "request",
      description: "What to find, in plain words. For example: dentists in Leeds with their website and phone.",
    }),
    coda.makeParameter({
      type: coda.ParameterType.Number,
      name: "results",
      description: "How many results to price. Leave empty to use the number in the request, or 25.",
      optional: true,
    }),
  ],
  resultType: coda.ValueType.Object,
  schema: PriceSchema,
  execute: async function ([request, results], context) {
    const { read, said } = await reading(context, request);
    const units = results || (read.ast && read.ast.limit && read.ast.limit.max) || 25;
    const quote = await call(context, "POST", "/v1/capacity/quotes", {
      ast_hash: read.ast_hash,
      operation: "find",
      requested_units: Math.round(units),
    });
    return {
      request: withCount(said, Math.round(units)),
      results: Number(quote.terms && quote.terms.maximum_units) || Math.round(units),
      maximumPrice: quote.maximum_cents / 100,
      freeBelow: Number(quote.terms && quote.terms.minimum_units) || null,
      expires: quote.expires_at,
    };
  },
});

const RunSchema = coda.makeObjectSchema({
  properties: {
    listId: { type: coda.ValueType.String, description: "The new list's ID." },
    status: { type: coda.ValueType.String },
    request: { type: coda.ValueType.String, description: "Your request as SpecStream read it." },
    maximumPrice: { type: coda.ValueType.Number, codaType: coda.ValueHintType.Currency },
    link: { type: coda.ValueType.String, codaType: coda.ValueHintType.Url, description: "The list in SpecStream." },
  },
  displayProperty: "request",
  idProperty: "listId",
  featuredProperties: ["status", "maximumPrice", "link"],
});

pack.addFormula({
  name: "FindList",
  description:
    "Finds a list from the live web if the price is within your maximum. The list fills in SpecStream; sync it into a Records table.",
  isAction: true,
  parameters: [
    coda.makeParameter({ type: coda.ParameterType.String, name: "request", description: "What to find, in plain words." }),
    coda.makeParameter({ type: coda.ParameterType.Number, name: "results", description: "How many results to find." }),
    coda.makeParameter({
      type: coda.ParameterType.Number,
      name: "maximumPrice",
      description: "The most this list may cost, in US dollars. If the price is higher, nothing runs.",
    }),
  ],
  resultType: coda.ValueType.Object,
  schema: RunSchema,
  execute: async function ([request, results, maximumPrice], context) {
    const count = Math.round(results);
    if (!Number.isSafeInteger(count) || count < 1) throw new coda.UserVisibleError("Results must be 1 or more.");
    if (!(maximumPrice > 0)) throw new coda.UserVisibleError("Set a maximum price above $0.");
    const maxCents = Math.round(maximumPrice * 100);
    const key = runKey(request.trim(), count, maxCents, new Date());
    try {
      const existing = await call(context, "GET", `/v1/capacity/requests/${encodeURIComponent(key)}`, undefined, true);
      if (existing && existing.find_id) {
        return {
          listId: existing.find_id,
          status: existing.status || "running",
          request: request.trim(),
          maximumPrice: (existing.maximum_cents || maxCents) / 100,
          link: listLink(existing.find_id),
        };
      }
    } catch (error: any) {
      if (apiError(error).status !== 404) throw error;
    }
    const { read, said } = await reading(context, request);
    const quote = await call(context, "POST", "/v1/capacity/quotes", {
      ast_hash: read.ast_hash,
      operation: "find",
      requested_units: count,
    });
    if (quote.maximum_cents > maxCents) {
      throw new coda.UserVisibleError(
        `This list can cost up to ${dollars(quote.maximum_cents)}, above your maximum of ${dollars(maxCents)}. Raise the maximum or ask for fewer results.`,
      );
    }
    const run = await call(context, "POST", "/v1/capacity/executions", {
      quote_id: quote.quote_id,
      quote_hash: quote.quote_hash,
      confirm_max_cents: quote.maximum_cents,
      idempotency_key: key,
    });
    return {
      listId: run.find_id,
      status: run.state || run.status || "running",
      request: withCount(said, count),
      maximumPrice: quote.maximum_cents / 100,
      link: listLink(run.find_id),
    };
  },
});

pack.addFormula({
  name: "WebSearch",
  description:
    "Searches the live web in seconds with the SpecStream Search API ($5 per 1,000 searches of up to 10 results, or $1 on the fast tier) and returns the answer or top matching row.",
  parameters: [
    coda.makeParameter({ type: coda.ParameterType.String, name: "question", description: "The question in everyday words (1 to 2,000 characters)." }),
  ],
  resultType: coda.ValueType.String,
  execute: async function ([question], context) {
    const q = String(question || "").trim();
    if (!q || q.length > 2000) throw new coda.UserVisibleError("Write the question in 1 to 2,000 characters.");
    const data = await call(context, "GET", coda.withQueryParams("/v1/web-search", { q }));
    if (data?.answer?.value != null && data.answer.value !== "") return String(data.answer.value);
    const rows = data?.rows || [];
    return rows.length ? String(rows[0].name || "") : "";
  },
});

pack.addFormula({
  name: "ExtractPage",
  description:
    "Reads the main text of a web page, PDF, Word or Excel file live with the SpecStream Extract API ($0.80 per 1,000 pages, empty pages free).",
  parameters: [
    coda.makeParameter({ type: coda.ParameterType.String, name: "url", description: "The http or https URL to read live." }),
  ],
  resultType: coda.ValueType.String,
  execute: async function ([url], context) {
    const cleaned = String(url || "").trim();
    if (!cleaned) throw new coda.UserVisibleError("Enter a URL to read.");
    const data = await call(context, "POST", "/v1/extract", { urls: [cleaned], format: "markdown" });
    const first = (data?.results || [])[0];
    return String(first?.text || "");
  },
});
