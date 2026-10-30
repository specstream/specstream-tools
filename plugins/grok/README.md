# SpecStream plugin for Grok Build

Ask for any list in plain words and get the whole list from the live web: lead lists, company lists, grants, jobs, places. Every row comes with the page it was read from. You see the price before anything runs and pay for each row delivered, from 10 cents each. A search that finds nothing costs nothing.

[SpecStream](https://specstream.ai) is the live web data engine for teams and agents. This plugin connects Grok Build to SpecStream's hosted MCP server and adds four skills for the flow: read the request back, get the price, approve it, read and send the rows.

Published by SpecStream, the vendor. Source: [specstream/specstream-tools](https://github.com/specstream/specstream-tools), folder `plugins/grok`.

## Installation

1. In Grok Build, open the marketplace:

   ```text
   /marketplace
   ```

2. Find **specstream** in the list and press `i` to install it.
3. Open the MCP servers tab with `/mcp`, select **specstream**, and press `i` to sign in. Your browser opens SpecStream. New accounts get $10 of work free for 30 days.
4. Once specstream shows **ready**, run the `get-started` command for a guided first list, or just ask for one.

## Try it

```text
Find every independent bookstore in Oregon with a website and a phone number.
```

```text
List open grants for food banks in Texas, with the deadline and the award size.
```

```text
Every company that filed to raise $5M or more this week, with the filing.
```

Grok reads the request back first. Nothing runs until you approve a price.

## Tools

The hosted server has many tools. These are the ones you will see most:

| Tool | What it does |
|---|---|
| `compile`, `edit_spec` | Read a plain-English request back and change it without starting over |
| `quote_capacity_work` | Get the exact maximum price. Nothing runs |
| `authorize_capacity_work` | Approve that price and start the list. Spends money, so the agent asks you first |
| `get_find`, `list_find_rows` | Watch progress and read the rows with the source behind each fact |
| `export_find`, `send_to_destination` | CSV, Excel, JSON or HTML download, or send to Google Sheets, Excel, Notion, Airtable, HubSpot or Salesforce |
| `create_capacity_schedule` | Keep a list current and get told when it changes |

## Skills

| Skill | What it does |
|---|---|
| `specstream-compile` | Reads your request back before anything runs |
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

Reading a request and getting a price are free. Results cost 10 cents, 30 cents or $1 each depending on the kind of work, plus 10 cents for a person's email and 25 cents for a phone. Possible matches that were not confirmed are never billed. [Pricing](https://specstream.ai/pricing)

## Resources

- [Documentation](https://specstream.ai/docs/mcp)
- [Homepage](https://specstream.ai)
- Support: support@specstream.ai

## License

MIT
