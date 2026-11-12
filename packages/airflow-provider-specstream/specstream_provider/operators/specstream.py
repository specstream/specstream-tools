"""SpecStream operators: Search API, Extract API and Deep Search. Each pushes its result to XCom."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from functools import cached_property
from typing import Any

try:  # Airflow 3
    from airflow.sdk import BaseOperator
except ImportError:  # Airflow 2.9 and later 2.x
    from airflow.models import BaseOperator

from airflow.exceptions import AirflowException

from specstream_provider._api import DEFAULT_WAIT_SECONDS, FINISHED, STOPPED, SpecStreamError
from specstream_provider.hooks.specstream import SpecStreamHook


class _SpecStreamOperator(BaseOperator):
    def __init__(self, *, specstream_conn_id: str = SpecStreamHook.default_conn_name, timeout: float = 150.0, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.specstream_conn_id = specstream_conn_id
        self.timeout = timeout

    @cached_property
    def hook(self) -> SpecStreamHook:
        return SpecStreamHook(specstream_conn_id=self.specstream_conn_id, timeout=self.timeout)

    def _call(self, fn, *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except (SpecStreamError, ValueError) as error:
            raise AirflowException(str(error)) from None


class SpecStreamSearchOperator(_SpecStreamOperator):
    """Searches the live web with GET /v1/web-search and returns the answer, rows and ranked sources.

    $5 per 1,000 searches of up to 10 results; speed="fast" gives the results alone in about a second
    for $1 per 1,000.
    """

    template_fields: Sequence[str] = ("query", "country", "language")
    ui_color = "#e8f1fb"

    def __init__(
        self,
        *,
        query: str,
        passages: bool = False,
        speed: str = "default",
        num: int | None = None,
        news: bool = False,
        country: str | None = None,
        language: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.query = query
        self.passages = passages
        self.speed = speed
        self.num = num
        self.news = news
        self.country = country
        self.language = language

    def execute(self, context: Any) -> dict[str, Any]:
        return self._call(
            self.hook.web_search,
            self.query,
            passages=self.passages,
            speed=self.speed,
            num=self.num,
            news=self.news,
            country=self.country,
            language=self.language,
        )


class SpecStreamExtractOperator(_SpecStreamOperator):
    """Reads the main text, title and published date of 1 to 20 URLs with POST /v1/extract.

    $0.80 per 1,000 pages; a page with no text is not charged.
    """

    template_fields: Sequence[str] = ("urls",)
    ui_color = "#e8f1fb"

    def __init__(self, *, urls: list[str] | str, format: str = "markdown", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.urls = urls
        self.format = format

    def execute(self, context: Any) -> dict[str, Any]:
        urls = [self.urls] if isinstance(self.urls, str) else list(self.urls or [])
        return self._call(self.hook.extract_pages, urls, format=self.format)


def _run_key(context: Any, request: str, max_results: int, max_cents: int) -> str:
    """One key per task instance and request: a retry of the same run continues the same list."""
    ti = context.get("ti") or context.get("task_instance")
    parts = [
        str(getattr(ti, "dag_id", "") or ""),
        str(getattr(ti, "task_id", "") or ""),
        str(getattr(ti, "run_id", "") or context.get("run_id") or ""),
        str(getattr(ti, "map_index", -1)),
        request,
        str(max_results),
        str(max_cents),
    ]
    return "airflow-" + hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


class SpecStreamDeepSearchOperator(_SpecStreamOperator):
    """Builds a list of every match on the live web as structured rows (Deep Search).

    The run starts only when its quoted maximum is at or below ``max_price_usd``; otherwise nothing
    runs and the task fails. Each delivered row is charged 5 cents, 15 cents or $1 depending on
    what it needs. A retry of the same task instance continues the same list and never buys it twice.
    Returns ``list_id``, ``status``, ``list_link``, ``row_count`` and ``rows``.
    """

    template_fields: Sequence[str] = ("request",)
    ui_color = "#e8f1fb"

    def __init__(
        self,
        *,
        request: str,
        max_price_usd: float,
        max_results: int = 25,
        wait_seconds: float = DEFAULT_WAIT_SECONDS,
        poll_interval: float = 5.0,
        locale: str = "en-US",
        fail_if_unfinished: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.request = request
        self.max_price_usd = max_price_usd
        self.max_results = max_results
        self.wait_seconds = wait_seconds
        self.poll_interval = poll_interval
        self.locale = locale
        self.fail_if_unfinished = fail_if_unfinished

    def execute(self, context: Any) -> dict[str, Any]:
        request = (self.request or "").strip()
        key = _run_key(context, request, int(self.max_results), round(float(self.max_price_usd) * 100))
        result = self._call(
            self.hook.find_list,
            request,
            max_results=self.max_results,
            max_price_usd=self.max_price_usd,
            idempotency_key=key,
            wait_seconds=self.wait_seconds,
            poll_interval=self.poll_interval,
            locale=self.locale,
        )
        status = result.get("status")
        if status in {"needs_edit", "over_maximum"}:
            raise AirflowException(result["message"])
        if status in STOPPED:
            raise AirflowException(f"The list {result.get('list_link')} stopped with status {status}.")
        if status not in FINISHED and self.fail_if_unfinished:
            raise AirflowException(f"The list {result.get('list_link')} is still running; a retry of this task continues it.")
        self.log.info("SpecStream list %s: %s rows (%s)", result.get("list_id"), result.get("row_count"), status)
        return result
