# @specstream/openclaw-browser-plugin

A real Chromium browser in the cloud for your OpenClaw agent, from [SpecStream](https://specstream.ai/?utm_source=clawhub). The agent opens pages, clicks, types, reads and takes screenshots. There is no browser, no CLI and no Python to install on your machine.

The browser runs on SpecStream [browser sessions](https://specstream.ai/headless-browser-for-ai-agents?utm_source=clawhub): $0.10 an hour, charged by the second, and $1 per 1,000 steps.

This plugin gives OpenClaw four tools:

| Tool | What it does |
| --- | --- |
| `specstream_browser_open` | Opens a browser session, with a first page when you pass `url`. Returns `session_id` and `live_url`, a page where you watch the screen. |
| `specstream_browser_step` | Does one step: a Playwright MCP tool call such as `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type` or `browser_take_screenshot`. A screenshot comes back as an image. |
| `specstream_browser_read` | Reads the main text of the open page, as markdown or text. |
| `specstream_browser_close` | Ends the session, so that its time stops being charged. |

## Install

From ClawHub:

```sh
openclaw plugins install clawhub:@specstream/openclaw-browser-plugin
```

Or from npm:

```sh
openclaw plugins install @specstream/openclaw-browser-plugin
```

Needs OpenClaw 2026.10.3 or newer.

## Set it up

Create an API key under **Agents & API** in your [SpecStream workspace](https://specstream.ai/workspace?utm_source=clawhub). New accounts start with $10 of credit, no card.

The plugin reads the key from `SPECSTREAM_API_KEY`. To keep it in your OpenClaw config instead, store a SecretRef that points at the variable:

```sh
openclaw config set plugins.entries.specstream-browser.config.apiKey \
  '{"source":"env","provider":"default","id":"SPECSTREAM_API_KEY"}' --strict-json
```

Then enable the plugin and allow its tools:

```sh
openclaw plugins enable specstream-browser
openclaw config set tools.allow \
  '["specstream_browser_open","specstream_browser_step","specstream_browser_read","specstream_browser_close"]' --strict-json
```

## Settings

All settings are optional and live under `plugins.entries.specstream-browser.config`.

| Setting | Default | What it does |
| --- | --- | --- |
| `apiKey` | `SPECSTREAM_API_KEY` | The SpecStream API key, or a SecretRef. |
| `timeoutSeconds` | `300` | The most seconds one session runs (60 to 3,600). The model can ask for less and never more. |
| `idleTimeoutSeconds` | `300` | A session ends after this many seconds without a step (10 to 600). |
| `allowedDomains` | every public host | Hosts the browser may open, such as `example.com` or `*.example.com`. The model can narrow the list and never add a host. |
| `blockMedia` | `false` | `true` skips images, video, audio and fonts, so pages load faster. |

## What a session costs

Time costs $0.10 an hour, by the second, and each step costs $0.001. A session of five minutes with 30 steps costs less than 4 cents. A session ends at `timeoutSeconds` at the latest, so the default session costs at most 1 cent of time. A browser that never started is not charged.

## Use it

Ask the agent in plain words:

> Open https://news.ycombinator.com in the SpecStream browser, go to the second page and list the titles.

The agent opens a session, takes a snapshot of the page to find the elements, clicks, reads the page and closes the session.

## The same browser in OpenClaw's own browser tool

OpenClaw's built-in `browser` tool can attach to a SpecStream browser over the Chrome DevTools Protocol, with no plugin. Add a profile whose `cdpUrl` carries your key:

```json5
{
  browser: {
    profiles: {
      specstream: { cdpUrl: "wss://api.specstream.ai/browserless?token=YOUR_SPECSTREAM_API_KEY" },
    },
  },
}
```

```sh
openclaw browser --browser-profile specstream open https://example.com
```

The connect opens the session and the disconnect ends it.

## Privacy

The plugin sends SpecStream what the agent asks the browser to do: the addresses, the clicks and the text it types. It sends nothing else from your machine. The browser refuses private network addresses and sites that opted out.

## Links

- Browser sessions: https://specstream.ai/headless-browser-for-ai-agents?utm_source=clawhub
- API reference for agents: https://specstream.ai/agents.md?utm_source=clawhub
- Source: https://github.com/specstream/specstream-tools/tree/main/integrations/openclaw-browser

MIT license.
