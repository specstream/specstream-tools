from collections.abc import Generator
import re
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.client import SpecStreamClient


class ExtractPagesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        raw_urls = str(tool_parameters.get("urls") or "")
        urls = [u.strip() for u in re.split(r"[\r\n,]+", raw_urls) if u.strip()]
        if not 1 <= len(urls) <= 20:
            yield self.create_text_message("Provide 1 to 20 http or https URLs.")
            return
        fmt = "text" if str(tool_parameters.get("format") or "markdown").strip() == "text" else "markdown"

        client = SpecStreamClient(self.runtime.credentials["specstream_api_key"])
        data = client.post("/v1/extract", {"urls": urls, "format": fmt})
        yield self.create_json_message(data)
