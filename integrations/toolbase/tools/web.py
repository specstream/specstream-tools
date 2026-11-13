"""SpecStream tools: the Search API and the Extract API.

``api_key`` and ``api_base`` are state fields. Toolbase fills them from the user's
configuration (~/.toolbase/config/specstream.yaml), so the model never sees the key.
"""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from orchestral import define_tool

DEFAULT_BASE = "https://api.specstream.ai"
CLIENT = "specstream-toolbase/0.1"
KEY_HELP = (
    "Set the SpecStream API key: toolbase config set specstream api_key <key>. "
    "Get a key at https://specstream.ai/workspace?utm_source=toolbase"
)


def _error(message: str) -> str:
    return json.dumps({"status": "error", "message": message})


def _call(method: str, path: str, api_key: str, api_base: str, body: dict | None = None) -> str:
    key = (api_key or "").strip()
    if not key:
        return _error(KEY_HELP)
    base = (api_base or DEFAULT_BASE).strip().rstrip("/")
    headers = {"Authorization": "Bearer " + key, "Accept": "application/json", "User-Agent": CLIENT}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(base + path, data=data, method=method, headers=headers)
    try:
        with urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 401:
            return _error("SpecStream did not accept the API key. " + KEY_HELP)
        if exc.code == 402:
            return _error("The SpecStream balance is empty. Add credit at https://specstream.ai/workspace")
        return _error("SpecStream answered HTTP %d" % exc.code)
    except (URLError, OSError, ValueError):
        return _error("SpecStream could not be reached")
    inner = payload.get("data") if isinstance(payload, dict) else None
    return json.dumps({"status": "ok", "data": inner if inner is not None else payload}, ensure_ascii=False)


@define_tool(state=["api_key", "api_base"])
def web_search(
    query: str,
    fast: bool = False,
    passages: bool = False,
    api_key: str = "",
    api_base: str = DEFAULT_BASE,
) -> str:
    """
    Search the live web and get an answer with its source, matching rows and ranked sources.

    Calls the SpecStream Search API (GET /v1/web-search).
    A default search costs $5 per 1,000 searches of up to 10 results;
    a fast search costs $1 per 1,000.

    Args:
        query: The search question or request in everyday words (1 to 2,000 characters)
        fast: True for the fast tier: the first ranked results, sooner and at the lower price
        passages: True to include the main text passages of the top matching pages

    Returns:
        JSON string with status "ok" and data (answer, rows, sources), or status "error" and a message
    """
    text = (query or "").strip()
    if not text or len(text) > 2000:
        return _error("Provide a search query between 1 and 2,000 characters.")
    params = {"q": text}
    if fast:
        params["speed"] = "fast"
    if passages:
        params["passages"] = "true"
    return _call("GET", "/v1/web-search?" + urlencode(params), api_key, api_base)


@define_tool(state=["api_key", "api_base"])
def read_pages(
    urls: str,
    format: str = "markdown",
    api_key: str = "",
    api_base: str = DEFAULT_BASE,
) -> str:
    """
    Read the main text, title and published date of 1 to 20 web pages, PDFs or documents.

    Calls the SpecStream Extract API (POST /v1/extract). It costs $0.80 per 1,000 pages,
    and a page with no text is not charged.

    Args:
        urls: 1 to 20 http or https URLs separated by newlines or commas
        format: Output format, "markdown" or "text"

    Returns:
        JSON string with status "ok" and data (one result per page), or status "error" and a message
    """
    cleaned = [part.strip() for part in re.split(r"[\n,]+", urls or "") if part.strip()]
    if not 1 <= len(cleaned) <= 20 or not all(re.match(r"https?://", url) for url in cleaned):
        return _error("Provide 1 to 20 http or https URLs.")
    if format not in ("markdown", "text"):
        return _error('Use the format "markdown" or "text".')
    return _call("POST", "/v1/extract", api_key, api_base, {"urls": cleaned, "format": format})
