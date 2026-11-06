import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { afterEach, beforeEach, describe, it } from "node:test";
import { fileURLToPath } from "node:url";
import plugin from "../index.ts";
import { MCP_URL, bundledSkills, enabled, remoteServer, skillsDir } from "../shared.ts";

const root = dirname(dirname(fileURLToPath(import.meta.url)));

type V1Config = { mcp?: Record<string, unknown>; skills?: { paths?: string[] } };

async function runV1(config: V1Config, options?: unknown) {
  // The V1 host passes (input, options); the plugin never reads input, so an empty object is enough.
  const hooks = await (plugin.server as (input: unknown, options?: unknown) => Promise<{ config(c: V1Config): Promise<void> }>)(
    {},
    options,
  );
  await hooks.config(config);
  return config;
}

async function runV2(options?: unknown, existing: Record<string, unknown> = {}, skillIds: string[] = []) {
  const mcp: Record<string, unknown> = { ...existing };
  const skills: Record<string, { id: string; name: string; description: string; path: string; content: string }> = {};
  for (const id of skillIds) skills[id] = { id, name: id, description: "", path: "", content: "existing" };
  const ctx = {
    options,
    mcp: { transform: async (cb: (e: unknown) => void) => cb({ get: (n: string) => mcp[n], set: (n: string, v: unknown) => (mcp[n] = v) }) },
    skill: { transform: async (cb: (e: unknown) => void) => cb({ get: (id: string) => skills[id], add: (s: (typeof skills)[string]) => (skills[s.id] = s) }) },
  };
  await (plugin.setup as (c: unknown) => Promise<void>)(ctx);
  return { mcp, skills };
}

describe("opencode-specstream", () => {
  let saved: string | undefined;
  beforeEach(() => {
    saved = process.env.SPECSTREAM_API_KEY;
    delete process.env.SPECSTREAM_API_KEY;
  });
  afterEach(() => {
    if (saved === undefined) delete process.env.SPECSTREAM_API_KEY;
    else process.env.SPECSTREAM_API_KEY = saved;
  });

  it("identifies as specstream and answers to both hosts", () => {
    assert.equal(plugin.id, "specstream");
    assert.equal(typeof plugin.server, "function");
    assert.equal(typeof plugin.setup, "function");
  });

  it("points at the hosted MCP server", () => {
    assert.equal(MCP_URL, "https://api.specstream.ai/mcp");
    assert.deepEqual(remoteServer({}), { type: "remote", url: MCP_URL });
  });

  it("switches to a bearer header when an API key is set", () => {
    assert.deepEqual(remoteServer({ SPECSTREAM_API_KEY: " ss_live_test " }), {
      type: "remote",
      url: MCP_URL,
      headers: { Authorization: "Bearer ss_live_test" },
      oauth: false,
    });
    assert.deepEqual(remoteServer({ SPECSTREAM_API_KEY: "  " }), { type: "remote", url: MCP_URL });
  });

  it("only an explicit false turns an option off", () => {
    assert.equal(enabled(undefined, "mcp"), true);
    assert.equal(enabled({}, "mcp"), true);
    assert.equal(enabled({ mcp: false }, "mcp"), false);
    assert.equal(enabled({ mcp: false }, "skills"), true);
  });

  it("V1 adds the MCP server and the skills folder to an empty config", async () => {
    const config = await runV1({});
    assert.deepEqual(config.mcp, { specstream: { type: "remote", url: MCP_URL } });
    assert.deepEqual(config.skills?.paths, [skillsDir]);
  });

  it("V1 keeps a server the user already defined, and does not duplicate paths", async () => {
    const mine = { type: "remote", url: "https://example.test/mcp", oauth: false };
    const config = await runV1({ mcp: { specstream: mine, other: { type: "local" } }, skills: { paths: ["./team"] } });
    await runV1(config);
    assert.deepEqual(config.mcp?.specstream, mine);
    assert.ok(config.mcp?.other);
    assert.deepEqual(config.skills?.paths, ["./team", skillsDir]);
  });

  it("V1 honors the mcp and skills options", async () => {
    assert.deepEqual(await runV1({}, { mcp: false }), { skills: { paths: [skillsDir] } });
    assert.deepEqual(await runV1({}, { skills: false }), { mcp: { specstream: { type: "remote", url: MCP_URL } } });
  });

  it("V1 uses the API key from the environment", async () => {
    process.env.SPECSTREAM_API_KEY = "ss_live_test";
    const config = await runV1({});
    assert.deepEqual(config.mcp?.specstream, {
      type: "remote",
      url: MCP_URL,
      headers: { Authorization: "Bearer ss_live_test" },
      oauth: false,
    });
  });

  it("V2 registers the server and all six skills", async () => {
    const { mcp, skills } = await runV2();
    assert.deepEqual(mcp.specstream, { type: "remote", url: MCP_URL });
    assert.deepEqual(Object.keys(skills).sort(), ["approve-work", "compile", "continue-work", "extract-pages", "review-work", "search-web"]);
    for (const skill of Object.values(skills)) {
      assert.ok(skill.description, `${skill.name} has a description`);
      assert.ok(skill.content.startsWith("# "), `${skill.name} body starts at its heading`);
      assert.ok(existsSync(skill.path));
    }
  });

  it("V2 leaves existing entries alone and honors the options", async () => {
    const mine = { type: "remote", url: "https://example.test/mcp" };
    const kept = await runV2(undefined, { specstream: mine }, ["compile"]);
    assert.deepEqual(kept.mcp.specstream, mine);
    assert.equal(kept.skills.compile.content, "existing");

    const off = await runV2({ mcp: false, skills: false });
    assert.deepEqual(off.mcp, {});
    assert.deepEqual(off.skills, {});
  });

  it("bundles valid skills: folder name equals skill name", () => {
    const folders = readdirSync(skillsDir);
    assert.deepEqual(bundledSkills().map((s) => s.name).sort(), [...folders].sort());
  });

  it("ships the same skills as the repository's skills folder", () => {
    const upstream = join(root, "..", "..", "skills");
    if (!existsSync(upstream)) return; // running from the published package
    for (const name of readdirSync(upstream)) {
      assert.equal(
        readFileSync(join(skillsDir, name, "SKILL.md"), "utf8"),
        readFileSync(join(upstream, name, "SKILL.md"), "utf8"),
        `${name} drifted from skills/${name}; copy it over`,
      );
    }
  });
});
