# specstream-tables

The live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

This folder is an agent skill for SpecStream Deep Search: ask in plain words, get every match on the live web in structured rows. It also fills in and checks the rows of a CSV you already have. Source URL and read time on every value. Paid work starts only after you approve a maximum price.

## Install

Copy this folder into your skills folder:

```bash
mkdir -p ~/.claude/skills
cp -r catalog-skills/specstream-tables ~/.claude/skills/
```

Then add the SpecStream MCP server, which signs in through your browser the first time:

```bash
claude mcp add --transport http specstream https://api.specstream.ai/mcp
```

Then ask Claude for a table in plain words.

Each delivered row costs 5 cents, 15 cents or $1, depending on what the row needs. New accounts start with $10 of credit, no card. Docs: https://specstream.ai/docs. License: MIT.
