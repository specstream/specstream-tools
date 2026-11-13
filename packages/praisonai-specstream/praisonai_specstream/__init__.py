"""SpecStream search provider for PraisonAI, registered as `specstream` in `praisonai.tools.search`."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from praisonaiagents.tools.base import BaseTool

__version__ = "0.1.0"

DEFAULT_BASE_URL = "https://api.specstream.ai"
MAX_EXTRACT_URLS = 20
TIMEOUT_SECONDS = 60
USER_AGENT = f"praisonai-specstream/{__version__}"


class SpecStreamTool(BaseTool):
    """Search the live web (`GET /v1/web-search`) and read pages (`POST /v1/extract`) with SpecStream.

    PraisonAI builds the tool with no arguments, so the key comes from `SPECSTREAM_API_KEY`.
    """

    name = "specstream"
    description = (
        "Search the live web with SpecStream. Returns an answer when the pages state one, and the result "
        "pages with their title, URL and the passage that matches the query. "
        "With action='extract' and urls, returns the text of those pages."
    )

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        speed: str | None = None,
    ) -> None:
        self.api_key = (api_key or os.environ.get("SPECSTREAM_API_KEY") or "").strip()
        self.base_url = (base_url or os.environ.get("SPECSTREAM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.speed = (speed or os.environ.get("SPECSTREAM_SPEED") or "").strip().lower()
        super().__init__()

    def run(
        self,
        query: str = "",
        max_results: int = 5,
        action: str = "search",
        urls: str = "",
    ) -> dict:
        """Search the web for `query`, or read `urls` (comma-separated) with action='extract'."""
        if (action or "search").lower() == "extract":
            return self.extract(urls or "")
        return self.search(query or "", max_results=max_results)

    def search(self, query: str, max_results: int = 5) -> dict[str, Any]:
        """Return `{"query", "answer"?, "results": [{"title", "url", "content"}]}`, or `{"error"}`."""
        query = (query or "").strip()
        if not query:
            return {"error": "query is required"}
        if not self.api_key:
            return {"error": "SPECSTREAM_API_KEY not configured"}
        params = {"q": query[:2000], "passages": "true"}
        if self.speed == "fast":
            params["speed"] = "fast"
        try:
            data = self._request("GET", "/v1/web-search?" + urllib.parse.urlencode(params))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return {"error": _reason(exc)}
        result: dict[str, Any] = {"query": query}
        answer = data.get("answer")
        if isinstance(answer, dict) and answer.get("value"):
            result["answer"] = str(answer["value"])
        result["results"] = _results(data)[: max(1, int(max_results))]
        return result

    def extract(self, urls: str | list[str]) -> dict[str, Any]:
        """Return `{"results": [{"url", "content"}]}` for up to 20 pages, or `{"error"}`."""
        if isinstance(urls, str):
            urls = urls.split(",")
        wanted = [u.strip() for u in urls if u and u.strip()][:MAX_EXTRACT_URLS]
        if not wanted:
            return {"error": "urls is required"}
        if not self.api_key:
            return {"error": "SPECSTREAM_API_KEY not configured"}
        try:
            data = self._request("POST", "/v1/extract", {"urls": wanted, "format": "markdown"})
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return {"error": _reason(exc)}
        pages = []
        for page in data.get("results") or []:
            if isinstance(page, dict) and page.get("status") == "ok" and page.get("text"):
                pages.append({"url": str(page.get("url")), "content": str(page["text"])})
        return {"results": pages}

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base_url + path, data=data, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        part = payload.get("data") if isinstance(payload, dict) else None
        return part if isinstance(part, dict) else {}


def _reason(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"SpecStream answered HTTP {exc.code}"
    return f"SpecStream request failed: {exc}"


def _results(data: dict[str, Any]) -> list[dict[str, str]]:
    """One entry per page, in the API's order; the matching passage is the content when there is one."""
    passages: dict[str, str] = {}
    titles: dict[str, str] = {}
    for passage in data.get("passages") or []:
        if isinstance(passage, dict) and passage.get("url") and passage.get("text"):
            passages.setdefault(str(passage["url"]), str(passage["text"]))
            titles.setdefault(str(passage["url"]), str(passage.get("title") or ""))
    snippets: dict[str, str] = {}
    order: list[str] = []
    for source in data.get("sources") or []:
        if isinstance(source, dict) and source.get("url"):
            url = str(source["url"])
            if url not in snippets:
                order.append(url)
                snippets[url] = str(source.get("snippet") or "")
            if source.get("title"):
                titles[url] = str(source["title"])
    for row in data.get("rows") or []:
        if isinstance(row, dict) and row.get("page") and str(row["page"]) not in snippets:
            url = str(row["page"])
            order.append(url)
            snippets[url] = str(row.get("snippet") or "")
            titles.setdefault(url, str(row.get("name") or ""))
    for url in passages:
        if url not in snippets:
            order.append(url)
            snippets[url] = ""
    return [{"title": titles.get(url, ""), "url": url, "content": passages.get(url) or snippets[url]} for url in order]


__all__ = ["SpecStreamTool"]
