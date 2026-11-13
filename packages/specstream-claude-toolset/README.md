# SpecStream driver for the Claude browser toolset

`SpecStreamBrowser` is a driver for the browser toolset of the Claude SDK
([Browser and computer use with the SDK toolsets](https://platform.claude.com/docs/en/agents-and-tools/tool-use/browser-use-sdk)).
Claude navigates, reads, clicks and types in a real browser that SpecStream hosts. You run no browser and no container.

A session costs $0.10 an hour, charged by the second. The driver opens it on Claude's first call and releases it on `close()`.

## Install

```bash
pip install "specstream-claude-toolset @ git+https://github.com/specstream/specstream-tools#subdirectory=packages/specstream-claude-toolset"
```

The driver needs Python 3.10 or later, `anthropic` 2.8 or later and `playwright`. It connects Playwright to the hosted browser, so `playwright install` is not needed.

Set two keys and the model:

```bash
export ANTHROPIC_API_KEY=...     # https://platform.claude.com
export SPECSTREAM_API_KEY=...    # https://specstream.ai/workspace
export ANTHROPIC_MODEL=...       # a model that supports the browser toolset, listed on the page above
```

## Use

```python
import os

from anthropic import Anthropic
from specstream_claude_toolset import SpecStreamBrowser

client = Anthropic()
with SpecStreamBrowser(allowed_domains=["example.com", "*.iana.org"]) as browser:
    runner = client.beta.messages.tool_runner(
        model=os.environ["ANTHROPIC_MODEL"],
        max_tokens=1024,
        tools=[browser],
        messages=[{"role": "user", "content": "Open example.com and tell me its heading."}],
    )
    for message in runner:
        print(message)
```

Pass the driver itself as the `tools` entry. The runner never closes a toolset: the `with` block does, and that ends the session and its charge.

## What Claude can do

The driver serves 27 members of `browser_toolset_20260801`:

| Group | Members |
| --- | --- |
| Navigation and capture | `navigate`, `screenshot`, `zoom` |
| Pointer | `left_click`, `right_click`, `middle_click`, `double_click`, `triple_click`, `hover`, `left_click_drag`, `left_mouse_down`, `left_mouse_up`, `mouse_move`, `scroll`, `scroll_to` |
| Keyboard and timing | `type`, `key`, `hold_key`, `wait` |
| Page reading | `read_page`, `find`, `get_page_text` |
| Forms | `form_input` |
| Tabs | `new_tab`, `list_tabs`, `switch_tab`, `close_tab` |

`javascript_exec`, `file_upload`, `read_console` and `read_network` are sent as disabled.

Clicks take a viewport coordinate or a reference such as `ref_4` from `read_page` or `find`. A reference stays the same until the tab navigates; after that the driver answers that it is stale, and Claude reads the page again. A tab that a page opens is reported to Claude, and so is a dialog the driver dismissed.

## Options

| Option | Default | Sets |
| --- | --- | --- |
| `api_key` | `SPECSTREAM_API_KEY` | Your SpecStream API key |
| `allowed_domains` | every public host | Hosts the session may open, such as `example.com` or `*.example.com` |
| `timeout_s` | 300 | The most seconds the session runs (60 to 3,600) |
| `idle_timeout_s` | 60 | Seconds with no client before the session ends (10 to 600) |
| `viewport` | `(1280, 720)` | The size of the page and of every screenshot |
| `block_media` | `False` | `True` skips images, video, audio and fonts |
| `headless` | `True` | `False` runs the browser with a screen |
| `metadata` | none | Your own labels for the session |

The SDK's own options (`configs`, `confirm`, `url_policy`, `file_policy`, `tool_configs`) pass through unchanged.
`browser.session` holds the session as SpecStream answered it, with its `id` and `live_url`.

## Safety

Read [Run the toolset safely](https://platform.claude.com/docs/en/agents-and-tools/tool-use/browser-use-sdk#run-the-toolset-safely) before you point Claude at anything that matters.

- **Hosts.** The SDK's `url_policy` sees only `navigate` calls. `allowed_domains` is checked by SpecStream on the browser itself, so it also covers links Claude clicks, redirects and the requests a page makes. Set both when you can.
- **Schemes.** `navigate` opens `http` and `https` only. An address with no scheme gets `https://`.
- **The host.** The browser runs at SpecStream, not on your machine. It has no access to your files or your network, and it starts signed in to nothing.
- **Approval.** Pass `confirm` to ask a person before the calls you choose.

## Errors

A browser error reaches Claude as one line, and the run goes on. A SpecStream refusal (no credit, a bad key, a session limit) reaches Claude with the API's own message. A missing key raises `SpecStreamError` when you construct the driver.

## Tests

```bash
pip install -e ".[test]"
pytest
```

The tests script the SpecStream API, so they use no key and cost nothing. `tests/test_real_browser.py` drives a local Chromium and is skipped where Playwright has none.

## License

BSD 2-Clause. See [LICENSE](LICENSE).
