# SpecStream

**The live web data engine.**

One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. It runs through the API and MCP, and inside Sheets, CRMs, Slack, n8n, Zapier and the other tools teams already use.

This extension adds SpecStream to VS Code two ways: your agent can use it as an MCP server, and you can ask for data yourself with `@specstream` in chat.

## Three products

| Product | What it does | Price |
| --- | --- | --- |
| Search API | `GET /v1/web-search`. The most accurate web search API in the world ([scores and method](https://specstream.ai/benchmarks)). | $5 per 1,000 searches, $1 per 1,000 with `speed=fast` |
| Extract API | `POST /v1/extract`. The main text of up to 20 web pages, PDF, Word or Excel files a call. | $0.80 per 1,000 pages. A page with no text is not charged. |
| Deep Search | Ask in plain words. Get every match on the live web, in structured rows. | 5¢, 15¢ or $1 a row |

## Ask in chat

```
@specstream /find MCP servers on GitHub with more than 500 stars, pushed this month
```

1. Say what you need in plain words.
2. SpecStream shows the price. Nothing runs yet.
3. Press **Run for up to $X**. You pay for each result delivered, and a search that finds nothing costs nothing.
4. The matches stream into chat as a table. Source URL and read time on every value.
5. Press **Open in workspace** to send them to your sheet, CRM or agent, or save the request so new matches arrive on their own.

## Give your agent the same engine

The extension adds the SpecStream MCP server (`https://api.specstream.ai/mcp`) to VS Code. In agent mode, your agent asks for structured rows instead of reading pages, and it shows you the price before it spends anything.

Sign-in is VS Code's own: start **SpecStream** from **MCP: List Servers** and approve in the browser. Prefer a key? Run **SpecStream: Use an API Key Instead of Signing In**. The key is kept in VS Code's secret storage.

## A real browser for your agent

Some pages need a real browser: a form, a click, a page drawn by scripts. Through the same MCP server your agent opens a browser session on SpecStream's server with `open_browser`, drives it with the `browser_` tools, and ends it with `close_browser`. Nothing runs on your machine.

Browser sessions cost $0.10 an hour, charged by the second, and $1 per 1,000 steps. For the text of pages you already know, the Extract API is faster and cheaper.

## Get started

Open the **Get your first list with SpecStream** walkthrough from the Command Palette (**Welcome: Open Walkthrough**). Your account starts with $10 of credit, no card.

## Settings

| Setting | What it does |
| --- | --- |
| `specstream.maxMatches` | The most matches `@specstream /find` asks for. The price you approve covers at most this many. Default 25. |
| `specstream.workspaceUrl` | Where **Open in workspace** goes. |
| `specstream.serverUrl` | The MCP server address. |

## Links

[specstream.ai](https://specstream.ai) · [Pricing](https://specstream.ai/pricing) · [Docs](https://specstream.ai/docs/mcp/vscode) · [Privacy](https://specstream.ai/privacy) · support@specstream.ai
