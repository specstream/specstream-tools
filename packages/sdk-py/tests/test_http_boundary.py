from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from specstream_client.client import Client, SpecstreamError


@pytest.fixture
def endpoint():
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            if self.path.endswith("/redirect"):
                self.send_response(302)
                self.send_header("Location", "/unexpected")
                self.end_headers()
                return
            cases = {
                "error": (200, '{"error":{"code":"capacity"}}'),
                "null": (200, '{"data":null}'),
                "array": (200, "[]"),
                "html": (503, "<html>unavailable</html>"),
                "empty": (200, ""),
            }
            status, body = cases.get(
                self.path.rsplit("/", 1)[-1], (200, '{"data":{"status":"completed"}}')
            )
            busy = self.path.endswith("/busy") and seen.count(self.path) == 1
            if busy:
                status, body = 503, '{"error":{"code":"capacity"}}'
            self.send_response(status)
            if busy:
                self.send_header("Retry-After", "0")
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_error_envelopes_and_malformed_successes_are_not_deliveries(endpoint):
    origin, seen = endpoint
    client = Client("offline", base_url=origin)
    for case in ("error", "null", "array", "empty"):
        with pytest.raises(SpecstreamError) as failed:
            client.get_find(case)
        assert failed.value.status == 200
    with pytest.raises(SpecstreamError) as unavailable:
        client.get_find("html")
    assert unavailable.value.status == 503
    assert unavailable.value.body == "<html>unavailable</html>"
    assert client.get_find("valid")["status"] == "completed"
    assert client.get_find("busy")["status"] == "completed"
    assert seen.count("/v1/finds/html") == 1
    assert seen.count("/v1/finds/busy") == 2


def test_redirect_does_not_forward_account_authority(endpoint):
    origin, seen = endpoint
    with pytest.raises(SpecstreamError) as failed:
        Client("offline", base_url=origin).get_find("redirect")
    assert failed.value.status == 302
    assert seen == ["/v1/finds/redirect"]


def test_paid_confirmation_rejects_coercion_before_network():
    def refused(*_args):
        pytest.fail("invalid confirmation reached the network")

    client = Client("offline", opener=refused)
    for value in (True, float("inf"), float("nan"), [19], {"amount": 19}):
        with pytest.raises(ValueError):
            client.authorize_capacity_work(
                {
                    "quote_id": "cqt_test",
                    "quote_hash": "a" * 64,
                    "idempotency_key": "stable-request",
                    "confirm_max_cents": value,
                }
            )
