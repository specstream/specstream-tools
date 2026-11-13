"""SpecStream for Dagster: a resource for the Search API, the Extract API and Deep Search."""

from dagster_specstream._api import SpecStreamAPI, SpecStreamError
from dagster_specstream.resource import SpecStreamResource, run_key

__version__ = "0.1.0"

__all__ = ["SpecStreamAPI", "SpecStreamError", "SpecStreamResource", "__version__", "run_key"]
