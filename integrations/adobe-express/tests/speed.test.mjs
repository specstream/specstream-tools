import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { webSearch, searchUrl } from '../src/api.js';

// A scripted answer: no test calls the network.
function answer(body, seen) {
  return async (url) => {
    seen.push(url);
    return { ok: true, status: 200, json: async () => body };
  };
}
const ranked = { answer: null, rows: [], sources: [{ url: 'https://a.example/x', title: 'A' }] };

test('a fast search sends speed=fast and lists the ranked results', async () => {
  const seen = [];
  const hits = await webSearch(answer(ranked, seen), 'k', 'q', 'fast');
  assert.equal(new URL(seen[0]).searchParams.get('speed'), 'fast');
  assert.deepEqual(hits.map((h) => h.url), ['https://a.example/x']);
});

test('a search with no speed sends none, so the API default runs', async () => {
  const seen = [];
  await webSearch(answer(ranked, seen), 'k', 'q');
  assert.equal(new URL(seen[0]).searchParams.has('speed'), false);
  assert.equal(new URL(searchUrl('q', 'default')).searchParams.get('speed'), 'default');
});

test('an unknown speed is refused before any call', async () => {
  const seen = [];
  await assert.rejects(webSearch(answer(ranked, seen), 'k', 'q', 'turbo'), /fast or default/);
  assert.equal(seen.length, 0);
});

test('the panel and the README name the fast price', () => {
  const html = readFileSync(new URL('../src/index.html', import.meta.url), 'utf8');
  assert.match(html, /id="fast"[^\n]*\$1 per 1,000 searches/);
  const ui = readFileSync(new URL('../src/ui.js', import.meta.url), 'utf8');
  assert.match(ui, /\$\('fast'\)\.checked \? 'fast' : undefined/);
  const readme = readFileSync(new URL('../README.md', import.meta.url), 'utf8');
  assert.match(readme, /a fast search costs \$1 per 1,000/);
});
