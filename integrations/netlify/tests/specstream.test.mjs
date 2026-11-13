// Plain Node, no network: the fetch is scripted. Node 22.18 or later reads the .ts source directly.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { API_BASE, KEY_VARIABLE, buildLine, checkKey, keyHint, keyProblem } from "../src/lib/specstream.ts";

const KEY = "ss_live_scripted";
const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

function scripted(status, body) {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return { status, json: async () => body };
  };
  return { calls, fetchImpl };
}

test("a pasted text is refused before any call when it is not shaped like a key", async () => {
  assert.match(keyProblem(""), /Paste a SpecStream API key/);
  assert.match(keyProblem("tvly-123"), /starts with ss_live_/);
  assert.match(keyProblem("ss_live_"), /starts with ss_live_/);
  assert.match(keyProblem("ss_live_ab cd"), /starts with ss_live_/);
  assert.equal(keyProblem(`  ${KEY}\n`), null);
  const { calls, fetchImpl } = scripted(200, {});
  const answer = await checkKey("tvly-123", fetchImpl);
  assert.equal(answer.ok, false);
  assert.equal(calls.length, 0);
});

test("the check is one free GET of /v1/me with the key as a Bearer token", async () => {
  const { calls, fetchImpl } = scripted(200, { data: { email: "dev@example.com" } });
  const answer = await checkKey(` ${KEY} `, fetchImpl);
  assert.deepEqual(answer, { ok: true, email: "dev@example.com" });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, `${API_BASE}/v1/me`);
  assert.equal(calls[0].init.method, "GET");
  assert.equal(calls[0].init.headers.Authorization, `Bearer ${KEY}`);
  assert.ok(calls[0].init.signal, "the call has a time limit");
});

test("an answer without an email still connects", async () => {
  assert.deepEqual(await checkKey(KEY, scripted(200, {}).fetchImpl), { ok: true, email: null });
  const broken = async () => ({ status: 200, json: async () => { throw new Error("not json"); } });
  assert.deepEqual(await checkKey(KEY, broken), { ok: true, email: null });
});

test("a refused key, a server error and no answer each say what to do, and never repeat the key", async () => {
  const refused = await checkKey(KEY, scripted(401, {}).fetchImpl);
  assert.equal(refused.ok, false);
  assert.match(refused.message, /did not accept this key/);
  const down = await checkKey(KEY, scripted(503, {}).fetchImpl);
  assert.match(down.message, /status 503.*not saved/);
  const silent = await checkKey(KEY, async () => { throw new Error(`socket closed for ${KEY}`); });
  assert.match(silent.message, /did not answer.*not saved/);
  for (const answer of [refused, down, silent]) {
    assert.ok(!answer.message.includes(KEY));
  }
});

test("only the last four characters of a key are kept", () => {
  assert.equal(keyHint(KEY), "ss_live_...wxyz");
  assert.ok(!keyHint(KEY).includes("scripted"));
});

test("the build log gets one line with the variable name and never the key", () => {
  assert.equal(buildLine({}), null);
  assert.equal(buildLine({ [KEY_VARIABLE]: "" }), null);
  const line = buildLine({ [KEY_VARIABLE]: KEY });
  assert.match(line, /SPECSTREAM_API_KEY/);
  assert.ok(!line.includes(KEY));
});

test("the build event handler cannot fail a build or call the network", () => {
  const source = read("src/index.ts");
  assert.match(source, /addBuildEventHandler\("onPreBuild"/);
  assert.ok(!/failBuild|failPlugin|fetch\(/.test(source));
  assert.match(source, /export \{ extension \}/);
});

test("the key is saved as a secret team variable and never in the team configuration", () => {
  const router = read("src/server/router.ts");
  assert.match(router, /isSecret: true/);
  assert.match(router, /upsertTeamConfiguration\(team, \{ keyHint: keyHint\(key\), email: check\.email \}\)/);
  assert.ok(!/siteId/.test(router), "the variable is the team's, not one site's");
  const schema = read("src/schema/team-config.ts");
  const kept = schema.slice(schema.indexOf("TeamConfigSchema"));
  assert.ok(!/apiKey/.test(kept));
});

test("the manifest and the Netlify build file are what the SDK reads", () => {
  const manifest = read("extension.yaml");
  assert.match(manifest, /^  slug: specstream/m);
  assert.match(manifest, /^  name: SpecStream$/m);
  assert.match(manifest, /- extension-team-configuration/);
  const toml = read("netlify.toml");
  assert.match(toml, /command = "netlify-extension build"/);
  assert.match(toml, /publish = "\.ntli\/site\/static"/);
  assert.match(toml, /directory = "src\/endpoints"/);
  assert.match(toml, /package = "@netlify\/netlify-plugin-netlify-extension"/);
  const pkg = JSON.parse(read("package.json"));
  assert.equal(pkg.main, "src/index.ts");
  assert.equal(pkg.type, "module");
  assert.ok(pkg.dependencies["@netlify/sdk"]);
});

test("the words a stranger reads give today's prices and carry no dash", () => {
  for (const path of ["README.md", "details.md"]) {
    const text = read(path);
    assert.match(text, /\$5 per 1,000 searches/, path);
    assert.match(text, /\$0\.80 per 1,000 pages/, path);
    assert.ok(!/[–—]/.test(text), `${path} has a dash`);
    assert.ok(!/ss_live_[A-Za-z0-9]{8,}/.test(text), `${path} prints something shaped like a key`);
  }
});
