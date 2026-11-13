"""SpecStream for Temporal: live web search and page reading as durable Activities."""

from ._api import DEFAULT_BASE_URL, SpecStreamClient, SpecStreamError
from .activities import EXTRACT, WEB_SEARCH, ExtractInput, SpecStreamActivities, WebSearchInput
from .plugin import PLUGIN_NAME, SpecStreamPlugin

__all__ = [
    "DEFAULT_BASE_URL",
    "EXTRACT",
    "PLUGIN_NAME",
    "WEB_SEARCH",
    "ExtractInput",
    "SpecStreamActivities",
    "SpecStreamClient",
    "SpecStreamError",
    "SpecStreamPlugin",
    "WebSearchInput",
]
__version__ = "0.1.0"
