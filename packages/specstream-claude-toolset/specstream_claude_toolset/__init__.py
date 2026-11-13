"""A SpecStream driver for the Claude SDK's browser toolset."""

from ._session import SpecStreamError
from .browser import SpecStreamBrowser

__all__ = ["SpecStreamBrowser", "SpecStreamError"]
__version__ = "0.1.0"
