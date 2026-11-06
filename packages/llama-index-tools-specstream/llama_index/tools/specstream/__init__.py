"""SpecStream for LlamaIndex: the live web data engine, with the source URL and read time on every value, within a price set in code."""

from llama_index.tools.specstream._api import SpecStreamError
from llama_index.tools.specstream.base import SpecStreamToolSpec
from llama_index.tools.specstream.retriever import SpecStreamRetriever

__all__ = ["SpecStreamError", "SpecStreamRetriever", "SpecStreamToolSpec"]
__version__ = "0.2.0"
