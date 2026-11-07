import { z } from "zod/v3";
import { CallbackManagerForToolRun } from "@langchain/core/callbacks/manager";
import { StructuredTool, ToolParams } from "@langchain/core/tools";
import { InferInteropZodOutput } from "@langchain/core/utils/types";
import { SpecStreamSearchAPIWrapper, type SpecStreamSearchResponse } from "./utils.js";

/**
 * Options for the SpecStreamSearch tool.
 */
export type SpecStreamSearchAPIRetrieverFields = ToolParams & {
  /** The base URL of the SpecStream API. @default "https://api.specstream.ai" */
  apiBaseUrl?: string;
  /** The API key. Defaults to the `SPECSTREAM_API_KEY` environment variable. */
  specstreamApiKey?: string;
  /** Add the text of the top pages to every search. Takes up to about a second more. @default false */
  passages?: boolean;
  /** Replace the tool name. */
  name?: string;
  /** Replace the tool description. */
  description?: string;
  /** Use a custom API wrapper, for example in tests. */
  apiWrapper?: SpecStreamSearchAPIWrapper;
};

const inputSchema = z.object({
  query: z
    .string()
    .min(1)
    .max(2000)
    .describe("The question or request in everyday words, 1 to 2,000 characters."),
});

/**
 * A tool that searches the live web with the SpecStream Search API and
 * returns the answer, matching rows and ranked sources.
 *
 * Authentication is handled via an API key, passed at construction or set as
 * the environment variable `SPECSTREAM_API_KEY`.
 */
export class SpecStreamSearch extends StructuredTool<typeof inputSchema> {
  static lc_name(): string {
    return "SpecStreamSearch";
  }

  override description: string =
    "Search the live web with the SpecStream Search API. Returns the answer with the page it was read from, matching rows with their fields, and ranked sources. Input should be a question or request in everyday words.";

  override name: string = "specstream_search";

  override schema = inputSchema;

  passages?: boolean;

  private apiWrapper: SpecStreamSearchAPIWrapper;

  constructor(params: SpecStreamSearchAPIRetrieverFields = {}) {
    super(params);

    if (params.name) {
      this.name = params.name;
    }
    if (params.description) {
      this.description = params.description;
    }
    this.passages = params.passages;

    this.apiWrapper =
      params.apiWrapper ??
      new SpecStreamSearchAPIWrapper({
        specstreamApiKey: params.specstreamApiKey,
        apiBaseUrl: params.apiBaseUrl,
      });
  }

  async _call(
    input: InferInteropZodOutput<typeof inputSchema>,
    _runManager?: CallbackManagerForToolRun
  ): Promise<SpecStreamSearchResponse | { error: string }> {
    try {
      return await this.apiWrapper.rawResults({ q: input.query, passages: this.passages });
    } catch (e: unknown) {
      return { error: e instanceof Error ? e.message : String(e) };
    }
  }
}
