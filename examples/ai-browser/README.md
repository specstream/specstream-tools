# An AI browser on a SpecStream browser session

One Python file in which Claude drives a real browser. The browser runs at SpecStream, so nothing is installed on your machine but the model's client. You give a task in everyday words; the model opens pages, reads them, clicks and types, and answers.

```sh
pip install -r requirements.txt
export SPECSTREAM_API_KEY="ss_live_..."
export ANTHROPIC_API_KEY="sk-ant-..."
export ANTHROPIC_MODEL="..."   # the id of a Claude model, from Anthropic's model list
python agent.py "Open https://news.ycombinator.com and name the top three stories."
```

```json
{
  "session": "brs_...",
  "answer": "The top three stories are ...",
  "stopped": null,
  "steps": 2,
  "charged_usd": 0.0023,
  "model": "..."
}
```

Each step is printed while it runs, with an address where you can watch the browser live. The SpecStream key comes from **Agents & API** in the SpecStream workspace. Python 3.10 or newer.

## How it works

1. `POST /v1/browser/sessions` opens a browser and answers its `id`.
2. The model gets the browser's steps as tools: `browser_navigate`, `browser_read`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_press_key` and `browser_navigate_back`.
3. Each tool call goes to `POST /v1/browser/sessions/{id}/actions` as `{"tool": ..., "arguments": ...}`, and the step's result goes back to the model.
4. When the model answers in text, `POST /v1/browser/sessions/{id}/release` ends the browser and the charge.

The step names and arguments are Playwright MCP's own, so a model that knows Playwright MCP needs no new instructions. `browser_read` is SpecStream's addition: the open page as Markdown or text.

## What you can set

| Variable | What it does |
| --- | --- |
| `SPECSTREAM_API_KEY` | Your SpecStream key. Required. |
| `ANTHROPIC_API_KEY` | The key the model runs on. The model is charged to you by Anthropic, not by SpecStream. |
| `ANTHROPIC_MODEL` | The id of the Claude model that drives the browser, from [Anthropic's model list](https://docs.claude.com/en/docs/about-claude/models/overview). Required. |
| `MAX_STEPS` | The most browser steps one run takes. Default 20. |
| `ALLOWED_DOMAINS` | Hosts the browser may open, separated by commas, such as `example.com,*.example.org`. Default: any public site. |

## What it costs

A session costs its time, $0.10 an hour, charged by the second, and each step costs 0.1 cent ($1 per 1,000 steps). This example asks for a session of at most five minutes and takes at most 20 steps, so one run costs at most 3 cents at SpecStream. The script ends the session even when the model or a step fails. The model's tokens are charged by Anthropic.

## Limits

- A step that SpecStream does not run (a site that opted out, a private address, a host outside `ALLOWED_DOMAINS`) answers `blocked` with the reason, and the model reads it.
- A step result longer than 30,000 characters is cut, and the model is told that it was cut.
- A page's text can try to give the model orders. Set `ALLOWED_DOMAINS` when the task is about known sites.

More on browser sessions: [specstream.ai/headless-browser-for-ai-agents](https://specstream.ai/headless-browser-for-ai-agents).
