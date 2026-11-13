'use strict';
// Open a browser session, optionally open and read one page, and hand the session to the next steps.

const fs = require('node:fs');
const path = require('node:path');
const lib = require('./lib.js');

async function releaseNow(env, sessionId) {
  await lib.release(env, sessionId);
  lib.saveState(env, 'released', 'true');
}

async function run(env) {
  const url = lib.input(env, 'url');
  const format = lib.input(env, 'format', 'markdown').toLowerCase();
  if (format !== 'markdown' && format !== 'text') {
    throw new lib.ActionFailure(`format must be markdown or text, not "${format}"`);
  }
  const screenshot = lib.flag(env, 'screenshot', false);
  const keepOpen = lib.flag(env, 'keep_open', true);
  if (!url && !keepOpen) {
    throw new lib.ActionFailure('Nothing to do: set url, or leave keep_open true to connect your own code.');
  }
  if (!url && screenshot) throw new lib.ActionFailure('screenshot needs url.');
  const body = lib.sessionBody(env);

  const session = await lib.api(env, 'POST', '/v1/browser/sessions', body);
  // Saved before anything else can fail, so the post step always closes what was opened.
  lib.saveState(env, 'session_id', session.id);
  lib.mask(session.connect_url);
  lib.mask(session.live_url);
  lib.setOutput(env, 'session_id', session.id);
  console.log(`Browser open: session ${session.id}, at most ${session.timeout_s ?? body.timeout_s} s.`);

  try {
    if (url) {
      await lib.step(env, session.id, 'browser_navigate', { url });
      const read = await lib.step(env, session.id, 'browser_read', { format });
      const text = (read.result || [])
        .filter((part) => part.type === 'text' && part.text)
        .map((part) => part.text)
        .join('\n');
      const dir = lib.outDir(env);
      const pagePath = path.join(dir, format === 'markdown' ? 'page.md' : 'page.txt');
      fs.writeFileSync(pagePath, text);
      lib.setOutput(env, 'page_path', pagePath);
      lib.setOutput(env, 'page_url', read.url || url);
      lib.setOutput(env, 'page_title', read.title || '');
      console.log(`Read ${read.url || url}: ${text.length} characters in ${pagePath}`);
      if (screenshot) {
        const shot = await lib.step(env, session.id, 'browser_take_screenshot', { type: 'png' });
        const image = (shot.result || []).find((part) => part.type === 'image' && part.data);
        if (!image) throw new lib.ActionFailure('browser_take_screenshot returned no image.');
        const shotPath = path.join(dir, 'page.png');
        fs.writeFileSync(shotPath, Buffer.from(image.data, 'base64'));
        lib.setOutput(env, 'screenshot_path', shotPath);
        console.log(`Screenshot in ${shotPath}`);
      }
    }
  } catch (error) {
    // The post step would close it too; closing now stops the meter sooner.
    await releaseNow(env, session.id).catch(() => {});
    throw error;
  }

  if (keepOpen) {
    lib.setOutput(env, 'connect_url', session.connect_url || '');
    lib.setOutput(env, 'live_url', session.live_url || '');
  } else {
    await releaseNow(env, session.id);
  }
}

run(process.env).catch((error) => {
  const message = error instanceof lib.ActionFailure ? error.message : error.stack || String(error);
  process.stdout.write(`::error::${lib.escapeCommand(message)}\n`);
  process.exitCode = 1;
});
