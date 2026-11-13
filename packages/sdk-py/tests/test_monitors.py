"""Monitor calls: one list checked again on a schedule, within limits a person set."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from specstream_client import Client, SpecstreamError, verify_webhook

NOW = datetime(2026, 11, 13, 10, 42, 7, tzinfo=UTC)


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.status = 200
        self._buf = io.BytesIO(json.dumps({"data": payload}).encode())

    def read(self) -> bytes:
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class _Api:
    """Scripted API: answers by (method, path) and records each request."""

    def __init__(self, answers: dict[tuple[str, str], list[dict[str, Any]]]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str, dict[str, list[str]], Any]] = []

    def __call__(self, request, timeout):
        parts = urlsplit(request.full_url)
        body = json.loads(request.data) if request.data else None
        self.calls.append((request.get_method(), parts.path, parse_qs(parts.query), body))
        queue = self.answers[(request.get_method(), parts.path)]
        return _Response(queue.pop(0) if len(queue) > 1 else queue[0])


def _schedule(**extra: Any) -> dict[str, Any]:
    data = {
        "schedule_id": "sch_1",
        "state": "active",
        "version": 3,
        "cadence_seconds": 86_400,
        "next_due_at": "2026-11-14T10:00:00Z",
        "per_run_cents": 200,
        "period_cents": 6_200,
        "valid_until": "2027-11-14T10:00:00Z",
        "scope": {"parent_find_id": "fnd_1", "ast_hash": "h" * 64},
    }
    data.update(extra)
    return data


def _client(api: _Api) -> Client:
    client = Client("fixture-key", base_url="https://api.example.test", opener=api)
    client.clock = lambda: NOW
    return client


def test_monitor_list_prices_one_check_then_saves_a_daily_schedule():
    api = _Api(
        {
            ("GET", "/v1/finds/fnd_1"): [
                {"ast_hash": "h" * 64, "requested_count": 40, "project_id": "prj_9"}
            ],
            ("POST", "/v1/capacity/quotes"): [{"maximum_cents": 150}],
            ("POST", "/v1/capacity/schedules"): [_schedule()],
        }
    )
    client = _client(api)
    monitor = client.monitor_list("fnd_1", max_price_per_run_usd=2)

    assert monitor["status"] == "saved"
    assert monitor["monitor_id"] == "sch_1"
    assert monitor["list_id"] == "fnd_1"
    assert monitor["max_price_per_run_usd"] == 2.0
    quote = api.calls[1][3]
    assert quote == {
        "ast_hash": "h" * 64,
        "operation": "refresh",
        "parent_find_id": "fnd_1",
        "requested_units": 40,
        "project_id": "prj_9",
    }
    saved = api.calls[2][3]
    assert saved["cadence_seconds"] == 86_400
    assert saved["per_run_cents"] == 200
    assert saved["period_cents"] == 200 * 31
    assert saved["first_due_at"] == "2026-11-14T10:00:00Z"
    assert saved["valid_until"] == "2027-11-14T10:00:00Z"
    assert saved["scope"] == quote
    assert saved["idempotency_key"].startswith("python-monitor-")

    # The same call in the same hour sends the same key, so a retry saves nothing new.
    again = _Api(
        {
            ("GET", "/v1/finds/fnd_1"): [
                {"ast_hash": "h" * 64, "requested_count": 40, "project_id": "prj_9"}
            ],
            ("POST", "/v1/capacity/quotes"): [{"maximum_cents": 150}],
            ("POST", "/v1/capacity/schedules"): [_schedule()],
        }
    )
    _client(again).monitor_list("fnd_1", max_price_per_run_usd=2)
    assert again.calls[2][3]["idempotency_key"] == saved["idempotency_key"]


def test_monitor_list_saves_nothing_when_one_check_can_cost_more():
    api = _Api(
        {
            ("GET", "/v1/finds/fnd_1"): [{"ast_hash": "h" * 64}],
            ("POST", "/v1/capacity/quotes"): [{"maximum_cents": 500}],
        }
    )
    answer = _client(api).monitor_list("fnd_1", max_price_per_run_usd=2, every="week")
    assert answer["status"] == "over_maximum"
    assert answer["maximum_price_usd"] == 5.0
    assert "$5.00" in answer["message"] and "$2.00" in answer["message"]
    assert [call[:2] for call in api.calls] == [
        ("GET", "/v1/finds/fnd_1"),
        ("POST", "/v1/capacity/quotes"),
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_price_per_run_usd": 2, "every": "minute"},
        {"max_price_per_run_usd": 0},
        {"max_price_per_run_usd": float("nan")},
        {"max_price_per_run_usd": 2, "max_price_per_month_usd": 1},
        {
            "max_price_per_run_usd": 2,
            "first_run_at": "2026-12-01T00:00:00Z",
            "ends_at": "2026-11-30T00:00:00Z",
        },
        {"max_price_per_run_usd": 2, "first_run_at": "2026-12-01T00:00:00"},
    ],
)
def test_monitor_list_refuses_bad_limits_before_any_request(kwargs):
    def no_network(*args, **kwargs):
        raise AssertionError("a bad limit reached the network")

    with pytest.raises(ValueError):
        _client(no_network).monitor_list("fnd_1", **kwargs)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _client(no_network).monitor_list("  ", max_price_per_run_usd=2)


def test_monitors_follow_every_page():
    api = _Api(
        {
            ("GET", "/v1/capacity/schedules"): [
                {"schedules": [_schedule()], "next_after": "cur_1"},
                {"schedules": [_schedule(schedule_id="sch_2", state="paused")], "next_after": None},
            ]
        }
    )
    found = _client(api).monitors(project_id="prj_9")
    assert [item["monitor_id"] for item in found] == ["sch_1", "sch_2"]
    assert found[1]["state"] == "paused"
    assert api.calls[1][2] == {"project_id": ["prj_9"], "after": ["cur_1"], "limit": ["100"]}


def test_pause_resume_and_delete_send_the_current_version():
    for call, state in (
        ("pause_monitor", "paused"),
        ("resume_monitor", "active"),
        ("delete_monitor", "deleted"),
    ):
        api = _Api(
            {
                ("GET", "/v1/capacity/schedules"): [{"schedules": [_schedule()]}],
                ("PATCH", "/v1/capacity/schedules/sch_1"): [_schedule(state=state, version=4)],
            }
        )
        result = getattr(_client(api), call)("sch_1")
        assert result["state"] == state and result["version"] == 4
        assert api.calls[-1][3] == {"expected_version": 3, "state": state}


def test_unknown_monitor_is_an_error_not_a_write():
    api = _Api({("GET", "/v1/capacity/schedules"): [{"schedules": [_schedule()]}]})
    with pytest.raises(SpecstreamError):
        _client(api).pause_monitor("sch_missing")
    assert all(call[0] == "GET" for call in api.calls)


def test_runs_and_run_now():
    api = _Api(
        {
            ("GET", "/v1/capacity/schedules/sch_1/occurrences"): [
                {
                    "occurrences": [
                        {
                            "due_at": "2026-11-13T10:00:00Z",
                            "status": "completed",
                            "find_id": "fnd_2",
                        },
                        {
                            "due_at": "2026-11-12T10:00:00Z",
                            "status": "blocked",
                            "reason": "balance",
                        },
                    ]
                }
            ],
            ("POST", "/v1/capacity/schedules/sch_1/run"): [
                {"find_id": "fnd_3", "started_at": "2026-11-13T10:43:00Z"}
            ],
        }
    )
    client = _client(api)
    runs = client.monitor_runs("sch_1", limit=500)
    assert runs[0] == {
        "due_at": "2026-11-13T10:00:00Z",
        "status": "completed",
        "reason": None,
        "list_id": "fnd_2",
    }
    assert runs[1]["reason"] == "balance" and runs[1]["list_id"] is None
    assert api.calls[0][2] == {"limit": ["100"]}
    assert client.run_monitor_now("sch_1") == {
        "monitor_id": "sch_1",
        "list_id": "fnd_3",
        "started_at": "2026-11-13T10:43:00Z",
    }


def test_set_monitor_delivery_sends_only_what_was_given():
    api = _Api(
        {
            ("GET", "/v1/capacity/schedules"): [{"schedules": [_schedule()]}],
            ("PATCH", "/v1/workspace/schedules/sch_1/delivery"): [
                {
                    "schedule_id": "sch_1",
                    "version": 4,
                    "delivery": {},
                    "webhook_secret": "whsec_fixture",
                }
            ],
        }
    )
    answer = _client(api).set_monitor_delivery("sch_1", webhook="https://hooks.example.test/in")
    assert answer["webhook_secret"] == "whsec_fixture"
    assert api.calls[-1][3] == {
        "expected_version": 3,
        "notify": True,
        "webhook": "https://hooks.example.test/in",
    }


def _signed(secret: str, stamp: int, body: bytes) -> str:
    digest = hmac.new(
        secret.encode(), str(stamp).encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    return f"t={stamp},v1={digest}"


def test_verify_webhook_accepts_a_signed_recent_body_and_refuses_the_rest():
    body = b'{"event":"monitor.found","rows":[]}'
    stamp = 1_800_000_000
    header = _signed("whsec_fixture", stamp, body)
    assert verify_webhook(secret="whsec_fixture", signature=header, body=body, now=stamp + 10)
    assert verify_webhook(secret="whsec_fixture", signature=header, body=body.decode(), now=stamp)
    for kwargs in (
        {"secret": "whsec_other", "signature": header, "body": body, "now": stamp},
        {"secret": "whsec_fixture", "signature": header, "body": body + b" ", "now": stamp},
        {"secret": "whsec_fixture", "signature": header, "body": body, "now": stamp + 301},
        {"secret": "whsec_fixture", "signature": "v1=abc", "body": body, "now": stamp},
        {"secret": "", "signature": header, "body": body, "now": stamp},
    ):
        with pytest.raises(SpecstreamError):
            verify_webhook(**kwargs)
