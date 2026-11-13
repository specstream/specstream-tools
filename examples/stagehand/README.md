# Stagehand on a SpecStream browser session

[Stagehand](https://github.com/browserbase/stagehand) 3 opens a browser on SpecStream, goes to a page, reads its title and closes the session. Stagehand's code does not change: SpecStream answers Browserbase's session API at `https://api.specstream.ai/browserbase`, so only the address and the key are different.

```sh
npm install
export SPECSTREAM_API_KEY="ss_live_..."
npm start
```

```json
{
  "session": "brs_...",
  "title": "Example Domain"
}
```

The key comes from **Agents & API** in the SpecStream workspace. Node 20.19 or newer, or 22.12 or newer.

## What you can set

| Variable | What it does |
| --- | --- |
| `SPECSTREAM_API_KEY` | Your SpecStream key. Required. |
| `START_URL` | The page to open. Default `https://example.com`. |
| `STAGEHAND_MODEL` | Optional. A model name such as `openai/gpt-4.1-mini`, with that provider's key in its usual variable (`OPENAI_API_KEY`). Adds one `extract()` step that asks the model what the page is about. The model runs on your key, not on SpecStream. |

## The three lines that matter

```js
process.env.BROWSERBASE_BASE_URL = "https://api.specstream.ai/browserbase";

const stagehand = new Stagehand({
  env: "BROWSERBASE",
  apiKey: process.env.SPECSTREAM_API_KEY,
  projectId: "specstream",
  disableAPI: true,
});
```

`disableAPI: true` keeps Stagehand's hosted API out of the way, so `act`, `extract` and `observe` run in your process against the session's browser.

## What it costs

Stagehand drives the browser over CDP, and a session costs its time: $0.10 an hour, charged by the second. This example asks for a session of at most five minutes, so one run costs less than 1 cent. `stagehand.close()` ends the session and the charge.

## Limits

- Use Stagehand 3 (this example pins 3.7.3). Stagehand 4 loads its own Chrome extension into each session as a second CDP client, and a SpecStream session admits one client and runs no caller extension.
- One CDP client per session.

More on browser sessions: [specstream.ai/headless-browser-for-ai-agents](https://specstream.ai/headless-browser-for-ai-agents).
