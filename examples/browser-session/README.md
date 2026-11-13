# A browser session over MCP

One Python file opens a real Chromium browser on SpecStream's server, goes to a page, reads it and closes the browser. It uses the standard library only, so there is nothing to install. Python 3.10 or newer.

```sh
export SPECSTREAM_API_KEY="ss_live_..."
python run.py https://example.com
```

The script asks before it opens the browser, because a session is charged. Answer `y`, and it prints:

```json
{
  "session": "brs_...",
  "title": "Example Domain",
  "snapshot_lines": 6,
  "text": "# Example Domain\n\n...",
  "seconds": 4,
  "steps": 3,
  "charged_usd": 0.003112
}
```

The key comes from **Agents & API** in the SpecStream workspace. New accounts start with $10 of credit, no card.

## The five calls

The script talks to the SpecStream MCP server at `https://api.specstream.ai/mcp`. Any MCP client can make the same calls.

| Tool | What it does here |
| --- | --- |
| `open_browser` | Opens the browser and returns the session's `id`. `allowed_domains` holds the page's host, so the browser opens nothing else. |
| `browser_navigate` | Goes to the page. |
| `browser_snapshot` | Returns the page as a tree of elements, each with a reference. A step that acts on an element (`browser_click`, `browser_type`) takes that reference as `target`. |
| `browser_read` | Returns the page's text as Markdown. |
| `close_browser` | Ends the session and settles its charge. The script calls it even when a step fails. |

The `browser_` tools have the names and arguments of Playwright MCP, plus the `session_id` from `open_browser`. To click, type or fill a form, add the step between the snapshot and the read.

## What it costs

A session costs $0.10 an hour, charged by the second, plus $1 per 1,000 steps (0.1¢ a step). This example runs 3 steps and a few seconds, so one run costs less than 1 cent. An open session is charged until it times out, so always call `close_browser`.

## What you can set

| Setting | What it does |
| --- | --- |
| `SPECSTREAM_API_KEY` | Your SpecStream key. Required. |
| the first argument | The page to open. Default `https://example.com`. |
| `--timeout` | The most seconds the session runs. Default 120. |
| `--yes` | Opens the browser without the question. Use it with a key whose spending limit you set on purpose. |

## Limits

- A page whose site opted out, whose robots.txt disallows SpecStream, or that is outside `allowed_domains` answers `blocked`.
- For the text of a page that needs no clicks, the Extract API is faster and cheaper.

More on browser sessions: [specstream.ai/headless-browser-for-ai-agents](https://specstream.ai/headless-browser-for-ai-agents).
