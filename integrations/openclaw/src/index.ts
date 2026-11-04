import { Type } from "typebox";
import { defineToolPlugin } from "openclaw/plugin-sdk/tool-plugin";
import { SpecStreamClient, MAX_RESULTS } from "./client.js";
import { clampResults, effectiveCeiling, resolveConfig, DEFAULT_MAX_PRICE_USD } from "./config.js";

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

export default defineToolPlugin({
  id: "specstream",
  name: "SpecStream",
  description: "The live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web. Source URL and read time on every value.",
  activation: { onStartup: false },
  configSchema,
  tools: (tool) => [
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
