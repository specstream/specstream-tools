# specstream-claude-browser

A driver for the [browser toolset of the Claude SDK](https://platform.claude.com/docs/en/agents-and-tools/tool-use/browser-use-sdk) that runs on [SpecStream](https://specstream.ai) browser sessions. Claude navigates, reads and acts in a real browser that SpecStream hosts. You run no browser yourself.

```bash
pip install specstream-claude-browser
```

## Quick start

Set `ANTHROPIC_API_KEY`, `SPECSTREAM_API_KEY`, and `CLAUDE_MODEL` to a model the browser toolset supports (the Claude page above lists them). Create a SpecStream key under Agents & API at https://specstream.ai/workspace.

```python
import os

from anthropic import Anthropic
from specstream_claude_browser import SpecStreamBrowser

client = Anthropic()
with SpecStreamBrowser() as browser:
    runner = client.beta.messages.tool_runner(
        model=os.environ["CLAUDE_MODEL"],  # a model the browser toolset supports
        max_tokens=1024,
        tools=[browser],
        messages=[{"role": "user", "content": "Open example.com and tell me its heading."}],
    )
    for message in runner:
        print(message)
```

The session opens at the first call and ends when the `with` block ends. A toolset that Claude never calls opens no session.

## What it costs

A session costs $0.10 an hour, charged by the second, plus $1 per 1,000 steps. One member call is one step, with three exceptions: `key` is one step for each key press, `form_input` on a text field or a select is two steps, and a refused call is none.

## Members

| Member | How it runs |
| --- | --- |
| `navigate` | Opens the URL. `back`, `forward` and `reload` work. The HTTP status is not reported. |
| `screenshot` | A PNG of the viewport. One image pixel is one CSS pixel. |
| `read_page` | The page's accessibility snapshot. Each element carries a ref, such as `[ref=e12]`. |
| `get_page_text` | The page's text. |
| `find` | The snapshot lines that contain the words of the query. It matches text, not a description. |
| `left_click`, `double_click`, `right_click`, `middle_click`, `hover` | By ref, with the pointer. `left_click` also takes a coordinate, and then clicks the element at that point by script. |
| `scroll`, `scroll_to` | `scroll` moves the scrollable box under the point. `scroll_to` brings a ref into view. |
| `type` | Inserts text into the field that has the focus. |
| `key` | Keys and chords as Claude writes them (`ctrl+a`, `Return`). |
| `form_input` | Fills a text field, chooses an option of a select, or sets a checkbox, by ref. |
| `wait` | Waits up to 60 seconds. |
| `read_console`, `read_network` | The page's console messages and network requests. |
| `javascript_exec` | Runs a script in the page. Served only when you pass `confirm`. |

Not served, and sent to the API as disabled: `zoom`, `left_click_drag`, `left_mouse_down`, `left_mouse_up`, `mouse_move`, `hold_key`, `file_upload`, `new_tab`, `switch_tab`, `list_tabs` and `close_tab`. The driver follows one page and reports it as one tab.

## Options

```python
SpecStreamBrowser(
    api_key=None,  # default: the SPECSTREAM_API_KEY environment variable
    session_id=None,  # drive a session that is already open, and leave it open at close()
    timeout_s=900,  # the longest the session lasts, 60 to 3600 seconds
    idle_timeout_s=300,  # the session ends after this long without a step, 10 to 600 seconds
    allowed_domains=None,  # hosts the session may open, such as ["example.com", "*.example.com"]
    block_media=False,  # do not load images, video and fonts
    url_policy=...,  # the toolset's own options are passed through:
    confirm=...,  # url_policy, confirm, configs, file_policy, tool_configs
)
```

`browser.session_id` is the session's id once it is open. `browser.live_url` is a page that shows the browser's screen as it changes.

## Run it safely

Claude's next action depends on the pages it reads, and a page can try to steer it. Before you run the driver on anything that matters, read [Run the toolset safely](https://platform.claude.com/docs/en/agents-and-tools/tool-use/browser-use-sdk#run-the-toolset-safely) and do these two things:

- Pass `allowed_domains`. The session itself then refuses every other host, also for links a page opens. A `url_policy` checks only the URLs Claude navigates to.
- Pass `confirm` for calls that have an effect, and leave `javascript_exec` off unless the task needs it.

SpecStream sessions never open private addresses, and they do not open sites that opted out.

## Errors

A step that fails reaches Claude as an error result with SpecStream's own message, and the run continues. That includes a key that SpecStream refuses. A missing key raises `SpecStreamError` when you create the toolset. `close()` does not raise: if the release call fails, the session ends at its idle wait.

## Tests

```bash
pip install -e ".[test]"
pytest -q
```

The tests script the SpecStream API. They need no key and no network.

## License

BSD-2-Clause.
