# SpecStream toolkit for Toolbase

Live web search and page reading for AI agents. This toolkit gives an agent two tools that call the SpecStream API.

| Tool | What it does | Price |
| --- | --- | --- |
| `web_search` | Searches the live web. Returns an answer with its source, matching rows and ranked sources. | $5 per 1,000 searches of up to 10 results. $1 per 1,000 with `fast`. |
| `read_pages` | Reads the main text, title and published date of 1 to 20 pages, PDFs or documents. | $0.80 per 1,000 pages. A page with no text is not charged. |

## Install

```bash
pip install toolbase
toolbase install specstream
```

The install asks for your SpecStream API key. Get one at https://specstream.ai/workspace?utm_source=toolbase. To set it later:

```bash
toolbase config set specstream api_key <key>
```

Toolbase keeps the key in `~/.toolbase/config/specstream.yaml` and passes it to the tools. The model does not see it.

## Tools

### web_search

- `query` (str): the question or request in everyday words, 1 to 2,000 characters.
- `fast` (bool, optional): the fast tier. The first ranked results, sooner and at the lower price.
- `passages` (bool, optional): include the main text passages of the top pages.

### read_pages

- `urls` (str): 1 to 20 http or https URLs separated by newlines or commas.
- `format` (str, optional): `markdown` (default) or `text`.

Each tool returns a JSON string: `{"status": "ok", "data": ...}`, or `{"status": "error", "message": ...}`.

## Links

- Source: https://github.com/specstream/specstream-tools/tree/main/integrations/toolbase
- License: MIT
