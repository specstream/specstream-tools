# SpecStream

The live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. In AnythingLLM, you ask `@agent` and the rows come back in the chat.

- Source URL and read time on every value.
- You approve the price before anything runs, and you pay for each row delivered: 5¢, 15¢ or $1 a row, depending on how much it needs. A run that finds nothing costs nothing.
- New accounts start with $10 of credit, no card.

## Set up

1. In SpecStream ([specstream.ai](https://specstream.ai)), open **Agents & API** and create an API key (it starts with `ss_live_`).
2. In AnythingLLM, open **Agent Skills**, find **SpecStream**, paste the key, and set the spending cap.
3. In a workspace chat, ask with `@agent`:

> @agent Find open tenders on SAM.gov for translation services, with the buyer and the deadline. Give me 50.

The agent shows how SpecStream read your request and the most it can cost, and waits for you to approve. Then it returns the rows, with the source URL and read time on every value, and a link to the full results in SpecStream, where you can export them or keep them up to date. Ask for a run you started by its ID (`fnd_...`) to read its rows again for free.

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
