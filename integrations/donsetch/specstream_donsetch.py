#!/usr/bin/env python3
"""SpecStream search plugin for DonSeTch.

DonSeTch runs this file as a search plugin (format 1): it writes one JSON request to stdin
and reads one JSON reply from stdout. The adapter answers with the SpecStream Search API
(GET /v1/web-search). Python 3.9 or later, standard library only.

    donsetch keys add plugin specstream --cmd "python3 $HOME/specstream_donsetch.py" --test

The API key comes from SPECSTREAM_API_KEY, or from the file named by --key-file or
SPECSTREAM_API_KEY_FILE. It never goes into DonSeTch's config.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

VERSION = "1.0.0"
FORMAT = 1
BASE_URL = "https://api.specstream.ai"
# The Search API returns up to 10 results a search.
MAX_RESULTS = 10
SPEEDS = ("fast", "default")
# Time kept back from DonSeTch's deadline so the reply is written before the plugin is killed.
DEADLINE_MARGIN_S = 1.0
MIN_TIMEOUT_S = 1.0


class PluginError(Exception):
    def __init__(self, message: str, retryable: bool, kind: Optional[str] = None):
        super().__init__(message)
        self.retryable = retryable
        self.kind = kind

    def envelope(self) -> dict:
        reply: dict[str, Any] = {"format": FORMAT, "error": str(self), "retryable": self.retryable}
        if self.kind:
            reply["error_kind"] = self.kind
        return reply


def read_key(argv: list[str], env: dict) -> str:
    key = (env.get("SPECSTREAM_API_KEY") or "").strip()
    if key:
        return key
    path = option(argv, "--key-file") or env.get("SPECSTREAM_API_KEY_FILE") or ""
    if path:
        try:
            with open(os.path.expanduser(path), encoding="utf-8") as handle:
                key = handle.read().strip()
        except OSError as exc:
            raise PluginError(f"cannot read the key file {path}: {exc.strerror}", False, "invalid_key") from None
        if key:
            return key
    raise PluginError(
        "no SpecStream API key: set SPECSTREAM_API_KEY, or pass --key-file with the path of a file that holds it",
        False,
        "invalid_key",
    )


def option(argv: list[str], name: str) -> Optional[str]:
    for index, arg in enumerate(argv):
        if arg == name and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith(name + "="):
            return arg[len(name) + 1 :]
    return None


def parse_request(raw: str) -> dict:
    try:
        request = json.loads(raw)
    except ValueError:
        raise PluginError("stdin is not a JSON request", False) from None
    if not isinstance(request, dict):
        raise PluginError("stdin is not a JSON object", False)
    if request.get("format", FORMAT) != FORMAT:
        raise PluginError(f"unsupported format {request.get('format')!r} (this adapter speaks {FORMAT})", False)
    query = request.get("query")
    if not isinstance(query, str) or not query.strip():
        raise PluginError("the request has no query", False)
    return request


def search_params(request: dict, speed: str) -> dict:
    try:
        wanted = int(request.get("max_results") or MAX_RESULTS)
    except (TypeError, ValueError):
        wanted = MAX_RESULTS
    params = {"q": request["query"].strip()[:2000], "num": str(max(1, min(wanted, MAX_RESULTS)))}
    if speed != "default":
        params["speed"] = speed
    if request.get("intent") == "news":
        params["news"] = "true"
    return params


def timeout_for(request: dict) -> float:
    try:
        deadline = float(request.get("deadline_ms") or 30_000) / 1000
    except (TypeError, ValueError):
        deadline = 30.0
    return max(MIN_TIMEOUT_S, deadline - DEADLINE_MARGIN_S)


def http_get(url: str, key: str, timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": f"specstream-donsetch/{VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if exc.fp else b""


def error_for(status: int, body: bytes) -> PluginError:
    message, code = f"SpecStream answered HTTP {status}", None
    try:
        error = json.loads(body.decode("utf-8", "replace")).get("error") or {}
        message = error.get("message") or message
        code = error.get("code")
    except (ValueError, AttributeError):
        pass
    message = f"SpecStream: {message}"
    if status in (401, 403) or code in ("invalid_api_key", "missing_api_key"):
        return PluginError(message, False, "invalid_key")
    if status == 402 or code in ("insufficient_balance", "payment_required"):
        return PluginError(message, False, "credit_depleted")
    if status == 429 or code == "rate_limited":
        return PluginError(message, True, "rate_limited")
    if status >= 500:
        return PluginError(message, True, "server_error")
    return PluginError(message, False)


def to_results(data: dict, limit: int) -> list[dict]:
    sources = [s for s in data.get("sources") or [] if isinstance(s, dict)]
    results = []
    for source in sources:
        url = str(source.get("url") or "").strip()
        title = str(source.get("title") or source.get("site") or "").strip()
        if not url.startswith(("http://", "https://")) or not title:
            continue
        snippet = str(source.get("snippet") or source.get("excerpt") or "").strip()
        results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) == limit:
            break
    # The API returns sources best first; DonSeTch reads the score as 0..1.
    for rank, result in enumerate(results):
        result["score"] = round(max(0.05, 1.0 - rank * 0.05), 2)
    return results


def search(request: dict, key: str, speed: str, get: Callable[[str, str, float], tuple[int, bytes]]) -> dict:
    params = search_params(request, speed)
    url = f"{BASE_URL}/v1/web-search?{urllib.parse.urlencode(params)}"
    try:
        status, body = get(url, key, timeout_for(request))
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise PluginError(f"could not reach SpecStream: {reason}", True, "network_error") from None
    if status != 200:
        raise error_for(status, body)
    try:
        payload = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        raise PluginError("SpecStream sent a reply that is not JSON", True, "server_error") from None
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise PluginError("SpecStream sent a reply without data", True, "server_error")
    return {"format": FORMAT, "results": to_results(data, int(params["num"]))}


def main(argv: Optional[list[str]] = None, stdin=None, stdout=None, env=None, get=http_get) -> int:
    argv = sys.argv[1:] if argv is None else argv
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    env = os.environ if env is None else env
    if "--version" in argv:
        stdout.write(f"specstream-donsetch {VERSION}\n")
        return 0
    try:
        speed = (option(argv, "--speed") or env.get("SPECSTREAM_SPEED") or "fast").strip()
        if speed not in SPEEDS:
            raise PluginError(f"--speed must be one of {', '.join(SPEEDS)}", False)
        request = parse_request(stdin.read())
        key = read_key(argv, env)
        reply = search(request, key, speed, get)
    except PluginError as exc:
        reply = exc.envelope()
    stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
    stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
