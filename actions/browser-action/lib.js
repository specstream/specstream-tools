'use strict';
// Shared by main.js and post.js. No dependencies: Node's own fetch and fs.

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const DEFAULT_BASE_URL = 'https://api.specstream.ai';
const USER_AGENT = 'specstream-browser-action/1.0.0';
// A page load can take a while; the session's own timeout_s is the real limit.
const REQUEST_TIMEOUT_MS = 120_000;

class ActionFailure extends Error {}

function input(env, name, fallback = '') {
  const value = env[`INPUT_${name.toUpperCase()}`];
  return value === undefined || value.trim() === '' ? fallback : value.trim();
}

function flag(env, name, fallback) {
  const value = input(env, name, String(fallback)).toLowerCase();
  if (value === 'true') return true;
  if (value === 'false') return false;
  throw new ActionFailure(`${name} must be true or false, not "${value}"`);
}

function sessionBody(env) {
  const timeoutText = input(env, 'timeout_s', '300');
  const timeout = Number(timeoutText);
  if (!Number.isInteger(timeout) || timeout < 60 || timeout > 3600) {
    throw new ActionFailure(`timeout_s must be a whole number from 60 to 3600, not "${timeoutText}"`);
  }
  const body = {
    timeout_s: timeout,
    // The steps after this one connect and disconnect as they like; the post step ends the session.
    keep_alive: true,
    headless: flag(env, 'headless', true),
    block_media: flag(env, 'block_media', false),
    metadata: { source: 'github-action' },
  };
  const domains = input(env, 'allowed_domains')
    .split(/[\s,]+/)
    .filter(Boolean);
  if (domains.length) body.allowed_domains = domains;
  return body;
}

async function api(env, method, apiPath, body) {
  const key = input(env, 'api_key');
  if (!key) throw new ActionFailure('api_key is required. Keep it in a repository secret.');
  const base = input(env, 'base_url', DEFAULT_BASE_URL).replace(/\/+$/, '');
  let response;
  try {
    response = await fetch(base + apiPath, {
      method,
      headers: {
        Authorization: /^bearer /i.test(key) ? key : `Bearer ${key}`,
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'User-Agent': USER_AGENT,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (error) {
    throw new ActionFailure(`${method} ${apiPath} did not answer: ${error.message}`);
  }
  const text = await response.text();
  let payload = {};
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = {};
  }
  if (!response.ok) {
    const error = payload && payload.error ? payload.error : {};
    const code = error.code || `http_${response.status}`;
    const message = error.message || text.slice(0, 300) || response.statusText;
    throw new ActionFailure(`${method} ${apiPath} answered ${response.status} ${code}: ${message}`);
  }
  return payload && typeof payload.data === 'object' && payload.data !== null ? payload.data : payload;
}

// One step in the session. A step the browser refused (a blocked page, an unknown tool) answers
// 200 with error set, so it is checked here.
async function step(env, sessionId, tool, args) {
  const result = await api(env, 'POST', `/v1/browser/sessions/${encodeURIComponent(sessionId)}/actions`, {
    tool,
    arguments: args,
  });
  if (result.error) {
    const reason = result.error.reason ? ` (${result.error.reason})` : '';
    throw new ActionFailure(`${tool} failed: ${result.error.code}${reason}: ${result.error.message}`);
  }
  return result;
}

async function release(env, sessionId) {
  const ended = await api(env, 'POST', `/v1/browser/sessions/${encodeURIComponent(sessionId)}/release`);
  console.log(
    `Browser closed. ${ended.seconds ?? 0} s, ${ended.actions ?? 0} steps, $${ended.charged_usd ?? 0} charged.`,
  );
  return ended;
}

// The workflow command file protocol: name<<delimiter, value, delimiter.
function appendFileCommand(env, variable, name, value) {
  const file = env[variable];
  if (!file) return;
  const text = String(value ?? '');
  let delimiter = 'ss_eof';
  while (text.includes(delimiter)) delimiter += '_';
  fs.appendFileSync(file, `${name}<<${delimiter}${os.EOL}${text}${os.EOL}${delimiter}${os.EOL}`);
}

const setOutput = (env, name, value) => appendFileCommand(env, 'GITHUB_OUTPUT', name, value);
const saveState = (env, name, value) => appendFileCommand(env, 'GITHUB_STATE', name, value);

function mask(value) {
  if (value) process.stdout.write(`::add-mask::${value}${os.EOL}`);
}

function escapeCommand(text) {
  return String(text).replace(/%/g, '%25').replace(/\r/g, '%0D').replace(/\n/g, '%0A');
}

function outDir(env) {
  const dir = path.join(env.RUNNER_TEMP || os.tmpdir(), 'specstream-browser');
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

module.exports = {
  ActionFailure,
  api,
  escapeCommand,
  flag,
  input,
  mask,
  outDir,
  release,
  saveState,
  sessionBody,
  setOutput,
  step,
};
