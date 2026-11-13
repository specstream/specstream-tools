import { v } from "convex/values";
import { paginationOptsValidator } from "convex/server";
import { SpecStreamClient } from "@specstream/convex";
import {
  action,
  internalAction,
  internalMutation,
  internalQuery,
  mutation,
  query,
  type QueryCtx,
} from "./_generated/server.js";
import { components, internal } from "./_generated/api.js";
import { requireUser } from "./auth.js";

const specstream = new SpecStreamClient(components.specstream);

/**
 * The most this app lets one list cost, whatever a caller asks for. Spending
 * limits belong in your app: the component only ever spends what you approve.
 */
const APP_MAX_PRICE_USD = 25;

/**
 * List-scoped operations go through this. Without it, anyone could read,
 * cancel or delete anyone else's list by guessing an id: the component has no
 * notion of who owns what.
 */
async function requireOwnedList(
  ctx: QueryCtx & { auth: any },
  listId: string,
): Promise<string> {
  const userId = await requireUser(ctx);
  const owner = await ctx.db
    .query("listOwners")
    .withIndex("listId", (q) => q.eq("listId", listId))
    .first();
  if (!owner || owner.userId !== userId) {
    throw new Error("No such list.");
  }
  return userId;
}

// ---------------------------------------------------------------------------
// Two steps: see the price, then approve it
// ---------------------------------------------------------------------------

/**
 * Step one. Reads the request and prices it. Nothing runs and nothing is
 * charged. Show the result to the person, then call `approveList`.
 */
export const quoteList = action({
  args: { request: v.string(), rows: v.number() },
  handler: async (ctx, args) => {
    await requireUser(ctx);
    return await specstream.quote(ctx, args);
  },
});

/**
 * Step two. `confirmMaxCents` is the maximum the person saw and approved. It
 * must equal the quote's, so what runs is what was shown.
 */
export const approveList = action({
  args: {
    quoteId: v.string(),
    confirmMaxCents: v.number(),
    label: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const userId = await requireUser(ctx);
    const started = await specstream.approve(ctx, {
      quoteId: args.quoteId,
      confirmMaxCents: args.confirmMaxCents,
      // Makes a double click start one list.
      idempotencyKey: `${userId}-${args.quoteId}`.replace(
        /[^A-Za-z0-9_.:-]/g,
        "-",
      ),
      onComplete: internal.example.onListComplete,
      context: { userId, label: args.label },
    });
    await ctx.runMutation(internal.example.recordOwner, {
      listId: started.listId,
      userId,
      label: args.label,
    });
    return started;
  },
});

/**
 * One call, with the app's own ceiling: it prices the request and starts it
 * only when the most it can cost is within `APP_MAX_PRICE_USD`.
 */
export const findListUnderBudget = action({
  args: {
    request: v.string(),
    rows: v.number(),
    label: v.optional(v.string()),
  },
  handler: async (ctx, args) => {
    const userId = await requireUser(ctx);
    const result = await specstream.findList(ctx, {
      request: args.request,
      rows: args.rows,
      maxPriceUsd: APP_MAX_PRICE_USD,
      onComplete: internal.example.onListComplete,
      context: { userId, label: args.label },
    });
    if (result.status === "started") {
      await ctx.runMutation(internal.example.recordOwner, {
        listId: result.listId,
        userId,
        label: args.label,
      });
    }
    return result;
  },
});

export const recordOwner = internalMutation({
  args: {
    listId: v.string(),
    userId: v.string(),
    label: v.optional(v.string()),
  },
  returns: v.null(),
  handler: async (ctx, args) => {
    await ctx.db.insert("listOwners", args);
    return null;
  },
});

/**
 * Runs once, when the list reaches a final state. Whatever you passed as
 * `context` comes back untouched.
 */
export const onListComplete = internalMutation({
  args: {
    listId: v.string(),
    specstreamListId: v.string(),
    status: v.union(
      v.literal("completed"),
      v.literal("partial"),
      v.literal("failed"),
      v.literal("canceled"),
      v.literal("expired"),
    ),
    rowCount: v.number(),
    requestedCount: v.number(),
    error: v.optional(v.string()),
    context: v.optional(v.any()),
  },
  returns: v.null(),
  handler: async (ctx, args) => {
    await ctx.db.insert("listReports", {
      listId: args.listId,
      userId: args.context?.userId ?? "unknown",
      label: args.context?.label,
      status: args.status,
      rowCount: args.rowCount,
      requestedCount: args.requestedCount,
      error: args.error,
    });
    return null;
  },
});

// ---------------------------------------------------------------------------
// Reading what came back
// ---------------------------------------------------------------------------

/** Subscribe to this for live progress: the count climbs as rows arrive. */
export const listProgress = query({
  args: { listId: v.string() },
  handler: async (ctx, args) => {
    await requireOwnedList(ctx, args.listId);
    return await specstream.getList(ctx, args.listId);
  },
});

/** Rows as they arrive, each with its source URL. Pairs with React's `usePaginatedQuery`. */
export const listRows = query({
  args: { listId: v.string(), paginationOpts: paginationOptsValidator },
  handler: async (ctx, args) => {
    await requireOwnedList(ctx, args.listId);
    return await specstream.listRows(ctx, {
      listId: args.listId,
      paginationOpts: args.paginationOpts,
    });
  },
});

/** Only the caller's lists, never the whole table. */
export const myLists = query({
  args: {},
  handler: async (ctx) => {
    const userId = await requireUser(ctx);
    const owned = await ctx.db
      .query("listOwners")
      .withIndex("userId", (q) => q.eq("userId", userId))
      .order("desc")
      .take(20);
    return await Promise.all(
      owned.map(async (row) => ({
        label: row.label,
        list: await specstream.getList(ctx, row.listId),
      })),
    );
  },
});

export const reports = query({
  args: {},
  handler: async (ctx) => {
    const userId = await requireUser(ctx);
    return await ctx.db
      .query("listReports")
      .withIndex("userId", (q) => q.eq("userId", userId))
      .order("desc")
      .take(20);
  },
});

export const cancelList = action({
  args: { listId: v.string() },
  handler: async (ctx, args) => {
    await ctx.runQuery(internal.example.assertOwned, {
      listId: args.listId,
      userId: await requireUser(ctx),
    });
    return await specstream.cancel(ctx, args.listId);
  },
});

/** Ownership check callable from an action, which has no `ctx.db`. */
// ---------------------------------------------------------------------------
// A real browser: open, go to a page, read it, close
// ---------------------------------------------------------------------------

/**
 * Reads a page the way a person sees it, in a real browser SpecStream runs
 * ($0.10 an hour by the second, $0.001 a step). The browser is closed in
 * `finally`, so its time stops even when a step fails.
 */
export const readPageInBrowser = action({
  args: { url: v.string() },
  handler: async (ctx, args) => {
    await requireUser(ctx);
    const session = await specstream.openBrowser(ctx, { timeoutSeconds: 120, blockMedia: true });
    try {
      await specstream.browserStep(ctx, session.sessionId, "browser_navigate", { url: args.url });
      const page = await specstream.browserStep(ctx, session.sessionId, "browser_read");
      return { url: page.url, title: page.title, text: page.text, error: page.error };
    } finally {
      await specstream.closeBrowser(ctx, session.sessionId);
    }
  },
});

export const assertOwned = internalQuery({
  args: { listId: v.string(), userId: v.string() },
  returns: v.null(),
  handler: async (ctx, args) => {
    const owner = await ctx.db
      .query("listOwners")
      .withIndex("listId", (q) => q.eq("listId", args.listId))
      .first();
    if (!owner || owner.userId !== args.userId)
      throw new Error("No such list.");
    return null;
  },
});

export const resumeList = mutation({
  args: { listId: v.string() },
  handler: async (ctx, args) => {
    await requireOwnedList(ctx, args.listId);
    return await specstream.resume(ctx, args.listId);
  },
});

export const deleteList = mutation({
  args: { listId: v.string() },
  handler: async (ctx, args) => {
    await requireOwnedList(ctx, args.listId);
    const owner = await ctx.db
      .query("listOwners")
      .withIndex("listId", (q) => q.eq("listId", args.listId))
      .first();
    if (owner) await ctx.db.delete("listOwners", owner._id);
    return await specstream.deleteList(ctx, args.listId);
  },
});

// ---------------------------------------------------------------------------
// One-time setup, run from the CLI
// ---------------------------------------------------------------------------

/** Check the key and see what is left to spend: `npx convex run example:whoAmI`. */
export const whoAmI = internalAction({
  args: {},
  handler: async (ctx) => await specstream.account(ctx),
});

/**
 * Ask SpecStream to call this deployment when a list finishes:
 * `npx convex run example:registerWebhook '{"siteUrl":"https://<name>.convex.site"}'`.
 * Then set the printed secret as SPECSTREAM_WEBHOOK_SECRET.
 */
export const registerWebhook = internalAction({
  args: { siteUrl: v.string() },
  handler: async (ctx, args) =>
    await specstream.registerWebhook(
      ctx,
      `${args.siteUrl.replace(/\/+$/, "")}/specstream/webhook`,
    ),
});
