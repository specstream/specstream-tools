#
# Copyright (c) 2026, SpecStream SAS
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""SpecStream live web search, page reading, Deep Search lists and research reports for Pipecat."""

from pipecat_specstream._api import SpecStreamClient, SpecStreamError
from pipecat_specstream.search import SpecStreamDeepSearch, SpecStreamResearch

__all__ = ["SpecStreamClient", "SpecStreamDeepSearch", "SpecStreamError", "SpecStreamResearch"]
__version__ = "0.2.0"
