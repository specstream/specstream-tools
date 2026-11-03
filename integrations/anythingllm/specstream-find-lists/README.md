# SpecStream: live web data

Ask `@agent` in plain words and get live web data back, every match with its values and the page each one came from. Every roofer in Columbus rated 4.5 or better with their phone, every food bank in Texas with its revenue, every company that filed to raise $5M or more this week. SpecStream reads the live web where those things are kept, at the moment you ask.

You approve the price before anything runs, and you pay for each result delivered: 5¢, 15¢ or $1 each, depending on how many facts you ask for. A search that finds nothing is free. New accounts start with $10 of work, no card.

## Set up

1. In SpecStream ([specstream.ai](https://specstream.ai)), open **Agents & API** and create an API key (it starts with `ss_live_`).
2. In AnythingLLM, open **Agent Skills**, find **SpecStream: live web data**, paste the key, and set the spending cap.
3. In a workspace chat, ask with `@agent`:

> @agent Find every roofing company in Columbus, Ohio rated 4.5 or better with fewer than 20 Google reviews, with their phone number. Give me 50.

The agent reads your request back, shows the most it can cost and waits for you to approve. Then it returns every match with the pages it came from and a link to the full results in SpecStream, where you can export them or keep them current. Ask for a run you started by its ID (`fnd_...`) to read its rows again for free.

## Settings

| Setting | Default | What it does |
|---|---|---|
| `SPECSTREAM_API_KEY` | empty | Your SpecStream API key |
| `MAX_PRICE_USD` | 5 | The most one request may cost. A price above it is refused before anything runs |
| `APPROVAL` | `ask` | `ask` shows an approval prompt for every price. `within_cap` starts requests at or under the cap without asking |
| `WAIT_SECONDS` | 90 | How long to wait for results after a request starts. It keeps running after that |
| `MAX_ROWS` | 25 | Most results handed to the model per read |

AnythingLLM approves automatically in runs with nobody at the screen, such as scheduled jobs. The cap still applies there, so keep it at a number you're happy to spend.

## Prefer MCP?

Add SpecStream's server to `anythingllm_mcp_servers.json` in the `plugins` folder of your AnythingLLM storage directory, then reload the Agent Skills page:

```json
{
  "mcpServers": {
    "specstream": {
      "type": "streamable",
      "url": "https://api.specstream.ai/mcp",
      "headers": { "Authorization": "Bearer ss_live_your_key" }
    }
  }
}
```

Docs: [specstream.ai/docs/mcp](https://specstream.ai/docs/mcp) · Support: support@specstream.ai · MIT license.
