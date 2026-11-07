"""SpecStream for CrewAI: the live web data engine, within a price you set."""

from crewai_specstream._api import SpecStreamError
from crewai_specstream.tools import (
    SpecStreamExtractPagesTool,
    SpecStreamFindListTool,
    SpecStreamGetListResultsTool,
    SpecStreamWebSearchTool,
    specstream_tools,
)

__all__ = [
    "SpecStreamError",
    "SpecStreamExtractPagesTool",
    "SpecStreamFindListTool",
    "SpecStreamGetListResultsTool",
    "SpecStreamWebSearchTool",
    "specstream_tools",
]
__version__ = "0.2.1"
