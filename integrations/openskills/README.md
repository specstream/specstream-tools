# SpecStream skills for OpenSkills

SpecStream is the live web data engine for teams and agents. [OpenSkills](https://github.com/numman-ali/openskills) installs `SKILL.md` folders from a public GitHub repository into Claude Code, Cursor, Windsurf, Aider, Codex and any agent that reads `AGENTS.md`. The SpecStream skills are in this repository, so one line installs each of them.

## One skill for all of SpecStream

```bash
npx openskills install specstream/specstream-tools/catalog-skills/specstream
npx openskills sync
```

The `specstream` skill teaches an agent the three products: search the live web, read the text of pages, and build a table with Deep Search.

## One skill for each job

Install only the skills that you need. Each line installs one skill.

```bash
npx openskills install specstream/specstream-tools/skills/search-web
npx openskills install specstream/specstream-tools/skills/extract-pages
npx openskills install specstream/specstream-tools/skills/compile
npx openskills install specstream/specstream-tools/skills/review-work
npx openskills install specstream/specstream-tools/skills/approve-work
npx openskills install specstream/specstream-tools/skills/continue-work
npx openskills install specstream/specstream-tools/skills/schedules
npx openskills install specstream/specstream-tools/skills/deep-search
npx openskills install specstream/specstream-tools/skills/research
npx openskills install specstream/specstream-tools/skills/browser
npx openskills install specstream/specstream-tools/catalog-skills/specstream-tables
npx openskills sync
```

| Skill | What it teaches |
| --- | --- |
| `search-web` | Answer a question from the live web with the Search API |
| `extract-pages` | Read the main text of web pages and files with the Extract API |
| `compile` | Read a request in plain words back to the person before anything runs |
| `review-work` | Get the real price for the exact request. Nothing runs |
| `approve-work` | Approve an exact price, up to the maximum the person set |
| `continue-work` | Read the finished rows with their sources and send them where the person works |
| `schedules` | Keep a list current on a schedule, within a limit per run and per month |
| `deep-search` | Run the whole Deep Search flow, from the request to the rows with their sources |
| `research` | Get a written report on a question, with the page behind each cited sentence |
| `browser` | Open a real browser and drive it step by step, for a page that needs clicks or a form |
| `specstream-tables` | Build a table with Deep Search, in one skill |

## Give the path of the skill

Always give the path of a skill after the repository name. The short form `specstream/specstream-tools`, with no path, makes OpenSkills search the whole repository. The plugins in this repository carry copies of the same skills, so the short form shows each skill more than once.

Add `--global` to install a skill for all your projects. Add `--universal` to install it into `.agent/skills/`, for agents other than Claude Code.

## Connect the server

The skills call the SpecStream MCP server. Add it one time. It signs you in through your browser the first time, so you need no key:

```bash
claude mcp add --transport http specstream https://api.specstream.ai/mcp
```

Setup for other clients is in the [README](../../README.md) of this repository. Prices are at [specstream.ai/pricing](https://specstream.ai/pricing).
