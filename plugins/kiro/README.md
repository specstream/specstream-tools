# SpecStream power for Kiro

Ask for any list in plain words and get every match from the live web: lead lists, company lists, grants, jobs, places. Each row comes with the page it was read from. You see the price before anything runs and pay for each row delivered, from 10 cents each. A search that finds nothing costs nothing.

[SpecStream](https://specstream.ai) is the live web data engine for teams and agents. This power connects Kiro to SpecStream's hosted MCP server and adds four skills for the flow: read the request back, get the price, approve it, read and send the rows. It follows the [Agent Plugins](https://agent-plugins.org) format, so the same folder works in other compatible clients.

## Install

In Kiro, open the Powers panel, choose **Add Custom Power**, then either:

- **Import power from GitHub** and enter `https://github.com/specstream/specstream-tools/tree/main/plugins/kiro`, or
- clone [specstream/specstream-tools](https://github.com/specstream/specstream-tools) and choose **Import power from a folder**, pointing at `plugins/kiro`.

The first time Kiro calls SpecStream it opens your browser to sign in (OAuth 2.1 with dynamic client registration). There is no key to paste. New accounts get $10 of work free for 30 days.

## Try it

Say any of these in a Kiro chat:

```text
Find every independent bookstore in Oregon with a website and a phone number.
```

```text
List open grants for food banks in Texas, with the deadline and the award size.
```

```text
Every company that filed to raise $5M or more this week, with the filing.
```

Kiro reads the request back first. Nothing runs until you approve a price.

## What it adds

- **The SpecStream MCP server** at `https://api.specstream.ai/mcp`, declared in `mcp.json` as a remote streamable HTTP server. Kiro namespaces it on install. It is a generally available server, not a beta or preview.
- **Four skills**:

| Skill | What it does |
|---|---|
| `specstream-compile` | Reads your request back before anything runs |
| `specstream-review-work` | Gets the exact price and its expiry |
| `specstream-approve-work` | Starts the list after you approve that price |
| `specstream-continue-work` | Reads every row, sends them to Google Sheets, Excel, Notion, Airtable, HubSpot or Salesforce, brings back more, refreshes, monitors |

## Use an API key instead (servers, CI)

For unattended use, create a key under **Agents & API** in the [workspace](https://specstream.ai/workspace) with only the access the task needs, an expiry and a spending limit. Add the server to `~/.kiro/settings/mcp.json` with an `Authorization` header that references the key by environment variable, never the key itself:

```json
{
  "mcpServers": {
    "specstream": {
      "url": "https://api.specstream.ai/mcp",
      "headers": { "Authorization": "Bearer ${SPECSTREAM_API_KEY}" }
    }
  }
}
```

Approve the variable under **Mcp Approved Env Vars** in Kiro's settings.

## What it sends

Your request and your answers to the price go to `api.specstream.ai` over HTTPS, and results come back from the same API. The power ships no scripts, runs nothing locally, reads nothing from your machine and stores no credentials.

## Price

Reading a request and getting a price are free. A list runs only after you approve its maximum price. Results cost 10 cents, 30 cents or $1 each depending on the kind of work, plus 10 cents for a person's email and 25 cents for a phone. Possible matches that were not confirmed are never billed. [Pricing](https://specstream.ai/pricing)

## Privacy and support

- Privacy policy: <https://specstream.ai/privacy>
- Terms: <https://specstream.ai/terms>
- Documentation: <https://specstream.ai/docs/mcp>
- Support: support@specstream.ai

## License

MIT
