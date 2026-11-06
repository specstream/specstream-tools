import json
from typing import Any, Optional

from haystack import Document, component, default_from_dict, default_to_dict
from haystack.utils import Secret, deserialize_secrets_inplace

from haystack_integrations.components.fetchers.specstream._api import (
    DEFAULT_BASE_URL,
    DEFAULT_WAIT_SECONDS,
    SpecStreamAPI,
    SpecStreamError,
)

# Row fields that say where a row came from rather than what it says.
_META = ("list_id", "list_link", "position", "source_url", "checked_at")


@component
class SpecStreamListFetcher:
    """
    Turns a plain-English request into the finished list: one Document per matching row.

    The Document content is the row as JSON. The metadata carries the page the row was read from
    (`source_url`), when it was checked, the list it belongs to, and the row's fields.
    The list starts only if its price is within `max_price_usd`, which you set in code.

    ```python
    from haystack_integrations.components.fetchers.specstream import SpecStreamListFetcher

    fetcher = SpecStreamListFetcher(max_price_usd=3, max_results=25)
    result = fetcher.run(request="Breweries in Portland, Oregon that host events, with their website")
    for doc in result["documents"]:
        print(doc.meta["source_url"], doc.content)
    ```
    """

    def __init__(
        self,
        max_price_usd: float,
        api_key: Secret = Secret.from_env_var("SPECSTREAM_API_KEY"),
        max_results: int = 25,
        base_url: str = DEFAULT_BASE_URL,
        wait_seconds: float = DEFAULT_WAIT_SECONDS,
        poll_interval: float = 3.0,
        locale: str = "en-US",
    ):
        """
        :param max_price_usd: The most one list may cost, in US dollars. If the quoted price is higher, nothing runs.
        :param api_key: A SpecStream API key. Read from `SPECSTREAM_API_KEY` by default.
        :param max_results: How many matching rows to find when `run` doesn't say.
        :param base_url: The SpecStream API address.
        :param wait_seconds: How long to wait for the list to finish before returning the rows found so far.
        :param poll_interval: Seconds between checks while the list runs.
        :param locale: The language the request is read in.
        """
        if not max_price_usd or max_price_usd <= 0:
            raise ValueError("max_price_usd must be greater than 0.")
        if max_results < 1:
            raise ValueError("max_results must be 1 or more.")
        self.max_price_usd = max_price_usd
        self.api_key = api_key
        self.max_results = max_results
        self.base_url = base_url
        self.wait_seconds = wait_seconds
        self.poll_interval = poll_interval
        self.locale = locale

    def to_dict(self) -> dict[str, Any]:
        return default_to_dict(
            self,
            max_price_usd=self.max_price_usd,
            api_key=self.api_key.to_dict(),
            max_results=self.max_results,
            base_url=self.base_url,
            wait_seconds=self.wait_seconds,
            poll_interval=self.poll_interval,
            locale=self.locale,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpecStreamListFetcher":
        deserialize_secrets_inplace(data["init_parameters"], keys=["api_key"])
        return default_from_dict(cls, data)

    @component.output_types(documents=list[Document], list_id=str, status=str, list_link=str, message=str)
    def run(self, request: str, max_results: Optional[int] = None) -> dict[str, Any]:
        """
        Find the list and return its rows.

        :param request: The list to find, in plain words: what every row must be or meet, and the details to bring back.
        :param max_results: How many matching rows to find. Defaults to the value set at init.
        :returns: `documents` (one per row), `list_id`, `status`, `list_link` and, when the list was still running, a `message`.
        :raises SpecStreamError: When the request is too vague to price, or the price is above `max_price_usd`.
        """
        result = SpecStreamAPI(self.api_key.resolve_value() or "", self.base_url).find_list(
            request,
            max_results=max_results or self.max_results,
            max_price_usd=self.max_price_usd,
            wait_seconds=self.wait_seconds,
            poll_interval=self.poll_interval,
            locale=self.locale,
            key_prefix="haystack",
        )
        if result["status"] in ("needs_edit", "over_maximum"):
            raise SpecStreamError(result["message"])
        documents = [self._to_document(row, result.get("request")) for row in result["rows"]]
        return {
            "documents": documents,
            "list_id": result["list_id"],
            "status": result["status"],
            "list_link": result["list_link"],
            "message": result.get("message", ""),
        }

    @staticmethod
    def _to_document(row: dict[str, Any], request: Optional[str]) -> Document:
        fields = {label: value for label, value in row.items() if label not in _META}
        meta: dict[str, Any] = {key: row.get(key) for key in _META}
        meta["request"] = request
        meta["fields"] = fields
        return Document(content=json.dumps(fields, ensure_ascii=False, default=str), meta=meta)


@component
class SpecStreamWebSearch:
    """Searches the live web in seconds with the SpecStream Search API (`GET /v1/web-search`, $5 per 1,000 searches)."""

    def __init__(
        self,
        api_key: Secret = Secret.from_env_var("SPECSTREAM_API_KEY"),
        base_url: str = DEFAULT_BASE_URL,
    ):
        self.api_key = api_key
        self.base_url = base_url

    def to_dict(self) -> dict[str, Any]:
        return default_to_dict(self, api_key=self.api_key.to_dict(), base_url=self.base_url)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpecStreamWebSearch":
        deserialize_secrets_inplace(data["init_parameters"], keys=["api_key"])
        return default_from_dict(cls, data)

    @component.output_types(documents=list[Document], answer=dict[str, Any])
    def run(self, q: str, passages: bool = False) -> dict[str, Any]:
        data = SpecStreamAPI(self.api_key.resolve_value() or "", self.base_url).web_search(q, passages=passages)
        docs: list[Document] = []
        for row in data.get("rows") or []:
            if isinstance(row, dict):
                docs.append(
                    Document(
                        content=str(row.get("snippet") or row.get("name") or ""),
                        meta={"title": row.get("name"), "source_url": row.get("page"), "fields": row.get("fields")},
                    )
                )
        for src in data.get("sources") or []:
            if isinstance(src, dict):
                docs.append(
                    Document(
                        content=str(src.get("snippet") or src.get("title") or ""),
                        meta={"title": src.get("title"), "source_url": src.get("url"), "published": src.get("published")},
                    )
                )
        return {"documents": docs, "answer": data.get("answer") or {}}


@component
class SpecStreamExtractor:
    """Reads the main text of 1 to 20 URLs live with the SpecStream Extract API (`POST /v1/extract`, $0.80 per 1,000 pages)."""

    def __init__(
        self,
        api_key: Secret = Secret.from_env_var("SPECSTREAM_API_KEY"),
        base_url: str = DEFAULT_BASE_URL,
    ):
        self.api_key = api_key
        self.base_url = base_url

    def to_dict(self) -> dict[str, Any]:
        return default_to_dict(self, api_key=self.api_key.to_dict(), base_url=self.base_url)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpecStreamExtractor":
        deserialize_secrets_inplace(data["init_parameters"], keys=["api_key"])
        return default_from_dict(cls, data)

    @component.output_types(documents=list[Document])
    def run(self, urls: list[str], format: str = "markdown") -> dict[str, Any]:
        data = SpecStreamAPI(self.api_key.resolve_value() or "", self.base_url).extract_pages(urls, format=format)
        docs = [
            Document(
                content=str(item.get("text") or ""),
                meta={
                    "source_url": item.get("url"),
                    "title": item.get("title"),
                    "published": item.get("published"),
                    "status": item.get("status"),
                    "read_from": item.get("read_from"),
                },
            )
            for item in (data.get("results") or [])
            if isinstance(item, dict)
        ]
        return {"documents": docs}
