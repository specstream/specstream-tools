"""Prefect tasks for the SpecStream Search API and Extract API."""

from __future__ import annotations

from typing import Any, Literal

from prefect import task

from prefect_specstream.credentials import SpecStreamCredentials, SpecStreamError

MAX_QUERY_CHARS = 2000
MAX_EXTRACT_URLS = 20


@task(name="specstream-web-search")
def web_search(
    query: str,
    specstream_credentials: SpecStreamCredentials,
    speed: Literal["default", "fast"] = "default",
    num: int | None = None,
    passages: bool = False,
) -> dict[str, Any]:
    """Search the live web with SpecStream (`POST /v1/web-search`).

    Args:
        query: The question or request in everyday words, 1 to 2,000 characters.
        specstream_credentials: The block that holds the API key.
        speed: "default" ($5 per 1,000 searches of up to 10 results, with an answer) or
            "fast" ($1 per 1,000 searches of up to 10 results, ranked sources only).
        num: How many results to return. None leaves the API default (10).
        passages: Add the text of the top pages closest to the request.

    Returns:
        The `data` object of the reply: `sources`, and on the default speed `answer` and `rows`.
    """
    question = (query or "").strip()[:MAX_QUERY_CHARS]
    if not question:
        raise SpecStreamError("Send the question in query, 1 to 2,000 characters.")
    body: dict[str, Any] = {"q": question}
    if speed == "fast":
        body["speed"] = "fast"
    if num is not None:
        body["num"] = int(num)
    if passages:
        body["passages"] = True
    return specstream_credentials.get_client().call("POST", "/v1/web-search", json=body)


@task(name="specstream-extract-pages")
def extract_pages(
    urls: list[str],
    specstream_credentials: SpecStreamCredentials,
    format: Literal["markdown", "text"] = "markdown",
) -> dict[str, Any]:
    """Read the main text of web pages, PDF, Word and Excel files with SpecStream (`POST /v1/extract`).

    $0.80 per 1,000 pages; a page with no text is not charged. Up to 20 URLs a call: a longer list
    is sent in calls of 20 and the results are joined in order.

    Args:
        urls: http or https URLs to read.
        specstream_credentials: The block that holds the API key.
        format: "markdown" (default) or "text".

    Returns:
        `{"results": [...]}`, one result per URL with its `url`, `status` and text.
    """
    cleaned = [url.strip() for url in urls if url and url.strip()]
    if not cleaned:
        raise SpecStreamError("Send 1 or more http or https URLs.")
    client = specstream_credentials.get_client()
    results: list[Any] = []
    for start in range(0, len(cleaned), MAX_EXTRACT_URLS):
        body = {"urls": cleaned[start : start + MAX_EXTRACT_URLS], "format": "text" if format == "text" else "markdown"}
        data = client.call("POST", "/v1/extract", json=body)
        results.extend(data.get("results") or [])
    return {"results": results}
