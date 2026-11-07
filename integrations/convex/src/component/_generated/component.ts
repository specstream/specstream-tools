/* eslint-disable */
/**
 * Generated `ComponentApi` utility.
 *
 * THIS CODE IS AUTOMATICALLY GENERATED.
 *
 * To regenerate, run `npx convex dev`.
 * @module
 */

import type { FunctionReference } from "convex/server";

/**
 * A utility for referencing a Convex component's exposed API.
 *
 * Useful when expecting a parameter like `components.myComponent`.
 * Usage:
 * ```ts
 * async function myFunction(ctx: QueryCtx, component: ComponentApi) {
 *   return ctx.runQuery(component.someFile.someQuery, { ...args });
 * }
 * ```
 */
export type ComponentApi<Name extends string | undefined = string | undefined> =
  {
    lib: {
      account: FunctionReference<
        "action",
        "internal",
        {},
        { availableCents: number | null; email?: string },
        Name
      >;
      extractPages: FunctionReference<
        "action",
        "internal",
        { format?: "markdown" | "text"; urls: Array<string> },
        any,
        Name
      >;
      read: FunctionReference<
        "action",
        "internal",
        { locale?: string; request: string },
        {
          astHash?: string;
          canonicalSentence?: string;
          notice?: string;
          rowsInferred: boolean;
          statedRows?: number;
          status: string;
        },
        Name
      >;
      registerWebhook: FunctionReference<
        "action",
        "internal",
        { url: string },
        { hookId: string; secret: string },
        Name
      >;
      webSearch: FunctionReference<
        "action",
        "internal",
        { passages?: boolean; q: string },
        any,
        Name
      >;
    };
    lists: {
      approve: FunctionReference<
        "action",
        "internal",
        {
          confirmMaxCents: number;
          context?: any;
          idempotencyKey?: string;
          mode?: "webhook" | "poll";
          onComplete?: string;
          quoteId: string;
        },
        {
          link: string;
          listId: string;
          maximumCents: number;
          specstreamListId: string;
          status: "started";
        },
        Name
      >;
      cancel: FunctionReference<
        "action",
        "internal",
        { listId: string },
        null,
        Name
      >;
      deleteList: FunctionReference<
        "mutation",
        "internal",
        { listId: string },
        null,
        Name
      >;
      findList: FunctionReference<
        "action",
        "internal",
        {
          context?: any;
          idempotencyKey?: string;
          locale?: string;
          maxCents: number;
          mode?: "webhook" | "poll";
          onComplete?: string;
          request: string;
          rows: number;
        },
        {
          link: string;
          listId: string;
          maximumCents: number;
          specstreamListId: string;
          status: "started";
        } | {
          message: string;
          notice?: string;
          readAs: string;
          request: string;
          status: "needs_edit";
        } | {
          maximumCents: number;
          message: string;
          request: string;
          status: "over_maximum";
        },
        Name
      >;
      get: FunctionReference<
        "query",
        "internal",
        { listId: string },
        null | {
          _creationTime: number;
          _id: string;
          acceptedCount: number;
          canonicalSentence?: string;
          completedAt?: number;
          context?: any;
          currency?: string;
          error?: string;
          finalized: boolean;
          link: string;
          maximumCents?: number;
          mode: "webhook" | "poll";
          quoteId?: string;
          request: string;
          requestedCount: number;
          rowCount: number;
          specstreamListId: string;
          startedAt: number;
          status: "running" | "completed" | "partial" | "failed" | "canceled" | "expired";
          updatedAt: number;
        },
        Name
      >;
      getBySpecstreamListId: FunctionReference<
        "query",
        "internal",
        { specstreamListId: string },
        null | {
          _creationTime: number;
          _id: string;
          acceptedCount: number;
          canonicalSentence?: string;
          completedAt?: number;
          context?: any;
          currency?: string;
          error?: string;
          finalized: boolean;
          link: string;
          maximumCents?: number;
          mode: "webhook" | "poll";
          quoteId?: string;
          request: string;
          requestedCount: number;
          rowCount: number;
          specstreamListId: string;
          startedAt: number;
          status: "running" | "completed" | "partial" | "failed" | "canceled" | "expired";
          updatedAt: number;
        },
        Name
      >;
      getQuote: FunctionReference<
        "query",
        "internal",
        { quoteId: string },
        null | {
          _creationTime: number;
          _id: string;
          canAuthorize: boolean;
          canonicalSentence?: string;
          createdAt: number;
          currency: string;
          expiresAt?: number;
          listId?: string;
          maximumCents: number;
          request: string;
          rows: number;
          unitCents?: number;
        },
        Name
      >;
      getRow: FunctionReference<
        "query",
        "internal",
        { entityId: string; listId: string },
        null | {
          _creationTime: number;
          _id: string;
          cells: Array<{
            absence?: string;
            columnId: string;
            display?: string;
            label: string;
            observedAt?: string;
            sourceUrl?: string;
            value?: any;
          }>;
          details?: Array<{
            absence?: string;
            columnId: string;
            display?: string;
            label: string;
            observedAt?: string;
            sourceUrl?: string;
            value?: any;
          }>;
          entityId: string;
          listId: string;
          locked?: boolean;
          observedAt?: string;
          ordinal: number;
          sourceUrl?: string;
        },
        Name
      >;
      list: FunctionReference<
        "query",
        "internal",
        {
          limit?: number;
          status?: "running" | "completed" | "partial" | "failed" | "canceled" | "expired";
        },
        Array<{
          _creationTime: number;
          _id: string;
          acceptedCount: number;
          canonicalSentence?: string;
          completedAt?: number;
          context?: any;
          currency?: string;
          error?: string;
          finalized: boolean;
          link: string;
          maximumCents?: number;
          mode: "webhook" | "poll";
          quoteId?: string;
          request: string;
          requestedCount: number;
          rowCount: number;
          specstreamListId: string;
          startedAt: number;
          status: "running" | "completed" | "partial" | "failed" | "canceled" | "expired";
          updatedAt: number;
        }>,
        Name
      >;
      listRows: FunctionReference<
        "query",
        "internal",
        {
          listId: string;
          paginationOpts: {
            cursor: string | null;
            endCursor?: string | null;
            id?: number;
            maximumBytesRead?: number;
            maximumRowsRead?: number;
            numItems: number;
          };
        },
        {
          continueCursor: string;
          isDone: boolean;
          page: Array<{
            _creationTime: number;
            _id: string;
            cells: Array<{
              absence?: string;
              columnId: string;
              display?: string;
              label: string;
              observedAt?: string;
              sourceUrl?: string;
              value?: any;
            }>;
            details?: Array<{
              absence?: string;
              columnId: string;
              display?: string;
              label: string;
              observedAt?: string;
              sourceUrl?: string;
              value?: any;
            }>;
            entityId: string;
            listId: string;
            locked?: boolean;
            observedAt?: string;
            ordinal: number;
            sourceUrl?: string;
          }>;
          pageStatus?: "SplitRecommended" | "SplitRequired" | null;
          splitCursor?: string | null;
        },
        Name
      >;
      quote: FunctionReference<
        "action",
        "internal",
        {
          locale?: string;
          request: string;
          rows: number;
        },
        {
          canAuthorize: boolean;
          currency: string;
          expiresAt?: number;
          maximumCents: number;
          quoteId: string;
          readAs?: string;
          request: string;
          rows: number;
          status: "quoted";
          unitCents?: number;
        } | {
          message: string;
          notice?: string;
          readAs: string;
          request: string;
          status: "needs_edit";
        },
        Name
      >;
      refresh: FunctionReference<
        "action",
        "internal",
        { listId: string },
        null,
        Name
      >;
      resume: FunctionReference<
        "mutation",
        "internal",
        { listId: string },
        boolean,
        Name
      >;
    };
  };
