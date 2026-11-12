# specstream

The live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

This folder is an agent skill for SpecStream: search the live web, read the text of pages, and build tables with Deep Search, with a source URL on every value. Deep Search work starts only after you approve a maximum price.

## Install

Copy this folder into your skills folder:

```bash
mkdir -p ~/.claude/skills
cp -r catalog-skills/specstream ~/.claude/skills/
```

Then add the SpecStream MCP server, which signs in through your browser the first time:

```bash
claude mcp add --transport http specstream https://api.specstream.ai/mcp
```

Setup for Claude: https://specstream.ai/docs/mcp/claude

Search: $5 per 1,000 searches, or $1 on the fast tier. Extract: $0.80 per 1,000 pages. Deep Search: 5 cents, 15 cents or $1 a row. New accounts start with $10 of credit, no card. Docs: https://specstream.ai/docs. License: MIT.
