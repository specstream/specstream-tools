from collections.abc import Generator
from datetime import date
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.client import SpecStreamClient, error_message

SITE = "https://specstream.ai"


def refusal(error: requests.HTTPError) -> str:
    """The API's reason; when the maximum pays for no row, the rows waiting and their price."""
    response = error.response
    try:
        body = response.json()["error"] if response is not None else {}
    except (ValueError, KeyError, TypeError):
        body = {}
    details = (body.get("details") or {}) if isinstance(body, dict) else {}
    if (
        isinstance(body, dict)
        and body.get("code") == "payment_required"
        and "price_cents" in details
    ):
        waiting = details.get("new_rows_waiting", details.get("rows_available", 0))
        price = details.get("price_cents_all", details["price_cents"])
        return (
            f"{waiting} new rows wait and cost ${price / 100:.2f}. Nothing was charged. "
            "Raise the maximum price per call to get them."
        )
    return f"SpecStream did not return the rows: {error_message(error)}"


class GetPublicRecordsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        page = str(tool_parameters.get("page") or "").strip()
        if page.startswith(SITE + "/"):
            page = page[len(SITE) :]
        since = str(tool_parameters.get("since") or "").strip()
        cursor = str(tool_parameters.get("cursor") or "").strip()
        limit = max(1, min(1000, int(tool_parameters.get("limit") or 100)))
        max_cents = round(float(tool_parameters.get("max_price_usd") or 0) * 100)
        if not page.startswith("/data/"):
            yield self.create_text_message(
                "Pass the list's page from Find Public Records. It starts with /data/."
            )
            return
        if since:
            try:
                date.fromisoformat(since)
            except ValueError:
                yield self.create_text_message("Send since as a date: YYYY-MM-DD.")
                return
        if max_cents < 0:
            yield self.create_text_message("Set a maximum price of 0 or more.")
            return
        params = {"page": page, "limit": str(limit), "max_cents": str(max_cents)}
        if since:
            params["since"] = since
        if cursor:
            params["cursor"] = cursor
        if tool_parameters.get("new_only"):
            params["new_only"] = "true"
        client = SpecStreamClient(self.runtime.credentials["specstream_api_key"])
        try:
            data = client.get_bare("/v1/data/lists/rows", params)
        except requests.HTTPError as error:
            yield self.create_text_message(refusal(error))
            return
        reply: dict[str, Any] = {
            "page": data.get("page"),
            "title": data.get("title"),
            "list_link": SITE + str(data.get("page") or page),
            "columns": data.get("columns") or [],
            "date_column": data.get("date_column"),
            "rows": data.get("rows") or [],
            "charged_rows": data.get("charged_rows", 0),
            "price_usd": round((data.get("price_cents") or 0) / 100, 2),
            "next_cursor": data.get("next_cursor"),
        }
        for name in ("rows_available", "rows_waiting", "new_rows_waiting"):
            if name in data:
                reply[name] = data[name]
        if "price_cents_all" in data:
            reply["price_usd_all_waiting"] = round(data["price_cents_all"] / 100, 2)
        if "balance_cents" in data:
            reply["balance_usd"] = round(data["balance_cents"] / 100, 2)
        yield self.create_json_message(reply)
