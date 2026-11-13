from collections.abc import Generator
from typing import Any
from urllib.parse import urlencode

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.client import SpecStreamClient


class WebSearchTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        q = str(tool_parameters.get("q") or "").strip()
        passages = bool(tool_parameters.get("passages"))
        speed = str(tool_parameters.get("speed") or "").strip()
        if not q or len(q) > 2000:
            yield self.create_text_message("Provide a search query between 1 and 2,000 characters.")
            return
        if speed not in ("", "fast", "default"):
            yield self.create_text_message('Use a speed of "fast" or "default".')
            return

        client = SpecStreamClient(self.runtime.credentials["specstream_api_key"])
        params: dict[str, str] = {"q": q}
        if passages:
            params["passages"] = "true"
        if speed:
            params["speed"] = speed
        data = client.get(f"/v1/web-search?{urlencode(params)}")
        yield self.create_json_message(data)
