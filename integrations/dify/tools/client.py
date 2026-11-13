from typing import Any

import requests

BASE_URL = "https://api.specstream.ai"
LIST_URL = "https://specstream.ai/workspace/collections/"
MONITORS_URL = "https://specstream.ai/workspace/schedules"

# Fields every row carries; a column with the same name is renamed so it can't overwrite them.
RESERVED = {"id", "list_id", "list_link", "position", "source_url", "checked_at"}


class SpecStreamClient:
    def __init__(self, api_key: str) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
                "User-Agent": "specstream-dify/0.6.0",
            }
        )

    def _send(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self.session.request(
            method, BASE_URL + path, json=body, headers=headers, timeout=60, allow_redirects=False
        )
        response.raise_for_status()
        return response.json()["data"]

    def get(self, path: str) -> dict[str, Any]:
        return self._send("GET", path)

    def get_bare(self, path: str, params: dict[str, str], signed: bool = True) -> dict[str, Any]:
        """A GET on an address whose body has no `data` envelope (the /v1/data/lists addresses).
        The catalog is public: unsigned, a key the API refuses cannot block a search that costs nothing."""
        # A None header drops the session's key from this one request.
        headers = None if signed else {"Authorization": None}
        response = self.session.get(
            BASE_URL + path, params=params, headers=headers, timeout=60, allow_redirects=False
        )
        response.raise_for_status()
        return response.json()

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._send("POST", path, body)

    def post_once(self, path: str, body: dict[str, Any], request_key: str) -> dict[str, Any]:
        """A POST the API runs once for this key: a retry with the same key and body gets the
        first call's answer."""
        return self._send("POST", path, body, {"Idempotency-Key": request_key})

    def recover(self, request_key: str) -> dict[str, Any] | None:
        try:
            data = self.get(f"/v1/capacity/requests/{request_key}")
        except requests.HTTPError:
            return None
        return data if data.get("find_id") else None


def error_message(error: requests.HTTPError) -> str:
    """The API's own words for a refused request, else its HTTP status."""
    response = error.response
    try:
        message = response.json()["error"]["message"] if response is not None else ""
    except (ValueError, KeyError, TypeError):
        message = ""
    status = response.status_code if response is not None else "no response"
    return str(message or f"HTTP {status}")


def list_link(list_id: str) -> str:
    return LIST_URL + list_id


def flatten(
    list_id: str, record: dict[str, Any], flat: dict[str, Any] | None = None
) -> dict[str, Any]:
    """One row as flat fields: each column's label holds what the list shows. The page of each value
    (<field>_source) and of the fact that put the row in the list (source_url, checked_at) come from
    the API's flat row, so every tool shows the same pages."""
    flat = flat or {}
    sources = {
        key: value
        for key, value in flat.items()
        if key.endswith("_source") and key[: -len("_source")] in flat
    }
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
    return [
        flatten(list_id, record, flat.get(f"{list_id}:{record.get('entity_id')}"))
        for record in page.get("rows") or []
    ]
