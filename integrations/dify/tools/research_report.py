import hashlib
import time
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.client import SpecStreamClient, error_message
from tools.research import ENDED, PRICE_CENTS, report_text, shown


class ResearchReportTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        question = str(tool_parameters.get("question") or "").strip()
        depth = str(tool_parameters.get("depth") or "standard").strip().lower()
        max_cents = round(float(tool_parameters.get("max_price_usd") or 0) * 100)
        wait = max(0, min(150, int(tool_parameters.get("wait_seconds") or 0)))
        if not question:
            yield self.create_text_message("Ask the question the report answers.")
            return
        if depth not in PRICE_CENTS:
            yield self.create_text_message("Set the depth to quick, standard or deep.")
            return
        price = PRICE_CENTS[depth]
        if price > max_cents:
            yield self.create_text_message(
                f"A {depth} report costs ${price / 100:.2f}, above the maximum of "
                f"${max_cents / 100:.2f}, so it did not start and cost nothing. Raise the maximum "
                "or choose a lower depth."
            )
            return

        client = SpecStreamClient(self.runtime.credentials["specstream_api_key"])
        # The same question at the same depth within the same hour gets the report it already
        # started, so a retried call never buys the report twice.
        hour = time.strftime("%Y-%m-%dT%H", time.gmtime())
        digest = hashlib.sha256(f"{question}|{depth}|{hour}".encode()).hexdigest()[:32]
        try:
            created = client.post_once(
                "/v1/research", {"input": question, "depth": depth}, f"dify-{digest}"
            )
            run = client.get(f"/v1/research/{created['id']}")
            deadline = time.monotonic() + wait
            while run.get("status") not in ENDED and time.monotonic() < deadline:
                time.sleep(5)
                run = client.get(f"/v1/research/{created['id']}")
        except requests.HTTPError as error:
            yield self.create_text_message(
                "SpecStream could not make this report: " + error_message(error)
            )
            return

        yield self.create_json_message(shown(run))
        yield self.create_text_message(report_text(run))
