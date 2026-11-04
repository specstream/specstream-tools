import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export const SERVER_NAME = "specstream";
export const MCP_URL = "https://api.specstream.ai/mcp";

const DESCRIPTION =
  "SpecStream, the live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web. Reading and pricing a request are free; paid work needs the person's approval of an exact maximum.";

// The flow that every list goes through stays visible to the model. The rest of the
// server's tools load on demand through tool_search.
const DIRECT_TOOLS = ["compile", "quote_capacity_work", "authorize_capacity_work", "get_find", "list_find_rows"];

/**
 * The server entry registered with Pi. Without a key Pi signs in with OAuth (`/mcp login specstream`).
 * With SPECSTREAM_API_KEY set the entry sends it as a Bearer header; the value stays a `${...}`
 * reference, so Pi reads the key from the environment when it connects and this file never holds it.
 */
export function serverConfig(env: Record<string, string | undefined> = process.env) {
  const useKey = Boolean(env.SPECSTREAM_API_KEY?.trim());
  return {
    url: MCP_URL,
    description: DESCRIPTION,
    exposure: "deferred" as const,
    toolExposure: Object.fromEntries(DIRECT_TOOLS.map((name) => [name, "direct" as const])),
    ...(useKey ? { headers: { Authorization: "Bearer ${SPECSTREAM_API_KEY}" } } : {}),
  };
}

export default function specstream(pi: ExtensionAPI) {
  // oh-my-pi (omp) has no registerMcpServer: there the package loads only its skills, and the
  // server comes from omp's mcp.json (integrations/omp/README.md). Without the guard omp rolls back the install.
  if (typeof pi.registerMcpServer === "function") pi.registerMcpServer(SERVER_NAME, serverConfig());
}
