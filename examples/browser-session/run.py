"""Open a browser on SpecStream, read one page with it, and close it.

    export SPECSTREAM_API_KEY="ss_live_..."
    python run.py https://example.com

The script talks to the SpecStream MCP server with the standard library only. It calls
open_browser, browser_navigate, browser_snapshot, browser_read and close_browser, in that
order, and prints the page's title, its text and what the session cost.

A browser session is charged, so the script asks before it opens one. Pass --yes to skip
the question, for a key whose spending limit you set on purpose.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

MCP_URL = os.environ.get("SPECSTREAM_MCP_URL", "https://api.specstream.ai/mcp")
PROTOCOL = "2025-06-18"
PRICE = (
    "A browser session costs $0.10 an hour, charged by the second, "
    "plus $1 per 1,000 steps (0.1¢ a step). This run takes 3 steps."
)


class ToolError(RuntimeError):
    """A call to the MCP server answered with an error."""


class Mcp:
    """The few lines of MCP this example needs: JSON-RPC over one HTTP address."""

    def __init__(self, url: str, key: str) -> None:
        self.url = url
        self.headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "specstream-browser-session-example/1",
        }
        self.next_id = 0

    def rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params}
        request = urllib.request.Request(
            self.url, data=json.dumps(message).encode(), headers=self.headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=150) as answer:
                session = answer.headers.get("Mcp-Session-Id")
                kind = answer.headers.get("Content-Type", "")
                raw = answer.read().decode()
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:300]
            raise ToolError(f"{method}: HTTP {error.code} {detail}") from None
        except urllib.error.URLError as error:
            raise ToolError(f"{method}: no answer from {self.url} ({error.reason})") from None
        if session:
            self.headers["Mcp-Session-Id"] = session
        body = _from_stream(raw) if "text/event-stream" in kind else json.loads(raw)
        if "error" in body:
            raise ToolError(f"{method}: {body['error'].get('message', body['error'])}")
        result: dict[str, Any] = body["result"]
        return result

    def start(self) -> None:
        result = self.rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "specstream-browser-session-example", "version": "1"},
            },
        )
        self.headers["MCP-Protocol-Version"] = result.get("protocolVersion", PROTOCOL)

    def tool(self, name: str, **arguments: Any) -> dict[str, Any]:
        result = self.rpc("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise ToolError(f"{name}: {text_of(result) or result.get('structuredContent')}")
        return result


def _from_stream(raw: str) -> dict[str, Any]:
    """The JSON-RPC answer in a server-sent event stream."""
    for line in reversed(raw.splitlines()):
        if line.startswith("data:") and line[5:].strip():
            answer: dict[str, Any] = json.loads(line[5:])
            if "result" in answer or "error" in answer:
                return answer
    raise ToolError("the server's stream held no answer")


def text_of(result: dict[str, Any]) -> str:
    parts = result.get("content", [])
    return "\n".join(part["text"] for part in parts if part.get("type") == "text")


def approved(url: str) -> bool:
    print(f"This opens a real browser on SpecStream's server and reads {url}.", file=sys.stderr)
    print(PRICE, file=sys.stderr)
    print("Open it? [y/N] ", end="", file=sys.stderr, flush=True)
    return sys.stdin.readline().strip().lower() in {"y", "yes"}


def run(mcp: Mcp, url: str, timeout_s: int) -> dict[str, Any]:
    mcp.start()
    # The browser opens pages of this one host and nothing else.
    host = urlsplit(url).hostname
    opened = mcp.tool("open_browser", timeout_s=timeout_s, allowed_domains=[host])
    session_id = opened["structuredContent"]["id"]
    try:
        went = mcp.tool("browser_navigate", session_id=session_id, url=url)
        # The snapshot is the page as a tree of elements, each with a reference to act on.
        snapshot = text_of(mcp.tool("browser_snapshot", session_id=session_id))
        page = text_of(mcp.tool("browser_read", session_id=session_id, format="markdown"))
    finally:
        # An open session is charged until it times out, so it closes whatever happened.
        closed = mcp.tool("close_browser", session_id=session_id).get("structuredContent") or {}
    return {
        "session": session_id,
        "title": (went.get("structuredContent") or {}).get("title"),
        "snapshot_lines": len(snapshot.splitlines()),
        "text": page,
        "seconds": closed.get("seconds"),
        "steps": closed.get("actions"),
        "charged_usd": closed.get("charged_usd"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("url", nargs="?", default="https://example.com", help="the page to open")
    parser.add_argument("--yes", action="store_true", help="open the browser without asking")
    parser.add_argument(
        "--timeout", type=int, default=120, help="the most seconds the session runs"
    )
    args = parser.parse_args()

    key = os.environ.get("SPECSTREAM_API_KEY")
    if not key:
        print("Set SPECSTREAM_API_KEY (Agents & API in the SpecStream workspace).", file=sys.stderr)
        return 2
    target = urlsplit(args.url)
    if target.scheme not in {"http", "https"} or not target.hostname:
        print(f"Not a web address: {args.url}", file=sys.stderr)
        return 2
    if not args.yes and not approved(args.url):
        print("Nothing was opened.", file=sys.stderr)
        return 1
    try:
        result = run(Mcp(MCP_URL, key), args.url, args.timeout)
    except ToolError as error:
        print(error, file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
