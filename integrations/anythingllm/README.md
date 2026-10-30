# SpecStream for AnythingLLM

Ask `@agent` for a list and get the whole list. Every roofer in Columbus rated 4.5 or better, every food bank in Texas with its revenue, every company that filed to raise $5M or more this week. SpecStream reads the live web where those things are kept and hands back every matching row with the page it came from.

You approve the price before anything runs, and you pay for each result delivered: 10¢, 30¢ or $1 a row, and 5¢ for a company left out for a detail you marked as needed. New accounts start with $10 of work, no card.

Two ways to connect it. Pick one.

| | Agent skill (this folder) | MCP server |
|---|---|---|
| Setup | Import the skill, paste a key | Add one block to `anythingllm_mcp_servers.json` |
| Price check | Approval prompt in the chat, plus a spending cap you set | Your model asks you before it approves |
| What the agent sees | One tool | The tools you leave on |
| Works on | Desktop and Docker (self-hosted) | Desktop and Docker (self-hosted) |

## Option 1: the agent skill

The skill is in [`specstream-find-lists/`](specstream-find-lists): `plugin.json` and `handler.js`, Node 18 or newer, no packages to install.

1. In SpecStream, open **Agents & API** and create an API key (it starts with `ss_live_`). [Sign up](https://specstream.ai) if you don't have an account.
2. Get the skill into AnythingLLM, either way:
   - **From the Community Hub:** open the skill, click **Import to AnythingLLM**, and paste the import string into AnythingLLM. On Docker and self-hosted installs an admin has to allow hub imports first (`COMMUNITY_HUB_BUNDLE_DOWNLOADS_ENABLED`).
   - **By hand:** copy the `specstream-find-lists` folder into `plugins/agent-skills` inside your AnythingLLM storage folder, then reload the page.
3. Open **Agent Skills**, find **SpecStream: find a list**, paste the key, and set the spending cap.
4. In a workspace chat, start with `@agent`:

> @agent Find every roofing company in Columbus, Ohio rated 4.5 or better with fewer than 20 Google reviews, with their phone number. Give me 50.

The agent reads your request back, shows the most it can cost, and waits for you to approve. Then it returns every row with the pages it came from and a link to the full list in SpecStream.

To read a list that's already started, ask for it by ID: `@agent show me the rows of list fnd_1a2b3c4d`. Reading costs nothing.

### Settings

| Setting | Default | What it does |
|---|---|---|
| `SPECSTREAM_API_KEY` | empty | SpecStream API key |
| `MAX_PRICE_USD` | 5 | The most one list may cost. A price above it is refused before anything runs |
| `APPROVAL` | `ask` | `ask` shows an approval prompt for every price. `within_cap` starts lists at or under the cap without asking |
| `WAIT_SECONDS` | 90 | How long to wait for rows after a list starts. The list keeps running after that |
| `MAX_ROWS` | 25 | Most rows handed to the model per read |

### How the price check works

- The skill reads the request, gets the price, and checks it against `MAX_PRICE_USD` before it asks you anything.
- With `APPROVAL` set to `ask`, AnythingLLM pauses the agent and asks you to approve. No approval, nothing runs and nothing is charged.
- AnythingLLM approves automatically in runs with nobody at the screen, such as scheduled jobs. The cap still applies there, so keep it at a number you're happy to lose.
- Each quote starts at most one list. A retry returns the list it already started instead of buying it twice.
- An API key also carries its own spending ceiling, set in SpecStream. The skill can't raise it.

## Option 2: MCP, no code

AnythingLLM reads MCP servers from `anythingllm_mcp_servers.json` in the `plugins` folder of its storage directory (on Docker, the folder you mount as `STORAGE_LOCATION`). Add SpecStream's server, `https://api.specstream.ai/mcp`, as a Streamable HTTP server with your key:

```json
{
  "mcpServers": {
    "specstream": {
      "type": "streamable",
      "url": "https://api.specstream.ai/mcp",
      "headers": {
        "Authorization": "Bearer ss_live_..."
      }
    }
  }
}
```

Then open **Agent Skills**, click **Refresh** (or restart the MCP servers from the MCP management page), and check that **specstream** shows as running with its tools. Ask `@agent` for a list as above.

The server tells the model to show you the price and wait for your yes before anything runs. The file holds your key, so keep it out of shared folders and git.

## Pricing

A match costs 10¢, 30¢ or $1 depending on how many facts it carries. No match, no charge. A recheck costs half. The same rates apply on every plan, Free included. See [specstream.ai/pricing](https://specstream.ai/pricing).

## Troubleshooting

- **"SpecStream did not accept this API key."** Paste the key again in the skill's settings. Keys start with `ss_live_`.
- **The agent answers without calling the skill.** Start the message with `@agent`, and check **SpecStream: find a list** is switched on under Agent Skills.
- **"Needs a clearer request."** Add the place, the kind of thing, or what every row must meet.
- **A list is still running.** It keeps going. Ask the agent to read the list again later by its ID.

## Links

- [SpecStream](https://specstream.ai) · [Agents and API docs](https://specstream.ai/docs/mcp) · [Pricing](https://specstream.ai/pricing)
- [Source and issues](https://github.com/specstream/specstream-tools/tree/main/integrations/anythingllm)
- Support: support@specstream.ai

MIT license.
