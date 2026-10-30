# SpecStream for Hermes Agent

SpecStream hands your agent the finished list. Describe it in plain words ("food banks in Texas, with their annual revenue") and get every matching row from the live web, each with the page it was read from. Hermes sees the price before anything runs, you approve a maximum, and you pay for each result delivered. A search that finds nothing costs nothing.

This is a portable [Agent Plugins v1](https://agent-plugins.org) package for [Hermes Agent](https://hermes-agent.nousresearch.com). It ships no code and installs no dependencies:

- `mcp.json`: the hosted SpecStream MCP server, `https://api.specstream.ai/mcp` (streamable HTTP, OAuth 2.1 with dynamic client registration).
- `skills/`: four skills. `compile` reads the request back, `review-work` gets the price, `approve-work` starts the list once you approve that price, and `continue-work` brings back more rows, refreshes a list or adds details.
- `plugin.json`: the manifest. It marks the `specstream` server as `untrusted`, so Hermes asks you before any call that is not read-only, including the call that approves spending.

## Set up SpecStream in Hermes

### Option 1: the plugin (MCP server and skills)

```bash
hermes plugins install specstream/specstream-tools --no-enable
hermes plugins enable specstream
hermes gateway restart   # only if you run the messaging gateway
```

Once the plugin is in the Hermes plugin catalog you can use `hermes plugins install specstream` instead.

On the first SpecStream tool call Hermes prints an authorization link. Open it, sign in to SpecStream, and approve access. Hermes stores the token and refreshes it. To sign in again later, run `hermes mcp login specstream`. New accounts get $10 of work free.

### Option 2: only the MCP server, in `config.yaml`

```yaml
mcp_servers:
  specstream:
    url: "https://api.specstream.ai/mcp"
    auth: oauth
```

A server in `config.yaml` replaces the plugin's server of the same name and drops the `untrusted` setting. Add `trust: untrusted` to keep Hermes asking before spending.

### Option 3: API key instead of browser sign-in (servers, cron, CI)

Create a key under **Agents & API** in the [workspace](https://specstream.ai/workspace). Give it only what the task needs (read, prepare or execute), the projects it may use, an expiry and a spending limit. Put it in `~/.hermes/.env`:

```bash
SPECSTREAM_API_KEY=your-key-here
```

Then reference it from `config.yaml`. Hermes substitutes `${VAR}` in `headers` when it connects:

```yaml
mcp_servers:
  specstream:
    url: "https://api.specstream.ai/mcp"
    headers:
      Authorization: "Bearer ${SPECSTREAM_API_KEY}"
    trust: untrusted
```

Never put the key itself in `config.yaml` or in this plugin's `mcp.json`.

## Try it (free)

Ask Hermes: "Use SpecStream to read this request back: independent bookstores in Oregon with a website and a phone number." Reading a request and getting its price cost nothing.

## What it sends

Your request and your answers to the price go to `api.specstream.ai` over HTTPS, and results come back from the same API. Nothing is read from your machine, nothing runs locally, and the plugin stores no credentials. Hermes keeps the OAuth token.

## Price

A list runs only after you approve its maximum price, and you pay for each row delivered, from 10 cents each. Possible candidates that were not confirmed are never billed. [Pricing](https://specstream.ai/pricing) · [API docs](https://specstream.ai/docs/api) · support@specstream.ai

## Unattended runs

Under cron and the messaging gateway nobody can answer an approval prompt, so a call that would spend is refused rather than run. Schedule a refresh from the workspace, or use an API key with a spending limit for work that must run unattended.

## License

MIT
