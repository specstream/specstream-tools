import { getEnvironmentVariable } from "@langchain/core/utils/env";

export const SPECSTREAM_BASE_URL = "https://api.specstream.ai";
export const MAX_EXTRACT_URLS = 20;

export type SpecStreamSearchParams = {
  /** The question or request in everyday words, 1 to 2,000 characters. */
  q: string;
  /** Add the text of the top pages to the reply. */
  passages?: boolean;
};

export type SpecStreamSource = {
  url: string;
  title?: string;
  site?: string;
  snippet?: string;
  published?: string;
  cited?: boolean;
};

export type SpecStreamSearchResponse = {
  id?: string;
  request_id?: string;
  kind: "fact" | "list";
  query?: string;
  columns?: unknown[];
  answer: { value: string; page: string; seen_at?: string } | null;
  rows: Array<{
    name?: string;
    page?: string;
    snippet?: string;
    probability?: number;
    sources?: string[];
    fields?: Record<string, unknown>;
  }>;
  sources: SpecStreamSource[];
  passages?: Array<{ url: string; title?: string; text: string }>;
  handoff?: Record<string, unknown>;
  took_ms?: number;
  price_usd?: number;
};

export type SpecStreamExtractParams = {
  /** 1 to 20 http or https URLs. */
  urls: string[];
  format?: "markdown" | "text";
};

export type SpecStreamExtractResult = {
  url: string;
  status: "ok" | "blocked" | "not_found" | "empty" | "unsupported" | "invalid_url" | "failed";
  text?: string;
  title?: string;
  published?: string;
  read_from?: "live" | "site" | "archive";
  captured_at?: string;
};

export type SpecStreamExtractResponse = {
  results: SpecStreamExtractResult[];
  request_id?: string;
  took_ms?: number;
  price_usd?: number;
};

export type SpecStreamAPIWrapperParams = {
  specstreamApiKey?: string;
  apiBaseUrl?: string;
};

abstract class BaseSpecStreamAPIWrapper {
  protected specstreamApiKey: string;

  protected apiBaseUrl: string;

  constructor(params: SpecStreamAPIWrapperParams = {}) {
    const apiKey = (params.specstreamApiKey ?? getEnvironmentVariable("SPECSTREAM_API_KEY") ?? "").trim();
    if (!apiKey) {
      throw new Error(
        "No SpecStream API key found. Pass specstreamApiKey or set SPECSTREAM_API_KEY. Create a key under Agents & API in your SpecStream workspace."
      );
    }
    this.specstreamApiKey = apiKey.replace(/^bearer\s+/i, "");
    this.apiBaseUrl = (params.apiBaseUrl ?? getEnvironmentVariable("SPECSTREAM_BASE_URL") ?? SPECSTREAM_BASE_URL).replace(/\/+$/, "");
  }

  protected async call<T>(method: "GET" | "POST", path: string, body?: Record<string, unknown>): Promise<T> {
    const response = await fetch(`${this.apiBaseUrl}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${this.specstreamApiKey}`,
        Accept: "application/json",
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        "User-Agent": "@specstream/langchain",
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let payload: { data?: T; error?: { message?: string } } = {};
    try {
      payload = await response.json();
    } catch {
      // A reply that is not JSON is reported by its status below.
    }
    if (!response.ok || !payload?.data) {
      throw new Error(`Error ${response.status}: ${payload?.error?.message ?? "Unknown error"}`);
    }
    return payload.data;
  }
}

/**
 * A wrapper that encapsulates access to the SpecStream Search API
 * (`GET /v1/web-search`). Primarily used for testing.
 */
export class SpecStreamSearchAPIWrapper extends BaseSpecStreamAPIWrapper {
  async rawResults(params: SpecStreamSearchParams): Promise<SpecStreamSearchResponse> {
    const query = new URLSearchParams({ q: params.q.trim() });
    if (params.passages) {
      query.set("passages", "true");
    }
    return this.call<SpecStreamSearchResponse>("GET", `/v1/web-search?${query.toString()}`);
  }
}

/**
 * A wrapper that encapsulates access to the SpecStream Extract API
 * (`POST /v1/extract`). Primarily used for testing.
 */
export class SpecStreamExtractAPIWrapper extends BaseSpecStreamAPIWrapper {
  async rawResults(params: SpecStreamExtractParams): Promise<SpecStreamExtractResponse> {
    const urls = params.urls.map((url) => url.trim()).filter(Boolean).slice(0, MAX_EXTRACT_URLS);
    return this.call<SpecStreamExtractResponse>("POST", "/v1/extract", {
      urls,
      format: params.format === "text" ? "text" : "markdown",
    });
  }
}
