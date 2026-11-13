// Stagehand 3 on a SpecStream browser session.
//
// SpecStream answers Browserbase's session API at https://api.specstream.ai/browserbase, so Stagehand
// runs unchanged: env stays "BROWSERBASE", the address and the key are SpecStream's. disableAPI keeps
// Stagehand's own hosted API out of the way, so every step goes straight to the session's browser.
//
//   SPECSTREAM_API_KEY          your key (Agents & API in the SpecStream workspace)
//   START_URL                   the page to open (default https://example.com)
//   STAGEHAND_MODEL             optional, for example "openai/gpt-4.1-mini" with OPENAI_API_KEY set:
//                               adds one extract() step that asks the model about the page
//   SPECSTREAM_BROWSERBASE_URL  optional, another address for the session API

const key = process.env.SPECSTREAM_API_KEY;
if (!key) {
  console.error("Set SPECSTREAM_API_KEY first: the key is under Agents & API in the SpecStream workspace.");
  process.exit(2);
}
// The Browserbase client inside Stagehand reads its address from this variable.
process.env.BROWSERBASE_BASE_URL =
  process.env.SPECSTREAM_BROWSERBASE_URL || "https://api.specstream.ai/browserbase";

const { Stagehand } = require("@browserbasehq/stagehand");

async function main() {
  const model = process.env.STAGEHAND_MODEL;
  const stagehand = new Stagehand({
    env: "BROWSERBASE",
    apiKey: key,
    projectId: "specstream", // Browserbase's client asks for one; SpecStream does not read it
    disableAPI: true,
    verbose: 0,
    disablePino: true,
    browserbaseSessionCreateParams: { timeout: 300 }, // seconds: the session ends by itself after this
    ...(model ? { model } : {}),
  });
  await stagehand.init();
  const out = { session: stagehand.browserbaseSessionID };
  try {
    const page = stagehand.context.pages()[0];
    await page.goto(process.env.START_URL || "https://example.com");
    out.title = await page.title();
    if (model) {
      out.extract = await stagehand.extract("What is this page about? Answer in one sentence.");
    }
  } finally {
    // close() disconnects, and a session without keepAlive ends at the disconnect: billing stops here.
    await stagehand.close();
  }
  console.log(JSON.stringify(out, null, 2));
}

main().catch((error) => {
  console.error(String(error && error.message ? error.message : error));
  process.exit(1);
});
