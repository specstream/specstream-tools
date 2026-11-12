import { tool } from "ai";
import { z } from "zod";
import {
  DEFAULT_BASE_URL,
  DEFAULT_LOCALE,
  DEFAULT_POLL_INTERVAL_SECONDS,
  DEFAULT_WAIT_SECONDS,
  MAX_RESULTS,
  MISSING_KEY_MESSAGE,
  SpecStreamClient,
  type FindListResult,
  type ListResults,
  type Monitor,
  type MonitorEvery,
  type MonitorListResult,
} from "./client.js";

export type SpecStreamToolsOptions = {
  /** The most one list may cost, in US dollars. Set in code; the model can't see it or raise it. Above it, nothing runs. */
  maxPriceUsd: number;
  /** A SpecStream API key. Defaults to the SPECSTREAM_API_KEY environment variable. */
  apiKey?: string;
  /** The SpecStream API address. */
  baseUrl?: string;
  /** How long `specstream_find_list` waits for the list before returning the rows found so far. Defaults to 420. */
  waitSeconds?: number;
  /** Seconds between checks while a list is running. Defaults to 3. */
  pollIntervalSeconds?: number;
  /** The language and region the request is written in. Defaults to "en-US". */
  locale?: string;
  /** Replaces the global fetch. */
  fetch?: typeof fetch;
  /**
   * The most one check of a monitored list may cost, in US dollars. Set it to give the model
   * `specstream_monitor_list` and `specstream_list_monitors`. Without it, the model can't start recurring work.
   */
  monitorMaxPricePerRunUsd?: number;
  /** The most one monitor may spend in a UTC calendar month. Defaults to the per-check maximum times the checks in 31 days. */
  monitorMaxPricePerMonthUsd?: number;
};

const findListInput = z.object({
  request: z
    .string()
    .min(1)
    .describe(
      "The list in plain words: what to find, where, what every row must meet, and the facts to bring back. " +
        'Example: "Dental clinics in Lisbon with online booking, with their website and phone".',
    ),
  maxResults: z
    .number()
    .int()
    .min(1)
    .max(MAX_RESULTS)
    .default(25)
    .describe("How many rows to find, from 1 to 1000. Ask for what the task needs; the price grows with the matches."),
});

const getListResultsInput = z.object({
  listId: z.string().min(1).describe('The list_id that specstream_find_list returned, like "fnd_gk5y3d0r97bvyz0t08zzh75kr6".'),
});

const webSearchInput = z.object({
  q: z.string().min(1).max(2000).describe("The search question or request in everyday words (1 to 2,000 characters). Quoted phrases are searched as phrases."),
  passages: z.boolean().optional().describe("Set true to include the main text passages of the top matching pages in the response."),
});

const extractPagesInput = z.object({
  urls: z.array(z.string().min(1)).min(1).max(20).describe("1 to 20 http or https URLs (web pages, PDF, Word, Excel) to read live."),
  format: z.enum(["markdown", "text"]).optional().describe('Output format: "markdown" (default) or "text".'),
});

const monitorListInput = z.object({
  listId: z.string().min(1).describe('The list_id of the list to keep current, like "fnd_gk5y3d0r97bvyz0t08zzh75kr6".'),
  every: z
    .enum(["hour", "day", "week", "month"])
    .default("day")
    .describe('How often to check the list again: "hour", "day" (default), "week" or "month".'),
});

const MONITOR_LIST_DESCRIPTION = [
  "Keep a SpecStream list current: check its rows again on the live web every hour, day, week or month.",
  "Use it only when the user asks to watch or monitor a list. Each check is billed, within a maximum per check and per month set in code.",
  'Returns JSON with status "saved", monitor_id, state and next_run_at.',
  'status "over_maximum" means nothing was saved because one check costs more than the maximum: tell the user.',
].join(" ");

const LIST_MONITORS_DESCRIPTION =
  "List the account's SpecStream monitors: the list each one checks, its state, how often, the next check and the last list it made. Reading is free.";

const FIND_LIST_DESCRIPTION = [
  "Find a list of real things on the live web and return every matching row, each with the page it was read from.",
  "Use it when the answer is many things that meet conditions: companies in a city, local businesses with a service, funding filings, open grants, tenders, clinical trials, repositories, people in a role.",
  "For one fact or a summary of one page, use a search tool instead.",
  "Rows that couldn't be confirmed are left out and aren't charged.",
  "Returns JSON with status, list_id, list_link and rows (one object per match: its columns, source_url and checked_at).",
  'status "over_maximum" means nothing ran because the price was above the cap: ask for fewer rows or tell the user.',
  'status "needs_edit" means the request was too vague to price: add the place or the conditions.',
  "If the list is still running, call specstream_get_list_results with its list_id for the rest.",
].join(" ");

const GET_LIST_RESULTS_DESCRIPTION = [
  "Read every row found so far for a SpecStream list, such as one that was still running. Reading is free.",
  "Returns JSON with status, list_id, list_link and rows, each with its columns, source_url and checked_at.",
].join(" ");

function baseTools(client: SpecStreamClient, options: SpecStreamToolsOptions) {
  const { maxPriceUsd } = options;
  return {
    specstream_web_search: tool({
      description:
        "Search the live web in seconds with the SpecStream Search API (GET /v1/web-search, $5 per 1,000 searches of up to 10 results, or $1 on the fast tier, no quote needed). " +
        "Returns JSON with kind ('fact' or 'list'), answer (value, page and seen_at), matching rows, ranked sources and optional passages.",
      inputSchema: webSearchInput,
      execute: async ({ q, passages }, { abortSignal }) => client.webSearch(q, { passages, abortSignal }),
    }),
    specstream_extract_pages: tool({
      description:
        "Read the main text, title and published date of 1 to 20 web pages, PDFs, Word or Excel files live with the SpecStream Extract API " +
        "(POST /v1/extract, $0.80 per 1,000 pages, empty pages free, no quote needed).",
      inputSchema: extractPagesInput,
      execute: async ({ urls, format }, { abortSignal }) => client.extractPages(urls, { format, abortSignal }),
    }),
    specstream_find_list: tool({
      description: FIND_LIST_DESCRIPTION,
      inputSchema: findListInput,
      execute: async ({ request, maxResults }, { abortSignal }): Promise<FindListResult> =>
        client.findList(request, {
          maxResults: Math.max(1, Math.min(Math.trunc(Number(maxResults ?? 25)) || 25, MAX_RESULTS)),
          maxPriceUsd,
          waitSeconds: options.waitSeconds ?? DEFAULT_WAIT_SECONDS,
          pollIntervalSeconds: options.pollIntervalSeconds ?? DEFAULT_POLL_INTERVAL_SECONDS,
          locale: options.locale ?? DEFAULT_LOCALE,
          abortSignal,
        }),
    }),
    specstream_get_list_results: tool({
      description: GET_LIST_RESULTS_DESCRIPTION,
      inputSchema: getListResultsInput,
      execute: async ({ listId }, { abortSignal }): Promise<ListResults> => client.results(listId.trim(), abortSignal),
    }),
  };
}

function monitorTools(client: SpecStreamClient, maxPricePerRunUsd: number, maxPricePerMonthUsd: number | undefined) {
  return {
    specstream_monitor_list: tool({
      description: MONITOR_LIST_DESCRIPTION,
      inputSchema: monitorListInput,
      execute: async ({ listId, every }, { abortSignal }): Promise<MonitorListResult> =>
        client.monitorList(listId, { every: (every ?? "day") as MonitorEvery, maxPricePerRunUsd, maxPricePerMonthUsd, abortSignal }),
    }),
    specstream_list_monitors: tool({
      description: LIST_MONITORS_DESCRIPTION,
      inputSchema: z.object({}),
      execute: async (_input, { abortSignal }): Promise<Monitor[]> => client.monitors(abortSignal),
    }),
  };
}

/** The four tools every agent gets. */
export type SpecStreamBaseTools = ReturnType<typeof baseTools>;
/** The two monitor tools, there only when `monitorMaxPricePerRunUsd` is set. */
export type SpecStreamMonitorTools = ReturnType<typeof monitorTools>;

/**
 * The SpecStream tools for an AI SDK agent: search the web, read pages, find a list, read a list's rows,
 * and, with `monitorMaxPricePerRunUsd`, keep a list current on a schedule.
 *
 * Every price cap is set here, in code, and is not a tool input, so the model can't raise it.
 *
 * @example
 * const { text } = await generateText({
 *   model,
 *   tools: specstreamTools({ maxPriceUsd: 5 }),
 *   stopWhen: stepCountIs(5),
 *   prompt: "Find dental clinics in Lisbon with online booking.",
 * });
 */
export function specstreamTools(
  options: SpecStreamToolsOptions & { monitorMaxPricePerRunUsd: number },
): SpecStreamBaseTools & SpecStreamMonitorTools;
export function specstreamTools(options: SpecStreamToolsOptions): SpecStreamBaseTools;
export function specstreamTools(options: SpecStreamToolsOptions): SpecStreamBaseTools | (SpecStreamBaseTools & SpecStreamMonitorTools) {
  const { maxPriceUsd } = options;
  if (typeof maxPriceUsd !== "number" || !Number.isFinite(maxPriceUsd) || maxPriceUsd <= 0) {
    throw new Error("maxPriceUsd must be greater than 0.");
  }
  const monitorMax = options.monitorMaxPricePerRunUsd;
  if (monitorMax !== undefined && !(typeof monitorMax === "number" && Number.isFinite(monitorMax) && monitorMax > 0)) {
    throw new Error("monitorMaxPricePerRunUsd must be greater than 0.");
  }
  const client = new SpecStreamClient({ apiKey: options.apiKey, baseUrl: options.baseUrl ?? DEFAULT_BASE_URL, fetch: options.fetch });
  if (!client.hasKey) throw new Error(MISSING_KEY_MESSAGE);
  const tools = baseTools(client, options);
  if (monitorMax === undefined) return tools;
  return { ...tools, ...monitorTools(client, monitorMax, options.monitorMaxPricePerMonthUsd) };
}
