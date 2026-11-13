"""Writes specstream-openapi.json, the API specification a Retool REST API resource loads by URL.

It is the research part of finder/openapi.yaml (start, read, list and cancel a research report) as OpenAPI 3.0.3,
because a spec loader that reads 3.0 does not read the 3.1 forms (a null type, const, a list of types).
Run it from the repository root after the research routes change: python3 integrations/retool/build_spec.py
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "finder" / "openapi.yaml"
SPEC = ROOT / "integrations" / "retool" / "specstream-openapi.json"
# The address the Retool resource loads: the website serves apps/website/static/ at its root.
SERVED = ROOT / "apps" / "website" / "static" / "retool" / "specstream-openapi.json"

# (path, method) -> (operationId, the name Retool shows, what the builder reads under it)
OPERATIONS = {
    ("/v1/research", "post"): (
        "startResearch",
        "Start a research report",
        "Starts a written report that answers a question from the live web. Each cited sentence links to the page "
        "it was read from. Answers at once with the report's id. A report costs $0.10 (quick), $0.30 (standard) or "
        "$1.00 (deep), taken from the balance once, when the report is delivered. A cancelled report is not charged.",
    ),
    ("/v1/research/{run_id}", "get"): (
        "getResearch",
        "Read a research report",
        "Reads a report by its id. Call it until status is completed: a quick report takes about a minute, a "
        "standard report about four minutes and a deep report about five. report.content is the text with [1] "
        "markers, report.citations gives each cited sentence its page, and report.sources lists every page read.",
    ),
    ("/v1/research", "get"): (
        "listResearch",
        "List research reports",
        "Lists the account's reports, newest first. Send next_after as after to read the next page.",
    ),
    ("/v1/research/{run_id}/cancel", "post"): (
        "cancelResearch",
        "Cancel a research report",
        "Stops a report at its next step. A cancelled report is not charged.",
    ),
}

# Keys of 3.1 (JSON Schema 2020-12) that a 3.0 schema does not have.
_ONLY_3_1 = ("examples", "discriminator", "propertyNames", "prefixItems")


def _to_3_0(node):
    """Rewrite the 3.1 forms as 3.0: `anyOf [X, null]` and `type [X, null]` become `nullable`, `const` an enum."""
    if isinstance(node, list):
        return [_to_3_0(item) for item in node]
    if not isinstance(node, dict):
        return node
    node = {key: _to_3_0(value) for key, value in node.items()}
    for union in ("anyOf", "oneOf"):
        options = node.get(union)
        if not isinstance(options, list):
            continue
        kept = [option for option in options if option != {"type": "null"}]
        nullable = len(kept) != len(options)
        del node[union]
        if len(kept) == 1:
            node.update(kept[0])
        else:
            # Several shapes for one value: a loader that reads no union takes it as any JSON value.
            names = [
                option.get("title") or option.get("$ref", "").rsplit("/", 1)[-1] or option.get("type") or ""
                for option in kept
            ]
            names = [str(name) for name in names if name]
            if names:
                node["description"] = (node.get("description", "") + " One of: " + ", ".join(names) + ".").strip()
        if nullable:
            node["nullable"] = True
    if isinstance(node.get("type"), list):
        types = [name for name in node["type"] if name != "null"]
        if len(types) != len(node["type"]):
            node["nullable"] = True
        if len(types) == 1:
            node["type"] = types[0]
        else:
            del node["type"]
    if "const" in node:
        node["enum"] = [node.pop("const")]
    if "$ref" in node and len(node) > 1:
        # 3.0 ignores the keys beside a $ref, so a described or nullable reference goes inside allOf.
        ref = node.pop("$ref")
        node = {"allOf": [{"$ref": ref}], **node}
    return node


def _without_3_1_keys(schema):
    """Drop the 3.1-only keys of a schema, but never a property that happens to carry such a name."""
    if isinstance(schema, list):
        return [_without_3_1_keys(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    cleaned = {}
    for key, value in schema.items():
        if key in _ONLY_3_1:
            continue
        if key == "properties" and isinstance(value, dict):
            cleaned[key] = {name: _without_3_1_keys(member) for name, member in value.items()}
        else:
            cleaned[key] = _without_3_1_keys(value)
    return cleaned


def _referenced(node, schemas: dict, found: dict) -> None:
    if isinstance(node, list):
        for item in node:
            _referenced(item, schemas, found)
    elif isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            name = ref.removeprefix("#/components/schemas/")
            if name not in found:
                found[name] = schemas[name]
                _referenced(schemas[name], schemas, found)
        for value in node.values():
            _referenced(value, schemas, found)


def build() -> dict:
    api = yaml.safe_load(API.read_text())
    paths: dict = {}
    for (path, method), (operation_id, summary, description) in OPERATIONS.items():
        source = api["paths"][path][method]
        operation = {
            "operationId": operation_id,
            "summary": summary,
            "description": description,
            "tags": ["Research"],
        }
        for key in ("parameters", "requestBody", "responses"):
            if key in source:
                operation[key] = source[key]
        operation["security"] = [{"bearerAuth": []}]
        paths.setdefault(path, {})[method] = operation
    schemas: dict = {}
    _referenced(paths, api["components"]["schemas"], schemas)
    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "SpecStream",
            "version": "1.0.0",
            "description": "Research reports from the live web: a written answer to a question, in which each cited "
            "sentence links to the page it was read from. $0.10, $0.30 or $1.00 a report, by depth. "
            "Authenticate with a SpecStream API key as a Bearer token.",
            "contact": {"name": "SpecStream", "url": "https://specstream.ai", "email": "support@specstream.ai"},
        },
        "servers": [{"url": "https://api.specstream.ai"}],
        "tags": [{"name": "Research", "description": "Research reports with a source behind each cited sentence."}],
        "paths": paths,
        "components": {
            "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}},
            "schemas": dict(sorted(schemas.items())),
        },
    }
    return _to_3_0(_without_3_1_keys(spec))


def text() -> str:
    return json.dumps(build(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    for target in (SPEC, SERVED):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text())
        print(f"wrote {target.relative_to(ROOT)}")
