"""SPECSTREAM console: inspect a Spec, prepare a Find, and read its Delivery."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from typing import Any, TextIO

from specstream_client.client import DEFAULT_BASE_URL, Client, SpecstreamError
from specstream_client.families import FAMILIES
from specstream_client.lifecycle_commands import COMMANDS

PROG = "specstream"
DESC = (
    "The web. To your spec. Compile the request, quote-capacity-work, then "
    "authorize-capacity-work with the exact approved maximum and a stable key. "
    "Read the same work, evidence and balance from every interface. "
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROG, description=DESC)
    parser.add_argument(
        "--base-url", default=os.environ.get("SPECSTREAM_BASE_URL", DEFAULT_BASE_URL)
    )
    parser.add_argument("--api-key", default=os.environ.get("SPECSTREAM_API_KEY", ""))
    sub = parser.add_subparsers(dest="cmd")
    compile_cmd = sub.add_parser("compile", help="Interpret a brief as an editable Spec")
    compile_cmd.add_argument("q")
    compile_cmd.add_argument("--locale", default="en-US")
    edit = sub.add_parser(
        "edit-spec", help="Validate exact edited AST JSON, including required facts"
    )
    edit.add_argument(
        "--ast", required=True, type=argparse.FileType("r"), help="AST JSON file or -"
    )
    options = sub.add_parser("spec-options", help="Read supported conditions and return facts")
    options.add_argument(
        "target", help="A record kind, for example: " + ", ".join(FAMILIES[:4])
    )
    for command, help_text in (
        ("get", "Inspect an owned Find"),
        ("rows", "Read Matches with evidence"),
        ("revisit", "Read one page of retained-target outcomes"),
        ("export", "Request a Delivery download link"),
    ):
        item = sub.add_parser(command, help=help_text)
        item.add_argument("--find-id", required=True)
        if command == "rows":
            item.add_argument("--cursor", default=None)
            item.add_argument("--limit", type=int, default=100)
        if command == "revisit":
            item.add_argument("--after", default="")
            item.add_argument("--limit", type=int, default=100)
        if command == "export":
            item.add_argument("--format", default="csv", choices=("csv", "xlsx", "json", "html"))
    sub.add_parser("families", help="Print supported public targets")
    for name, contract in COMMANDS.items():
        command = sub.add_parser(name, help=contract["summary"])
        for argument in contract["arguments"]:
            command.add_argument("--" + argument.replace("_", "-"), required=True)
        if contract["body"]:
            command.add_argument(
                "--request",
                required=contract["body_required"],
                type=argparse.FileType("r"),
                help="Exact request JSON file or - for stdin",
            )
        for parameter, kind in contract["query"].items():
            options: dict[str, Any] = {"default": None}
            if kind == "boolean":
                options["action"] = argparse.BooleanOptionalAction
            else:
                options["type"] = int if kind == "integer" else str
            command.add_argument("--" + parameter.replace("_", "-"), **options)
    return parser


def _dump(payload: Any, out: TextIO) -> None:
    json.dump(payload, out, indent=2, sort_keys=True)
    out.write("\n")


def main(
    argv: Sequence[str] | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    stdout, stderr = out or sys.stdout, err or sys.stderr
    parser = _parser()
    ns = parser.parse_args(list(argv) if argv is not None else None)
    if not ns.cmd:
        parser.print_help(stdout)
        return 0
    try:
        if ns.cmd == "families":
            result: Any = list(FAMILIES)
        else:
            client = Client(api_key=ns.api_key, base_url=ns.base_url)
            if ns.cmd in COMMANDS:
                contract = COMMANDS[ns.cmd]
                arguments = [getattr(ns, argument) for argument in contract["arguments"]]
                if contract["body"]:
                    body = None
                    if ns.request is not None:
                        with ns.request as source:
                            body = json.load(source)
                        if not isinstance(body, dict):
                            raise ValueError("Request must be a JSON object")
                    arguments.append(body)
                options = {name: getattr(ns, name) for name in contract["query"]}
                result = getattr(client, contract["method"])(*arguments, **options)
            elif ns.cmd == "compile":
                result = client.compile(ns.q, locale=ns.locale)
            elif ns.cmd == "edit-spec":
                with ns.ast as source:
                    ast = json.load(source)
                if not isinstance(ast, dict):
                    raise ValueError("AST must be a JSON object")
                result = client.edit_spec(ast)
            elif ns.cmd == "spec-options":
                result = client.spec_options(ns.target)
            elif ns.cmd == "get":
                result = client.get_find(ns.find_id)
            elif ns.cmd == "rows":
                result = client.rows(ns.find_id, cursor=ns.cursor, limit=ns.limit)
            elif ns.cmd == "revisit":
                result = client.revisit(ns.find_id, after=ns.after, limit=ns.limit)
            else:
                result = client.export(ns.find_id, format=ns.format)
        _dump(result, stdout)
        return 0
    except SpecstreamError as exc:
        print(str(exc), file=stderr)
        return 1
    except (ValueError, OSError) as exc:
        print(str(exc), file=stderr)
        return 2
