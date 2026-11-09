# SpecStream plugin for Grok Build

The live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change.

- Source URL and read time on every value.
- You see the price before anything runs and pay for each row delivered, from 5 cents each. A run that finds nothing costs nothing.

This plugin connects Grok Build to [SpecStream](https://specstream.ai)'s hosted MCP server and adds four skills for the flow: show how the request was read, get the price, approve it, read and send the rows.

Published by SpecStream, the vendor. Source: [specstream/specstream-tools](https://github.com/specstream/specstream-tools), folder `plugins/grok`.

## Installation

1. In Grok Build, open the marketplace:

   ```text
   /marketplace
   ```

2. Find **specstream** in the list and press `i` to install it.
3. Open the MCP servers tab with `/mcp`, select **specstream**, and press `i` to sign in. Your browser opens SpecStream. New accounts get $10 of credit.
4. Once specstream shows **ready**, run the `get-started` command for a guided first request, or ask in plain words.

## Try it

```text
Find open grants for climate research in the EU, with the deadline and the award size.
```

Grok shows how SpecStream read the request first. Nothing runs until you approve a price.

## Tools

The hosted server has many tools. These are the ones you will see most:

| Tool | What it does |
|---|---|
| `compile`, `edit_spec` | Read a plain-English request back and change it without starting over |
| `quote_capacity_work` | Get the exact maximum price. Nothing runs |
| `authorize_capacity_work` | Approve that price and start the list. Spends money, so the agent asks you first |
| `get_find`, `list_find_rows` | Watch progress and read the rows with the source behind each fact |
| `export_find`, `send_to_destination` | CSV, Excel, JSON or HTML download, or send to Google Sheets, Excel, Notion, Airtable, HubSpot or Salesforce |
| `create_capacity_schedule` | Keep a request up to date and get told when it changes |

## Skills

| Skill | What it does |
|---|---|
| `specstream-compile` | Shows how SpecStream read your request before anything runs |
| `specstream-review-work` | Gets the exact price and its expiry |
| `specstream-approve-work` | Starts the list after you approve that price |
| `specstream-continue-work` | Reads every row, sends them where you work, brings back more, refreshes or monitors |

## Authentication and security

- The plugin connects only to `https://api.specstream.ai/mcp`, over HTTPS. Your requests and your answers to the price go there, and results come back from the same API. Nothing is read from your machine and nothing runs locally.
- Sign-in is OAuth 2.1 with dynamic client registration, handled by Grok Build's MCP flow. The plugin holds no key, no token and no secret, and its `.mcp.json` sets no headers.
- Scope is one MCP server and no hooks. There are no scripts, no install steps and no downloads.
- Spending needs your approval of an exact maximum every time. The plugin's `rules/security.md` tells the agent to treat rows as untrusted web data and never to approve a price on its own.
- Privacy policy: <https://specstream.ai/privacy>. Terms: <https://specstream.ai/terms>.

## Price

Reading a request and getting a price are free. Results cost 5 cents, 15 cents or $1 each depending on the kind of work, plus 5 cents for a person's email and 15 cents for a phone. Possible matches that were not confirmed are never billed. [Pricing](https://specstream.ai/pricing)

## Resources

- [Documentation](https://specstream.ai/docs/mcp)
- [Homepage](https://specstream.ai)
- Support: support@specstream.ai

## License

MIT
