import { v } from "convex/values";
import { action } from "./_generated/server.js";
import { asString, specstreamRequest } from "./api.js";
import { fail, readRequest } from "./helpers.js";
import { readingResult } from "./validators.js";

/**
 * Read a request in plain words and say what SpecStream understood. Nothing is
 * priced, nothing runs and nothing is charged.
 */
export const read = action({
  args: { request: v.string(), locale: v.optional(v.string()) },
  returns: readingResult,
  handler: async (_ctx, args) => await readRequest(args.request, args.locale),
});

/**
 * Search the live web in seconds with the SpecStream Search API
 * (`GET /v1/web-search`, $5 per 1,000 searches, no quote needed).
 */
export const webSearch = action({
  args: { q: v.string(), passages: v.optional(v.boolean()) },
  returns: v.any(),
  handler: async (_ctx, args) => {
    const q = args.q.trim();
    if (!q || q.length > 2000) {
      fail("specstream_invalid_query", "Provide a search query between 1 and 2,000 characters.");
    }
    const params = new URLSearchParams({ q });
    if (args.passages) params.set("passages", "true");
    return await specstreamRequest(`/v1/web-search?${params.toString()}`);
  },
});

/**
 * Read the main text, title and published date of 1 to 20 web pages, PDFs,
 * Word or Excel files live (`POST /v1/extract`, $0.80 per 1,000 pages).
 */
export const extractPages = action({
  args: { urls: v.array(v.string()), format: v.optional(v.union(v.literal("markdown"), v.literal("text"))) },
  returns: v.any(),
  handler: async (_ctx, args) => {
    const urls = args.urls.map((u) => u.trim()).filter(Boolean);
    if (urls.length < 1 || urls.length > 20) {
      fail("specstream_invalid_urls", "Provide 1 to 20 http or https URLs.");
    }
    return await specstreamRequest("/v1/extract", {
      method: "POST",
      body: { urls, format: args.format === "text" ? "text" : "markdown" },
    });
  },
});

/** Who the API key belongs to and what is left to spend. */
export const account = action({
  args: {},
  returns: v.object({
    email: v.optional(v.string()),
    /** Null when the balance could not be read. */
    availableCents: v.union(v.number(), v.null()),
  }),
  handler: async () => {
    const me = await specstreamRequest("/v1/me");
    let availableCents: number | null = null;
    try {
      const balance = await specstreamRequest("/v1/capacity/balance");
      if (typeof balance.available_cents === "number") {
        availableCents = balance.available_cents;
      }
    } catch {
      availableCents = null;
    }
    return { email: asString(me.email), availableCents };
  },
});

/**
 * Ask SpecStream to call your deployment when a list finishes. Webhooks belong
 * to the account, so do this once, then set the returned `secret` as
 * SPECSTREAM_WEBHOOK_SECRET. The URL must be public HTTPS, for example
 * `https://<your-deployment>.convex.site/specstream/webhook`.
 */
export const registerWebhook = action({
  args: { url: v.string() },
  returns: v.object({ hookId: v.string(), secret: v.string() }),
  handler: async (_ctx, args) => {
    const data = await specstreamRequest("/v1/account/webhooks", {
      method: "POST",
      body: { url: args.url, events: ["find.completed"] },
    });
    const hookId = asString(data.hook_id);
    const secret = asString(data.secret);
    if (!hookId || !secret) {
      fail(
        "specstream_unreadable",
        "SpecStream returned a webhook this component could not read.",
      );
    }
    return { hookId, secret };
  },
});
