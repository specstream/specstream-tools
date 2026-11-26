---
name: search-and-read
description: Answer a question from the live web with search_web, and read the text of pages with read_pages. Use for one fact, a quick answer, or the text of pages the user names or a search returned.
---

# Search the web and read pages

Use the SpecStream MCP server at `https://api.specstream.ai/mcp`.

For one fact or a quick answer, call `search_web` with the user's question, in their own words and language, as `q`. Give the answer with the page it was read from. If the answer is empty, say that no page read so far states it, show the closest sources, and offer to search again with other words. Don't guess a value the pages don't print.

When the user asks for many results, `search_web` returns the first rows and names the estimated full table. Show those rows, then offer Deep Search for the rest and follow the compile skill.

To read pages, call `read_pages` with up to 20 `urls`: addresses the user gave, or pages a search returned. Each page comes back with a status. Say which pages were blocked, not found or empty, and never fill in their text. Use the text of the pages that were read to answer.

`list_web_searches` and `get_web_search` open an earlier search again without a new search.

Each search and each page read takes a small amount from the user's balance, with no price to approve first. Search once per question, and ask before running many searches or reading many pages in a row.

Never ask the user for an API key. The connection is already signed in.
