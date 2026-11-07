# opencode-specstream

SpecStream plugin for [OpenCode](https://opencode.ai). SpecStream is the live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change.

- Source URL and read time on every value.
- You see the price first and approve a ceiling. You pay for each row delivered, and a run that finds nothing costs nothing.

The plugin does two things when OpenCode starts:

- adds the hosted SpecStream MCP server, `https://api.specstream.ai/mcp`, to your config as `specstream`
- adds six agent skills: `search-web` (Search API), `extract-pages` (Extract API), `compile` (show how SpecStream read the request), `review-work` (get the price), `approve-work` (approve it) and `continue-work` (read the rows, send them on, keep them up to date)

## Install

OpenCode 1.18.29 or newer, and OpenCode 2:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["opencode-specstream"]
}
```

In OpenCode 2 the key is `plugins`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugins": ["opencode-specstream"]
}
```

OpenCode installs the package on the next launch.

## Sign in

The server uses OAuth, so you do not paste a key. Run:

```sh
opencode mcp auth specstream
```

Your browser opens, you sign in to SpecStream, and OpenCode keeps the token. New accounts start with $10 of credit for 30 days, no card.

To use an API key instead, for example on a machine with no browser, create one under **Agents & API** in the [workspace](https://specstream.ai/workspace) and set it where OpenCode starts:

```sh
export SPECSTREAM_API_KEY="ss_live_..."
```

With the variable set, the plugin sends it as a bearer header and turns the browser sign-in off. Give the key only what the task needs: its scope, projects, an expiry and a spending limit.

## Use it

Ask in plain words. The agent shows how SpecStream read the request and the quoted ceiling, and starts only after you say yes. Rows come back with their source pages, ready to export as CSV, Excel or JSON or to send to Google Sheets, Notion, Airtable, HubSpot or Salesforce.

## Options

Both parts are on by default. Turn either off with plugin options:

```json
{
  "plugin": [["opencode-specstream", { "skills": false }]]
}
```

| Option | Default | Effect |
| --- | --- | --- |
| `mcp` | `true` | `false` leaves the MCP server out |
| `skills` | `true` | `false` leaves the four skills out |

A `specstream` entry you already wrote under `mcp` is never replaced.

## Develop

```sh
npm ci
npm run check   # tsc --noEmit
npm test
```

The skills in `skills/` are copies of the repository's [`skills/`](../../skills); a test fails when they drift. The package ships its TypeScript source, as OpenCode runs plugins directly.

Docs: https://specstream.ai/docs/mcp. Licensed MIT.
