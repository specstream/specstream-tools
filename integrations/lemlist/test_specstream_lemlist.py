"""The lemlist enrich step, with SpecStream and lemlist both scripted."""

from __future__ import annotations

import csv
import importlib.util
import io
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

SCRIPT = Path(__file__).resolve().parent / "specstream_lemlist.py"
_spec = importlib.util.spec_from_file_location("specstream_lemlist", SCRIPT)
assert _spec and _spec.loader
step_module = importlib.util.module_from_spec(_spec)
sys.modules["specstream_lemlist"] = step_module
_spec.loader.exec_module(step_module)

EnrichStep = step_module.EnrichStep
StepError = step_module.StepError
parse_fact = step_module.parse_fact

LEADS = [
    {
        "_id": "lea_1",
        "email": "ada@engines.example",
        "firstName": "Ada",
        "lastName": "Lovelace",
        "companyName": "Analytical Engines",
        "companyDomain": "https://www.engines.example/team",
        "companyHeadcount": "",
    },
    {"_id": "lea_2", "email": "nobody@example.com", "firstName": "Nobody"},
    {
        "_id": "lea_3",
        "firstName": "Alan",
        "lastName": "Turing",
        "companyName": "Bletchley Ltd",
        "companyHeadcount": "12",
    },
]
FACTS = [parse_fact("Company headcount=companyHeadcount"), parse_fact("Work email=workEmail")]


class Script:
    def __init__(self, answers: dict[tuple[str, str], Any]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str, Mapping[str, Any] | None]] = []

    def __call__(self, method: str, path: str, body: Mapping[str, Any] | None) -> tuple[int, Any]:
        self.calls.append((method, path, body))
        answer = self.answers[(method, path.split("?", 1)[0])]
        return answer if isinstance(answer, tuple) else (200, answer)


def _lemlist() -> Script:
    export = "/v2/campaigns/cam_1/export/leads"
    return Script(
        {
            ("GET", export): LEADS,
            ("POST", "/leads/lea_1/variables"): {"ok": True},
            ("PATCH", "/leads/lea_1/variables"): {"ok": True},
            ("POST", "/leads/lea_3/variables"): {"ok": True},
            ("PATCH", "/leads/lea_3/variables"): {"ok": True},
        }
    )


def _specstream_start(maximum: int) -> Script:
    return Script(
        {
            ("POST", "/v1/imports/file"): {
                "data": {"id": "imp_1", "rows": [{"id": "r1"}, {"id": "r3"}]}
            },
            ("POST", "/v1/parse"): {"data": {"ast_hash": "a" * 64}},
            ("POST", "/v1/capacity/quotes"): {
                "data": {"quote_id": "q_1", "quote_hash": "b" * 64, "maximum_cents": maximum}
            },
            ("POST", "/v1/capacity/executions"): (202, {"data": {"find_id": "fnd_1"}}),
        }
    )


def test_start_sends_researchable_leads_without_email_and_approves_the_quote() -> None:
    specstream = _specstream_start(30)
    started = EnrichStep(specstream, _lemlist()).start("cam_1", FACTS, 50, "req-9")

    assert started["state"] == "started"
    assert started["find_id"] == "fnd_1"
    assert started["skipped"] == ["lea_2"]
    imported = specstream.calls[0][2]
    assert imported is not None
    rows = list(csv.DictReader(io.StringIO(imported["content"])))
    assert [row["lead_ref"] for row in rows] == ["lea_1", "lea_3"]
    assert rows[0]["website"] == "engines.example"
    assert "@" not in imported["content"]
    assert specstream.calls[1][2] == {
        "q": "For the 2 people: Company headcount, Work email",
        "locale": "en-US",
    }
    assert specstream.calls[2][2]["source_row_ids"] == ["r1", "r3"]  # type: ignore[index]
    assert specstream.calls[3][2]["confirm_max_cents"] == 30  # type: ignore[index]

    again = _specstream_start(30)
    EnrichStep(again, _lemlist()).start("cam_1", FACTS, 50, "req-9")
    assert again.calls[0][2] == imported
    assert again.calls[3][2] == specstream.calls[3][2]


def test_start_above_the_maximum_runs_nothing() -> None:
    specstream = _specstream_start(75)
    started = EnrichStep(specstream, _lemlist()).start("cam_1", FACTS, 50, "req-9")

    assert started["state"] == "above_maximum"
    assert started["maximum_cents"] == 75
    assert all(path != "/v1/capacity/executions" for _, path, _ in specstream.calls)


def test_a_refused_lemlist_key_stops_before_specstream() -> None:
    lemlist = Script(
        {("GET", "/v2/campaigns/cam_1/export/leads"): (401, {"error": "Unauthorized"})}
    )
    specstream = _specstream_start(30)
    with pytest.raises(StepError) as raised:
        EnrichStep(specstream, lemlist).start("cam_1", FACTS, 50, "req-9")
    assert raised.value.status == 401
    assert specstream.calls == []


@pytest.mark.parametrize(
    "text",
    ["Work email=email", "Company=companyName", "Headcount", "Headcount=2fast", "x=fooSource"],
)
def test_lead_fields_and_bad_names_are_refused(text: str) -> None:
    with pytest.raises(StepError):
        parse_fact(text)


def _specstream_rows(status: str) -> Script:
    return Script(
        {
            ("GET", "/v1/finds/fnd_1/rows"): {
                "data": {
                    "status": status,
                    "next_cursor": None,
                    "flat_rows": [
                        {
                            "id": "fnd_1:ent_a",
                            "source_url": "https://engines.example/about",
                            "Company Headcount": "45",
                            "Company Headcount_source": "https://engines.example/team",
                            "email": "ada@engines.example",
                            "email_source": "https://engines.example/contact",
                        },
                        {
                            "id": "fnd_1:ent_c",
                            "source_url": "https://bletchley.example",
                            "Company headcount": "30",
                            "email": "alan@bletchley.example",
                        },
                    ],
                }
            },
            ("GET", "/v1/workspace/collections/fnd_1/input"): {
                "data": {
                    "rows": [
                        {"entity_id": "ent_a", "provided": {"lead_ref": {"value": "lea_1"}}},
                        {"entity_id": "ent_c", "provided": {"lead_ref": "lea_3"}},
                    ]
                }
            },
        }
    )


def _query(path: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlsplit(path).query).items()}


def test_finish_waits_for_the_find() -> None:
    lemlist = _lemlist()
    result = EnrichStep(_specstream_rows("running"), lemlist).finish("fnd_1", "cam_1", FACTS)

    assert result == {"find_id": "fnd_1", "status": "processing"}
    assert lemlist.calls == []


def test_finish_writes_found_facts_with_their_pages_and_keeps_filled_values() -> None:
    lemlist = _lemlist()
    result = EnrichStep(_specstream_rows("completed"), lemlist).finish("fnd_1", "cam_1", FACTS)

    writes = {(method, path.split("?")[0]): _query(path) for method, path, _ in lemlist.calls[1:]}
    assert writes[("POST", "/leads/lea_1/variables")] == {
        "companyHeadcountSource": "https://engines.example/team",
        "workEmail": "ada@engines.example",
        "workEmailSource": "https://engines.example/contact",
    }
    # The lead has the variable, empty: it is changed, not added.
    assert writes[("PATCH", "/leads/lea_1/variables")] == {"companyHeadcount": "45"}
    # lea_3 already holds a headcount: kept without --overwrite.
    assert ("PATCH", "/leads/lea_3/variables") not in writes
    assert writes[("POST", "/leads/lea_3/variables")] == {
        "workEmail": "alan@bletchley.example",
        "workEmailSource": "https://bletchley.example",
    }
    assert result["leads_written"] == 2
    assert result["values_written"] == 3


def test_finish_with_overwrite_replaces_a_filled_value() -> None:
    lemlist = _lemlist()
    EnrichStep(_specstream_rows("completed"), lemlist).finish(
        "fnd_1", "cam_1", FACTS, overwrite=True
    )

    patches = [_query(path) for method, path, _ in lemlist.calls if method == "PATCH"]
    assert {"companyHeadcount": "30"} in patches


def test_lemlist_auth_is_basic_with_an_empty_user(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake(request: Any, timeout: float, retries: int) -> tuple[int, Any]:
        seen.update(dict(request.header_items()))
        return 200, []

    monkeypatch.setattr(step_module, "_call_json", fake)
    step_module.lemlist_transport("k3y")("GET", "/team", None)
    assert seen["Authorization"] == "Basic OmszeQ=="
