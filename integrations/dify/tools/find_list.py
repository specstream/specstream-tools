import hashlib
import time
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.client import SpecStreamClient, flatten_page, list_link

FINISHED = {"completed", "partial", "failed", "canceled", "expired"}


class FindListTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        request = str(tool_parameters.get("request") or "").strip()
        count = int(tool_parameters.get("count") or 25)
        max_cents = round(float(tool_parameters.get("max_price_usd") or 0) * 100)
        wait = max(0, min(150, int(tool_parameters.get("wait_seconds") or 0)))
        if not request:
            yield self.create_text_message("Describe the list to find.")
            return
        if count < 1 or max_cents <= 0:
            yield self.create_text_message("Set at least 1 result and a maximum price above 0.")
            return

        client = SpecStreamClient(self.runtime.credentials["specstream_api_key"])
        # The same request within the same hour gets the list it already started, so a retried
        # call never buys the list twice.
        hour = time.strftime("%Y-%m-%dT%H", time.gmtime())
        digest = hashlib.sha256(f"{request}|{count}|{max_cents}|{hour}".encode()).hexdigest()[:32]
        request_key = f"dify-{digest}"

        run = client.recover(request_key)
        if run is None:
            reading = client.post("/v1/parse", {"q": request, "locale": "en-US"})
            if reading.get("status") != "runnable":
                read_as = reading.get("canonical_sentence") or request
                yield self.create_text_message(
                    f'SpecStream needs a clearer request before it can price it. It read: "{read_as}". '
                    "Add the place or what every row must meet."
                )
                return
            quote = client.post(
                "/v1/capacity/quotes",
                {"ast_hash": reading["ast_hash"], "operation": "find", "requested_units": count},
            )
            if quote["maximum_cents"] > max_cents:
                yield self.create_text_message(
                    f"This list can cost up to ${quote['maximum_cents'] / 100:.2f}, above the maximum of "
                    f"${max_cents / 100:.2f}, so it did not start and cost nothing. Raise the maximum or ask for fewer results."
                )
                return
            run = client.post(
                "/v1/capacity/executions",
                {
                    "quote_id": quote["quote_id"],
                    "quote_hash": quote["quote_hash"],
                    "confirm_max_cents": quote["maximum_cents"],
                    "idempotency_key": request_key,
                },
            )

        list_id = run["find_id"]
        page = client.get(f"/v1/finds/{list_id}/rows")
        deadline = time.monotonic() + wait
        while page.get("status") not in FINISHED and time.monotonic() < deadline:
            time.sleep(5)
            page = client.get(f"/v1/finds/{list_id}/rows")

        yield self.create_json_message(
            {
                "list_id": list_id,
                "status": page.get("status"),
                "number_of_rows": page.get("accepted_count", 0),
                "list_link": list_link(list_id),
                "rows": flatten_page(list_id, page),
            }
        )
