import { test } from 'node:test';
import assert from 'node:assert/strict';
import { httpClient } from '@activepieces/pieces-common';
import { webSearchAction } from '../src/lib/actions/web-search';

// Web Search passes the Search API's speed: fast at $1 per 1,000, the API's default when left empty.

type Req = { method: string; url: string };
function stub() {
  const calls: Req[] = [];
  (httpClient as { sendRequest: unknown }).sendRequest = async (req: Req) => {
    calls.push(req);
    return { status: 200, headers: {}, body: { data: { kind: 'fact', sources: [] } } };
  };
  return calls;
}

const run = (props: Record<string, unknown>) =>
  (webSearchAction as any).run({ auth: { secret_text: 'key' }, propsValue: { q: 'capital of Portugal', ...props } });

test('a fast search sends speed=fast; left empty, no speed is sent', async () => {
  const calls = stub();
  await run({ speed: 'fast' });
  await run({});
  assert.deepEqual(calls.map((c) => new URL(c.url).searchParams.get('speed')), ['fast', null]);
});

test('an unknown speed is refused before any call', async () => {
  const calls = stub();
  await assert.rejects(run({ speed: 'turbo' }), /Speed/);
  assert.equal(calls.length, 0);
});

test('the Speed field names the fast price', () => {
  const field = (webSearchAction as any).props.speed;
  assert.deepEqual(field.options.options.map((o: { value: string }) => o.value), ['fast', 'default']);
  assert.match(field.description, /\$1 per 1,000/);
});
