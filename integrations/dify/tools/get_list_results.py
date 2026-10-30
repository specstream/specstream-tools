from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.client import SpecStreamClient, flatten_page, list_link


class GetListResultsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        list_id = str(tool_parameters.get("list_id") or "").strip()
        if not list_id.startswith("fnd_"):
            yield self.create_text_message("Pass the list ID from Find a List. It starts with fnd_.")
            return
        client = SpecStreamClient(self.runtime.credentials["specstream_api_key"])
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
