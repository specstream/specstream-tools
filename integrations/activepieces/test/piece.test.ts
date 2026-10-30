import { test } from 'node:test';
import assert from 'node:assert/strict';
import { HttpMethod, httpClient } from '@activepieces/pieces-common';
import { specstreamApi, specstreamRows } from '../src/lib/common/client';
import { newRowTrigger } from '../src/lib/triggers/row-triggers';

type Req = { method: string; url: string };
function stub(handler: (req: Req) => unknown) {
  const calls: Req[] = [];
  (httpClient as { sendRequest: unknown }).sendRequest = async (req: Req) => {
    calls.push(req);
    return { status: 200, headers: {}, body: handler(req) };
  };
  return calls;
}

test('credential URLs: only paths or exactly https://api.specstream.ai', () => {
  const ok = ['/v1/me', 'https://api.specstream.ai/v1/me', 'https://api.specstream.ai'];
  const bad = [
    'http://api.specstream.ai/v1/me',
    'https://api.specstream.ai.evil.com/v1/me',
    'https://evil.com/v1/me',
    'https://api.specstream.ai@evil.com/',
    'https://user:pw@api.specstream.ai/v1/me',
    '//evil.com/v1/me',
    'v1/me',
    '/\\evil.com',
    'ftp://api.specstream.ai/',
  ];
  for (const u of ok) assert.equal(specstreamApi.isAllowedUrl(u), true, u);
  for (const u of bad) assert.equal(specstreamApi.isAllowedUrl(u), false, u);
});

test('run key is stable for the same request in the same UTC hour and changes otherwise', () => {
  const base = { request: 'Roofers in Columbus', count: 25, maxPrice: 5 };
  const a = specstreamApi.runKey({ ...base, now: new Date('2026-10-15T10:01:00Z') });
  const b = specstreamApi.runKey({ ...base, now: new Date('2026-10-15T10:59:59Z') });
  assert.equal(a, b);
  assert.match(a, /^activepieces-[a-f0-9]{32}$/);
  assert.notEqual(a, specstreamApi.runKey({ ...base, now: new Date('2026-10-15T11:00:00Z') }));
  assert.notEqual(a, specstreamApi.runKey({ ...base, count: 26, now: new Date('2026-10-15T10:30:00Z') }));
  assert.notEqual(a, specstreamApi.runKey({ ...base, request: 'Plumbers', now: new Date('2026-10-15T10:30:00Z') }));
  assert.notEqual(a, specstreamApi.runKey({ ...base, maxPrice: 6, now: new Date('2026-10-15T10:30:00Z') }));
  assert.equal(specstreamApi.runKey({ ...base, override: ' my-own-key-1 ' }), 'my-own-key-1');
});

test('columns named like built-in fields never overwrite them, and the pages come from the flat row', () => {
  const cell = (label: string, display: string) => ({ label, display });
  const flat = {
    id: 'fnd_1:e1',
    name: 'Acme',
    name_source: 'https://a.example/p',
    rating: '4.6',
    rating_source: 'https://maps.example/acme',
    lead_source: 'Referral',
    source_url: 'https://www.sec.gov/filing',
    checked_at: '2026-10-16T00:00:00Z',
  };
  const [row] = specstreamRows.flattenAll('fnd_1', [{
    entity_id: 'e1',
    ordinal: 3,
    cells: [
      cell('rating_source', 'x'),
      { ...cell('id', 'col-id'), provenance: { source_url: 'https://a.example/p', observed_at: '2026-10-15T00:00:00Z' } },
      cell('list_id', 'col-list'),
      cell('list_link', 'col-link'),
      cell('position', 'col-pos'),
      cell('source_url', 'col-src'),
      cell('checked_at', 'col-chk'),
      cell('id (column)', 'second'),
      cell('Name', 'Acme'),
      cell('Name', 'Acme again'),
    ],
  }], [flat]);
  assert.equal(row['id'], 'fnd_1:e1');
  assert.equal(row['list_id'], 'fnd_1');
  assert.equal(row['list_link'], 'https://specstream.ai/workspace/collections/fnd_1');
  assert.equal(row['position'], 3);
  assert.equal(row['source_url'], 'https://www.sec.gov/filing');
  assert.equal(row['checked_at'], '2026-10-16T00:00:00Z');
  assert.deepEqual([row['name_source'], row['rating_source']], ['https://a.example/p', 'https://maps.example/acme']);
  assert.equal(row['rating_source (column)'], 'x');
  assert.equal(row['lead_source'], undefined);
  assert.equal(row['id (column)'], 'col-id');
  assert.equal(row['id (column) (column)'], 'second');
  assert.equal(row['list_id (column)'], 'col-list');
  assert.equal(row['source_url (column)'], 'col-src');
  assert.equal(row['Name'], 'Acme');
  assert.equal(row['Name (column)'], 'Acme again');
});

test('latest picks the newest finished list, not the first one with rows', async () => {
  const finds: Record<string, unknown> = {
    fnd_old: { find_id: 'fnd_old', status: 'completed', updated_at: '2026-10-01T00:00:00Z' },
    fnd_running: { find_id: 'fnd_running', status: 'running', updated_at: '2026-10-15T00:00:00Z' },
    fnd_new: { find_id: 'fnd_new', status: 'completed', updated_at: '2026-10-10T00:00:00Z' },
  };
  const calls = stub(({ url }) => {
    const path = url.replace('https://api.specstream.ai', '');
    if (path.startsWith('/v1/specs?')) return { data: { specs: [{ spec_id: 'spc_1' }] } };
    if (path.startsWith('/v1/specs/')) return { data: { finds: [{ find_id: 'fnd_old' }, { find_id: 'fnd_running' }, { find_id: 'fnd_new' }] } };
    const rows = /^\/v1\/finds\/([^/]+)\/rows$/.exec(path);
    if (rows) {
      const f = finds[rows[1]] as { status: string };
      return { data: { find_id: rows[1], status: f.status, rows: [{ entity_id: 'e', ordinal: 1, cells: [] }] } };
    }
    return { data: finds[path.split('/').pop() as string] };
  });
  const out = await specstreamRows.latest('key');
  assert.equal(out[0]?.['list_id'], 'fnd_new');
  assert.ok(!calls.some((c) => c.url.includes('fnd_running/rows')));
});

test('enabling again deletes the stored webhook first, and a missing one is fine', async () => {
  const store = new Map<string, unknown>([['specstream_webhook', { hook_id: 'hk_old', secret: 's_old' }]]);
  const calls = stub((req) => (req.method === HttpMethod.POST ? { data: { hook_id: 'hk_new', secret: 's_new' } } : { data: {} }));
  const context = {
    auth: { secret_text: 'key' },
    webhookUrl: 'https://flows.example/hook',
    store: {
      get: async (k: string) => store.get(k),
      put: async (k: string, v: unknown) => void store.set(k, v),
      delete: async (k: string) => void store.delete(k),
    },
  };
  await (newRowTrigger as any).onEnable(context);
  assert.deepEqual(
    calls.map((c) => `${c.method} ${c.url.replace('https://api.specstream.ai', '')}`),
    ['DELETE /v1/account/webhooks/hk_old', 'POST /v1/account/webhooks'],
  );
  assert.deepEqual(store.get('specstream_webhook'), { hook_id: 'hk_new', secret: 's_new' });

  // The old hook is already gone (404): still registers the new one.
  (httpClient as { sendRequest: unknown }).sendRequest = async (req: Req) => {
    if (req.method === HttpMethod.DELETE) throw Object.assign(new Error('gone'), { response: { status: 404, body: {} } });
    return { status: 200, headers: {}, body: { data: { hook_id: 'hk_3', secret: 's3' } } };
  };
  await (newRowTrigger as any).onEnable(context);
  assert.equal((store.get('specstream_webhook') as { hook_id: string }).hook_id, 'hk_3');
});
