"""A retriever whose nodes are the rows of a SpecStream list."""

from __future__ import annotations

from typing import Any, List, Optional

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode

from llama_index.tools.specstream._api import DEFAULT_BASE_URL, DEFAULT_WAIT_SECONDS, SpecStreamError
from llama_index.tools.specstream.base import MAX_RESULTS, _api

# Row fields that say where the row came from rather than what it says.
_META = ("list_id", "list_link", "position", "source_url", "checked_at")


class SpecStreamRetriever(BaseRetriever):
    """Turn a plain-English request into nodes, one per matching row, with its source in the metadata.

    Example:
        .. code-block:: python

            from llama_index.tools.specstream import SpecStreamRetriever

            retriever = SpecStreamRetriever(max_price_usd=3, max_results=25)
            nodes = retriever.retrieve("Breweries in Portland, Oregon that host events, with their website")
    """

    def __init__(
        self,
        *,
        max_price_usd: float,
        max_results: int = 25,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        wait_seconds: float = DEFAULT_WAIT_SECONDS,
        poll_interval: float = 3.0,
        locale: str = "en-US",
        **kwargs: Any,
    ) -> None:
        if not max_price_usd or float(max_price_usd) <= 0:
            raise ValueError("max_price_usd must be greater than 0.")
        if not 1 <= int(max_results) <= MAX_RESULTS:
            raise ValueError(f"max_results must be from 1 to {MAX_RESULTS}.")
        self.max_price_usd = float(max_price_usd)
        self.max_results = int(max_results)
        self.wait_seconds = wait_seconds
        self.poll_interval = poll_interval
        self.locale = locale
        self._client = _api(api_key, base_url)
        if not self._client.api_key.strip():
            raise ValueError("Set SPECSTREAM_API_KEY or pass api_key. Create a key under Agents & API in your SpecStream workspace.")
        super().__init__(**kwargs)

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        result = self._client.find_list(
            query_bundle.query_str,
            max_results=self.max_results,
            max_price_usd=self.max_price_usd,
            wait_seconds=self.wait_seconds,
            poll_interval=self.poll_interval,
            locale=self.locale,
            key_prefix="llamaindex-retriever",
        )
        if result["status"] in ("needs_edit", "over_maximum"):
            raise SpecStreamError(result["message"])
        nodes = []
        for row in result["rows"]:
            # Each value's page (<field>_source) goes in the metadata beside the row's own source.
            sources = {key: value for key, value in row.items() if key.endswith("_source")}
            facts = "\n".join(
                f"{label}: {value}" for label, value in row.items() if label not in _META and label not in sources and value not in ("", None)
            )
            node = TextNode(
                id_=f"{row['list_id']}:{row['position']}",
                text=facts,
                metadata={key: row.get(key) for key in _META} | sources | {"request": result.get("request")},
                # The model sees each row's facts and the page behind them; the bookkeeping stays out of its prompt.
                excluded_llm_metadata_keys=["list_id", "list_link", "position", "request"],
                excluded_embed_metadata_keys=list(_META) + list(sources) + ["request"],
            )
            nodes.append(NodeWithScore(node=node, score=None))
        return nodes
