# Browser agent on a SpecStream browser session

A browser agent in one Python file. You give it a task in plain words. Claude opens pages, clicks, types and reads in a real Chromium that runs at SpecStream, and gives you the answer. No browser is installed on your machine.

```sh
pip install -r requirements.txt
export SPECSTREAM_API_KEY="ss_live_..."
export ANTHROPIC_API_KEY="sk-ant-..."
python agent.py "Open news.ycombinator.com and give me the title of the first story."
```

```json
{
  "session": "brs_...",
  "answer": "The first story is ...",
  "stopped": null,
  "steps": 2,
  "seconds": 9,
  "charged_usd": 0.00225
}
```

The SpecStream key comes from **Agents & API** in the [SpecStream workspace](https://specstream.ai/workspace/agents?tab=keys). Python 3.10 or newer. While the agent works, it prints each step and an address where you can watch the browser's screen.

## How it works

`agent.py` makes three kinds of call to SpecStream:

1. `POST /v1/browser/sessions` opens a browser session.
2. `POST /v1/browser/sessions/{id}/actions` takes one step. The body names a tool and its arguments, for example `{"tool": "browser_navigate", "arguments": {"url": "https://example.com"}}`. The tools are Playwright MCP's (`browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type` and the others), plus `browser_read` for the text of the page as Markdown.
3. `POST /v1/browser/sessions/{id}/release` ends the session.

Between these calls is a short loop. Claude gets the task and the tools. Each tool call that Claude makes becomes one step on the session, and the step's result goes back to Claude. The loop ends when Claude answers without a tool call. The session is released in every case, also after an error or Ctrl-C.

## What you can set

| Variable | What it does |
| --- | --- |
| `SPECSTREAM_API_KEY` | Your SpecStream key. Required. |
| `ANTHROPIC_API_KEY` | The model's key. The model runs on your key, not on SpecStream. |
| `MODEL` | The Claude model. Default `claude-opus-5-5`. |
| `MAX_STEPS` | The most browser steps in one run. Default 20. |
| `SESSION_TIMEOUT_S` | The session ends by itself after this many seconds. Default 300. |
| `ALLOWED_DOMAINS` | Hosts the browser may open, separated by commas, for example `example.com,*.example.org`. Without it, the browser may open every public page. |

## What it costs

A session costs its time and its steps: $0.10 an hour, charged by the second, and $1 per 1,000 steps (0.1 cent a step). A run with the default limits (20 steps, five minutes) costs at most 3 cents at SpecStream. The `charged_usd` field in the output shows what the run did cost. The model's tokens are charged by Anthropic on your key.

## Limits

- The agent does what the task says with the pages it opens. Set `ALLOWED_DOMAINS` when the task must stay on known sites.
- A page that opted out of automated reading, or a private address, is refused, and Claude gets the reason as the step's result.
- When `MAX_STEPS` is reached, Claude is told to answer with what it has.
- The exit code is 0 with an answer, 3 when the run stopped without a full answer, 1 when SpecStream or the model's API refused a call, 2 when a setting is absent.

More on browser sessions: [specstream.ai/headless-browser-for-ai-agents](https://specstream.ai/headless-browser-for-ai-agents).
