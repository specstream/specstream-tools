"""SpecStream Deep Search as an enrich step for a lemlist campaign.

The step reads the leads of one lemlist campaign, asks SpecStream for the facts you name
(for example "Company headcount" or "Latest funding round"), and writes each fact found back on
its lead as a lemlist custom variable, with the page that prints it in a second variable
(<variable>Source). Your email steps can then use {{variable}} like any other lemlist variable.

    export LEMLIST_API_KEY=...      # lemlist > Settings > Integrations > API key
    export SPECSTREAM_API_KEY=...   # specstream.ai > Settings > API keys
    python specstream_lemlist.py --campaign cam_123 \
        --fact "Company headcount=companyHeadcount" \
        --fact "Latest funding round=lastFundingRound" \
        --max-cents 500

Nothing runs above --max-cents: when SpecStream's quote for the work is higher, the step stops
before any work starts and prints the quote. A lead's own lemlist fields (email, firstName,
companyName and the others) are never written, and a variable that already holds a value keeps
it unless you pass --overwrite. Only the Python standard library is used.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

LEMLIST_BASE = "https://api.lemlist.com/api"
SPECSTREAM_BASE = "https://api.specstream.ai"
USER_AGENT = "specstream-lemlist/0.1"
MAX_LEADS = 2000
ROWS_PAGE = 100
# A lead's email address stays in lemlist: no fact needs it to find the lead.
COLUMNS = ("lead_ref", "full_name", "company", "website", "linkedin_url")
DONE = frozenset({"completed", "partial", "failed", "canceled", "expired"})
# lemlist's own lead fields: the step never writes them, so a guess never replaces a lead's data.
LEAD_FIELDS = frozenset(
    {
        "email",
        "firstName",
        "lastName",
        "picture",
        "phone",
        "linkedinUrl",
        "companyName",
        "companyDomain",
        "icebreaker",
        "timezone",
    }
)
VARIABLE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
SOURCE_SUFFIX = "Source"
# Fields every SpecStream row carries; a fact is never read from them.
ROW_FIELDS = frozenset(
    {"id", "list_id", "list_link", "position", "summary", "source_url", "checked_at"}
)
# A fact asked in words that names one of these comes back under the shared field name.
SHARED_FIELDS = (("email", "email"), ("phone", "phone"), ("website", "website"))

# (method, path with its query, JSON body or None) -> (HTTP status, decoded JSON body)
Transport = Callable[[str, str, Mapping[str, Any] | None], tuple[int, Any]]


class StepError(Exception):
    """A service refused a step. Nothing past that step ran."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Fact:
    words: str
    variable: str


@dataclass(frozen=True)
class Lead:
    ref: str
    full_name: str
    company: str
    website: str
    linkedin_url: str
    source: Mapping[str, Any]

    def researchable(self) -> bool:
        # A fact about a lead needs the lead's company, its site or its profile link.
        return bool(self.linkedin_url or self.company or self.website)


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _plain(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _domain(value: str) -> str:
    host = value.strip().lower()
    for prefix in ("https://", "http://"):
        host = host.removeprefix(prefix)
    return host.removeprefix("www.").split("/", 1)[0]


def parse_fact(text: str) -> Fact:
    """'Company headcount=companyHeadcount': the fact in words, then the lemlist variable."""
    words, sep, variable = text.rpartition("=")
    words, variable = _text(words), variable.strip()
    if not sep or not words:
        raise StepError(f"Write the fact as 'words=variableName', not {text!r}")
    if not VARIABLE_NAME.fullmatch(variable):
        raise StepError(f"{variable!r} is not a lemlist variable name (letters, digits, _)")
    if variable in LEAD_FIELDS or variable.endswith(SOURCE_SUFFIX):
        raise StepError(f"Choose another name than {variable!r}: the step does not write it")
    return Fact(words=words, variable=variable)


def lead(item: Mapping[str, Any]) -> Lead:
    """One lead of lemlist's campaign export (format=json)."""
    return Lead(
        ref=_text(item.get("_id")),
        full_name=_text(f"{_text(item.get('firstName'))} {_text(item.get('lastName'))}"),
        company=_text(item.get("companyName")),
        website=_domain(_text(item.get("companyDomain"))),
        linkedin_url=_text(item.get("linkedinUrl")),
        source=item,
    )


def leads_csv(leads: Sequence[Lead]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for one in leads:
        writer.writerow([one.ref, one.full_name, one.company, one.website, one.linkedin_url])
    return out.getvalue()


def request_text(count: int, facts: Sequence[Fact]) -> str:
    noun = "person" if count == 1 else "people"
    return f"For the {count} {noun}: " + ", ".join(fact.words for fact in facts)


def fact_value(row: Mapping[str, Any], fact: Fact) -> tuple[str, str]:
    """The fact's value in one SpecStream row and the page that prints it, or two empty texts.

    A fact asked in words comes back under the request's own words; a fact that names an email,
    a phone or a website comes back under that shared name.
    """
    wanted = _plain(fact.words)
    keys = [
        key
        for key in row
        if isinstance(key, str)
        and key not in ROW_FIELDS
        and not key.endswith("_source")
        and _plain(key) == wanted
    ]
    keys += [shared for word, shared in SHARED_FIELDS if word in fact.words.lower()]
    for key in keys:
        value = _text(row.get(key))
        source = _text(row.get(f"{key}_source")) or _text(row.get("source_url"))
        if value and source:
            return value, source
    return "", ""


def _call_json(request: Request, timeout: float, retries: int) -> tuple[int, Any]:
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.status, json.loads(response.read().decode("utf-8") or "{}")
        except HTTPError as exc:
            if exc.code == 429 and attempt < retries:
                # lemlist allows 20 requests per 2 seconds for one key.
                time.sleep(float(exc.headers.get("Retry-After") or 2))
                continue
            try:
                return exc.code, json.loads(exc.read().decode("utf-8") or "{}")
            except ValueError:
                return exc.code, {}
        except (URLError, OSError) as exc:
            raise StepError(f"{request.host} could not be reached") from exc
    return 429, {}


def http_transport(
    authorization: str, base: str, timeout: float = 120, retries: int = 0
) -> Transport:
    root = base.rstrip("/")

    def call(method: str, path: str, body: Mapping[str, Any] | None) -> tuple[int, Any]:
        headers = {
            "Authorization": authorization,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(root + path, data=data, method=method, headers=headers)
        return _call_json(request, timeout, retries)

    return call


def specstream_transport(api_key: str, base: str = SPECSTREAM_BASE) -> Transport:
    return http_transport("Bearer " + api_key, base)


def lemlist_transport(api_key: str, base: str = LEMLIST_BASE) -> Transport:
    # lemlist takes Basic auth with an empty user name and the key as the password.
    token = base64.b64encode((":" + api_key).encode("utf-8")).decode("ascii")
    return http_transport("Basic " + token, base, timeout=60, retries=3)


def _answer(transport: Transport, method: str, path: str, body: Mapping[str, Any] | None) -> Any:
    status, payload = transport(method, path, body)
    if status >= 400:
        error = payload.get("error") if isinstance(payload, Mapping) else None
        message = error.get("message") if isinstance(error, Mapping) else error
        raise StepError(_text(message) or f"{path} answered HTTP {status}", status)
    return payload


class EnrichStep:
    def __init__(self, specstream: Transport, lemlist: Transport) -> None:
        self._specstream = specstream
        self._lemlist = lemlist

    def _data(
        self, method: str, path: str, body: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = _answer(self._specstream, method, path, body)
        data = payload.get("data") if isinstance(payload, Mapping) else None
        return dict(data) if isinstance(data, Mapping) else {}

    def leads(self, campaign_id: str) -> list[Lead]:
        path = (
            "/v2/campaigns/" + quote(campaign_id, safe="") + "/export/leads?state=all&format=json"
        )
        payload = _answer(self._lemlist, "GET", path, None)
        items = payload if isinstance(payload, list) else []
        return [lead(item) for item in items if isinstance(item, Mapping) and item.get("_id")]

    def start(
        self, campaign_id: str, facts: Sequence[Fact], max_cents: int, request_id: str
    ) -> dict[str, Any]:
        """One SpecStream find for the campaign's leads, started only when its quoted maximum is
        within max_cents. The same request_id imports and approves the same work once."""
        if not facts:
            raise StepError("Name at least one fact to find")
        leads = self.leads(campaign_id)
        asked = [one for one in leads if one.researchable()]
        base = {
            "request_id": request_id,
            "leads": len(leads),
            "skipped": [one.ref for one in leads if not one.researchable()],
            "find_id": None,
        }
        if len(asked) > MAX_LEADS:
            raise StepError(f"A campaign of more than {MAX_LEADS} leads runs in parts")
        if not asked:
            return {**base, "state": "nothing_to_find", "maximum_cents": 0}
        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:40]
        imported = self._data(
            "POST",
            "/v1/imports/file",
            {
                "import_id": "lemlist_" + digest,
                "name": "lemlist campaign " + campaign_id[:80],
                "format": "csv",
                "content": leads_csv(asked),
            },
        )
        row_ids = [
            str(row["id"])
            for row in imported.get("rows") or ()
            if isinstance(row, Mapping) and isinstance(row.get("id"), str)
        ]
        if not row_ids or not isinstance(imported.get("id"), str):
            return {**base, "state": "needs_edit", "maximum_cents": 0}
        reading = self._data(
            "POST", "/v1/parse", {"q": request_text(len(row_ids), facts), "locale": "en-US"}
        )
        ast_hash = reading.get("ast_hash")
        if not isinstance(ast_hash, str):
            return {**base, "state": "needs_edit", "maximum_cents": 0}
        quoted = self._data(
            "POST",
            "/v1/capacity/quotes",
            {
                "ast_hash": ast_hash,
                "source_import_id": imported["id"],
                "source_row_ids": row_ids,
                "requested_units": len(row_ids),
            },
        )
        maximum = int(quoted.get("maximum_cents") or 0)
        if not quoted.get("quote_id") or maximum > max_cents:
            return {**base, "state": "above_maximum", "maximum_cents": maximum}
        started = self._data(
            "POST",
            "/v1/capacity/executions",
            {
                "quote_id": quoted["quote_id"],
                "quote_hash": quoted.get("quote_hash"),
                "idempotency_key": "lemlist-" + digest,
                "confirm_max_cents": maximum,
            },
        )
        return {
            **base,
            "state": "started",
            "maximum_cents": maximum,
            "find_id": started.get("find_id"),
        }

    def _found(self, find_id: str, facts: Sequence[Fact]) -> dict[str, dict[str, str]] | None:
        """Each lead's found values by lemlist variable, or None while the find runs."""
        path = "/v1/finds/" + quote(find_id, safe="")
        by_entity: dict[str, dict[str, str]] = {}
        cursor: str | None = None
        while True:
            page = self._data(
                "GET",
                f"{path}/rows?limit={ROWS_PAGE}"
                + (f"&cursor={quote(cursor, safe='')}" if cursor else ""),
            )
            if page.get("status") not in DONE:
                return None
            for row in page.get("flat_rows") or ():
                if not isinstance(row, Mapping):
                    continue
                entity = str(row.get("id") or "").split(":", 2)
                if len(entity) < 2:
                    continue
                values = by_entity.setdefault(entity[1], {})
                for fact in facts:
                    value, source = fact_value(row, fact)
                    if value and fact.variable not in values:
                        values[fact.variable] = value
                        values[fact.variable + SOURCE_SUFFIX] = source
            cursor = page.get("next_cursor")
            if not isinstance(cursor, str) or not cursor:
                break
        inputs = self._data(
            "GET", "/v1/workspace/collections/" + quote(find_id, safe="") + "/input"
        )
        by_lead: dict[str, dict[str, str]] = {}
        for row in inputs.get("rows") or ():
            if not isinstance(row, Mapping):
                continue
            provided = row.get("provided")
            ref = provided.get("lead_ref") if isinstance(provided, Mapping) else None
            ref = ref.get("value") if isinstance(ref, Mapping) else ref
            entity_id = row.get("entity_id")
            if ref is not None and isinstance(entity_id, str) and by_entity.get(entity_id):
                by_lead[_text(ref)] = by_entity[entity_id]
        return by_lead

    def _write(self, one: Lead, values: Mapping[str, str], overwrite: bool) -> dict[str, str]:
        kept = {
            name
            for name in values
            if not name.endswith(SOURCE_SUFFIX) and not overwrite and _text(one.source.get(name))
        }
        # A value the lead keeps keeps its own source too.
        values = {
            name: value
            for name, value in values.items()
            if name not in kept and name.removesuffix(SOURCE_SUFFIX) not in kept
        }
        existing = {
            name: value
            for name, value in values.items()
            if name in one.source and (overwrite or not _text(one.source.get(name)))
        }
        new = {name: value for name, value in values.items() if name not in one.source}
        path = "/leads/" + quote(one.ref, safe="") + "/variables?"
        # lemlist adds a variable with POST and changes one the lead already has with PATCH.
        if new:
            _answer(self._lemlist, "POST", path + urlencode(new), None)
        if existing:
            _answer(self._lemlist, "PATCH", path + urlencode(existing), None)
        return {**new, **existing}

    def finish(
        self, find_id: str, campaign_id: str, facts: Sequence[Fact], overwrite: bool = False
    ) -> dict[str, Any]:
        """Write the find's facts on the campaign's leads: status processing until it ends."""
        found = self._found(find_id, facts)
        if found is None:
            return {"find_id": find_id, "status": "processing"}
        written: dict[str, dict[str, str]] = {}
        for one in self.leads(campaign_id):
            values = found.get(one.ref)
            if values:
                done = self._write(one, values, overwrite)
                if done:
                    written[one.ref] = done
        return {
            "find_id": find_id,
            "status": "written",
            "leads_written": len(written),
            "values_written": sum(
                1
                for values in written.values()
                for name in values
                if not name.endswith(SOURCE_SUFFIX)
            ),
            "written": written,
        }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill lemlist lead variables with SpecStream.")
    parser.add_argument("--campaign", required=True, help="lemlist campaign id (cam_...)")
    parser.add_argument(
        "--fact", action="append", required=True, help="'Fact in words=lemlistVariable'"
    )
    parser.add_argument("--max-cents", type=int, required=True, help="most the work may cost")
    parser.add_argument("--request-id", help="the same id never starts the same work twice")
    parser.add_argument("--find", help="write the results of a find already started")
    parser.add_argument("--overwrite", action="store_true", help="replace values leads have")
    parser.add_argument("--poll-seconds", type=float, default=30)
    args = parser.parse_args(argv)
    specstream_key = os.environ.get("SPECSTREAM_API_KEY", "")
    lemlist_key = os.environ.get("LEMLIST_API_KEY", "")
    if not specstream_key or not lemlist_key:
        print("Set SPECSTREAM_API_KEY and LEMLIST_API_KEY", file=sys.stderr)
        return 2
    try:
        facts = [parse_fact(text) for text in args.fact]
        step = EnrichStep(specstream_transport(specstream_key), lemlist_transport(lemlist_key))
        find_id = args.find
        if not find_id:
            request_id = args.request_id or "lemlist-" + args.campaign + "-" + "|".join(args.fact)
            started = step.start(args.campaign, facts, args.max_cents, request_id)
            print(json.dumps(started, indent=2))
            if started["state"] != "started":
                return 1
            find_id = str(started["find_id"])
        while True:
            result = step.finish(find_id, args.campaign, facts, overwrite=args.overwrite)
            if result["status"] != "processing":
                print(json.dumps(result, indent=2))
                return 0
            time.sleep(args.poll_seconds)
    except StepError as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
