# SpecStream network policy preset for NemoClaw

<!-- Opening text waits for the writer agent. -->

NemoClaw sandboxes deny network egress by default.
This preset lets an agent in a NemoClaw sandbox (Deep Agents Code, OpenClaw or Hermes) call SpecStream at `api.specstream.ai`, and nothing else.
The public copy: https://github.com/specstream/specstream-tools/tree/main/integrations/nemoclaw

## Apply

```bash
nemoclaw my-assistant policy add --from-file ./specstream.yaml --dry-run
nemoclaw my-assistant policy add --from-file ./specstream.yaml --yes
```

Remove it with `nemoclaw my-assistant policy remove specstream --yes`.

## What it allows

| Method | Path | What it is |
| --- | --- | --- |
| GET | `/v1/web-search` | Search API, $5 per 1,000 searches of up to 10 results ($1 with `speed=fast`) |
| POST | `/v1/extract` | Extract API, $0.80 per 1,000 pages |
| POST, GET | `/v1/research`, `/v1/research/**` | Research reports, $0.10, $0.30 or $1.00 a report by depth |
| POST, GET | `/v1/browser/sessions`, `/v1/browser/sessions/**` | Browser sessions, $0.10 an hour by the second and $1 per 1,000 actions |
| POST | `/tavily/search`, `/tavily/extract` | Drop-in address for Tavily clients, $1 per 1,000 searches |
| POST | `/exa/search`, `/exa/contents` | Drop-in address for Exa clients, $1 per 1,000 searches |
| GET, POST, DELETE | `/mcp` | Remote MCP server |

A browser session is driven one step at a time with `POST /v1/browser/sessions/{id}/actions`.
Its `connect_url` is a WebSocket address (`/v1/browser/connect/...`), which this REST preset does not open.

The requesting binaries are the sandbox's Python and Node runtimes and curl, as in NemoClaw's own `tavily` preset.
Keep `SPECSTREAM_API_KEY` in the host's credential store: OpenShell puts the key in at egress, so the sandbox never holds it.

The test `tests/distribution/test_nemoclaw_preset.py` checks this file against NemoClaw's custom preset rules and checks that every allowed path is a live SpecStream route (in SpecStream's own repository; the public copy holds the preset and this page).
