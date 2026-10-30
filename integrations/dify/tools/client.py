from typing import Any

import requests

BASE_URL = "https://api.specstream.ai"
LIST_URL = "https://specstream.ai/workspace/collections/"

# Fields every row carries; a column with the same name is renamed so it can't overwrite them.
RESERVED = {"id", "list_id", "list_link", "position", "source_url", "checked_at"}


class SpecStreamClient:
    def __init__(self, api_key: str) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json"}
        )

    def _send(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.request(
            method, BASE_URL + path, json=body, timeout=60, allow_redirects=False
        )
        response.raise_for_status()
        return response.json()["data"]

    def get(self, path: str) -> dict[str, Any]:
        return self._send("GET", path)

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._send("POST", path, body)

    def recover(self, request_key: str) -> dict[str, Any] | None:
        try:
            data = self.get(f"/v1/capacity/requests/{request_key}")
        except requests.HTTPError:
            return None
        return data if data.get("find_id") else None


def list_link(list_id: str) -> str:
    return LIST_URL + list_id


def flatten(list_id: str, record: dict[str, Any], flat: dict[str, Any] | None = None) -> dict[str, Any]:
    """One row as flat fields: each column's label holds what the list shows. The page of each value
    (<field>_source) and of the fact that put the row in the list (source_url, checked_at) come from
    the API's flat row, so every tool shows the same pages."""
    flat = flat or {}
    sources = {key: value for key, value in flat.items() if key.endswith("_source") and key[: -len("_source")] in flat}
    row: dict[str, Any] = {
        "id": f"{list_id}:{record.get('entity_id')}",
        "list_id": list_id,
        "list_link": list_link(list_id),
        "position": record.get("ordinal"),
    }
    for cell in record.get("cells") or []:
        label = str(cell.get("label") or cell.get("column_id") or "").strip()
        if not label:
            continue
        if label in RESERVED or label in sources:
            label = f"{label} (column)"
        value = cell.get("display")
        row[label] = value if value is not None else cell.get("value", "")
    row.update(sources)
    row["source_url"] = flat.get("source_url") or ""
    row["checked_at"] = flat.get("checked_at") or ""
    return row


def flatten_page(list_id: str, page: dict[str, Any]) -> list[dict[str, Any]]:
    """Every record of a rows page as a flat row, each with its own flat row's pages."""
    flat = {str(item.get("id")): item for item in page.get("flat_rows") or []}
    return [flatten(list_id, record, flat.get(f"{list_id}:{record.get('entity_id')}")) for record in page.get("rows") or []]
