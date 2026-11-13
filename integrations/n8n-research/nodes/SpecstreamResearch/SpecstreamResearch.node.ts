import type {
  IDataObject,
  IExecuteFunctions,
  INodeExecutionData,
  INodeType,
  INodeTypeDescription,
  JsonObject,
} from "n8n-workflow";
import { NodeApiError, NodeConnectionTypes, NodeOperationError, sleep } from "n8n-workflow";
import { resolveBase } from "../../lib/base.js";
import { endedWithoutReport, hasEnded, idempotencyKey, reportBody } from "../../lib/report.js";

type Method = "GET" | "POST";

const CREDENTIAL = "specstreamResearchApi";
const LIST_MOST = 100;

async function request(
  context: IExecuteFunctions,
  base: string,
  method: Method,
  path: string,
  extra: { body?: IDataObject; qs?: IDataObject; headers?: IDataObject } = {},
): Promise<IDataObject> {
  const response = (await context.helpers.httpRequestWithAuthentication.call(context, CREDENTIAL, {
    method,
    url: base + path,
    headers: { Accept: "application/json", ...(extra.headers ?? {}) },
    body: extra.body,
    qs: extra.qs,
    json: true,
    disableFollowRedirect: true,
  })) as IDataObject | undefined;
  if (!response || typeof response !== "object" || Array.isArray(response)) {
    throw new NodeApiError(context.getNode(), {} as JsonObject, {
      message: "SpecStream returned a response this node could not read",
    });
  }
  return response;
}

function reportPath(context: IExecuteFunctions, itemIndex: number): string {
  const id = String(context.getNodeParameter("reportId", itemIndex, "")).trim();
  if (!id) throw new NodeOperationError(context.getNode(), "Enter the report ID.", { itemIndex });
  return "/v1/research/" + encodeURIComponent(id);
}

// Reads the report until it ends or the wait is over. A report that is still running after the wait is not lost:
// the error names its ID, and Get a Report reads it later.
async function waitForReport(
  context: IExecuteFunctions,
  base: string,
  id: string,
  waitMinutes: number,
  everySeconds: number,
  itemIndex: number,
): Promise<IDataObject> {
  const path = "/v1/research/" + encodeURIComponent(id);
  const until = Date.now() + Math.max(1, waitMinutes) * 60_000;
  const pause = Math.max(1, everySeconds) * 1000;
  for (;;) {
    const run = await request(context, base, "GET", path);
    if (hasEnded(run)) {
      if (run.status !== "completed") {
        throw new NodeOperationError(context.getNode(), endedWithoutReport(run) as string, { itemIndex });
      }
      return run;
    }
    if (Date.now() + pause > until) {
      throw new NodeOperationError(
        context.getNode(),
        `Report ${id} is still being written after ${waitMinutes} minutes. Read it later with the Get a Report operation.`,
        { itemIndex },
      );
    }
    await sleep(pause);
  }
}

export class SpecstreamResearch implements INodeType {
  description: INodeTypeDescription = {
    displayName: "SpecStream Research",
    name: "specstreamResearch",
    icon: { light: "file:specstream.svg", dark: "file:specstream.dark.svg" },
    group: ["transform"],
    version: 1,
    subtitle: '={{$parameter["operation"]}}',
    description: "Write a research report from the live web, with the page behind each cited sentence",
    defaults: { name: "SpecStream Research" },
    usableAsTool: true,
    inputs: [NodeConnectionTypes.Main],
    outputs: [NodeConnectionTypes.Main],
    credentials: [{ name: CREDENTIAL, required: true }],
    properties: [
      {
        displayName: "Operation",
        name: "operation",
        type: "options",
        noDataExpression: true,
        default: "write",
        options: [
          {
            name: "Cancel a Report",
            value: "cancel",
            description: "Stop a report that is being written. A cancelled report is not charged.",
            action: "Cancel a report",
          },
          {
            name: "Get a Report",
            value: "get",
            description: "Read a report by its ID. Reading is free.",
            action: "Get a report",
          },
          {
            name: "Get Many Reports",
            value: "getMany",
            description: "List the reports of your account, newest first. Listing is free.",
            action: "Get many reports",
          },
          {
            name: "Write a Report",
            value: "write",
            description: "Answer a question with a written report from the live web",
            action: "Write a report",
          },
        ],
      },
      {
        displayName: "Question",
        name: "input",
        type: "string",
        typeOptions: { rows: 4 },
        default: "",
        required: true,
        placeholder: "How do the five largest US grocery chains price their delivery subscriptions?",
        description: "The question the report answers, in plain words. Up to 15,000 characters.",
        displayOptions: { show: { operation: ["write"] } },
      },
      {
        displayName: "Depth",
        name: "depth",
        type: "options",
        default: "standard",
        description:
          "How far the report goes, which sets its price. The price is taken from your balance once, when the report is delivered.",
        options: [
          { name: "Quick ($0.10 a Report, About a Minute)", value: "quick" },
          { name: "Standard ($0.30 a Report, About Four Minutes)", value: "standard" },
          { name: "Deep ($1.00 a Report, About Five Minutes)", value: "deep" },
        ],
        displayOptions: { show: { operation: ["write"] } },
      },
      {
        displayName: "Wait for the Report",
        name: "wait",
        type: "boolean",
        default: true,
        description:
          "Whether the step waits until the report is written and returns it. Turn off to return the report ID at once and read the report later.",
        displayOptions: { show: { operation: ["write"] } },
      },
      {
        displayName: "Report ID",
        name: "reportId",
        type: "string",
        default: "",
        required: true,
        description: "The ID that Write a Report returned",
        displayOptions: { show: { operation: ["get", "cancel"] } },
      },
      {
        displayName: "Limit",
        name: "limit",
        type: "number",
        typeOptions: { minValue: 1, maxValue: LIST_MOST },
        default: 50,
        description: "Max number of results to return",
        displayOptions: { show: { operation: ["getMany"] } },
      },
      {
        displayName: "Options",
        name: "options",
        type: "collection",
        placeholder: "Add option",
        default: {},
        displayOptions: { show: { operation: ["write"] } },
        options: [
          {
            displayName: "Check Every (Seconds)",
            name: "everySeconds",
            type: "number",
            typeOptions: { minValue: 1, maxValue: 60 },
            default: 5,
            description: "How often the step reads the report while it waits",
          },
          {
            displayName: "Exclude Domains",
            name: "excludeDomains",
            type: "string",
            default: "",
            placeholder: "example.com, example.org",
            description: "Sites the report must not read, separated by commas",
          },
          {
            displayName: "Include Domains",
            name: "includeDomains",
            type: "string",
            default: "",
            placeholder: "example.com, example.org",
            description: "The only sites the report reads, separated by commas",
          },
          {
            displayName: "JSON Schema",
            name: "jsonSchema",
            type: "json",
            default: "",
            description:
              "A JSON Schema for the answer. When set, the report also returns the answer as JSON in this shape, in report.structured.",
          },
          {
            displayName: "Language",
            name: "language",
            type: "string",
            default: "",
            placeholder: "fr",
            description: "The language of the report, as a language code such as en, fr or pt-BR",
          },
          {
            displayName: "Length",
            name: "length",
            type: "options",
            default: "standard",
            options: [
              { name: "Short", value: "short" },
              { name: "Standard", value: "standard" },
              { name: "Long", value: "long" },
            ],
          },
          {
            displayName: "Pages Published After",
            name: "afterDate",
            type: "dateTime",
            default: "",
            description: "Read only pages published after this day",
          },
          {
            displayName: "Wait Up To (Minutes)",
            name: "waitMinutes",
            type: "number",
            typeOptions: { minValue: 1, maxValue: 60 },
            default: 15,
            description: "The longest the step waits for the report before it stops with the report ID",
          },
        ],
      },
    ],
  };

  async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
    const items = this.getInputData();
    const out: INodeExecutionData[] = [];
    const credentials = await this.getCredentials(CREDENTIAL);
    let base: string;
    try {
      base = resolveBase(credentials.apiBase) as string;
    } catch (error) {
      throw new NodeOperationError(this.getNode(), (error as Error).message);
    }

    for (let i = 0; i < items.length; i++) {
      try {
        const operation = this.getNodeParameter("operation", i) as string;
        if (operation === "write") {
          const options = this.getNodeParameter("options", i, {}) as IDataObject;
          let body: IDataObject;
          try {
            body = reportBody(this.getNodeParameter("input", i), this.getNodeParameter("depth", i, "standard"), options) as IDataObject;
          } catch (error) {
            throw new NodeOperationError(this.getNode(), (error as Error).message, { itemIndex: i });
          }
          const key = idempotencyKey(this.getExecutionId(), this.getNode().id, i) as string;
          const created = await request(this, base, "POST", "/v1/research", { body, headers: { "Idempotency-Key": key } });
          if (!created.id) {
            throw new NodeApiError(this.getNode(), created as JsonObject, {
              message: "SpecStream started no report",
              itemIndex: i,
            });
          }
          if (!this.getNodeParameter("wait", i, true)) {
            out.push({ json: created, pairedItem: { item: i } });
            continue;
          }
          const run = await waitForReport(
            this,
            base,
            String(created.id),
            Number(options.waitMinutes ?? 15),
            Number(options.everySeconds ?? 5),
            i,
          );
          out.push({ json: run, pairedItem: { item: i } });
        } else if (operation === "get") {
          out.push({ json: await request(this, base, "GET", reportPath(this, i)), pairedItem: { item: i } });
        } else if (operation === "cancel") {
          out.push({ json: await request(this, base, "POST", reportPath(this, i) + "/cancel"), pairedItem: { item: i } });
        } else if (operation === "getMany") {
          const limit = Math.min(LIST_MOST, Math.max(1, Number(this.getNodeParameter("limit", i, 50))));
          const page = await request(this, base, "GET", "/v1/research", { qs: { limit } });
          for (const run of (page.data as IDataObject[] | undefined) ?? []) {
            out.push({ json: run, pairedItem: { item: i } });
          }
        } else {
          throw new NodeOperationError(this.getNode(), `Unknown operation: ${operation}`, { itemIndex: i });
        }
      } catch (error) {
        if (this.continueOnFail()) {
          out.push({ json: { error: (error as Error).message }, pairedItem: { item: i } });
          continue;
        }
        if (error instanceof NodeOperationError) {
          throw new NodeOperationError(this.getNode(), error.message, { itemIndex: i });
        }
        throw new NodeApiError(this.getNode(), error as JsonObject, { itemIndex: i });
      }
    }
    return [out];
  }
}
