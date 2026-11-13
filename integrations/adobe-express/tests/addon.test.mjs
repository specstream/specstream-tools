import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import {
  API, ApiError, webSearch, extract, parseUrls, searchUrl, hitsToLines, pagesToLines, linesToBlock, PAGE_LIMIT,
} from '../src/api.js';
import { zip, packageFiles } from '../package.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

// A scripted answer: no test calls the network.
function answer(status, body, seen) {
  return async (url, init) => {
    if (seen) seen.push({ url, init });
    return { ok: status >= 200 && status < 300, status, json: async () => body };
  };
}

test('search sends the key as a bearer token to api.specstream.ai and maps the sources', async () => {
  const seen = [];
  const hits = await webSearch(
    answer(200, { sources: [{ title: 'A', url: 'https://a.example/x', snippet: 's', site: 'a.example' }, { nourl: 1 }] }, seen),
    '  key-1  ',
    ' coffee chains ',
  );
  assert.equal(seen[0].url, `${API}/v1/web-search?q=coffee%20chains`);
  assert.equal(seen[0].init.method, 'GET');
  assert.equal(seen[0].init.headers.Authorization, 'Bearer key-1');
  assert.deepEqual(hits, [{ title: 'A', url: 'https://a.example/x', snippet: 's', site: 'a.example' }]);
  assert.equal(searchUrl('a b&c'), `${API}/v1/web-search?q=a%20b%26c`);
});

test('search refuses an empty question, a long question and a missing key before any call', async () => {
  const seen = [];
  const f = answer(200, {}, seen);
  await assert.rejects(webSearch(f, 'k', '   '), /Type a question first/);
  await assert.rejects(webSearch(f, 'k', 'x'.repeat(2001)), /under 2,000/);
  await assert.rejects(webSearch(f, '  ', 'q'), /Paste your SpecStream API key/);
  assert.equal(seen.length, 0);
});

test('each failure says what to do next', async () => {
  await assert.rejects(webSearch(answer(401, {}), 'k', 'q'), (e) => e instanceof ApiError && e.status === 401 && /not accepted/.test(e.message));
  await assert.rejects(webSearch(answer(402, {}), 'k', 'q'), /Add credit/);
  await assert.rejects(webSearch(answer(429, {}), 'k', 'q'), /Try again in a moment/);
  await assert.rejects(webSearch(answer(500, { detail: 'boom' }), 'k', 'q'), /boom/);
  await assert.rejects(webSearch(answer(503, null), 'k', 'q'), /answered 503/);
  const down = async () => { throw new TypeError('network'); };
  await assert.rejects(webSearch(down, 'k', 'q'), /could not be reached/);
});

test('extract posts up to 20 URLs as JSON', async () => {
  const seen = [];
  const pages = await extract(
    answer(200, { results: [{ url: 'https://a.example', title: 'T', status: 'ok', text: 'hello' }] }, seen),
    'k',
    ['https://a.example'],
  );
  assert.equal(seen[0].url, `${API}/v1/extract`);
  assert.equal(seen[0].init.method, 'POST');
  assert.deepEqual(JSON.parse(seen[0].init.body), { urls: ['https://a.example'], format: 'markdown' });
  assert.equal(pages[0].text, 'hello');
  await assert.rejects(extract(answer(200, {}), 'k', []), /at least one/);
  const many = Array.from({ length: 21 }, (_, i) => `https://a.example/${i}`);
  await assert.rejects(extract(answer(200, {}), 'k', many), /up to 20/);
});

test('parseUrls keeps http and https addresses once each', () => {
  assert.deepEqual(parseUrls('https://a.example, ftp://x  http://b.example\nhttps://a.example notaurl'), ['https://a.example', 'http://b.example']);
});

test('search rows become a text block with the source URL on every row and title ranges', () => {
  const block = linesToBlock(hitsToLines([
    { title: 'First\ntitle', url: 'https://a.example', snippet: 'One.', site: '' },
    { title: 'Second', url: 'https://b.example', snippet: '', site: '' },
  ]));
  assert.equal(block.text, 'First title\nOne.\nhttps://a.example\n\nSecond\nhttps://b.example');
  assert.deepEqual(block.heads.map((h) => block.text.substr(h.start, h.length)), ['First title', 'Second']);
  assert.deepEqual(linesToBlock(hitsToLines([])), { text: '', heads: [] });
});

test('pages become a text block, cut at the page limit, and a page with no text says so', () => {
  const lines = pagesToLines([
    { url: 'https://a.example', title: 'A', status: 'ok', text: `para one\n\npara two ${'x'.repeat(PAGE_LIMIT)}` },
    { url: 'https://b.example', title: '', status: 'blocked', text: '' },
  ]);
  const block = linesToBlock(lines);
  assert.ok(block.text.startsWith('A\nhttps://a.example\npara one\npara two '));
  assert.ok(block.text.includes('...\n\nhttps://b.example\nNo text (blocked).'));
  assert.ok(block.text.length < PAGE_LIMIT + 200);
  assert.deepEqual(block.heads.map((h) => block.text.substr(h.start, h.length)), ['A', 'https://b.example']);
});

test('the manifest is what Adobe Express loads: a panel, a document sandbox, no experimental APIs', () => {
  const m = JSON.parse(readFileSync(join(root, 'src/manifest.json'), 'utf8'));
  assert.equal(m.manifestVersion, 2);
  assert.match(m.version, /^\d+\.\d+\.\d+$/);
  assert.deepEqual(m.requirements.apps.map((a) => [a.name, a.apiVersion]), [['Express', 1]]);
  assert.equal(m.requirements.experimentalApis, undefined);
  assert.equal(m.entryPoints.length, 1);
  const e = m.entryPoints[0];
  assert.equal(e.type, 'panel');
  for (const f of [e.main, e.documentSandbox]) readFileSync(join(root, 'src', f));
  const allowed = ['allow-popups', 'allow-popups-to-escape-sandbox', 'allow-presentation', 'allow-downloads'];
  for (const s of e.permissions.sandbox) assert.ok(allowed.includes(s), s);
  assert.equal(m.version, JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')).version);
});

test('the package has the manifest at the root of the zip, without the development fields', () => {
  const files = packageFiles();
  assert.equal(files[0].name, 'manifest.json');
  assert.deepEqual(files.map((f) => f.name).sort(), ['api.js', 'code.js', 'index.html', 'manifest.json', 'styles.css', 'ui.js']);
  const m = JSON.parse(files[0].data.toString('utf8'));
  assert.equal(m.testId, undefined);
  assert.equal(m.name, undefined);
  assert.equal(m.entryPoints[0].documentSandbox, 'code.js');

  const z = zip(files);
  assert.equal(z.readUInt32LE(0), 0x04034b50);
  const end = z.length - 22;
  assert.equal(z.readUInt32LE(end), 0x06054b50);
  assert.equal(z.readUInt16LE(end + 10), files.length);
  assert.equal(z.subarray(30, 30 + 'manifest.json'.length).toString('utf8'), 'manifest.json');
  assert.ok(z.equals(zip(packageFiles())), 'the same source gives the same zip');
});

test('the key, the question and the URLs can only go to SpecStream', () => {
  const read = (f) => readFileSync(join(root, 'src', f), 'utf8');
  const hosts = new Set([...`${read('ui.js')}${read('api.js')}${read('index.html')}${read('code.js')}`.matchAll(/https:\/\/([a-z0-9.-]+)/g)].map((m) => m[1]));
  hosts.delete('example.com');
  assert.deepEqual([...hosts].sort(), ['api.specstream.ai', 'express.adobe.com', 'specstream.ai']);
});
