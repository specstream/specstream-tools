import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import specstream, { MCP_URL, RESEARCH_COMMAND, researchArgs, researchPrompt, SERVER_NAME, serverConfig } from "../extensions/specstream.ts";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const WORK = ["compile", "review-work", "approve-work", "continue-work"].map((n) => `specstream-${n}`);
const NAMES = [...WORK, "specstream-search-web", "specstream-extract-pages", "specstream-research"];

const body = (text: string) => text.replace(/^---\n[\s\S]*?\n---\n/, "");

describe("@specstream/pi-package", () => {
  it("is a Pi package", () => {
    assert.equal(pkg.name, "@specstream/pi-package");
    assert.ok(pkg.keywords.includes("pi-package"));
    assert.deepEqual(pkg.pi.extensions, ["./extensions/specstream.ts"]);
    assert.deepEqual(pkg.pi.skills, ["./skills"]);
    for (const path of pkg.pi.extensions) assert.ok(existsSync(join(root, path)), path);
  });

  it("registers the hosted server and holds no credentials", () => {
    const calls: Array<[string, Record<string, unknown>]> = [];
    specstream({ registerMcpServer: (name: string, config: Record<string, unknown>) => calls.push([name, config]) } as never);
    assert.equal(calls.length, 1);
    assert.equal(calls[0][0], SERVER_NAME);
    assert.equal(calls[0][1].url, MCP_URL);
    assert.equal(MCP_URL, "https://api.specstream.ai/mcp");
    // oh-my-pi has no registerMcpServer: loading must not throw there.
    assert.doesNotThrow(() => specstream({} as never));
  });

  it("signs in with OAuth unless a key is set", () => {
    assert.equal("headers" in serverConfig({}), false);
    assert.equal("headers" in serverConfig({ SPECSTREAM_API_KEY: "  " }), false);
    const keyed = serverConfig({ SPECSTREAM_API_KEY: "ss_live_secret" });
    assert.deepEqual(keyed.headers, { Authorization: "Bearer ${SPECSTREAM_API_KEY}" });
    assert.ok(!JSON.stringify(keyed).includes("ss_live_secret"));
  });

  it("keeps the price and approval tools visible", () => {
    const tools = serverConfig({}).toolExposure;
    for (const name of ["compile", "quote_capacity_work", "authorize_capacity_work", "list_find_rows"]) {
      assert.equal(tools[name], "direct");
    }
  });

  it("ships the seven skills, named after their folders", () => {
    const dirs = readdirSync(join(root, "skills")).sort();
    assert.deepEqual(dirs, [...NAMES].sort());
    for (const name of NAMES) {
      const text = readFileSync(join(root, "skills", name, "SKILL.md"), "utf8");
      assert.match(text, new RegExp(`^---\\nname: ${name}\\n`));
      const description = /^description: (.+)$/m.exec(text)?.[1] ?? "";
      assert.ok(description.length > 0 && description.length <= 1024, name);
    }
  });

  it("keeps the research price and start tools visible", () => {
    const tools = serverConfig({}).toolExposure;
    for (const name of ["research_price", "start_research", "get_research"]) assert.equal(tools[name], "direct");
  });

  it("reads an optional depth before the question", () => {
    assert.deepEqual(researchArgs("  deep Who supplies EU battery cells?  "), { depth: "deep", question: "Who supplies EU battery cells?" });
    assert.deepEqual(researchArgs("QUICK what changed"), { depth: "quick", question: "what changed" });
    assert.deepEqual(researchArgs("Who supplies cells?"), { depth: "standard", question: "Who supplies cells?" });
    assert.deepEqual(researchArgs("deep"), { depth: "standard", question: "deep" });
    assert.equal(researchPrompt("   "), null);
  });

  it("/research asks for the price and the approval, and starts nothing itself", async () => {
    const commands: Record<string, { description?: string; handler: (args: string, ctx: unknown) => Promise<void> }> = {};
    const sent: Array<[string, unknown]> = [];
    const notes: string[] = [];
    const pi = {
      registerCommand: (name: string, options: (typeof commands)[string]) => (commands[name] = options),
      sendUserMessage: (text: string, options?: unknown) => sent.push([text, options]),
    };
    specstream(pi as never);
    assert.deepEqual(Object.keys(commands), [RESEARCH_COMMAND]);
    assert.equal(RESEARCH_COMMAND, "research");
    const ctx = (idle: boolean) => ({ isIdle: () => idle, ui: { notify: (text: string) => notes.push(text) } });

    await commands.research.handler("", ctx(true));
    assert.equal(sent.length, 0);
    assert.ok(notes[0].includes("/research [quick|standard|deep] <question>"));
    assert.ok(notes[0].includes("$0.10 (quick), $0.30 (standard) or $1.00 (deep)"));

    await commands.research.handler("quick Who supplies EU battery cells?", ctx(true));
    const [text, options] = sent[0];
    assert.equal(options, undefined);
    assert.ok(text.includes("Who supplies EU battery cells?"));
    assert.ok(text.includes('research_price with {"depth": "quick"}'));
    assert.ok(text.indexOf("research_price") < text.indexOf("wait for my approval"));
    assert.ok(text.indexOf("wait for my approval") < text.indexOf("start_research"));
    assert.ok(text.includes("confirm_max_cents"));

    await commands.research.handler("a question", ctx(false));
    assert.deepEqual(sent[1][1], { deliverAs: "followUp" });
  });

  it("the research skill names the tools, their arguments and the three prices", () => {
    const text = readFileSync(join(root, "skills", "specstream-research", "SKILL.md"), "utf8");
    for (const word of ["research_price", "start_research", "get_research", '"question"', "confirm_max_cents", "idempotency_key", "$0.10", "$0.30", "$1.00"]) {
      assert.ok(text.includes(word), word);
    }
    assert.ok(text.indexOf("ask them to approve") < text.indexOf("call `start_research`"));
  });

  it("matches the Kilo skills it is copied from", () => {
    const kilo = join(root, "..", "kilo", "skills");
    if (!existsSync(kilo)) return;
    for (const name of WORK) {
      const ours = readFileSync(join(root, "skills", name, "SKILL.md"), "utf8");
      const theirs = readFileSync(join(kilo, name, "SKILL.md"), "utf8");
      assert.equal(body(ours), body(theirs), `${name} drifted from integrations/kilo`);
    }
  });
});
