"""Canonical client identity, explicit authorization, pagination and no hidden funding."""

from __future__ import annotations

import io
import json
import unittest
from typing import Any

from specstream_client.client import Client
from specstream_client.families import FAMILIES, assert_family


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self.status = status
        self._buf = io.BytesIO(json.dumps({"data": payload}).encode())

    def read(self) -> bytes:
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class ClientTests(unittest.TestCase):
    def test_public_families(self):
        self.assertEqual(len(FAMILIES), len(set(FAMILIES)))
        for family in ("software_repository", "dataset", "organization", "grant", "tender"):
            self.assertIn(family, FAMILIES)
        self.assertNotIn("company", FAMILIES)

    def test_any_kind_name_is_a_valid_entity_type(self):
        self.assertEqual(assert_family("organization"), "organization")
        self.assertEqual(assert_family("wine_estate"), "wine_estate")
        with self.assertRaises(ValueError):
            assert_family("  ")

    def test_no_obsolete_spending_or_sample_methods(self):
        client = Client("fixture-key")
        for name in ("quote", "confirm", "run", "create_find", "continue_find", "start_spec_find"):
            self.assertFalse(hasattr(client, name), name)

    def test_authorization_rejects_implicit_or_invalid_money_before_network(self):
        def no_network(*args, **kwargs):
            self.fail("Invalid approval reached the transport")

        client = Client("fixture-key", opener=no_network)
        for amount in (True, None, -1, 1.2, float("inf"), float("nan"), "1900"):
            with self.assertRaises(ValueError):
                client.authorize_capacity_work(
                    {
                        "quote_id": "cqt_fixture",
                        "quote_hash": "a" * 64,
                        "idempotency_key": "stable-review-001",
                        "confirm_max_cents": amount,
                    }
                )
        with self.assertRaises(ValueError):
            client.authorize_capacity_work({"quote_id": "cqt_fixture", "quote_hash": "a" * 64})

    def test_compile_quote_approve_and_recover_same_work(self):
        calls = []
        offer = {"quote_id": "cqt_fixture", "quote_hash": "a" * 64, "maximum_cents": 900}
        approval = {
            "quote_id": "cqt_fixture",
            "quote_hash": "a" * 64,
            "confirm_max_cents": 900,
            "idempotency_key": "stable-review-001",
        }

        def opener(request, timeout):
            body = json.loads(request.data) if request.data else None
            calls.append((request.get_method(), request.full_url, body))
            if request.full_url.endswith("/parse"):
                return _FakeResponse(
                    {"ast_hash": "b" * 64, "ast": {"entity_type": "scholarly_work"}}
                )
            if request.full_url.endswith("/capacity/quotes"):
                return _FakeResponse(offer)
            if request.full_url.endswith("/capacity/executions"):
                self.assertEqual(body, approval)
                return _FakeResponse({"find_id": "fnd_fixture", "state": "running"}, 202)
            if request.full_url.endswith("/requests/stable-review-001"):
                return _FakeResponse({"find_id": "fnd_fixture", "state": "committed"})
            self.fail(request.full_url)

        client = Client("fixture-key", opener=opener)
        result = client.compile("papers with a DOI")
        client.quote_capacity_work({"ast_hash": result["ast_hash"], "requested_units": 5})
        self.assertEqual(len(calls), 2)
        self.assertEqual(client.authorize_capacity_work(approval)["find_id"], "fnd_fixture")
        self.assertEqual(client.get_capacity_request("stable-review-001")["find_id"], "fnd_fixture")
        self.assertFalse(any("/funding" in path or "/run" in path for _, path, _ in calls))
