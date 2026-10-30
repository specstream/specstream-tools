# SpecStream for VS Code

**Ask for the list no one sells. Get every match, with its source, without leaving your editor.**

SpecStream is the live web data engine for teams and agents. This extension adds it to VS Code two ways: your agent can use it as an MCP server, and you can ask for lists yourself with `@specstream` in chat.

## Ask for a list

```
@specstream /find Companies that filed a Form D this week to raise $5M or more, with state and industry
```

```
@specstream /find MCP servers on GitHub with more than 500 stars, pushed this month
```

1. Say what you need in plain words.
2. SpecStream shows the price. Nothing runs yet.
3. Press **Run for up to $X**. You pay for each result delivered, and a search that finds nothing costs nothing.
4. The matches stream into chat as a table, each with a link to its source.
5. Press **Open in workspace** to send them to your sheet, CRM or agent, or save the request so new matches arrive on their own.

## Give your agent the same engine

The extension adds the SpecStream MCP server (`https://api.specstream.ai/mcp`) to VS Code. In agent mode, your agent asks for finished lists instead of reading pages, and it shows you the price before it spends anything.

Sign-in is VS Code's own: start **SpecStream** from **MCP: List Servers** and approve in the browser. Prefer a key? Run **SpecStream: Use an API Key Instead of Signing In**. The key is kept in VS Code's secret storage.

## Get started

Open the **Get your first list with SpecStream** walkthrough from the Command Palette (**Welcome: Open Walkthrough**). Your account starts with $10 of work free, no card.

## Settings

| Setting | What it does |
| --- | --- |
| `specstream.maxMatches` | The most matches `@specstream /find` asks for. The price you approve covers at most this many. Default 25. |
| `specstream.workspaceUrl` | Where **Open in workspace** goes. |
| `specstream.serverUrl` | The MCP server address. |

## Links

[specstream.ai](https://specstream.ai) · [Pricing](https://specstream.ai/pricing) · [Docs](https://specstream.ai/docs/mcp/vscode) · [Privacy](https://specstream.ai/privacy) · support@specstream.ai
