"""The SpecStream hook: one Airflow connection (conn type "specstream") holds the API key."""

from __future__ import annotations

from typing import Any

try:  # Airflow 3.1 and later
    from airflow.sdk import BaseHook
except ImportError:  # Airflow 2.9 to 3.0
    from airflow.hooks.base import BaseHook

from specstream_provider._api import DEFAULT_BASE_URL, DEFAULT_WAIT_SECONDS, SpecStreamAPI


class SpecStreamHook(BaseHook):
    """Calls the SpecStream API with the key in an Airflow connection.

    The connection's password field holds the API key (Agents & API in your SpecStream workspace).
    The host field is optional and replaces https://api.specstream.ai.
    """

    conn_name_attr = "specstream_conn_id"
    default_conn_name = "specstream_default"
    conn_type = "specstream"
    hook_name = "SpecStream"

    def __init__(self, specstream_conn_id: str = default_conn_name, timeout: float = 150.0, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.specstream_conn_id = specstream_conn_id
        self.timeout = timeout
        self._api: SpecStreamAPI | None = None

    @classmethod
    def get_ui_field_behaviour(cls) -> dict[str, Any]:
        return {
            "hidden_fields": ["schema", "login", "port", "extra"],
            "relabeling": {"password": "API key", "host": "API address (optional)"},
            "placeholders": {"host": DEFAULT_BASE_URL},
        }

    def get_conn(self) -> SpecStreamAPI:
        if self._api is None:
            conn = self.get_connection(self.specstream_conn_id)
            host = (conn.host or "").strip()
            if host and "://" not in host:
                host = f"https://{host}"
            self._api = SpecStreamAPI(api_key=conn.password or "", base_url=host or DEFAULT_BASE_URL, timeout=self.timeout)
        return self._api

    def test_connection(self) -> tuple[bool, str]:
        """Checks the key with a fast search, which costs $0.001."""
        try:
            self.get_conn().web_search("SpecStream", speed="fast", num=1)
        except Exception as error:  # the UI shows the message
            return False, str(error)
        return True, "Connection successfully tested"

    def web_search(self, q: str, **kwargs: Any) -> dict[str, Any]:
        return self.get_conn().web_search(q, **kwargs)

    def extract_pages(self, urls: list[str], *, format: str = "markdown") -> dict[str, Any]:
        return self.get_conn().extract_pages(urls, format=format)

    def find_list(
        self,
        request: str,
        *,
        max_results: int,
        max_price_usd: float,
        idempotency_key: str,
        wait_seconds: float = DEFAULT_WAIT_SECONDS,
        poll_interval: float = 5.0,
        locale: str = "en-US",
    ) -> dict[str, Any]:
        return self.get_conn().find_list(
            request,
            max_results=max_results,
            max_price_usd=max_price_usd,
            idempotency_key=idempotency_key,
            wait_seconds=wait_seconds,
            poll_interval=poll_interval,
            locale=locale,
        )
