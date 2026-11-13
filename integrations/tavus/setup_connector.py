"""Create a Tavus MCP connector for the SpecStream tool server and attach it to a PAL.

Tavus API (https://docs.tavus.io/sections/conversational-video-interface/pal/mcp-connectors):
  POST  /v2/connectors                     create the connector
  POST  /v2/connectors/{id}/runtime_check  check that a call reaches the server
  POST  /v2/pals                           create a PAL with layers.mcp.connectors
  PATCH /v2/pals/{id}                      JSON Patch to attach to an existing PAL

Keys come from the environment only and are never printed:
  TAVUS_API_KEY       the Tavus account key (x-api-key)
  SPECSTREAM_API_KEY  sent by Tavus to SpecStream as a bearer token; without it the
                      connector uses OAuth and the answer carries an authorize_url

Usage:
  python setup_connector.py --face-id <face>          # new test PAL
  python setup_connector.py --pal-id <pal>            # attach to an existing PAL
  python setup_connector.py --face-id <face> --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Callable

TAVUS_API = "https://tavusapi.com"
SPECSTREAM_MCP_URL = "https://api.specstream.ai/mcp"
CONNECTOR_NAME = "SpecStream"
PAL_NAME = "SpecStream web data test"
SYSTEM_PROMPT = (
    "You help people get data from the live web. When someone asks for a list, "
    "a fact or the text of a page, use the SpecStream tools and say where each "
    "value comes from. Ask before any step that costs money."
)
SECRET_FIELDS = {"token", "value", "password", "client_secret"}

Sender = Callable[[str, str, Any], dict]


def auth_config(specstream_key: str | None) -> dict:
    if specstream_key:
        return {"type": "bearer", "token": specstream_key}
    return {"type": "oauth2"}


def connector_body(specstream_key: str | None, server_url: str = SPECSTREAM_MCP_URL) -> dict:
    return {"name": CONNECTOR_NAME, "server_url": server_url, "auth_config": auth_config(specstream_key)}


def pal_body(connector_id: str, face_id: str) -> dict:
    return {
        "pal_name": PAL_NAME,
        "system_prompt": SYSTEM_PROMPT,
        "pipeline_mode": "full",
        "default_face_id": face_id,
        "layers": {"mcp": {"connectors": [connector_id]}},
    }


def attach_patch(connector_id: str, existing: list[str] | None) -> list[dict]:
    """JSON Patch for an existing PAL: add when layers.mcp is unset, replace otherwise."""
    if existing is None:
        return [{"op": "add", "path": "/layers/mcp/connectors", "value": [connector_id]}]
    merged = list(existing) if connector_id in existing else [*existing, connector_id]
    return [{"op": "replace", "path": "/layers/mcp/connectors", "value": merged}]


def redact(body: Any) -> Any:
    if isinstance(body, dict):
        return {k: ("***" if k in SECRET_FIELDS else redact(v)) for k, v in body.items()}
    if isinstance(body, list):
        return [redact(v) for v in body]
    return body


def http_sender(tavus_key: str, base: str = TAVUS_API) -> Sender:
    def send(method: str, path: str, body: Any) -> dict:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(base + path, data=data, method=method)
        req.add_header("x-api-key", tavus_key)
        req.add_header("content-type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as err:
            raise SystemExit(f"{method} {path} answered {err.code}: {err.read()[:500]!r}") from None
        return json.loads(raw) if raw else {}

    return send


def run(send: Sender, specstream_key: str | None, face_id: str | None, pal_id: str | None) -> dict:
    connector = send("POST", "/v2/connectors", connector_body(specstream_key))
    connector_id = connector["connector_id"]
    result: dict = {"connector_id": connector_id, "oauth_status": connector.get("oauth_status")}
    if connector.get("authorize_url"):
        result["authorize_url"] = connector["authorize_url"]
    else:
        result["runtime_check"] = send("POST", f"/v2/connectors/{connector_id}/runtime_check", None)
    if pal_id:
        pal = send("GET", f"/v2/pals/{pal_id}", None)
        existing = ((pal.get("layers") or {}).get("mcp") or {}).get("connectors")
        send("PATCH", f"/v2/pals/{pal_id}", attach_patch(connector_id, existing))
        result["pal_id"] = pal_id
    elif face_id:
        result["pal_id"] = send("POST", "/v2/pals", pal_body(connector_id, face_id))["pal_id"]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--face-id", help="face for a new test PAL")
    target.add_argument("--pal-id", help="existing PAL to attach the connector to")
    parser.add_argument("--dry-run", action="store_true", help="print the requests, send nothing")
    args = parser.parse_args(argv)

    specstream_key = os.environ.get("SPECSTREAM_API_KEY") or None
    if args.dry_run:
        def send(method: str, path: str, body: Any) -> dict:
            print(method, path, json.dumps(redact(body)))
            return {"connector_id": "<connector_id>", "pal_id": "<pal_id>", "layers": {}}
    else:
        tavus_key = os.environ.get("TAVUS_API_KEY")
        if not tavus_key:
            print("Set TAVUS_API_KEY (Tavus Developer Portal, API Keys).", file=sys.stderr)
            return 2
        send = http_sender(tavus_key)
    result = run(send, specstream_key, args.face_id, args.pal_id)
    print(json.dumps(result, indent=2))
    check = result.get("runtime_check") or {}
    return 1 if check.get("ok") is False else 0


if __name__ == "__main__":
    sys.exit(main())
