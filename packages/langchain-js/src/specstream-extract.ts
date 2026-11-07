import { z } from "zod/v3";
import { CallbackManagerForToolRun } from "@langchain/core/callbacks/manager";
import { StructuredTool, ToolParams } from "@langchain/core/tools";
import { InferInteropZodOutput } from "@langchain/core/utils/types";
import { SpecStreamExtractAPIWrapper, type SpecStreamExtractResponse } from "./utils.js";

/**
 * Options for the SpecStreamExtract tool.
 */
export type SpecStreamExtractAPIRetrieverFields = ToolParams & {
  /** The base URL of the SpecStream API. @default "https://api.specstream.ai" */
  apiBaseUrl?: string;
  /** The API key. Defaults to the `SPECSTREAM_API_KEY` environment variable. */
  specstreamApiKey?: string;
  /** Output format of the page text. Takes precedence over the call parameter. */
  format?: "markdown" | "text";
  /** Replace the tool name. */
  name?: string;
  /** Replace the tool description. */
  description?: string;
  /** Use a custom API wrapper, for example in tests. */
  apiWrapper?: SpecStreamExtractAPIWrapper;
};

const inputSchema = z.object({
  urls: z
    .array(z.string().min(1))
    .min(1)
    .max(20)
    .describe("1 to 20 http or https URLs of web pages, PDF, Word or Excel files to read."),
  format: z
    .enum(["markdown", "text"])
    .optional()
    .describe('The format of the page text: "markdown" (default) keeps headings, lists and links; "text" is plain text.'),
});

/**
 * A tool that reads the main text of web pages and documents live with the
 * SpecStream Extract API.
 *
 * Authentication is handled via an API key, passed at construction or set as
 * the environment variable `SPECSTREAM_API_KEY`.
 */
export class SpecStreamExtract extends StructuredTool<typeof inputSchema> {
  static lc_name(): string {
    return "SpecStreamExtract";
  }

  override description: string =
    "Read the main text, title and published date of up to 20 web pages, PDF, Word or Excel files live with the SpecStream Extract API. Input should be a list of URLs.";

  override name: string = "specstream_extract";

  override schema = inputSchema;

  format?: "markdown" | "text";

  private apiWrapper: SpecStreamExtractAPIWrapper;

  constructor(params: SpecStreamExtractAPIRetrieverFields = {}) {
    super(params);

    if (params.name) {
      this.name = params.name;
    }
    if (params.description) {
      this.description = params.description;
    }
    this.format = params.format;

    this.apiWrapper =
      params.apiWrapper ??
      new SpecStreamExtractAPIWrapper({
        specstreamApiKey: params.specstreamApiKey,
        apiBaseUrl: params.apiBaseUrl,
      });
  }

  async _call(
    input: InferInteropZodOutput<typeof inputSchema>,
    _runManager?: CallbackManagerForToolRun
  ): Promise<SpecStreamExtractResponse | { error: string }> {
    try {
      return await this.apiWrapper.rawResults({
        urls: input.urls,
        format: this.format ?? input.format,
      });
    } catch (e: unknown) {
      return { error: e instanceof Error ? e.message : String(e) };
    }
  }
}
