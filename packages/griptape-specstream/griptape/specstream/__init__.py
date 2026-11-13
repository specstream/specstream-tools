"""SpecStream drivers for Griptape: live web search and page reading."""

from griptape.specstream._api import SpecStreamError
from griptape.specstream.drivers.web_scraper.specstream_web_scraper_driver import SpecStreamWebScraperDriver
from griptape.specstream.drivers.web_search.specstream_web_search_driver import SpecStreamWebSearchDriver

__version__ = "0.1.0"

__all__ = ["SpecStreamError", "SpecStreamWebScraperDriver", "SpecStreamWebSearchDriver"]
