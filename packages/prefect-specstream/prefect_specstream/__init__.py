"""SpecStream as Prefect tasks and a flow: Search API, Extract API and research reports, with a credentials block."""

from prefect_specstream._version import __version__
from prefect_specstream.credentials import SpecStreamClient, SpecStreamCredentials, SpecStreamError
from prefect_specstream.research import get_research, research_report, start_research, wait_for_research
from prefect_specstream.tasks import extract_pages, web_search

__all__ = [
    "SpecStreamClient",
    "SpecStreamCredentials",
    "SpecStreamError",
    "__version__",
    "extract_pages",
    "get_research",
    "research_report",
    "start_research",
    "wait_for_research",
    "web_search",
]
