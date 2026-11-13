"""specstream-pinecone: load SpecStream Deep Search lists, public records, web pages read with the Extract API
and research reports into a Pinecone index."""

from __future__ import annotations

import argparse
import os
import sys

from specstream_pinecone import __version__
from specstream_pinecone.api import SpecStreamAPI, SpecStreamError
from specstream_pinecone.load import (
    DEFAULT_DIMENSION,
    DEFAULT_INDEX,
    DEFAULT_MODEL,
    DEFAULT_NAMESPACE,
    load,
    open_index,
    pinecone_embed,
)
from specstream_pinecone.pages import DEFAULT_CHUNK_CHARS, DEFAULT_OVERLAP_CHARS, load_pages
from specstream_pinecone.research import DEFAULT_WAIT_SECONDS, load_research
from specstream_pinecone.records import DEFAULT_FEED, RecordFiles, sync_feed, sync_records

SOURCE_TAG = "specstream"


def connect(args: argparse.Namespace):
    from pinecone import Pinecone

    key = os.environ.get("PINECONE_API_KEY", "")
    if not key:
        raise ValueError("A Pinecone API key is required (PINECONE_API_KEY).")
    host = args.host or os.environ.get("PINECONE_HOST") or None  # Pinecone Local: http://localhost:5080
    return Pinecone(api_key=key, host=host, source_tag=SOURCE_TAG)


def _index_options(run: argparse.ArgumentParser) -> None:
    run.add_argument("--index", default=os.environ.get("PINECONE_INDEX", DEFAULT_INDEX),
                     help="Index name; made on first use as a serverless index.")
    run.add_argument("--namespace", default=os.environ.get("PINECONE_NAMESPACE", DEFAULT_NAMESPACE))
    run.add_argument("--model", default=os.environ.get("SPECSTREAM_PINECONE_MODEL", DEFAULT_MODEL),
                     help=f"Embedding model Pinecone hosts. Default: {DEFAULT_MODEL}.")
    run.add_argument("--dimension", type=int, default=DEFAULT_DIMENSION,
                     help=f"Vector size of the model. Default: {DEFAULT_DIMENSION}.")
    run.add_argument("--cloud", default="aws", help="Cloud of a new index. Default: aws.")
    run.add_argument("--region", default="us-east-1", help="Region of a new index. Default: us-east-1.")
    run.add_argument("--host", help="Pinecone API host, for Pinecone Local. Default: PINECONE_HOST or Pinecone.")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specstream-pinecone", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("load", help="Load lists into the index, one vector per record.")
    run.add_argument("--list", dest="list_ids", action="append", metavar="LIST_ID",
                     help="Load this list (repeatable). Default: every list not yet in the namespace.")
    run.add_argument("--full", action="store_true", help="Read every list again.")
    _index_options(run)
    run.add_argument("--api-url", default=os.environ.get("SPECSTREAM_API_URL"))
    rec = sub.add_parser("records", help="Keep the index in step with SpecStream's public-records files, or with a "
                                         "public feed. Run it once a day.")
    rec.add_argument("--feed", nargs="?", const=DEFAULT_FEED, metavar="URL",
                     help=f"Load a public feed, which needs no licence. Default address: {DEFAULT_FEED}")
    rec.add_argument("--family", dest="families", action="append", metavar="FAMILY",
                     help="A family of the licence (repeatable). Default: every family the licence holds.")
    rec.add_argument("--full", action="store_true", help="Load each whole file again.")
    _index_options(rec)
    pages = sub.add_parser("pages", help="Read web pages with the Extract API ($0.80 per 1,000 pages with text) "
                                         "and load their text, one vector per chunk.")
    pages.add_argument("urls", nargs="*", metavar="URL", help="Pages to read.")
    pages.add_argument("--file", help="A file with one URL a line (a line that starts with # is a comment), "
                                      "or - for stdin.")
    pages.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_CHARS,
                       help=f"Most characters in a chunk. Default: {DEFAULT_CHUNK_CHARS}.")
    pages.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP_CHARS,
                       help=f"Characters a cut paragraph's chunks share. Default: {DEFAULT_OVERLAP_CHARS}.")
    pages.add_argument("--format", choices=("markdown", "text"), default="markdown")
    _index_options(pages)
    pages.add_argument("--api-url", default=os.environ.get("SPECSTREAM_API_URL"))
    res = sub.add_parser("research", help="Load research reports, one vector per chunk with the pages it cites. "
                                          "A question starts a new report ($0.10 quick, $0.30 standard, "
                                          "$1.00 deep); --id and --all only read reports the account has.")
    res.add_argument("questions", nargs="*", metavar="QUESTION", help="A question to answer with a new report.")
    res.add_argument("--depth", choices=("quick", "standard", "deep"), default="standard",
                     help="Depth of a new report. Default: standard ($0.30).")
    res.add_argument("--id", dest="report_ids", action="append", metavar="REPORT_ID",
                     help="Load this report (repeatable). No spend.")
    res.add_argument("--all", action="store_true",
                     help="Load every completed report of the account that is not yet in the namespace. No spend.")
    res.add_argument("--full", action="store_true", help="With --all: write every completed report again.")
    res.add_argument("--include-domain", dest="include_domains", action="append", metavar="DOMAIN",
                     help="Read only these sites for a new report (repeatable).")
    res.add_argument("--exclude-domain", dest="exclude_domains", action="append", metavar="DOMAIN",
                     help="Leave these sites out of a new report (repeatable).")
    res.add_argument("--wait", type=int, default=DEFAULT_WAIT_SECONDS, metavar="SECONDS",
                     help=f"Longest wait for a report to end. Default: {DEFAULT_WAIT_SECONDS}.")
    res.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_CHARS,
                     help=f"Most characters in a chunk. Default: {DEFAULT_CHUNK_CHARS}.")
    res.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP_CHARS,
                     help=f"Characters a cut paragraph's chunks share. Default: {DEFAULT_OVERLAP_CHARS}.")
    _index_options(res)
    res.add_argument("--api-url", default=os.environ.get("SPECSTREAM_API_URL"))
    return p


def read_urls(args: argparse.Namespace) -> list[str]:
    urls = list(args.urls)
    if args.file:
        handle = sys.stdin if args.file == "-" else open(args.file, encoding="utf-8")
        with handle:
            urls += [line.strip() for line in handle if line.strip() and not line.strip().startswith("#")]
    return urls


def pages(args: argparse.Namespace) -> int:
    urls = read_urls(args)
    if not urls:
        raise ValueError("Give one or more URLs, or --file with one URL a line.")
    api = SpecStreamAPI(os.environ.get("SPECSTREAM_API_KEY", ""), args.api_url)
    pc = connect(args)
    index = open_index(pc, args.index, args.dimension, args.cloud, args.region)
    result = load_pages(api, pinecone_embed(pc, args.model), urls, index=index, namespace=args.namespace,
                        chunk_chars=args.chunk_size, overlap_chars=args.overlap, format=args.format,
                        dimension=args.dimension)
    for url, status, reason in result.skipped:
        print(f"Not loaded ({status}): {url}" + (f" - {reason}" if reason else ""), file=sys.stderr)
    print(f"Loaded {result.pages} page(s) as {result.chunks} chunk(s) into {args.index}; "
          f"Extract charged ${result.price_usd:.4f}.")
    return 0


def research(args: argparse.Namespace) -> int:
    if not (args.questions or args.report_ids or args.all):
        raise ValueError("Give a question, --id with a report's id, or --all.")
    api = SpecStreamAPI(os.environ.get("SPECSTREAM_API_KEY", ""), args.api_url)
    pc = connect(args)
    index = open_index(pc, args.index, args.dimension, args.cloud, args.region)
    result = load_research(api, pinecone_embed(pc, args.model), index, questions=args.questions,
                           report_ids=args.report_ids, every=args.all, full=args.full, depth=args.depth,
                           namespace=args.namespace, chunk_chars=args.chunk_size, overlap_chars=args.overlap,
                           dimension=args.dimension, wait_seconds=args.wait,
                           include_domains=args.include_domains, exclude_domains=args.exclude_domains)
    for report_id, status, reason in result.skipped:
        print(f"Not loaded ({status}): {report_id}" + (f" - {reason}" if reason else ""), file=sys.stderr)
    print(f"Loaded {result.reports} report(s) as {result.chunks} chunk(s) into {args.index}; "
          f"new reports cost ${result.price_usd:.2f}.")
    return 1 if result.skipped and not result.reports else 0


def records(args: argparse.Namespace) -> int:
    # The licence link is read from the environment only: it is a secret, and a command line is seen by others.
    files = None if args.feed else RecordFiles(os.environ.get("SPECSTREAM_RECORDS_LINK", ""))
    pc = connect(args)
    index = open_index(pc, args.index, args.dimension, args.cloud, args.region)
    embed = pinecone_embed(pc, args.model)
    if files is None:
        found = sync_feed(index, embed, args.dimension, args.feed, args.namespace)
        print(f"Feed {found.feed}: {found.items} item(s), {found.written} new in {args.index}.")
        return 0
    for r in sync_records(index, files, embed, args.dimension, args.namespace, args.families, args.full):
        what = {"whole": "whole file", "days": f"{len(r.days)} day(s)", "current": "nothing new"}[r.mode]
        print(f"{r.family}: {what}, {r.written} written, {r.deleted} deleted, applied through {r.through}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "records":
            return records(args)
        if args.command == "pages":
            return pages(args)
        if args.command == "research":
            return research(args)
        api = SpecStreamAPI(os.environ.get("SPECSTREAM_API_KEY", ""), args.api_url)
        pc = connect(args)
        index = open_index(pc, args.index, args.dimension, args.cloud, args.region)
        result = load(index, api, pinecone_embed(pc, args.model), namespace=args.namespace,
                      list_ids=args.list_ids, full=args.full, dimension=args.dimension)
    except (SpecStreamError, ValueError, OSError) as exc:
        print(f"specstream-pinecone: {exc}", file=sys.stderr)
        return 1
    print(f"Loaded {result.lists} list(s) and {result.records} record(s) into {args.index}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
