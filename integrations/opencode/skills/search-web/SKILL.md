---
name: search-web
description: Answer a question from the live web in seconds with the Search API ($5 per 1,000 searches, no quote needed).
---

# Search the live web

SpecStream is the live web data engine for teams and agents. Use the configured MCP server at `https://api.specstream.ai/mcp`.

Use `search_web` with `{"q": "<the question>"}` when the person needs one fact, a fast web search with sources, or a quick look at the first rows of a request before pricing a full Deep Search run. Set `"passages": true` when you want the main text passages of the closest pages included in the reply.

Each call costs $0.005 ($5 per 1,000 searches) from the account balance and needs no quote or approval. The reply returns `kind` (`fact` or `list`), `answer` (with `value`, `page` and `seen_at`), `rows` and ranked `sources`. When `kind` is `list`, `handoff` gives the estimated size and the `compile` call to price and run the full dataset.
