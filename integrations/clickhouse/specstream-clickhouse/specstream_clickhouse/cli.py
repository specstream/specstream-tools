"""specstream-clickhouse: load SpecStream lists into ClickHouse."""

from __future__ import annotations

import argparse
import os
import sys

from specstream_clickhouse import __version__
from specstream_clickhouse.api import SpecStreamAPI, SpecStreamError
from specstream_clickhouse.load import load


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def connect(args: argparse.Namespace):
    import clickhouse_connect

    secure = args.secure if args.secure is not None else _truthy(os.environ.get("CLICKHOUSE_SECURE"))
    port = args.port or int(os.environ.get("CLICKHOUSE_PORT") or (8443 if secure else 8123))
    return clickhouse_connect.get_client(
        host=args.host or os.environ.get("CLICKHOUSE_HOST", "localhost"),
        port=port,
        username=os.environ.get("CLICKHOUSE_USER", "default"),
        password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
        secure=secure,
        # ClickHouse's user-agent convention: <app>/<version> before the client's own name.
        client_name=f"specstream-clickhouse/{__version__}",
    )


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specstream-clickhouse", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("load", help="Load lists into the specstream_lists and specstream_records tables.")
    run.add_argument("--list", dest="list_ids", action="append", metavar="LIST_ID",
                     help="Load this list (repeatable). Default: every list created since the last load.")
    run.add_argument("--full", action="store_true", help="Read every list again.")
    run.add_argument("--database", default=os.environ.get("CLICKHOUSE_DATABASE", "specstream"))
    run.add_argument("--host", help="Default: CLICKHOUSE_HOST or localhost.")
    run.add_argument("--port", type=int, help="Default: CLICKHOUSE_PORT, else 8443 with TLS or 8123.")
    run.add_argument("--secure", action=argparse.BooleanOptionalAction, default=None,
                     help="Use TLS (ClickHouse Cloud). Default: CLICKHOUSE_SECURE.")
    run.add_argument("--api-url", default=os.environ.get("SPECSTREAM_API_URL"))
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        api = SpecStreamAPI(os.environ.get("SPECSTREAM_API_KEY", ""), args.api_url)
        result = load(connect(args), api, database=args.database, list_ids=args.list_ids, full=args.full)
    except (SpecStreamError, ValueError) as exc:
        print(f"specstream-clickhouse: {exc}", file=sys.stderr)
        return 1
    print(f"Loaded {result.lists} list(s) and {result.records} record(s) into {args.database}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
