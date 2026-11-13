import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export const SERVER_NAME = "specstream";
export const MCP_URL = "https://api.specstream.ai/mcp";

const DESCRIPTION =
  "SpecStream, the live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web. Reading and pricing a request are free; paid work needs the person's approval of an exact maximum.";

// The flow that every list and every research report goes through stays visible to the model.
// The rest of the server's tools load on demand through tool_search.
const DIRECT_TOOLS = [
  "search_web",
  "read_pages",
  "compile",
  "quote_capacity_work",
  "authorize_capacity_work",
  "get_find",
  "list_find_rows",
  "research_price",
  "start_research",
  "get_research",
];

export const RESEARCH_COMMAND = "research";
export const RESEARCH_DEPTHS = ["quick", "standard", "deep"] as const;
export type ResearchDepth = (typeof RESEARCH_DEPTHS)[number];

const RESEARCH_USAGE =
  "Usage: /research [quick|standard|deep] <question>. A report costs $0.10 (quick), $0.30 (standard) or $1.00 (deep), and nothing runs before you approve the price.";

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

/** Splits the text after `/research` into an optional depth (its first word) and the question. */
export function researchArgs(args: string): { depth: ResearchDepth; question: string } {
  const text = args.trim();
  const [first = "", ...rest] = text.split(/\s+/);
  const depth = RESEARCH_DEPTHS.find((name) => name === first.toLowerCase());
  // A question of one word that is also a depth name stays a question.
  if (depth && rest.length > 0) return { depth, question: text.slice(first.length).trim() };
  return { depth: "standard", question: text };
}

/**
 * The message `/research` sends as the person. The command never starts a report itself: the
 * price is approved in the conversation, so the person sees it before the balance is charged.
 */
export function researchPrompt(args: string): string | null {
  const { depth, question } = researchArgs(args);
  if (!question) return null;
  return [
    `Write a SpecStream research report (depth: ${depth}) that answers this question from the live web:`,
    "",
    question,
    "",
    "Use the SpecStream MCP server. Follow the specstream-research skill:",
    `1. Call research_price with {"depth": "${depth}"}. It is free.`,
    "2. Show me the depth and its price, and wait for my approval. Do not start anything before I approve.",
    "3. After I approve, call start_research with the question, the depth, my approved price as confirm_max_cents, and a new idempotency_key.",
    "4. Call get_research with the report's id until its status is completed.",
    "5. Give me the report text with its citation markers, and the page behind each citation.",
  ].join("\n");
}

export default function specstream(pi: ExtensionAPI) {
  // oh-my-pi (omp) has no registerMcpServer: there the package loads only its skills, and the
  // server comes from omp's mcp.json (integrations/omp/README.md). Without the guard omp rolls back the install.
  if (typeof pi.registerMcpServer === "function") pi.registerMcpServer(SERVER_NAME, serverConfig());
  if (typeof pi.registerCommand === "function" && typeof pi.sendUserMessage === "function") {
    pi.registerCommand(RESEARCH_COMMAND, {
      description: "SpecStream research report from the live web, with the page behind each cited sentence ($0.10, $0.30 or $1.00)",
      getArgumentCompletions: (prefix) =>
        prefix.includes(" ")
          ? null
          : RESEARCH_DEPTHS.filter((name) => name.startsWith(prefix.toLowerCase())).map((name) => ({ value: `${name} `, label: name })),
      handler: async (args, ctx) => {
        const prompt = researchPrompt(args);
        if (prompt === null) {
          ctx.ui.notify(RESEARCH_USAGE, "info");
          return;
        }
        // A message sent while the agent answers must say how it queues.
        pi.sendUserMessage(prompt, ctx.isIdle() ? undefined : { deliverAs: "followUp" });
      },
    });
  }
}
