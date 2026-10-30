import { describe, expect, it } from "vitest";
import { generateText, stepCountIs } from "ai";
import { MockLanguageModelV4 } from "ai/test";
import { specstreamTools } from "../src/index.js";

const usage = {
  inputTokens: { total: 10, noCache: 10, cacheRead: undefined, cacheWrite: undefined },
  outputTokens: { total: 5, text: 5, reasoning: undefined },
};

const reply = (data: unknown) => new Response(JSON.stringify({ data }));

/** The whole path through the real AI SDK: the model calls the tool, the SDK validates the input and runs it. */
describe("generateText with specstreamTools", () => {
  it("runs a list the model asked for and hands the rows back to it", async () => {
    const paths: string[] = [];
    const fetchStub = (async (input: string | URL | Request) => {
      const url = new URL(String(input));
      paths.push(url.pathname);
      if (url.pathname.startsWith("/v1/capacity/requests/")) return new Response("{}", { status: 404 });
      if (url.pathname === "/v1/parse") return reply({ status: "runnable", ast_hash: "a".repeat(64) });
      if (url.pathname === "/v1/capacity/quotes") return reply({ quote_id: "cqt_1", quote_hash: "b".repeat(64), maximum_cents: 300 });
      if (url.pathname === "/v1/capacity/executions") return reply({ find_id: "fnd_1" });
      return reply({
        status: "completed",
        rows: [{ entity_id: "e1", ordinal: 1, cells: [{ label: "Organization", display: "RapidCanvas Inc", provenance: { source_url: "https://rapidcanvas.example" } }] }],
        flat_rows: [{ id: "fnd_1:e1", name: "RapidCanvas Inc", name_source: "https://rapidcanvas.example", source_url: "https://www.sec.gov/x" }],
      });
    }) as typeof fetch;

    let step = 0;
    const model = new MockLanguageModelV4({
      doGenerate: async () => {
        step += 1;
        return step === 1
          ? {
              content: [
                {
                  type: "tool-call" as const,
                  toolCallId: "call_1",
                  toolName: "specstream_find_list",
                  input: JSON.stringify({ request: "US startups with a Form D after October 8, 2026", maxResults: 10 }),
                },
              ],
              finishReason: { unified: "tool-calls" as const, raw: undefined },
              usage,
              warnings: [],
            }
          : {
              content: [{ type: "text" as const, text: "Found RapidCanvas Inc." }],
              finishReason: { unified: "stop" as const, raw: undefined },
              usage,
              warnings: [],
            };
      },
    });

    const result = await generateText({
      model,
      tools: specstreamTools({ apiKey: "ss_live_test_key", maxPriceUsd: 5, fetch: fetchStub, pollIntervalSeconds: 0 }),
      stopWhen: stepCountIs(3),
      prompt: "Which startups filed a Form D?",
    });

    expect(result.text).toBe("Found RapidCanvas Inc.");
    expect(paths).toContain("/v1/capacity/executions");
    const toolResult = result.steps[0].toolResults[0] as any;
    expect(toolResult.toolName).toBe("specstream_find_list");
    expect(toolResult.output.rows[0]).toMatchObject({ Organization: "RapidCanvas Inc", source_url: "https://www.sec.gov/x" });
    expect(JSON.stringify(model.doGenerateCalls[0].tools)).toContain("specstream_find_list");
    expect(JSON.stringify(model.doGenerateCalls[0].tools)).not.toContain("maxPriceUsd");
  });
});
