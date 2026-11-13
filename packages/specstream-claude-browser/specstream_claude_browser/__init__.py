"""A driver for the browser toolset of the Claude SDK that runs on SpecStream browser sessions."""

from specstream_claude_browser._client import BASE_URL, SessionClient, SpecStreamError
from specstream_claude_browser._driver import TAB_ID, SpecStreamBrowser

__all__ = ["BASE_URL", "TAB_ID", "SessionClient", "SpecStreamBrowser", "SpecStreamError"]
__version__ = "0.1.0"
