# SpecStream for Claude Desktop

Web search, page reading and structured web data for Claude, from the live web, with a source URL on every value.

This folder is a Claude Desktop extension (an MCP bundle, `.mcpb`). It runs a small local server that forwards Claude's requests over HTTPS to the hosted [SpecStream](https://specstream.ai) MCP server at `https://api.specstream.ai/mcp`. The server is one JavaScript file with no dependencies, and it runs on the Node.js that Claude Desktop ships, on macOS and Windows.

## Install

1. Build `specstream.mcpb` from this folder with `npm run pack`.
2. Double-click the file, or drag it into **Settings > Extensions** in Claude Desktop, and click **Install**.
3. Paste your API key into **API key**. Create the key under **Agents & API** in your [SpecStream workspace](https://specstream.ai/workspace). Claude Desktop stores it in your operating system's keychain.

Without a key the extension still starts: it lists its tools, and each tool call says how to get a key.

## Tools

| Product | Tool | What it does | Price |
|---|---|---|---|
| Search API | `search_web` | Answers a question in everyday words from the live web, with sources | $5 per 1,000 searches of up to 10 results |
| Extract API | `read_pages` | Returns the main text of 1 to 20 web pages, PDF, Word or Excel files | $0.80 per 1,000 pages; a page with no text is free |
| Deep Search | `compile`, `quote_capacity_work`, `authorize_capacity_work`, `get_find`, `list_find_rows` | Reads a request for a complete list or table, prices it, and returns every match in structured rows | Per row, quoted before the run |

A Deep Search run is quoted first and starts only after you approve its maximum. The extension lists every tool of the hosted server; see the [agent guide](https://specstream.ai/docs/mcp).

## Examples

- "Search the web: what is the latest stable release of PostgreSQL?"
- "Read https://www.postgresql.org/docs/release/ and list the releases of this year."
- "Find every company that makes heat pumps in Sweden, with its website and head office city. Show me the quote first."

## Privacy

The extension sends the tool calls Claude makes, and your API key, to `https://api.specstream.ai/mcp` over HTTPS. It sends nothing else and it reads no files. See the [privacy policy](https://specstream.ai/privacy).

## Build

```sh
npm test            # the server's tests, no network
npm run validate    # checks manifest.json with the mcpb tool
npm run pack        # writes specstream.mcpb
```

`server/tools.json` is a copy of the tool list of `specstream-mcp-stdio`.

## Problems

Open **Settings > Extensions > SpecStream** and check the key. A key that SpecStream refuses gives the answer "SpecStream refused the API key". For more help, open an issue in [specstream-tools](https://github.com/specstream/specstream-tools/issues).
