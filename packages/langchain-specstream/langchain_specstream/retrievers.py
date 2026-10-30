"""A retriever whose documents are the rows of a SpecStream list."""

from __future__ import annotations

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.utils import secret_from_env
from pydantic import Field, SecretStr

from langchain_specstream._api import DEFAULT_BASE_URL, DEFAULT_WAIT_SECONDS, SpecStreamAPI, SpecStreamError

# Row fields that describe where the row came from rather than what it says.
_META = ("list_id", "list_link", "position", "source_url", "checked_at")


class SpecStreamRetriever(BaseRetriever):
    """Turn a plain-English request into documents, one per matching row, with its source in the metadata.

    Example:
        .. code-block:: python

            from langchain_specstream import SpecStreamRetriever

            retriever = SpecStreamRetriever(max_price_usd=3, max_results=25)
            docs = retriever.invoke("Breweries in Portland, Oregon that host events, with their website")
    """

    api_key: SecretStr = Field(default_factory=secret_from_env("SPECSTREAM_API_KEY"))
    base_url: str = DEFAULT_BASE_URL
    max_price_usd: float = Field(gt=0)
    """The most one list may cost, in US dollars. If the price is higher, the retriever raises and nothing runs."""
    max_results: int = Field(default=25, ge=1, le=1000)
    wait_seconds: float = DEFAULT_WAIT_SECONDS
    poll_interval: float = 3.0
    locale: str = "en-US"

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
        result = SpecStreamAPI(self.api_key.get_secret_value(), self.base_url).find_list(
            query,
            max_results=self.max_results,
            max_price_usd=self.max_price_usd,
            wait_seconds=self.wait_seconds,
            poll_interval=self.poll_interval,
            locale=self.locale,
            key_prefix="langchain-retriever",
        )
        if result["status"] in ("needs_edit", "over_maximum"):
            raise SpecStreamError(result["message"])
        documents = []
        for row in result["rows"]:
            # Each value's page (<field>_source) goes in the metadata beside the row's own source.
            sources = {key: value for key, value in row.items() if key.endswith("_source")}
            facts = "\n".join(
                f"{label}: {value}" for label, value in row.items() if label not in _META and label not in sources and value not in ("", None)
            )
            metadata = {key: row.get(key) for key in _META} | sources | {"request": result.get("request")}
            documents.append(Document(page_content=facts, metadata=metadata))
        return documents
