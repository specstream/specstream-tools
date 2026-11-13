# gptme-specstream

[SpecStream](https://specstream.ai) is the live web data engine for teams and agents. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

This package is a [gptme](https://github.com/gptme/gptme) plugin. It gives the agent the `specstream` tool:

| Function | What it does | Cost |
| --- | --- | --- |
| `search_web(query, passages=False)` | Calls `GET /v1/web-search` and returns the answer, matching rows and ranked sources, with the text of the top pages when `passages=True` | $5 per 1,000 searches of up to 10 results |
| `read_pages(urls, format="markdown")` | Calls `POST /v1/extract` and returns the main text, title and published date of 1 to 20 web pages, PDF, Word or Excel files | $0.80 per 1,000 pages (pages with no text are free) |

## Install

```bash
pipx inject gptme gptme-specstream     # or: pip install gptme-specstream, in gptme's environment
export SPECSTREAM_API_KEY=ss_live_...  # Agents & API in your SpecStream workspace
gptme --tools specstream,ipython "Who won the 2025 Nobel Prize in Physics? Quote the announcement."
```

gptme finds the plugin through its `gptme.plugins` entry point. The key can also stay in gptme's config:

```toml
# ~/.config/gptme/config.toml
[env]
SPECSTREAM_API_KEY = "ss_live_..."
```

A free account comes with $10 of credit and needs no card: [specstream.ai](https://specstream.ai/signup).

## As a folder plugin

Without pip, clone the repository and point gptme at the folder that holds `gptme_specstream/`:

```toml
[plugins]
paths = ["~/src/specstream-tools/packages/gptme-specstream"]
```

`httpx` is already installed with gptme.

## Settings

| Setting | Default | What it does |
| --- | --- | --- |
| `SPECSTREAM_API_KEY` | | The API key, from the environment or `[env]` |
| `[plugin.specstream] base_url` | `https://api.specstream.ai` | The API address (`SPECSTREAM_BASE_URL` also works) |

A failed call raises `SpecStreamError` with the API message, which the agent reads and acts on.

MIT licensed.
