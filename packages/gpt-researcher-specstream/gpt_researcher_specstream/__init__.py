"""SpecStream retriever for GPT Researcher, registered as RETRIEVER=specstream."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

__version__ = "0.1.1"

DEFAULT_BASE_URL = "https://api.specstream.ai"
MAX_EXTRACT_URLS = 20
TIMEOUT_SECONDS = 60
USER_AGENT = f"gpt-researcher-specstream/{__version__}"


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


class SpecStreamSearch:
    """Search API retriever (`GET /v1/web-search`) with an optional Extract API read (`POST /v1/extract`).

    By default each result is a link with the page passages the Search API returns, and GPT Researcher
    reads the page. With `SPECSTREAM_EXTRACT=true` the top pages are read through the Extract API and
    returned as `raw_content`, so GPT Researcher does not fetch them again.
    """

    def __init__(
        self,
        query: str,
        query_domains: list[str] | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        extract: bool | None = None,
    ) -> None:
        self.query = (query or "").strip()
        self.query_domains = [d.strip() for d in (query_domains or []) if d and d.strip()]
        self.api_key = (api_key or os.environ.get("SPECSTREAM_API_KEY") or "").strip()
        self.base_url = (base_url or os.environ.get("SPECSTREAM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.extract_pages = _flag(os.environ.get("SPECSTREAM_EXTRACT")) if extract is None else extract

    @property
    def requires_scraping(self) -> bool:
        return not self.extract_pages

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
        data_part = payload.get("data") if isinstance(payload, dict) else None
        return data_part if isinstance(data_part, dict) else {}

    def _query_text(self) -> str:
        if not self.query_domains:
            return self.query
        sites = " OR ".join(f"site:{domain}" for domain in self.query_domains)
        return f"{self.query} ({sites})"

    def _links(self, data: dict[str, Any]) -> list[dict[str, str]]:
        passages: dict[str, str] = {}
        for passage in data.get("passages") or []:
            if isinstance(passage, dict) and passage.get("url") and passage.get("text"):
                passages.setdefault(str(passage["url"]), str(passage["text"]))
        snippets: dict[str, str] = {}
        order: list[str] = []
        for source in data.get("sources") or []:
            if isinstance(source, dict) and source.get("url"):
                url = str(source["url"])
                if url not in snippets:
                    order.append(url)
                snippets[url] = str(source.get("snippet") or source.get("title") or "")
        for row in data.get("rows") or []:
            if isinstance(row, dict) and row.get("page"):
                url = str(row["page"])
                if url not in snippets:
                    order.append(url)
                    snippets[url] = str(row.get("snippet") or row.get("name") or "")
        for url in passages:
            if url not in snippets:
                order.append(url)
                snippets[url] = ""
        answer = data.get("answer")
        answer_page = str(answer.get("page")) if isinstance(answer, dict) and answer.get("page") else ""
        answer_value = str(answer.get("value")) if isinstance(answer, dict) and answer.get("value") else ""
        if answer_page and answer_value and answer_page not in snippets:
            order.insert(0, answer_page)
            snippets[answer_page] = ""
        links: list[dict[str, str]] = []
        for url in order:
            body = passages.get(url) or snippets.get(url, "")
            if url == answer_page and answer_value:
                body = f"{answer_value}\n{body}".strip()
            links.append({"href": url, "body": body})
        return links

    def _read(self, urls: list[str]) -> dict[str, str]:
        data = self._request("POST", "/v1/extract", {"urls": urls[:MAX_EXTRACT_URLS], "format": "markdown"})
        pages: dict[str, str] = {}
        for result in data.get("results") or []:
            if isinstance(result, dict) and result.get("status") == "ok" and result.get("text"):
                pages[str(result.get("url"))] = str(result["text"])
        return pages

    def search(self, max_results: int = 7) -> list[dict[str, str]]:
        """Return `[{"href", "body"}]`, or `[{"href", "body", "raw_content"}]` with extraction on. Returns `[]` on any error."""
        if not self.query or not self.api_key:
            return []
        limit = max(1, int(max_results))
        try:
            params = urllib.parse.urlencode({"q": self._query_text()[:2000], "passages": "true"})
            links = self._links(self._request("GET", f"/v1/web-search?{params}"))[:limit]
            if not self.extract_pages or not links:
                return links
            try:
                pages = self._read([link["href"] for link in links])
            except (urllib.error.URLError, OSError, ValueError):
                return links
        except (urllib.error.URLError, OSError, ValueError):
            return []
        results: list[dict[str, str]] = []
        for link in links:
            text = pages.get(link["href"])
            if text:
                results.append({**link, "raw_content": text})
        return results or links


__all__ = ["SpecStreamSearch"]
