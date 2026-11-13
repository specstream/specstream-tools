from __future__ import annotations

from typing import Any, Optional

import requests
from attrs import define, field

from griptape.artifacts import TextArtifact
from griptape.drivers.web_scraper import BaseWebScraperDriver
from griptape.specstream import _api


@define
class SpecStreamWebScraperDriver(BaseWebScraperDriver):
    """Reads the main text of a web page, PDF, Word or Excel file with the SpecStream Extract API.

    `POST /v1/extract`, $0.80 per 1,000 pages; a page that gives no text is not charged. Use it with
    `WebLoader` or `WebScraperTool`. The artifact's `meta` holds the page's `url`, `title` and, when
    the page states them, `published` and `modified`.

    Attributes:
        api_key: The SpecStream API key. Default: the `SPECSTREAM_API_KEY` environment variable.
        base_url: The API address. Default: `SPECSTREAM_BASE_URL` or `https://api.specstream.ai`.
        format: `"markdown"` (headings, lists and links kept) or `"text"`.
        session: A shared `requests.Session`.
    """

    api_key: Optional[str] = field(default=None, kw_only=True, repr=False, metadata={"serializable": False})
    base_url: Optional[str] = field(default=None, kw_only=True, metadata={"serializable": True})
    format: str = field(default="markdown", kw_only=True, metadata={"serializable": True})
    session: Optional[requests.Session] = field(
        default=None, kw_only=True, repr=False, metadata={"serializable": False}
    )

    def scrape_url(self, url: str) -> TextArtifact:
        page = self._read(url)
        meta = {key: page[key] for key in ("url", "title", "published", "modified") if page.get(key)}
        return TextArtifact(page.get("text") or "", meta=meta)

    def fetch_url(self, url: str) -> str:
        return self._read(url).get("text") or ""

    def extract_page(self, page: str) -> TextArtifact:
        return TextArtifact(page)

    def _read(self, url: str) -> dict[str, Any]:
        target = (url or "").strip()
        if not target:
            raise _api.SpecStreamError("Send an http or https URL.")
        body = {"urls": [target], "format": "text" if self.format == "text" else "markdown"}
        data = _api.call("/v1/extract", body, api_key=self.api_key, base_url=self.base_url, session=self.session)
        results = data.get("results") or []
        page = results[0] if results and isinstance(results[0], dict) else {}
        if page.get("status") != "ok":
            status = page.get("status") or "no result"
            raise _api.SpecStreamError(f"SpecStream could not read {target}: {status}.", page.get("status_code"))
        return page
