"""specstream-qdrant: load SpecStream lists, or web pages read with the Extract API, into a Qdrant collection."""

from __future__ import annotations

import argparse
import os
import sys

from specstream_qdrant import __version__
from specstream_qdrant.api import SpecStreamAPI, SpecStreamError
from specstream_qdrant.load import DEFAULT_COLLECTION, fastembed, load
from specstream_qdrant.pages import (
    DEFAULT_CHUNK_CHARS,
    DEFAULT_OVERLAP_CHARS,
    DEFAULT_PAGES_COLLECTION,
    load_pages,
)

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


def connect(args: argparse.Namespace):
    from qdrant_client import QdrantClient

    url = args.url or os.environ.get("QDRANT_URL") or "http://localhost:6333"
    if url == ":memory:":
        return QdrantClient(":memory:")
    if not url.startswith(("http://", "https://")):
        return QdrantClient(path=url)  # Local mode: a folder on this machine.
    return QdrantClient(url=url, api_key=os.environ.get("QDRANT_API_KEY") or None)


def _shared(command: argparse.ArgumentParser) -> None:
    command.add_argument("--url", help="Qdrant URL, or a folder for local mode. Default: QDRANT_URL or "
                                       "http://localhost:6333. The key is read from QDRANT_API_KEY.")
    command.add_argument("--model", default=os.environ.get("SPECSTREAM_QDRANT_MODEL", DEFAULT_MODEL),
                         help=f"FastEmbed text model. Default: {DEFAULT_MODEL}.")
    command.add_argument("--api-url", default=os.environ.get("SPECSTREAM_API_URL"))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specstream-qdrant", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("load", help="Load lists into the collection, one point per record.")
    run.add_argument("--list", dest="list_ids", action="append", metavar="LIST_ID",
                     help="Load this list (repeatable). Default: every list not yet in the collection.")
    run.add_argument("--full", action="store_true", help="Read every list again.")
    run.add_argument("--collection", default=os.environ.get("QDRANT_COLLECTION", DEFAULT_COLLECTION))
    _shared(run)

    pages = sub.add_parser(
        "pages",
        help="Read web pages with the Extract API ($0.80 per 1,000 pages read) and load their text, "
             "one point per chunk.",
    )
    pages.add_argument("urls", nargs="*", metavar="URL", help="Pages to read.")
    pages.add_argument("--file", help="A file with one URL a line (a line that starts with # is a comment), or - for stdin.")
    pages.add_argument("--collection", default=os.environ.get("QDRANT_PAGES_COLLECTION", DEFAULT_PAGES_COLLECTION))
    pages.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_CHARS, help="Most characters in a chunk.")
    pages.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP_CHARS,
                       help="Characters a cut paragraph's chunks share.")
    pages.add_argument("--format", choices=("markdown", "text"), default="markdown")
    _shared(pages)
    return p


def read_urls(args: argparse.Namespace) -> list[str]:
    urls = list(args.urls)
    if args.file:
        handle = sys.stdin if args.file == "-" else open(args.file, encoding="utf-8")
        with handle:
            for line in handle:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
    return urls


def pages_main(args: argparse.Namespace) -> int:
    urls = read_urls(args)
    if not urls:
        raise ValueError("Give one or more URLs, or --file with one URL a line.")
    api = SpecStreamAPI(os.environ.get("SPECSTREAM_API_KEY", ""), args.api_url)
    embed = fastembed(args.model)
    result = load_pages(connect(args), api, embed, urls, collection=args.collection,
                        chunk_chars=args.chunk_size, overlap_chars=args.overlap, format=args.format)
    for url, status, reason in result.skipped:
        print(f"Not loaded ({status}): {url}" + (f" - {reason}" if reason else ""), file=sys.stderr)
    print(f"Loaded {result.pages} page(s) as {result.chunks} chunk(s) into {args.collection}; "
          f"Extract charged ${result.price_usd:.4f}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "pages":
        try:
            return pages_main(args)
        except (SpecStreamError, ValueError, OSError) as exc:
            print(f"specstream-qdrant: {exc}", file=sys.stderr)
            return 1
    try:
        api = SpecStreamAPI(os.environ.get("SPECSTREAM_API_KEY", ""), args.api_url)
        embed = fastembed(args.model)
        result = load(connect(args), api, embed, collection=args.collection,
                      list_ids=args.list_ids, full=args.full)
    except (SpecStreamError, ValueError) as exc:
        print(f"specstream-qdrant: {exc}", file=sys.stderr)
        return 1
    print(f"Loaded {result.lists} list(s) and {result.records} record(s) into {args.collection}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
