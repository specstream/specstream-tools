'use strict';
// Runs when the job ends, passed or failed: close the browser main.js opened, so the meter stops.

const lib = require('./lib.js');

async function run(env) {
  const sessionId = env.STATE_session_id;
  if (!sessionId || env.STATE_released === 'true') return;
  await lib.release(env, sessionId);
}

run(process.env).catch((error) => {
  // Not a failure of the job: the session ends on its own at timeout_s.
  const message = error instanceof lib.ActionFailure ? error.message : String(error);
  process.stdout.write(
    `::warning::${lib.escapeCommand(`The browser was not closed now and ends at its timeout: ${message}`)}\n`,
  );
});
