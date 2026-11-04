# @specstream/openclaw-plugin

[SpecStream](https://specstream.ai) is the live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. This plugin gives OpenClaw two tools for it and, if you want the full conversation with SpecStream, four skills.

- Source URL and read time on every value.
- You pay for each row delivered, and a run that finds nothing costs nothing.

## Install

From ClawHub:

```sh
openclaw plugins install clawhub:@specstream/openclaw-plugin
```

Or from npm:

```sh
openclaw plugins install @specstream/openclaw-plugin
```

Needs OpenClaw 2026.10.3 or newer.

## Set it up

Create an API key under **Agents & API** in your [SpecStream workspace](https://specstream.ai/workspace). New accounts start with $10 of work free for 30 days, no card.

The plugin reads the key from `SPECSTREAM_API_KEY`. To keep it in your OpenClaw config instead, store a SecretRef that points at the variable:

```sh
openclaw config set plugins.entries.specstream.config.apiKey \
  '{"source":"env","provider":"default","id":"SPECSTREAM_API_KEY"}' --strict-json
```

Then set the most one list may cost. This is the number that lets you hand the agent a tool that spends money:

```sh
openclaw config set plugins.entries.specstream.config.maxPriceUsd 5
```

| Option | Default | What it does |
| --- | --- | --- |
| `apiKey` | `SPECSTREAM_API_KEY` | Your SpecStream API key, or a SecretRef |
| `maxPriceUsd` | `5` | The price ceiling for one list, in US dollars |
| `waitSeconds` | `300` | How long a find waits for a running list before it returns the rows so far |

Give the key only what the task needs: its scope, projects, an expiry and a spending limit.

## The tools

### `specstream_find_list`

| Input | |
| --- | --- |
| `request` | The list in plain words: what to find, where, what every row must meet, and the facts to bring back |
| `max_results` | How many rows, 1 to 1000. Default 25 |
| `max_price_usd` | Optional. A lower ceiling for this call |

The tool reads the request, gets the price, and starts the run only if the quoted maximum is within your ceiling. The agent can ask for a lower ceiling on a call and can never raise yours. If the price is above the ceiling, nothing runs and the agent is told so. Results cost 5 cents, 15 cents or $1 each depending on the list, plus 5 cents for a person's email and 15 cents for a phone number, and nothing when nothing matches.

It waits for the list, then returns JSON: `state`, `list_id`, `list_link` and `rows`. Each row has its columns plus `source_url` and `checked_at`. A retry of the same request with the same limits within the hour reaches the run it already started, so a flaky turn does not buy the list twice.

### `specstream_get_list_rows`

Reads every row of a list you already own, by `list_id`. Free. Use it when a big list was still running at the end of the wait.

## Skills and the SpecStream server (optional)

The plugin ships four skills: `specstream-compile` (show how SpecStream read the request), `specstream-review-work` (get the price), `specstream-approve-work` (approve it) and `specstream-continue-work` (read the rows, send them to Sheets, Notion, HubSpot and more, keep them up to date). They use the hosted SpecStream server and stay hidden until you add it:

```sh
openclaw mcp set specstream '{"url":"https://api.specstream.ai/mcp","transport":"streamable-http","auth":"oauth"}'
openclaw mcp login specstream
```

The tools above work without it.

## Example

> Find open tenders on SAM.gov for translation services, with the buyer and the deadline. Keep it under $3.

The agent calls `specstream_find_list` with `max_price_usd: 3`, and you get a table of tenders, each row with its source URL and read time, plus a link to open the list in your workspace.

## Develop

```sh
npm ci
npm run check            # tsc, source and tests
npm test                 # vitest, fetch mocked
npm run plugin:validate  # OpenClaw's own manifest validator
```

## License

MIT
