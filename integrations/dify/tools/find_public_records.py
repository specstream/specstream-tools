from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.client import SpecStreamClient, error_message

SITE = "https://specstream.ai"


class FindPublicRecordsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        words = str(tool_parameters.get("words") or "").strip()
        family = str(tool_parameters.get("family") or "").strip().lower()
        limit = max(1, min(100, int(tool_parameters.get("limit") or 20)))
        if len(words) > 200 or len(family) > 60:
            yield self.create_text_message("Send at most 200 characters of words and 60 of family.")
            return
        client = SpecStreamClient(self.runtime.credentials["specstream_api_key"])
        # Only a list with a date column can be read row by row, so only those are offered.
        params = {"q": words, "feeds": "true", "limit": str(limit)}
        if family:
            params["family"] = family
        try:
            found = client.get_bare("/v1/data/lists/search", params, signed=False)
        except requests.HTTPError as error:
            yield self.create_text_message(
                f"SpecStream could not search the lists: {error_message(error)}"
            )
            return
        lists = [
            {
                "page": item.get("page"),
                "title": item.get("title"),
                "family": item.get("family"),
                "number_of_rows": item.get("rows"),
                "key_column": item.get("key_column"),
                "list_link": SITE + str(item.get("page") or ""),
            }
            for item in found.get("lists") or []
        ]
        yield self.create_json_message({"lists": lists, "more": bool(found.get("next_cursor"))})
