"""SpecStream for LangChain: the live web data engine, within a price you set."""

from langchain_specstream._api import SpecStreamError
from langchain_specstream.browser import (
    SpecStreamBrowserAction,
    SpecStreamBrowserClick,
    SpecStreamBrowserNavigate,
    SpecStreamBrowserRead,
    SpecStreamBrowserSnapshot,
    SpecStreamBrowserType,
    SpecStreamCloseBrowser,
    SpecStreamOpenBrowser,
    specstream_browser_tools,
)
from langchain_specstream.research import SpecStreamGetResearch, SpecStreamResearch
from langchain_specstream.retrievers import SpecStreamRetriever
from langchain_specstream.tools import (
    SpecStreamExtractPages,
    SpecStreamFindList,
    SpecStreamGetListResults,
    SpecStreamWebSearch,
    specstream_tools,
)

__all__ = [
    "SpecStreamBrowserAction",
    "SpecStreamBrowserClick",
    "SpecStreamBrowserNavigate",
    "SpecStreamBrowserRead",
    "SpecStreamBrowserSnapshot",
    "SpecStreamBrowserType",
    "SpecStreamCloseBrowser",
    "SpecStreamError",
    "SpecStreamExtractPages",
    "SpecStreamFindList",
    "SpecStreamGetListResults",
    "SpecStreamGetResearch",
    "SpecStreamOpenBrowser",
    "SpecStreamResearch",
    "SpecStreamRetriever",
    "SpecStreamWebSearch",
    "specstream_browser_tools",
    "specstream_tools",
]
__version__ = "0.4.0"
