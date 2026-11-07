import { Type } from "typebox";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";
import { SpecStreamClient, MAX_RESULTS } from "./client.js";
import { clampResults, effectiveCeiling, resolveConfig, DEFAULT_MAX_PRICE_USD, type PluginConfig } from "./config.js";

const configSchema = Type.Object(
  {
    apiKey: Type.Optional(
      Type.Union([Type.String(), Type.Record(Type.String(), Type.Unknown())], {
        description: "SpecStream API key, or a SecretRef. Falls back to the SPECSTREAM_API_KEY environment variable.",
      }),
    ),
    maxPriceUsd: Type.Optional(
      Type.Number({
        exclusiveMinimum: 0,
        description: `The most one list may cost, in US dollars. Defaults to ${DEFAULT_MAX_PRICE_USD}. The model can lower it per call and never raise it.`,
      }),
    ),
    waitSeconds: Type.Optional(
      Type.Integer({ minimum: 10, maximum: 900, description: "How long specstream_find_list waits for a running list. Defaults to 300." }),
    ),
  },
  { additionalProperties: false },
);

const entry = defineToolPlugin({
  id: "specstream",
  name: "SpecStream",
  description: "The live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web. Source URL and read time on every value.",
  activation: { onStartup: false },
  configSchema,
  tools: (tool) => [
    tool({
      name: "specstream_web_search",
      label: "Search the web",
      description: [
        "Search the live web in seconds with the SpecStream Search API (GET /v1/web-search, $5 per 1,000 searches, no quote needed).",
        "Use it for a single fact, a question with sources, or to see the first rows of a request before pricing a full Deep Search dataset.",
        "Returns JSON with kind ('fact' or 'list'), answer (value, page and seen_at), rows, ranked sources, and optional page passages.",
      ].join(" "),
      parameters: Type.Object({
        q: Type.String({
          minLength: 1,
          maxLength: 2000,
          description: "The search question or request in everyday words (1 to 2,000 characters). Quoted phrases are searched as phrases.",
        }),
        passages: Type.Optional(
          Type.Boolean({
            description: "Set true to include the main text passages of the top matching pages in the response.",
          }),
        ),
      }),
      execute: async ({ q, passages }, config, { signal }) => {
        const settings = resolveConfig(config);
        const client = new SpecStreamClient({ apiKey: settings.apiKey });
        return client.webSearch(q, { passages, abortSignal: signal });
      },
    }),
    tool({
      name: "specstream_extract_pages",
      label: "Extract pages",
      description: [
        "Read the main text, title and published date of 1 to 20 web pages, PDFs, Word documents or Excel spreadsheets live with the SpecStream Extract API (POST /v1/extract, $0.80 per 1,000 pages).",
        "A page that returns no text is not charged, and no quote or approval is needed.",
        "Returns JSON with results (one entry per URL: url, status, title, published, read_from and text), took_ms and price_usd.",
      ].join(" "),
      parameters: Type.Object({
        urls: Type.Array(Type.String({ minLength: 1 }), {
          minItems: 1,
          maxItems: 20,
          description: "1 to 20 http or https URLs to read live.",
        }),
        format: Type.Optional(
          Type.Union([Type.Literal("markdown"), Type.Literal("text")], {
            description: 'Output format: "markdown" (default, keeps headings, lists and links) or "text".',
          }),
        ),
      }),
      execute: async ({ urls, format }, config, { signal }) => {
        const settings = resolveConfig(config);
        const client = new SpecStreamClient({ apiKey: settings.apiKey });
        return client.extractPages(urls, { format, abortSignal: signal });
      },
    }),
    tool({
      name: "specstream_find_list",
      label: "Find a list",
      description: [
        "Find a list of real things on the live web and return every matching row, each with the page it was read from.",
        "Use it when the answer is many things that meet conditions: companies in a city, local businesses with a service, funding filings, open grants, tenders, clinical trials, repositories, people in a role.",
        "For one fact or a summary of one page, use a search tool instead.",
        "It is priced per match. Rows that could not be confirmed are left out and not charged. The run starts only if the quoted maximum is within the user's price ceiling.",
        "Returns JSON with state, list_id, list_link and rows (one object per match: its columns, source_url and checked_at).",
        'state "over_maximum" means nothing ran because the price was above the ceiling: ask for fewer rows or tell the user.',
        'state "needs_edit" means the request was too vague to price: add the place or the conditions.',
        "If the list is still running, call specstream_get_list_rows with its list_id for the rest.",
      ].join(" "),
      parameters: Type.Object({
        request: Type.String({
          minLength: 1,
          description:
            "The list in plain words: what to find, where, what every row must meet, and the facts to bring back. " +
            'Example: "Dental clinics in Lisbon with online booking, with their website and phone".',
        }),
        max_results: Type.Optional(
          Type.Integer({
            minimum: 1,
            maximum: MAX_RESULTS,
            description: "How many rows to find, 1 to 1000. Defaults to 25. Ask for what the task needs, because the price grows with the matches.",
          }),
        ),
        max_price_usd: Type.Optional(
          Type.Number({
            exclusiveMinimum: 0,
            description: "A lower price ceiling for this call, in US dollars. A value above the user's configured ceiling is ignored.",
          }),
        ),
      }),
      execute: async ({ request, max_results, max_price_usd }, config, { signal }) => {
        const settings = resolveConfig(config);
        const client = new SpecStreamClient({ apiKey: settings.apiKey });
        return client.findList(request, {
          maxResults: clampResults(max_results),
          maxPriceUsd: effectiveCeiling(settings.maxPriceUsd, max_price_usd),
          waitSeconds: settings.waitSeconds,
          abortSignal: signal,
        });
      },
    }),
    tool({
      name: "specstream_get_list_rows",
      label: "Read list rows",
      description: [
        "Read every row found so far for a SpecStream list the user already owns, such as one that was still running. Reading is free.",
        "Returns JSON with state, list_id, list_link and rows, each with its columns, source_url and checked_at.",
      ].join(" "),
      parameters: Type.Object({
        list_id: Type.String({
          minLength: 1,
          description: 'The list_id that specstream_find_list returned, like "fnd_gk5y3d0r97bvyz0t08zzh75kr6".',
        }),
      }),
      execute: async ({ list_id }, config, { signal }) => {
        const settings = resolveConfig(config);
        return new SpecStreamClient({ apiKey: settings.apiKey }).results(list_id.trim(), signal);
      },
    }),
  ],
});

type ProviderContext = { pluginConfig?: PluginConfig };
type PluginRegistrationApi = Parameters<typeof entry.register>[0] & {
  pluginConfig?: PluginConfig;
  registerWebSearchProvider?: (provider: Record<string, unknown>) => void;
  registerWebFetchProvider?: (provider: Record<string, unknown>) => void;
};

const baseRegister = entry.register.bind(entry);
entry.register = (api: PluginRegistrationApi) => {
  baseRegister(api);
  if (typeof api?.registerWebSearchProvider === "function") {
    api.registerWebSearchProvider({
      id: "specstream",
      label: "SpecStream Search",
      hint: "The most accurate web search API in the world ($5 per 1,000 searches, source URL and read time on every value)",
      onboardingScopes: ["text-inference"],
      credentialLabel: "SpecStream API key",
      envVars: ["SPECSTREAM_API_KEY"],
      placeholder: "ss_live_...",
      signupUrl: "https://specstream.ai/search-api?utm_source=openclaw",
      docsUrl: "https://specstream.ai/docs/api?utm_source=openclaw",
      autoDetectOrder: 55,
      credentialPath: "plugins.entries.specstream.config.apiKey",
      createTool: (ctx?: ProviderContext) => ({
        description:
          "Search the live web with the SpecStream Search API. Returns an answer with its source URL and read time, matching rows, ranked sources and optional page passages.",
        parameters: {
          type: "object",
          properties: {
            query: { type: "string", description: "Search query in everyday words." },
            passages: { type: "boolean", description: "Include main text passages from the closest pages." },
          },
          required: ["query"],
          additionalProperties: false,
        },
        execute: async (args: Record<string, unknown>, context?: { signal?: AbortSignal }) => {
          context?.signal?.throwIfAborted();
          const settings = resolveConfig(ctx?.pluginConfig ?? api?.pluginConfig);
          const client = new SpecStreamClient({ apiKey: settings.apiKey });
          return client.webSearch(String(args?.query ?? ""), {
            passages: args?.passages === true,
            abortSignal: context?.signal,
          });
        },
      }),
    });
  }
  if (typeof api?.registerWebFetchProvider === "function") {
    api.registerWebFetchProvider({
      id: "specstream",
      label: "SpecStream Extract",
      hint: "Read the main text of web pages, PDFs, Word and Excel files live ($0.80 per 1,000 pages, empty pages free)",
      credentialLabel: "SpecStream API key",
      envVars: ["SPECSTREAM_API_KEY"],
      placeholder: "ss_live_...",
      signupUrl: "https://specstream.ai/extract-api?utm_source=openclaw",
      docsUrl: "https://specstream.ai/docs/api?utm_source=openclaw",
      credentialPath: "plugins.entries.specstream.config.apiKey",
      createTool: (ctx?: ProviderContext) => ({
        description: "Extract the clean main text, title and published date of a URL using the SpecStream Extract API.",
        parameters: {
          type: "object",
          properties: {
            url: { type: "string", description: "HTTP or HTTPS URL to read live." },
            extractMode: { type: "string", enum: ["markdown", "text"], description: 'Output format ("markdown" or "text").' },
          },
          required: ["url"],
          additionalProperties: false,
        },
        execute: async (args: Record<string, unknown>, context?: { signal?: AbortSignal }) => {
          context?.signal?.throwIfAborted();
          const settings = resolveConfig(ctx?.pluginConfig ?? api?.pluginConfig);
          const client = new SpecStreamClient({ apiKey: settings.apiKey });
          return client.extractPages([String(args?.url ?? "")], {
            format: args?.extractMode === "text" ? "text" : "markdown",
            abortSignal: context?.signal,
          });
        },
      }),
    });
  }
};
export default entry;
