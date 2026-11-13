"""The SpecStream resource: the Search API, the Extract API and Deep Search for Dagster assets and ops."""

from __future__ import annotations

import hashlib
from typing import Any

from dagster import ConfigurableResource, Failure, MetadataValue, RetryRequested
from pydantic import Field

from dagster_specstream._api import DEFAULT_BASE_URL, DEFAULT_WAIT_SECONDS, FINISHED, STOPPED, SpecStreamAPI


def run_key(context: Any, name: str | None = None) -> str:
    """An idempotency key for a Deep Search list started from this step.

    It stays the same when the step is retried and when the run is re-executed (it uses the first
    run's id), so the list is bought once. A partitioned asset gets one key per partition.
    """
    run = getattr(context, "run", None)
    run_id = (getattr(run, "root_run_id", None) or getattr(run, "run_id", None) or "").strip()
    if not run_id:
        raise ValueError("Give deep_search an idempotency_key: this context has no run id.")
    step = name
    if step is None:
        try:
            step = context.asset_key.to_user_string()
        except Exception:  # an op, or an asset with more than one output
            step = getattr(getattr(context, "op_def", None), "name", None) or "step"
    partition = ""
    if getattr(context, "has_partition_key", False):
        partition = str(context.partition_key)
    digest = hashlib.sha256(f"{run_id}|{step}|{partition}".encode()).hexdigest()[:32]
    return f"dagster-{digest}"


class SpecStreamResource(ConfigurableResource):
    """Calls the SpecStream API with your key.

    Example:
        resources={"specstream": SpecStreamResource(api_key=EnvVar("SPECSTREAM_API_KEY"))}
    """

    api_key: str = Field(description="Your SpecStream API key (Agents & API in your SpecStream workspace).")
    base_url: str = Field(default=DEFAULT_BASE_URL, description="The API address. Change it only for a proxy.")
    timeout: float = Field(default=150.0, description="Seconds to wait for one API call.")

    def get_client(self) -> SpecStreamAPI:
        return SpecStreamAPI(api_key=self.api_key, base_url=self.base_url or DEFAULT_BASE_URL, timeout=self.timeout)

    def web_search(
        self,
        query: str,
        *,
        passages: bool = False,
        speed: str = "default",
        num: int | None = None,
        news: bool = False,
        country: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Search API, GET /v1/web-search: the answer, rows and ranked sources.

        $5 per 1,000 searches of up to 10 results; $1 per 1,000 with speed="fast".
        """
        return self.get_client().web_search(
            query, passages=passages, speed=speed, num=num, news=news, country=country, language=language
        )

    def extract_pages(self, urls: str | list[str], *, format: str = "markdown") -> dict[str, Any]:
        """Extract API, POST /v1/extract: the main text of 1 to 20 pages.

        $0.80 per 1,000 pages; a page with no text is not charged.
        """
        if isinstance(urls, str):
            urls = [urls]
        return self.get_client().extract_pages(list(urls), format=format)

    def find_list(self, request: str, **kwargs: Any) -> dict[str, Any]:
        """Deep Search without Dagster's handling: returns every status, including needs_edit and over_maximum."""
        return self.get_client().find_list(request, **kwargs)

    def deep_search(
        self,
        context: Any,
        request: str,
        *,
        max_results: int,
        max_price_usd: float,
        idempotency_key: str | None = None,
        wait_seconds: float = DEFAULT_WAIT_SECONDS,
        poll_interval: float = 5.0,
        locale: str = "en-US",
        retries_while_running: int = 3,
        seconds_between_retries: float = 60.0,
    ) -> dict[str, Any]:
        """Deep Search: a list built from the live web, in structured rows. 5 cents, 15 cents or $1 per delivered row.

        Nothing runs when the quoted maximum is above max_price_usd: the step fails with the price.
        A retry or a re-execution of the same step continues the same list and never buys it twice.
        When the list is still running after wait_seconds, the step asks Dagster to retry it
        (retries_while_running times), and the retry picks the list up.
        """
        key = idempotency_key or run_key(context)
        result = self.get_client().find_list(
            request,
            max_results=max_results,
            max_price_usd=max_price_usd,
            idempotency_key=key,
            wait_seconds=wait_seconds,
            poll_interval=poll_interval,
            locale=locale,
        )
        status = result.get("status")
        if status in {"needs_edit", "over_maximum"}:
            raise Failure(description=result["message"], allow_retries=False)
        link = result.get("list_link") or ""
        if status in STOPPED:
            raise Failure(
                description=f"The list {link} stopped with status {status}.",
                metadata={"list_link": MetadataValue.url(link)} if link else None,
            )
        if status not in FINISHED:
            raise RetryRequested(max_retries=retries_while_running, seconds_to_wait=seconds_between_retries)
        log = getattr(context, "log", None)
        if log is not None:
            log.info(f"SpecStream list {result.get('list_id')}: {result.get('row_count')} rows ({status}) {link}")
        return result
