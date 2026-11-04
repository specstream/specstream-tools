import type {
  IDataObject,
  IExecuteFunctions,
  IHttpRequestMethods,
  INodeExecutionData,
  INodeType,
  INodeTypeDescription,
} from "n8n-workflow";
import { NodeConnectionTypes, NodeOperationError } from "n8n-workflow";

import { requireConfirmMaxUsd } from "../../lib/confirm_max_usd.js";
import { flatRowsById, flattenRow, resolveBase, runKey } from "../../lib/specstream.js";

export class Specstream implements INodeType {
  description: INodeTypeDescription = {
    displayName: "SpecStream",
    name: "specstream",
    icon: { light: "file:specstream.svg", dark: "file:specstream.dark.svg" },
    group: ["transform"],
    version: 1,
    subtitle: '={{$parameter["operation"]}}',
    description: "Ask for a list in plain words and get every match from the live web, each with its source. Priced before it runs.",
    defaults: { name: "SpecStream" },
    usableAsTool: true,
    inputs: [NodeConnectionTypes.Main],
    outputs: [NodeConnectionTypes.Main],
    credentials: [{ name: "specstreamApi", required: true }],
    properties: [
      {
        displayName: "Operation",
        name: "operation",
        type: "options",
        noDataExpression: true,
        options: [
          { name: "Approve Quoted Work", value: "confirmAndRun", action: "Approve quoted work" },
          { name: "Find a List", value: "findList", action: "Find a list", description: "Ask for a list in plain words and start it if the price is within your maximum" },
          { name: "Get List Results", value: "getListRows", action: "Get the rows of a list", description: "One item per matching row, each with the page it was read from" },
          { name: "Read Request", value: "compile", action: "Read a request" },
          { name: "Review Quote", value: "quoteWork", action: "Review a quote" },
        ],
        default: "findList",
      },
      {
        displayName: "What to Find",
        name: "request",
        type: "string",
        typeOptions: { rows: 3 },
        default: "",
        required: true,
        placeholder: "Roofing companies in Columbus, Ohio with their website and phone",
        description: "Describe the list in plain words, with what every row must meet and the details to bring back",
        displayOptions: { show: { operation: ["findList"] } },
      },
      {
        displayName: "Number of Results",
        name: "count",
        type: "number",
        typeOptions: { minValue: 1 },
        default: 25,
        required: true,
        description: "How many matching rows to find. You pay for each row delivered.",
        displayOptions: { show: { operation: ["findList"] } },
      },
      {
        displayName: "Maximum Price (USD)",
        name: "max_price_usd",
        type: "number",
        typeOptions: { minValue: 0, numberPrecision: 2 },
        default: 0,
        required: true,
        description: "The most this list may cost. If the price comes back higher, nothing runs and the node stops with the price.",
        displayOptions: { show: { operation: ["findList"] } },
      },
      {
        displayName: "Options",
        name: "findOptions",
        type: "collection",
        placeholder: "Add Option",
        default: {},
        displayOptions: { show: { operation: ["findList"] } },
        options: [
          {
            displayName: "Run Key",
            name: "run_key",
            type: "string",
            default: "",
            description:
              "Identifies one run, 8 to 128 characters. A second request with the same key gets the run it already started and is not charged again. To start a fresh run every time, map something unique, such as the execution ID. If left empty, identical requests within the same UTC hour share one run.",
          },
        ],
      },
      {
        displayName: "List ID",
        name: "list_id",
        type: "string",
        default: "",
        required: true,
        placeholder: "fnd_...",
        description: "The List ID returned by Find a List",
        displayOptions: { show: { operation: ["getListRows"] } },
      },
      {
        displayName: "Return All",
        name: "returnAll",
        type: "boolean",
        default: false,
        description: "Whether to return all results or only up to a given limit",
        displayOptions: { show: { operation: ["getListRows"] } },
      },
      {
        displayName: "Limit",
        name: "limit",
        type: "number",
        typeOptions: { minValue: 1 },
        default: 50,
        description: "Max number of results to return",
        displayOptions: { show: { operation: ["getListRows"], returnAll: [false] } },
      },
      {
        displayName: "Request",
        name: "q",
        type: "string",
        typeOptions: { rows: 3 },
        default: "",
        required: true,
        description: "What you need, in your own words",
        displayOptions: { show: { operation: ["compile"] } },
      },
      {
        displayName: "Options",
        name: "readOptions",
        type: "collection",
        placeholder: "Add Option",
        default: {},
        displayOptions: { show: { operation: ["compile"] } },
        options: [
          {
            displayName: "Locale",
            name: "locale",
            type: "string",
            default: "en-US",
            description: "The language and region the request is written in",
          },
        ],
      },
      {
        displayName: "Confirm Max USD",
        name: "confirm_max_usd",
        type: "number",
        default: 0,
        required: true,
        description: "The most you approve for this run, in dollars. It is never filled in for you, and zero is refused.",
        displayOptions: { show: { operation: ["confirmAndRun"] } },
      },
      {
        displayName: "Request Hash",
        name: "ast_hash",
        type: "string",
        default: "",
        required: true,
        displayOptions: { show: { operation: ["quoteWork"] } },
      },
      {
        displayName: "Requested Amount",
        name: "requested_units",
        type: "number",
        default: 25,
        required: true,
        displayOptions: { show: { operation: ["quoteWork"] } },
      },
      {
        displayName: "Work Operation",
        name: "work_operation",
        type: "options",
        options: [
          { name: "Add Details", value: "add_facts" },
          { name: "Find", value: "find" },
          { name: "More Results", value: "extend" },
          { name: "Recheck", value: "refresh" },
        ],
        default: "find",
        required: true,
        displayOptions: { show: { operation: ["quoteWork"] } },
      },
      {
        displayName: "Earlier Run ID",
        name: "parent_find_id",
        type: "string",
        default: "",
        required: true,
        description: "The run to build on",
        displayOptions: { show: { operation: ["quoteWork"], work_operation: ["extend", "add_facts", "refresh"] } },
      },
      {
        displayName: "Options",
        name: "quoteOptions",
        type: "collection",
        placeholder: "Add Option",
        default: {},
        displayOptions: { show: { operation: ["quoteWork"] } },
        options: [
          {
            displayName: "Project ID",
            name: "project_id",
            type: "string",
            default: "",
            description: "The project the work belongs to",
          },
        ],
      },
      {
        displayName: "Reviewed Quote ID",
        name: "quote_id",
        type: "string",
        default: "",
        required: true,
        displayOptions: { show: { operation: ["confirmAndRun"] } },
      },
      {
        displayName: "Signed Quote Hash",
        name: "quote_hash",
        type: "string",
        default: "",
        required: true,
        displayOptions: { show: { operation: ["confirmAndRun"] } },
      },
      {
        displayName: "Stable Execution Key",
        name: "idempotency_key",
        type: "string",
        default: "",
        required: true,
        description: "Reuse the same key when you retry, so the work is never bought twice",
        displayOptions: { show: { operation: ["confirmAndRun"] } },
      },
    ],
  };

  async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
    const items = this.getInputData();
    const out: INodeExecutionData[] = [];
    const credentials = await this.getCredentials("specstreamApi");
    let base: string;
    try {
      base = resolveBase(credentials.apiBase) as string;
    } catch (error) {
      throw new NodeOperationError(this.getNode(), (error as Error).message);
    }

    for (let i = 0; i < items.length; i++) {
      const operation = this.getNodeParameter("operation", i) as string;
      const fail = (message: string) => new NodeOperationError(this.getNode(), message, { itemIndex: i });
      const call = async (method: IHttpRequestMethods, path: string, body?: IDataObject): Promise<IDataObject> => {
        let response: IDataObject | undefined;
        try {
          response = (await this.helpers.httpRequestWithAuthentication.call(this, "specstreamApi", {
            method,
            url: `${base}${path}`,
            headers: { Accept: "application/json" },
            body,
            json: true,
            disableFollowRedirect: true,
          })) as IDataObject | undefined;
        } catch (error) {
          throw new NodeOperationError(this.getNode(), error as Error, { itemIndex: i });
        }
        const data = response?.data as IDataObject | undefined;
        if (!response || response.error != null || !data || typeof data !== "object" || Array.isArray(data)) {
          throw fail("SpecStream returned a response this node could not read");
        }
        return data;
      };

      if (operation === "findList") {
        const q = String(this.getNodeParameter("request", i) || "").trim();
        const count = Math.floor(Number(this.getNodeParameter("count", i)));
        const maxCents = Math.round(Number(this.getNodeParameter("max_price_usd", i)) * 100);
        if (!q) throw fail("Describe the list to find");
        if (!Number.isSafeInteger(count) || count < 1) throw fail("Number of Results must be 1 or more");
        if (!Number.isSafeInteger(maxCents) || maxCents <= 0) throw fail("Set a Maximum Price above 0");
        const findOptions = this.getNodeParameter("findOptions", i, {}) as IDataObject;
        // Workflows saved before 1.1.6 kept Run Key at the top level.
        const given = String(findOptions.run_key ?? this.getNodeParameter("run_key", i, "") ?? "").trim();
        if (given && (given.length < 8 || given.length > 128)) throw fail("Run Key must be 8 to 128 characters");
        // A retry, even in a new execution, recovers the run it already started instead of buying the list again.
        const requestKey = runKey({ request: q, count, maxPrice: Number(this.getNodeParameter("max_price_usd", i)), override: given });
        let recovered: IDataObject | undefined;
        try {
          recovered = await call("GET", `/v1/capacity/requests/${encodeURIComponent(requestKey)}`);
        } catch {
          recovered = undefined;
        }
        if (recovered && recovered.find_id) {
          const listId = String(recovered.find_id);
          out.push({
            json: {
              list_id: listId,
              status: (recovered.state as string) || "running",
              request: q,
              number_of_results: count,
              maximum_price_usd: Number(recovered.maximum_cents || maxCents) / 100,
              list_link: `https://specstream.ai/workspace/collections/${listId}`,
            },
            pairedItem: { item: i },
          });
          continue;
        }
        const reading = await call("POST", "/v1/parse", { q, locale: "en-US" });
        if (reading.status !== "runnable") {
          throw fail(
            `SpecStream needs a clearer request before it can price it. It read: "${String(reading.read_back || reading.canonical_sentence || q)}". Add the place or what every row must meet.`,
          );
        }
        const quote = await call("POST", "/v1/capacity/quotes", {
          ast_hash: reading.ast_hash as string,
          operation: "find",
          requested_units: count,
        });
        const priceCents = Number(quote.maximum_cents);
        if (!(priceCents <= maxCents)) {
          throw fail(
            `This list can cost up to $${(priceCents / 100).toFixed(2)}, above your maximum of $${(maxCents / 100).toFixed(2)}. Raise the maximum or ask for fewer results.`,
          );
        }
        const run = await call("POST", "/v1/capacity/executions", {
          quote_id: quote.quote_id as string,
          quote_hash: quote.quote_hash as string,
          confirm_max_cents: priceCents,
          idempotency_key: requestKey,
        });
        const listId = String(run.find_id);
        out.push({
          json: {
            list_id: listId,
            status: run.state || run.status || "running",
            request: reading.read_back || reading.canonical_sentence || q,
            number_of_results: count,
            maximum_price_usd: priceCents / 100,
            list_link: `https://specstream.ai/workspace/collections/${listId}`,
          },
          pairedItem: { item: i },
        });
        continue;
      }

      if (operation === "getListRows") {
        const listId = String(this.getNodeParameter("list_id", i) || "").trim();
        const returnAll = this.getNodeParameter("returnAll", i, false) as boolean;
        const wanted = returnAll ? Infinity : Math.floor(Number(this.getNodeParameter("limit", i, 50)));
        if (!returnAll && (!Number.isSafeInteger(wanted) || wanted < 1)) throw fail("Limit must be 1 or more");
        let cursor = "";
        let returned = 0;
        // Each page holds up to 100 rows; follow next_cursor until the list ends or the limit is reached.
        for (let pages = 0; pages < 10000 && returned < wanted; pages++) {
          const pageSize = Math.min(100, wanted - returned);
          const query = `limit=${pageSize}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`;
          const page = await call("GET", `/v1/finds/${encodeURIComponent(listId)}/rows?${query}`);
          const rows = (page.rows as IDataObject[] | undefined) || [];
          const flat = flatRowsById(page.flat_rows as IDataObject[] | undefined);
          for (const record of rows) {
            if (returned >= wanted) break;
            const row = flattenRow(String(page.find_id), record, flat.get(`${String(page.find_id)}:${String(record.entity_id)}`));
            out.push({ json: { ...row, list_status: page.status as string }, pairedItem: { item: i } });
            returned++;
          }
          const next = page.next_cursor ? String(page.next_cursor) : "";
          if (!next || next === cursor || rows.length === 0) break;
          cursor = next;
        }
        continue;
      }
      let path = "";
      let method: IHttpRequestMethods = "GET";
      let body: IDataObject | undefined;

      if (operation === "compile") {
        method = "POST";
        path = "/v1/parse";
        body = {
          q: this.getNodeParameter("q", i) as string,
          locale: String((this.getNodeParameter("readOptions", i, {}) as IDataObject).locale ?? this.getNodeParameter("locale", i, "") ?? "") || "en-US",
        };
      } else if (operation === "quoteWork") {
        method = "POST";
        path = "/v1/capacity/quotes";
        body = {
          ast_hash: this.getNodeParameter("ast_hash", i) as string,
          operation: this.getNodeParameter("work_operation", i) as string,
          requested_units: this.getNodeParameter("requested_units", i) as number,
        };
        const workOperation = this.getNodeParameter("work_operation", i) as string;
        const parent = workOperation === "find" ? "" : String(this.getNodeParameter("parent_find_id", i, "") || "").trim();
        if (workOperation !== "find" && !parent) throw fail("Earlier Run ID is required to add results, add details or recheck");
        if (parent) body.parent_find_id = parent;
        const quoteOptions = this.getNodeParameter("quoteOptions", i, {}) as IDataObject;
        const project = String(quoteOptions.project_id ?? this.getNodeParameter("project_id", i, "") ?? "").trim();
        if (project) body.project_id = project;
      } else if (operation === "confirmAndRun") {
        let amount: number;
        try {
          amount = requireConfirmMaxUsd({ confirm_max_usd: this.getNodeParameter("confirm_max_usd", i) });
        } catch (error) {
          throw fail((error as Error).message);
        }
        const cents = Math.round(amount * 100);
        if (!Number.isSafeInteger(cents) || Math.abs(amount * 100 - cents) > 1e-7) {
          throw fail("Approve the exact maximum with at most two decimal places");
        }
        const quote_id = String(this.getNodeParameter("quote_id", i));
        const quote_hash = String(this.getNodeParameter("quote_hash", i));
        const idempotency_key = String(this.getNodeParameter("idempotency_key", i));
        if (
          !/^cqt_[a-z0-9_]+$/.test(quote_id) ||
          !/^[a-f0-9]{64}$/.test(quote_hash) ||
          idempotency_key.length < 8 ||
          idempotency_key.length > 128
        ) {
          throw fail("A reviewed quote and a stable execution key are required");
        }
        method = "POST";
        path = "/v1/capacity/executions";
        body = { quote_id, quote_hash, confirm_max_cents: cents, idempotency_key };
      } else {
        throw fail(`Unknown operation ${operation}`);
      }

      const data = await call(method, path, body);
      out.push({ json: data, pairedItem: { item: i } });
    }
    return [out];
  }
}
