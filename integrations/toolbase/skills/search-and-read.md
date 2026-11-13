---
name: Search the live web and read pages with SpecStream
description: When to call web_search and read_pages, and how to combine them for a question that needs current facts with sources.
---

# Search the live web and read pages

## When to use this toolkit

Use `specstream` when the user needs facts from the live web: a current number, a recent event, a product or company detail, or the text of a page they name.

## Steps

1. Call `web_search` with the user's question in everyday words. Set `fast` to true when a quick list of ranked results is enough.
2. Read the answer and its source. Give the user the source URL with the answer.
3. When the answer needs more detail, call `read_pages` with the URLs of the best sources (up to 20 in one call).
4. When the user gives a URL, call `read_pages` directly. It reads web pages, PDFs, Word documents and Excel spreadsheets.

## Notes

- A result with status "error" carries a message. Tell the user what the message says.
- Do not ask the user for the API key in the conversation. The key is set once with `toolbase config set specstream api_key <key>`.
