import type {
  IBinaryKeyData,
  IDataObject,
  IExecuteFunctions,
  INodeExecutionData,
  INodeType,
  INodeTypeDescription,
  JsonObject,
} from "n8n-workflow";
import { NodeApiError, NodeConnectionTypes, NodeOperationError } from "n8n-workflow";
import { resolveBase } from "../../lib/base.js";

type Method = "GET" | "POST";

const CREDENTIAL = "specstreamBrowserApi";
const SESSIONS = "/v1/browser/sessions";
const LIST_PAGE = 100;

async function request(
  context: IExecuteFunctions,
  method: Method,
  path: string,
  body?: IDataObject,
  qs?: IDataObject,
): Promise<IDataObject> {
  const credentials = await context.getCredentials(CREDENTIAL);
  let base: string;
  try {
    base = resolveBase(credentials.apiBase) as string;
  } catch (error) {
    throw new NodeOperationError(context.getNode(), (error as Error).message);
  }
  let response: IDataObject | undefined;
  try {
    response = (await context.helpers.httpRequestWithAuthentication.call(context, CREDENTIAL, {
      method,
      url: base + path,
      headers: { Accept: "application/json" },
      body,
      qs,
      json: true,
      disableFollowRedirect: true,
    })) as IDataObject | undefined;
  } catch (error) {
    throw new NodeApiError(context.getNode(), error as JsonObject);
  }
  if (!response || response.error || !response.data) {
    throw new NodeApiError(context.getNode(), (response ?? {}) as JsonObject, {
      message: "SpecStream returned a response this node could not read",
    });
  }
  return response.data as IDataObject;
}

function sessionPath(context: IExecuteFunctions, item: number): string {
  const id = String(context.getNodeParameter("sessionId", item, "")).trim();
  if (!id) {
    throw new NodeOperationError(context.getNode(), "Session ID is empty. Use the id that the Open operation of Session returned.", {
      itemIndex: item,
    });
  }
  return `${SESSIONS}/${encodeURIComponent(id)}`;
}

function hosts(value: unknown): string[] {
  return String(value ?? "")
    .split(/[\s,]+/)
    .map((host) => host.trim())
    .filter((host) => host !== "");
}

function createBody(context: IExecuteFunctions, item: number): IDataObject {
  const options = context.getNodeParameter("sessionOptions", item, {}) as IDataObject;
  const body: IDataObject = {};
  if (options.timeoutS !== undefined) body.timeout_s = options.timeoutS;
  if (options.idleTimeoutS !== undefined) body.idle_timeout_s = options.idleTimeoutS;
  if (options.keepAlive !== undefined) body.keep_alive = options.keepAlive;
  if (options.blockMedia !== undefined) body.block_media = options.blockMedia;
  if (options.headless !== undefined) body.headless = options.headless;
  const allowed = hosts(options.allowedDomains);
  if (allowed.length) body.allowed_domains = allowed;
  return body;
}

function toolArguments(context: IExecuteFunctions, operation: string, item: number): { tool: string; arguments: IDataObject } {
  if (operation === "navigate") {
    return { tool: "browser_navigate", arguments: { url: context.getNodeParameter("url", item) as string } };
  }
  if (operation === "read") {
    return { tool: "browser_read", arguments: { format: context.getNodeParameter("format", item, "markdown") as string } };
  }
  if (operation === "snapshot") return { tool: "browser_snapshot", arguments: {} };
  if (operation === "screenshot") {
    return {
      tool: "browser_take_screenshot",
      arguments: { type: "png", fullPage: context.getNodeParameter("fullPage", item, false) as boolean },
    };
  }
  if (operation === "click") {
    return {
      tool: "browser_click",
      arguments: {
        element: context.getNodeParameter("element", item) as string,
        ref: context.getNodeParameter("ref", item) as string,
      },
    };
  }
  if (operation === "type") {
    return {
      tool: "browser_type",
      arguments: {
        element: context.getNodeParameter("element", item) as string,
        ref: context.getNodeParameter("ref", item) as string,
        text: context.getNodeParameter("text", item) as string,
        submit: context.getNodeParameter("submit", item, false) as boolean,
      },
    };
  }
  const tool = String(context.getNodeParameter("tool", item)).trim();
  if (!/^browser_[a-z][a-z0-9_]{0,62}$/.test(tool)) {
    throw new NodeOperationError(context.getNode(), "Tool must be a Playwright MCP tool name such as browser_press_key.", {
      itemIndex: item,
    });
  }
  const raw = context.getNodeParameter("toolArguments", item, "{}");
  let parsed: unknown;
  try {
    parsed = typeof raw === "string" ? JSON.parse(raw || "{}") : raw;
  } catch {
    parsed = null;
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new NodeOperationError(context.getNode(), "Arguments must be a JSON object, such as {\"key\": \"Enter\"}.", {
      itemIndex: item,
    });
  }
  return { tool, arguments: parsed as IDataObject };
}

// One step of a session: the text parts joined, each image as a binary file, and what the step cost.
async function step(
  context: IExecuteFunctions,
  path: string,
  call: { tool: string; arguments: IDataObject },
  item: number,
): Promise<INodeExecutionData> {
  const data = await request(context, "POST", `${path}/actions`, call as unknown as IDataObject);
  const failure = data.error as IDataObject | null | undefined;
  if (failure) {
    const reason = failure.reason ? ` (${String(failure.reason)})` : "";
    throw new NodeOperationError(context.getNode(), `${String(failure.message ?? failure.code)}${reason}`, {
      itemIndex: item,
    });
  }
  const parts = (data.result as IDataObject[] | undefined) ?? [];
  const text = parts
    .filter((part) => part.type === "text" && typeof part.text === "string")
    .map((part) => part.text as string)
    .join("\n");
  const json: IDataObject = {
    tool: call.tool,
    text,
    url: data.url ?? null,
    title: data.title ?? null,
    took_ms: data.took_ms ?? null,
    price_usd: data.price_usd ?? null,
  };
  if (data.read_at) json.read_at = data.read_at;
  const output: INodeExecutionData = { json, pairedItem: { item } };
  const images = parts.filter((part) => part.type === "image" && typeof part.data === "string");
  if (images.length) {
    const binary: IBinaryKeyData = {};
    for (const [index, image] of images.entries()) {
      const mime = typeof image.mime_type === "string" ? image.mime_type : "image/png";
      const name = `screenshot${index ? `_${index + 1}` : ""}.${mime === "image/jpeg" ? "jpg" : "png"}`;
      binary[index ? `data_${index + 1}` : "data"] = await context.helpers.prepareBinaryData(
        Buffer.from(image.data as string, "base64"),
        name,
        mime,
      );
    }
    output.binary = binary;
  }
  return output;
}

async function listSessions(context: IExecuteFunctions, item: number): Promise<IDataObject[]> {
  const all = context.getNodeParameter("returnAll", item, false) as boolean;
  const limit = all ? Infinity : (context.getNodeParameter("limit", item, 50) as number);
  const status = context.getNodeParameter("status", item, "") as string;
  const found: IDataObject[] = [];
  const seen = new Set<string>();
  let cursor: string | undefined;
  while (found.length < limit) {
    const qs: IDataObject = { limit: Math.min(LIST_PAGE, limit - found.length) };
    if (status) qs.status = status;
    if (cursor) qs.cursor = cursor;
    const page = await request(context, "GET", SESSIONS, undefined, qs);
    found.push(...((page.sessions as IDataObject[] | undefined) ?? []));
    const next = page.next_cursor as string | null | undefined;
    // A cursor that comes back twice would page forever.
    if (!next || seen.has(next)) break;
    seen.add(next);
    cursor = next;
  }
  return found.slice(0, limit);
}

// Opens a session, goes to the address, reads the page and always ends the session, so no browser keeps running.
async function readUrl(context: IExecuteFunctions, item: number): Promise<INodeExecutionData> {
  const url = context.getNodeParameter("url", item) as string;
  const format = context.getNodeParameter("format", item, "markdown") as string;
  const session = await request(context, "POST", SESSIONS, { ...createBody(context, item), keep_alive: true });
  const path = `${SESSIONS}/${encodeURIComponent(String(session.id))}`;
  let output: INodeExecutionData;
  try {
    await step(context, path, { tool: "browser_navigate", arguments: { url } }, item);
    output = await step(context, path, { tool: "browser_read", arguments: { format } }, item);
  } catch (error) {
    try {
      await request(context, "POST", `${path}/release`);
    } catch {
      // The session ends by its own idle timeout; the first failure is the one to report.
    }
    if (error instanceof NodeOperationError) {
      throw new NodeOperationError(context.getNode(), error.message, { itemIndex: item });
    }
    throw new NodeApiError(context.getNode(), error as JsonObject, { itemIndex: item });
  }
  const ended = await request(context, "POST", `${path}/release`);
  output.json.session_id = session.id as string;
  output.json.seconds = ended.seconds ?? null;
  output.json.actions = ended.actions ?? null;
  output.json.charged_usd = ended.charged_usd ?? null;
  return output;
}

const ON_SESSION = ["get", "release", "navigate", "read", "snapshot", "screenshot", "click", "type", "tool"];

export class SpecstreamBrowser implements INodeType {
  description: INodeTypeDescription = {
    displayName: "SpecStream Browser",
    name: "specstreamBrowser",
    icon: { light: "file:specstream.svg", dark: "file:specstream.dark.svg" },
    group: ["transform"],
    version: 1,
    subtitle: '={{$parameter["operation"]}}',
    description: "Opens a real browser in the cloud and drives it step by step: go to a page, read it, click, type, take a screenshot",
    defaults: { name: "SpecStream Browser" },
    usableAsTool: true,
    inputs: [NodeConnectionTypes.Main],
    outputs: [NodeConnectionTypes.Main],
    credentials: [{ name: CREDENTIAL, required: true }],
    properties: [
      {
        displayName: "Resource",
        name: "resource",
        type: "options",
        noDataExpression: true,
        options: [
          { name: "Page", value: "page", description: "A page in a browser: open it, read it, click, type, take a screenshot" },
          { name: "Session", value: "session", description: "A browser that runs in the cloud until you close it" },
        ],
        default: "page",
      },
      // Operation values are unique across the two resources, and every field below is shown by its operation.
      {
        displayName: "Operation",
        name: "operation",
        type: "options",
        noDataExpression: true,
        displayOptions: { show: { resource: ["page"] } },
        options: [
          {
            name: "Click",
            value: "click",
            description: "Click an element of the page",
            action: "Click an element",
          },
          {
            name: "Get Page Snapshot",
            value: "snapshot",
            description: "Read the elements of the page with the ref of each, for Click and Type",
            action: "Get the page snapshot",
          },
          {
            name: "Go to a Page",
            value: "navigate",
            description: "Open an address in the session",
            action: "Go to a page",
          },
          {
            name: "Read a Web Page",
            value: "readUrl",
            description: "Open a browser, go to an address, read the text of the page and close the browser, in one step",
            action: "Read a web page",
          },
          {
            name: "Read the Page",
            value: "read",
            description: "Read the text of the page that the session shows",
            action: "Read the page of a session",
          },
          {
            name: "Run a Tool",
            value: "tool",
            description: "Run any other Playwright MCP tool in the session, such as browser_press_key",
            action: "Run a tool",
          },
          {
            name: "Take a Screenshot",
            value: "screenshot",
            description: "Get a picture of the page as a file",
            action: "Take a screenshot",
          },
          {
            name: "Type",
            value: "type",
            description: "Type text into a field of the page",
            action: "Type text",
          },
        ],
        default: "readUrl",
      },
      {
        displayName: "Operation",
        name: "operation",
        type: "options",
        noDataExpression: true,
        displayOptions: { show: { resource: ["session"] } },
        options: [
          {
            name: "Close",
            value: "release",
            description: "End the session and stop its charge",
            action: "Close a session",
          },
          {
            name: "Get",
            value: "get",
            description: "Read the state of a session, its time, its steps and what it has cost",
            action: "Get a session",
          },
          {
            name: "Get Many",
            value: "getAll",
            description: "List the sessions of your account",
            action: "Get many sessions",
          },
          {
            name: "Open",
            value: "create",
            description: "Start a browser and get its ID for the next steps",
            action: "Open a session",
          },
        ],
        default: "create",
      },
      {
        displayName: "Session ID",
        name: "sessionId",
        type: "string",
        required: true,
        default: "",
        description: "The ID that the Open operation of Session returned",
        displayOptions: { show: { operation: ON_SESSION } },
      },
      {
        displayName: "URL",
        name: "url",
        type: "string",
        required: true,
        default: "",
        placeholder: "https://example.com",
        description: "The address of the page to open",
        displayOptions: { show: { operation: ["navigate", "readUrl"] } },
      },
      {
        displayName: "Format",
        name: "format",
        type: "options",
        default: "markdown",
        options: [
          { name: "Markdown", value: "markdown" },
          { name: "Plain Text", value: "text" },
        ],
        displayOptions: { show: { operation: ["read", "readUrl"] } },
      },
      {
        displayName: "Element",
        name: "element",
        type: "string",
        required: true,
        default: "",
        placeholder: "Sign in button",
        description: "What the element is, in a few words",
        displayOptions: { show: { operation: ["click", "type"] } },
      },
      {
        displayName: "Ref",
        name: "ref",
        type: "string",
        required: true,
        default: "",
        placeholder: "e12",
        description: "The ref of the element, from Get Page Snapshot",
        displayOptions: { show: { operation: ["click", "type"] } },
      },
      {
        displayName: "Text",
        name: "text",
        type: "string",
        required: true,
        default: "",
        description: "The text to type into the element",
        displayOptions: { show: { operation: ["type"] } },
      },
      {
        displayName: "Press Enter After",
        name: "submit",
        type: "boolean",
        default: false,
        description: "Whether to press Enter after the text",
        displayOptions: { show: { operation: ["type"] } },
      },
      {
        displayName: "Full Page",
        name: "fullPage",
        type: "boolean",
        default: false,
        description: "Whether to take the whole page and not only the part in view",
        displayOptions: { show: { operation: ["screenshot"] } },
      },
      {
        displayName: "Tool",
        name: "tool",
        type: "string",
        required: true,
        default: "",
        placeholder: "browser_press_key",
        description: "A Playwright MCP tool name. It starts with browser_.",
        displayOptions: { show: { operation: ["tool"] } },
      },
      {
        displayName: "Arguments",
        name: "toolArguments",
        type: "json",
        default: "{}",
        description: "The arguments of the tool as a JSON object, with the names Playwright MCP uses",
        displayOptions: { show: { operation: ["tool"] } },
      },
      {
        displayName: "Return All",
        name: "returnAll",
        type: "boolean",
        default: false,
        description: "Whether to return all results or only up to a given limit",
        displayOptions: { show: { operation: ["getAll"] } },
      },
      {
        displayName: "Limit",
        name: "limit",
        type: "number",
        typeOptions: { minValue: 1 },
        default: 50,
        description: "Max number of results to return",
        displayOptions: { show: { operation: ["getAll"], returnAll: [false] } },
      },
      {
        displayName: "Status",
        name: "status",
        type: "options",
        default: "",
        options: [
          { name: "Any", value: "" },
          { name: "Ended", value: "ended" },
          { name: "Running", value: "running" },
          { name: "Starting", value: "starting" },
        ],
        displayOptions: { show: { operation: ["getAll"] } },
      },
      {
        displayName: "Options",
        name: "sessionOptions",
        type: "collection",
        placeholder: "Add option",
        default: {},
        displayOptions: { show: { operation: ["create", "readUrl"] } },
        options: [
          {
            displayName: "Allowed Domains",
            name: "allowedDomains",
            type: "string",
            default: "",
            placeholder: "example.com, *.example.org",
            description: "Hosts the browser may open, separated by commas. Leave empty to allow every public host.",
          },
          {
            displayName: "Block Media",
            name: "blockMedia",
            type: "boolean",
            default: false,
            description: "Whether to skip images, video, audio and fonts, so pages load faster",
          },
          {
            displayName: "Headless",
            name: "headless",
            type: "boolean",
            default: true,
            description: "Whether the browser runs without a screen. Turn it off for sites that act differently without one.",
          },
          {
            displayName: "Idle Timeout (Seconds)",
            name: "idleTimeoutS",
            type: "number",
            typeOptions: { minValue: 10, maxValue: 600 },
            default: 60,
            description: "The session ends after this many seconds with no step and no client connected",
          },
          {
            displayName: "Keep Alive",
            name: "keepAlive",
            type: "boolean",
            default: false,
            description: "Whether the session stays open when a client that drives it over its connect_url disconnects",
          },
          {
            displayName: "Timeout (Seconds)",
            name: "timeoutS",
            type: "number",
            typeOptions: { minValue: 60, maxValue: 3600 },
            default: 300,
            description: "The most seconds the session runs. It ends then in every case.",
          },
        ],
      },
    ],
  };

  async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
    const items = this.getInputData();
    const output: INodeExecutionData[] = [];
    for (let item = 0; item < items.length; item++) {
      try {
        const operation = this.getNodeParameter("operation", item) as string;
        if (operation === "readUrl") {
          output.push(await readUrl(this, item));
        } else if (operation === "create") {
          output.push({ json: await request(this, "POST", SESSIONS, createBody(this, item)), pairedItem: { item } });
        } else if (operation === "getAll") {
          for (const session of await listSessions(this, item)) output.push({ json: session, pairedItem: { item } });
        } else if (operation === "get") {
          output.push({ json: await request(this, "GET", sessionPath(this, item)), pairedItem: { item } });
        } else if (operation === "release") {
          output.push({ json: await request(this, "POST", `${sessionPath(this, item)}/release`), pairedItem: { item } });
        } else {
          const path = sessionPath(this, item);
          const result = await step(this, path, toolArguments(this, operation, item), item);
          result.json.session_id = String(this.getNodeParameter("sessionId", item)).trim();
          output.push(result);
        }
      } catch (error) {
        if (this.continueOnFail()) {
          output.push({ json: { error: (error as Error).message }, pairedItem: { item } });
          continue;
        }
        if (error instanceof NodeOperationError) {
          throw new NodeOperationError(this.getNode(), error.message, { itemIndex: item });
        }
        throw new NodeApiError(this.getNode(), error as JsonObject, { itemIndex: item });
      }
    }
    return [output];
  }
}
