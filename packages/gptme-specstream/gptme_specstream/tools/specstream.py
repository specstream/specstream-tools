"""The `specstream` gptme tool: live web search and page reading with SpecStream."""

from __future__ import annotations

from gptme.tools.base import ToolFunction, ToolSpec

from gptme_specstream.client import MAX_EXTRACT_URLS, MAX_QUERY_CHARS, SpecStreamError, as_text, call


def search_web(query: str, passages: bool = False) -> str:
    """Search the live web with SpecStream and return the answer, matching rows and ranked sources as JSON.

    Args:
        query: The question or request in everyday words, 1 to 2,000 characters.
        passages: True adds the text of the top pages to the reply.
    """
    question = (query or "").strip()[:MAX_QUERY_CHARS]
    if not question:
        raise SpecStreamError("Send the question in query, 1 to 2,000 characters.")
    params = {"q": question}
    if passages:
        params["passages"] = "true"
    return as_text(call("GET", "/v1/web-search", params=params))


def read_pages(urls: list[str], format: str = "markdown") -> str:
    """Read the main text of 1 to 20 web pages, PDF, Word or Excel files live with SpecStream, as JSON.

    Args:
        urls: 1 to 20 http or https URLs to read.
        format: "markdown" (default) or "text".
    """
    if isinstance(urls, str):
        urls = [urls]
    cleaned = [url.strip() for url in urls or [] if isinstance(url, str) and url.strip()][:MAX_EXTRACT_URLS]
    if not cleaned:
        raise SpecStreamError("Send 1 to 20 http or https URLs.")
    body = {"urls": cleaned, "format": "text" if format == "text" else "markdown"}
    return as_text(call("POST", "/v1/extract", body=body))


instructions = """
Use the specstream tool to read the live web. Call search_web with the question in everyday words to get
an answer, matching rows and ranked sources. Call read_pages with 1 to 20 URLs to read the main text of
web pages, PDF, Word and Excel files. Name the source URL of each fact you report.
""".strip()

examples = """
### Find a current fact

> User: Who won the 2025 Nobel Prize in Physics?
> Assistant:
```ipython
print(search_web("Who won the 2025 Nobel Prize in Physics?"))
```

### Read a page

> User: Summarise https://example.com
> Assistant:
```ipython
print(read_pages(["https://example.com"]))
```
""".strip()

tool = ToolSpec(
    name="specstream",
    desc="Live web search and page reading with SpecStream",
    instructions=instructions,
    examples=examples,
    functions=[ToolFunction.from_callable(search_web), ToolFunction.from_callable(read_pages)],
    hints=frozenset({"web", "read-only"}),
    read_only=True,
)

__all__ = ["read_pages", "search_web", "tool"]
