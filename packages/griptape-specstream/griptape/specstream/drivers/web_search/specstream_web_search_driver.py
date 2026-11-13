from __future__ import annotations

from typing import Any, Optional

import requests
from attrs import define, field

from griptape.artifacts import JsonArtifact, ListArtifact
from griptape.drivers.web_search import BaseWebSearchDriver
from griptape.specstream import _api

MAX_RESULTS = 100
MAX_QUERY_CHARS = 2000
# Fields of each search result handed to the model, in this order, when the reply has them.
SOURCE_FIELDS = ("title", "url", "site", "snippet", "excerpt", "published", "modified")


@define
class SpecStreamWebSearchDriver(BaseWebSearchDriver):
    """Live web search with the SpecStream Search API (`POST /v1/web-search`).

    Each search is one call: $5 per 1,000 searches of up to 10 results, or $1 per 1,000 with
    `speed="fast"`. `search()` returns a `ListArtifact` of `JsonArtifact`s: first the answer, when the
    question has one (`{"answer": ..., "url": <the page it was read from>}`), then one per result with
    its `title`, `url`, `site`, `snippet` and, with `passages=True`, the `excerpt` of its page.

    Attributes:
        api_key: The SpecStream API key. Default: the `SPECSTREAM_API_KEY` environment variable.
        base_url: The API address. Default: `SPECSTREAM_BASE_URL` or `https://api.specstream.ai`.
        results_count: How many results come back, 1 to 100 (default 5).
        speed: `"fast"` for the fast tier, or None for the default search.
        passages: Add the text of each top page closest to the query (`excerpt`).
        include_answer: Put the answer first when the question has one.
        params: More Search API parameters sent with every search (for example `{"country": "DE"}`).
        session: A shared `requests.Session`.
    """

    api_key: Optional[str] = field(default=None, kw_only=True, repr=False, metadata={"serializable": False})
    base_url: Optional[str] = field(default=None, kw_only=True, metadata={"serializable": True})
    speed: Optional[str] = field(default=None, kw_only=True, metadata={"serializable": True})
    passages: bool = field(default=False, kw_only=True, metadata={"serializable": True})
    include_answer: bool = field(default=True, kw_only=True, metadata={"serializable": True})
    params: dict[str, Any] = field(factory=dict, kw_only=True, metadata={"serializable": True})
    session: Optional[requests.Session] = field(
        default=None, kw_only=True, repr=False, metadata={"serializable": False}
    )

    def search(self, query: str, **kwargs: Any) -> ListArtifact:
        q = (query or "").strip()[:MAX_QUERY_CHARS]
        if not q:
            raise _api.SpecStreamError("Send a search query of 1 to 2,000 characters.")
        body: dict[str, Any] = {"q": q, "num": max(1, min(int(self.results_count), MAX_RESULTS))}
        if self.speed:
            body["speed"] = self.speed
        if self.passages:
            body["passages"] = True
        body.update(self.params)
        body.update(kwargs)
        data = _api.call("/v1/web-search", body, api_key=self.api_key, base_url=self.base_url, session=self.session)
        items: list[dict[str, Any]] = []
        answer = data.get("answer")
        if self.include_answer and isinstance(answer, dict) and answer.get("value") not in (None, ""):
            items.append({"answer": answer["value"], "url": answer.get("page")})
        for source in data.get("sources") or []:
            if isinstance(source, dict) and source.get("url"):
                items.append({key: source[key] for key in SOURCE_FIELDS if source.get(key) not in (None, "")})
        return ListArtifact([JsonArtifact(item) for item in items])
