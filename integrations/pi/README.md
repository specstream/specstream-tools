# SpecStream for Pi

The live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change.

- Source URL and read time on every value.
- You see the price before anything runs and pay for each row delivered, from 5 cents each.

This is a [Pi package](https://pi.dev/packages). It adds the hosted [SpecStream](https://specstream.ai) MCP server and four skills, so Pi shows how SpecStream read your request, gets the price, asks you to approve it, and returns the rows.

## Install

```bash
pi install npm:@specstream/pi-package
pi mcp login specstream
```

The second command opens SpecStream in your browser. Sign in and approve access; Pi stores the token and refreshes it. New accounts get $10 of work free for 30 days. Inside a session, `/mcp` shows the connection and lets you sign in or out.

Try it for one run without installing: `pi -e npm:@specstream/pi-package`.

## What you get

- **The SpecStream MCP server** at `https://api.specstream.ai/mcp`, registered by a small extension (`extensions/specstream.ts`). It uses Pi's built-in MCP support, OAuth 2.1 with dynamic client registration, and no stored credentials. Five tools stay in view (`compile`, `quote_capacity_work`, `authorize_capacity_work`, `get_find`, `list_find_rows`); the rest load on demand through `tool_search`. In Pi they are named `mcp__specstream__<tool>`.
- **Four skills**, loaded when the task calls for them or by name:

| Skill | What it does |
|---|---|
| `/skill:specstream-compile` | Shows how SpecStream read your request before anything runs |
| `/skill:specstream-review-work` | Gets the exact price and its expiry |
| `/skill:specstream-approve-work` | Starts the list after you approve that price |
| `/skill:specstream-continue-work` | Reads every row, sends them to Sheets, Excel, Notion, Airtable, HubSpot or Salesforce, brings back more, refreshes, monitors |

## Try it

```text
Find open grants for climate research in the EU, with the deadline and the award size.
```

Reading a request and getting its price are free. Nothing that costs money runs until you approve an exact maximum.

## Use an API key instead (servers, CI)

Create a key under **Agents & API** in the [workspace](https://specstream.ai/workspace), give it only what the task needs (read, prepare or execute), its projects, an expiry and a spending limit, then export it before starting Pi:

```bash
export SPECSTREAM_API_KEY=your-key-here
```

When the variable is set, the extension sends it as `Authorization: Bearer ${SPECSTREAM_API_KEY}`. Pi fills the value in from your environment, so the key is never written to a file by this package.

## Only the MCP server, no package

```bash
pi mcp add specstream --url https://api.specstream.ai/mcp
pi mcp login specstream
```

That adds the server to `~/.pi/agent/mcp.json` and skips the skills. A server of the same name in `mcp.json` takes precedence over the one this package registers.

## What it sends

Your request and your answers to the price go to `api.specstream.ai` over HTTPS, and results come back from the same API. The extension reads one environment variable, `SPECSTREAM_API_KEY`, and only to decide whether to add the header. It reads no files, runs no commands and installs no dependencies.

## Price

A list runs only after you approve its maximum price. Results cost 5 cents, 15 cents or $1 each depending on the kind of work, plus 5 cents for a person's email and 15 cents for a phone. Nothing is charged when nothing matches, and possible matches that were not confirmed are never billed. [Pricing](https://specstream.ai/pricing)

## Links

[Documentation](https://specstream.ai/docs/mcp) · [Privacy](https://specstream.ai/privacy) · [Terms](https://specstream.ai/terms) · support@specstream.ai

## License

MIT
