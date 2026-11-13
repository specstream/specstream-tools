import type {
  IDataObject,
  IHookFunctions,
  INodeExecutionData,
  INodeType,
  INodeTypeDescription,
  IWebhookFunctions,
  IWebhookResponseData,
  JsonObject,
} from "n8n-workflow";
import { NodeApiError, NodeConnectionTypes, NodeOperationError } from "n8n-workflow";
import { createHmac, timingSafeEqual } from "node:crypto";
import { resolveBase } from "../../lib/base.js";

type Method = "GET" | "POST" | "DELETE";

const CREDENTIAL = "specstreamMonitorApi";
const EVENT = "monitor.found";

async function request(context: IHookFunctions, method: Method, path: string, body?: IDataObject): Promise<IDataObject> {
  const credentials = await context.getCredentials(CREDENTIAL);
  let base: string;
  try {
    base = resolveBase(credentials.apiBase) as string;
  } catch (error) {
    throw new NodeOperationError(context.getNode(), (error as Error).message);
  }
  const response = (await context.helpers.httpRequestWithAuthentication.call(context, CREDENTIAL, {
    method,
    url: base + path,
    headers: { Accept: "application/json" },
    body,
    json: true,
    disableFollowRedirect: true,
  })) as IDataObject | undefined;
  if (!response || response.error || !response.data) {
    throw new NodeApiError(context.getNode(), (response ?? {}) as JsonObject, {
      message: "SpecStream returned a response this node could not read",
    });
  }
  return response.data as IDataObject;
}

// A hook that is already gone (404) is fine; any other failure stops the step so nothing is left registered unseen.
async function removeHook(context: IHookFunctions, hookId: string): Promise<void> {
  try {
    await request(context, "DELETE", "/v1/account/webhooks/" + encodeURIComponent(hookId));
  } catch (error) {
    const text = String((error as Error).message) + String((error as { httpCode?: string }).httpCode);
    if (!/404|not found/i.test(text)) throw new NodeOperationError(context.getNode(), error as Error);
  }
}

export class SpecstreamMonitorTrigger implements INodeType {
  description: INodeTypeDescription = {
    displayName: "SpecStream Monitor Trigger",
    name: "specstreamMonitorTrigger",
    icon: { light: "file:specstream.svg", dark: "file:specstream.dark.svg" },
    group: ["trigger"],
    version: 1,
    subtitle: '={{$parameter["output"] === "event" ? "whole event" : "each record"}}',
    description: "Starts a workflow when a SpecStream monitor finds new or changed records on the live web",
    defaults: { name: "SpecStream Monitor Trigger" },
    inputs: [],
    outputs: [NodeConnectionTypes.Main],
    credentials: [{ name: CREDENTIAL, required: true }],
    webhooks: [
      { name: "default", httpMethod: "POST", responseMode: "onReceived", path: "specstream-monitor", isFullPath: false },
    ],
    properties: [
      {
        displayName: "Monitor ID",
        name: "monitorId",
        type: "string",
        default: "",
        description:
          "Start the workflow only for this monitor. Leave empty to start it for every monitor of your account. The ID is the schedule_id of the monitor.",
      },
      {
        displayName: "Output",
        name: "output",
        type: "options",
        default: "records",
        options: [
          {
            name: "Each Record",
            value: "records",
            description: "One item per new or changed record, with its fields, its source and whether it is new or changed",
          },
          {
            name: "Whole Event",
            value: "event",
            description: "One item with the event as SpecStream sent it",
          },
        ],
      },
    ],
  };

  webhookMethods = {
    default: {
      async checkExists(this: IHookFunctions): Promise<boolean> {
        const saved = this.getWorkflowStaticData("node");
        if (!saved.hook_id) return false;
        const result = await request(this, "GET", "/v1/account/webhooks");
        const hooks = (result.webhooks as IDataObject[] | undefined) ?? [];
        return hooks.some((hook) => hook.hook_id === saved.hook_id && !hook.revoked_at);
      },
      async create(this: IHookFunctions): Promise<boolean> {
        const saved = this.getWorkflowStaticData("node");
        if (saved.hook_id) {
          // Activating again leaves no old hook behind.
          await removeHook(this, String(saved.hook_id));
          delete saved.hook_id;
          delete saved.secret;
        }
        const result = await request(this, "POST", "/v1/account/webhooks", {
          url: this.getNodeWebhookUrl("default") as string,
          events: [EVENT],
        });
        if (!result.hook_id || !result.secret) {
          throw new NodeOperationError(this.getNode(), "Webhook registration was not confirmed");
        }
        saved.hook_id = result.hook_id;
        saved.secret = result.secret;
        return true;
      },
      async delete(this: IHookFunctions): Promise<boolean> {
        const saved = this.getWorkflowStaticData("node");
        if (saved.hook_id) {
          await removeHook(this, String(saved.hook_id));
        }
        delete saved.hook_id;
        delete saved.secret;
        return true;
      },
    },
  };

  async webhook(this: IWebhookFunctions): Promise<IWebhookResponseData> {
    const saved = this.getWorkflowStaticData("node");
    const headers = this.getHeaderData();
    const signature = /^t=(\d+),v1=([a-f0-9]{64})$/.exec(String(headers["specstream-signature"] || ""));
    const raw = (this.getRequestObject() as unknown as { rawBody?: Buffer | string }).rawBody;
    if (
      !signature ||
      !saved.secret ||
      (!Buffer.isBuffer(raw) && typeof raw !== "string") ||
      Math.abs(Date.now() / 1000 - Number(signature[1])) > 300
    ) {
      throw new NodeOperationError(this.getNode(), "Unverifiable SpecStream webhook; enable raw request bodies");
    }
    const expected = createHmac("sha256", String(saved.secret)).update(signature[1] + ".").update(raw).digest();
    if (!timingSafeEqual(expected, Buffer.from(signature[2], "hex"))) {
      throw new NodeOperationError(this.getNode(), "Invalid SpecStream signature");
    }
    const body = JSON.parse(raw.toString()) as IDataObject;
    if (body.event !== EVENT || !body.id) {
      throw new NodeOperationError(this.getNode(), "Unexpected SpecStream event");
    }
    // A signed event of another monitor is received and starts nothing.
    const monitorId = String(this.getNodeParameter("monitorId", "") || "").trim();
    if (monitorId && body.schedule_id !== monitorId) {
      return {};
    }
    if (this.getNodeParameter("output", "records") === "event") {
      return { workflowData: [[{ json: body }]] };
    }
    const fresh = new Set((body.new_ids as string[] | undefined) ?? []);
    const records = (body.records as IDataObject[] | undefined) ?? [];
    const items: INodeExecutionData[] = records.map((record) => ({
      json: {
        change: fresh.has(String(record.entity_id)) ? "new" : "changed",
        event_id: body.id,
        monitor_id: body.schedule_id ?? null,
        run_id: body.find_id ?? null,
        previous_run_id: body.previous_find_id ?? null,
        record,
      },
    }));
    if (!items.length) {
      return {};
    }
    return { workflowData: [items] };
  }
}
