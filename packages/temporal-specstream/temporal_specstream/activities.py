"""SpecStream as Temporal Activities: search the live web and read pages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from temporalio import activity
from temporalio.exceptions import ApplicationError

from ._api import SpecStreamClient, SpecStreamError

WEB_SEARCH = "specstream.web_search"
EXTRACT = "specstream.extract"
ERROR_TYPE = "SpecStreamError"


@dataclass
class WebSearchInput:
    """What to search for.

    ``speed="fast"`` answers sooner at the fast price. ``passages=True`` adds the
    passages of each page that answer the query.
    """

    q: str
    speed: str = "default"
    passages: bool = False


@dataclass
class ExtractInput:
    """The pages to read: 1 to 20 URLs, as ``text`` or ``markdown``."""

    urls: list[str] = field(default_factory=list)
    format: str = "text"


def _failure(error: SpecStreamError) -> ApplicationError:
    """A refusal stops the Activity; what a later attempt can fix is left to the retry policy."""
    return ApplicationError(str(error), type=ERROR_TYPE, non_retryable=not error.retryable)


class SpecStreamActivities:
    """The Activities, bound to one client.

    A Workflow calls them by method reference or by name::

        await workflow.execute_activity(
            SpecStreamActivities.web_search,
            WebSearchInput(q="..."),
            start_to_close_timeout=timedelta(seconds=60),
        )
    """

    def __init__(self, client: SpecStreamClient) -> None:
        self._client = client

    @activity.defn(name=WEB_SEARCH)
    async def web_search(self, input: WebSearchInput) -> dict[str, Any]:
        """Search the live web. Returns the Search API's answer as it is."""
        try:
            return await self._client.web_search(input.q, speed=input.speed, passages=input.passages)
        except SpecStreamError as error:
            raise _failure(error) from None

    @activity.defn(name=EXTRACT)
    async def extract(self, input: ExtractInput) -> dict[str, Any]:
        """Read the text of up to 20 pages. Returns the Extract API's answer as it is."""
        try:
            return await self._client.extract(input.urls, format=input.format)
        except SpecStreamError as error:
            raise _failure(error) from None
