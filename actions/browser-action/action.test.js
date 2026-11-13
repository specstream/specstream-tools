'use strict';
// node --test actions/browser-action/action.test.js
// main.js and post.js run as GitHub runs them (a process with INPUT_ and GITHUB_ variables) against
// a scripted API on localhost. Nothing calls SpecStream.

const assert = require('node:assert/strict');
const { execFile } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');

const HERE = __dirname;
const SESSION = {
  id: 'bs_1',
  status: 'running',
  connect_url: 'wss://browser.example/connect?token=tok_1',
  live_url: 'https://browser.example/live/bs_1?token=tok_1',
  timeout_s: 300,
};
const PNG = Buffer.from('not really a png');

function fakeApi(overrides = {}) {
  const calls = [];
  const server = http.createServer((req, res) => {
    let raw = '';
    req.on('data', (chunk) => (raw += chunk));
    req.on('end', () => {
      const body = raw ? JSON.parse(raw) : null;
      calls.push({ method: req.method, path: req.url, auth: req.headers.authorization, body });
      const answer = (status, payload) => {
        res.writeHead(status, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(payload));
      };
      const key = `${req.method} ${req.url}${body && body.tool ? ` ${body.tool}` : ''}`;
      if (overrides[key]) return answer(...overrides[key]);
      if (key === 'POST /v1/browser/sessions') return answer(201, { data: SESSION });
      if (key === 'POST /v1/browser/sessions/bs_1/release') {
        return answer(200, { data: { ...SESSION, status: 'ended', seconds: 12, actions: 2, charged_usd: 0.0023 } });
      }
      if (key.endsWith('browser_navigate')) {
        return answer(200, { data: { result: [], url: body.arguments.url, took_ms: 5, price_usd: 0.001 } });
      }
      if (key.endsWith('browser_read')) {
        return answer(200, {
          data: {
            result: [{ type: 'text', text: '# Example Domain' }],
            url: 'https://example.com/',
            title: 'Example Domain',
            took_ms: 5,
            price_usd: 0.001,
          },
        });
      }
      if (key.endsWith('browser_take_screenshot')) {
        return answer(200, {
          data: {
            result: [{ type: 'image', data: PNG.toString('base64'), mime_type: 'image/png' }],
            took_ms: 5,
            price_usd: 0.001,
          },
        });
      }
      return answer(404, { error: { code: 'not_found', message: key } });
    });
  });
  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      resolve({ calls, server, base: `http://127.0.0.1:${server.address().port}` });
    });
  });
}

function parseCommandFile(file) {
  const out = {};
  const lines = fs.existsSync(file) ? fs.readFileSync(file, 'utf8').split(os.EOL) : [];
  for (let i = 0; i < lines.length; i += 1) {
    const match = /^([^<]+)<<(.+)$/.exec(lines[i]);
    if (!match) continue;
    const value = [];
    for (i += 1; lines[i] !== match[2]; i += 1) value.push(lines[i]);
    out[match[1]] = value.join('\n');
  }
  return out;
}

function runScript(script, env) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ss-browser-action-'));
  const files = { GITHUB_OUTPUT: path.join(dir, 'output'), GITHUB_STATE: path.join(dir, 'state'), RUNNER_TEMP: dir };
  return new Promise((resolve) => {
    execFile(
      process.execPath,
      [path.join(HERE, script)],
      { env: { PATH: process.env.PATH, ...files, ...env } },
      (error, stdout) => {
        resolve({
          code: error ? error.code : 0,
          stdout,
          outputs: parseCommandFile(files.GITHUB_OUTPUT),
          state: parseCommandFile(files.GITHUB_STATE),
        });
      },
    );
  });
}

async function withApi(overrides, body) {
  const api = await fakeApi(overrides);
  try {
    return await body(api);
  } finally {
    api.server.close();
  }
}

test('opens a browser and hands connect_url to the next steps, masked', () =>
  withApi({}, async (api) => {
    const run = await runScript('main.js', {
      INPUT_API_KEY: 'ss_test_x',
      INPUT_BASE_URL: api.base,
      INPUT_ALLOWED_DOMAINS: 'example.com, *.example.org',
    });
    assert.equal(run.code, 0, run.stdout);
    assert.deepEqual(api.calls.map((c) => `${c.method} ${c.path}`), ['POST /v1/browser/sessions']);
    assert.equal(api.calls[0].auth, 'Bearer ss_test_x');
    assert.deepEqual(api.calls[0].body, {
      timeout_s: 300,
      keep_alive: true,
      headless: true,
      block_media: false,
      metadata: { source: 'github-action' },
      allowed_domains: ['example.com', '*.example.org'],
    });
    assert.equal(run.outputs.session_id, 'bs_1');
    assert.equal(run.outputs.connect_url, SESSION.connect_url);
    assert.equal(run.outputs.live_url, SESSION.live_url);
    assert.equal(run.state.session_id, 'bs_1');
    assert.equal(run.state.released, undefined);
    assert.ok(run.stdout.includes(`::add-mask::${SESSION.connect_url}`));
    assert.ok(run.stdout.includes(`::add-mask::${SESSION.live_url}`));
  }));

test('reads a page and saves a screenshot, then closes when keep_open is false', () =>
  withApi({}, async (api) => {
    const run = await runScript('main.js', {
      INPUT_API_KEY: 'ss_test_x',
      INPUT_BASE_URL: api.base,
      INPUT_URL: 'https://example.com',
      INPUT_SCREENSHOT: 'true',
      INPUT_KEEP_OPEN: 'false',
    });
    assert.equal(run.code, 0, run.stdout);
    assert.deepEqual(
      api.calls.map((c) => (c.body && c.body.tool) || c.path),
      ['/v1/browser/sessions', 'browser_navigate', 'browser_read', 'browser_take_screenshot', '/v1/browser/sessions/bs_1/release'],
    );
    assert.deepEqual(api.calls[1].body.arguments, { url: 'https://example.com' });
    assert.deepEqual(api.calls[2].body.arguments, { format: 'markdown' });
    assert.equal(fs.readFileSync(run.outputs.page_path, 'utf8'), '# Example Domain');
    assert.ok(run.outputs.page_path.endsWith('page.md'));
    assert.equal(run.outputs.page_url, 'https://example.com/');
    assert.equal(run.outputs.page_title, 'Example Domain');
    assert.deepEqual(fs.readFileSync(run.outputs.screenshot_path), PNG);
    assert.equal(run.outputs.connect_url, undefined);
    assert.equal(run.state.released, 'true');
    assert.ok(run.stdout.includes('$0.0023 charged'));
  }));

test('a blocked page fails the step and closes the browser at once', () =>
  withApi(
    {
      'POST /v1/browser/sessions/bs_1/actions browser_navigate': [
        200,
        { data: { result: [], error: { code: 'blocked', reason: 'domain_not_allowed', message: 'not in allowed_domains' }, took_ms: 1, price_usd: 0 } },
      ],
    },
    async (api) => {
      const run = await runScript('main.js', {
        INPUT_API_KEY: 'ss_test_x',
        INPUT_BASE_URL: api.base,
        INPUT_URL: 'https://other.example',
      });
      assert.equal(run.code, 1);
      assert.ok(run.stdout.includes('::error::browser_navigate failed: blocked (domain_not_allowed): not in allowed_domains'));
      assert.equal(api.calls.at(-1).path, '/v1/browser/sessions/bs_1/release');
      assert.equal(run.state.released, 'true');
      assert.equal(run.outputs.page_path, undefined);
    },
  ));

test('a refused key fails with the API’s own words and opens nothing', () =>
  withApi(
    { 'POST /v1/browser/sessions': [401, { error: { code: 'invalid_api_key', message: 'This key was revoked.' } }] },
    async (api) => {
      const run = await runScript('main.js', { INPUT_API_KEY: 'ss_test_x', INPUT_BASE_URL: api.base });
      assert.equal(run.code, 1);
      assert.ok(run.stdout.includes('answered 401 invalid_api_key: This key was revoked.'));
      assert.equal(run.state.session_id, undefined);
      assert.equal(api.calls.length, 1);
    },
  ));

test('bad inputs stop before any call', () =>
  withApi({}, async (api) => {
    const cases = [
      [{ INPUT_TIMEOUT_S: '5' }, 'timeout_s must be a whole number from 60 to 3600'],
      [{ INPUT_FORMAT: 'html' }, 'format must be markdown or text'],
      [{ INPUT_KEEP_OPEN: 'false' }, 'Nothing to do'],
      [{ INPUT_SCREENSHOT: 'true' }, 'screenshot needs url'],
      [{ INPUT_HEADLESS: 'no' }, 'headless must be true or false'],
      [{ INPUT_API_KEY: '' }, 'api_key is required'],
    ];
    for (const [env, words] of cases) {
      const run = await runScript('main.js', { INPUT_API_KEY: 'ss_test_x', INPUT_BASE_URL: api.base, ...env });
      assert.equal(run.code, 1, words);
      assert.ok(run.stdout.includes(words), run.stdout);
    }
    assert.equal(api.calls.length, 0);
  }));

test('the post step closes the open browser, once', () =>
  withApi({}, async (api) => {
    const env = { INPUT_API_KEY: 'ss_test_x', INPUT_BASE_URL: api.base };
    const run = await runScript('post.js', { ...env, STATE_session_id: 'bs_1' });
    assert.equal(run.code, 0);
    assert.ok(run.stdout.includes('Browser closed. 12 s, 2 steps, $0.0023 charged.'));
    assert.deepEqual(api.calls.map((c) => c.path), ['/v1/browser/sessions/bs_1/release']);
    await runScript('post.js', { ...env, STATE_session_id: 'bs_1', STATE_released: 'true' });
    await runScript('post.js', env);
    assert.equal(api.calls.length, 1);
  }));

test('a release that fails in the post step warns and does not fail the job', () =>
  withApi(
    { 'POST /v1/browser/sessions/bs_1/release': [500, { error: { code: 'server_error', message: 'try again' } }] },
    async (api) => {
      const run = await runScript('post.js', {
        INPUT_API_KEY: 'ss_test_x',
        INPUT_BASE_URL: api.base,
        STATE_session_id: 'bs_1',
      });
      assert.equal(run.code, 0);
      assert.ok(run.stdout.includes('::warning::The browser was not closed now and ends at its timeout'));
    },
  ));
