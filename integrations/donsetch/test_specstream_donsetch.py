"""The DonSeTch search plugin: format 1 in, format 1 out, with the Search API scripted."""

import importlib.util
import io
import json
import subprocess
import sys
import urllib.error
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "specstream_donsetch.py"
spec = importlib.util.spec_from_file_location("specstream_donsetch", SCRIPT)
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)

REQUEST = {"format": 1, "query": "rust async", "max_results": 8, "intent": "web", "deadline_ms": 30000}
PAGE = {
    "data": {
        "query": "rust async",
        "sources": [
            {"url": "https://a.example/one", "title": "One", "site": "a.example", "snippet": "first"},
            {"url": "ftp://b.example/two", "title": "Bad scheme", "site": "b.example", "snippet": ""},
            {"url": "https://c.example/three", "title": "", "site": "c.example", "snippet": "", "excerpt": "third"},
            {"url": "https://d.example/four", "title": "Four", "site": "d.example", "snippet": ""},
        ],
    }
}


class Recorder:
    def __init__(self, status=200, body=PAGE, raises=None):
        self.status, self.body, self.raises, self.calls = status, body, raises, []

    def __call__(self, url, key, timeout):
        self.calls.append((url, key, timeout))
        if self.raises:
            raise self.raises
        body = self.body if isinstance(self.body, bytes) else json.dumps(self.body).encode()
        return self.status, body


def run(request=REQUEST, argv=(), env=None, get=None):
    out = io.StringIO()
    stdin = io.StringIO(request if isinstance(request, str) else json.dumps(request))
    env = {"SPECSTREAM_API_KEY": "test-key"} if env is None else env
    code = plugin.main(list(argv), stdin, out, env, get or Recorder())
    assert code == 0
    return json.loads(out.getvalue())


def test_results_follow_the_format():
    get = Recorder()
    reply = run(get=get)
    assert reply["format"] == 1
    assert [r["url"] for r in reply["results"]] == [
        "https://a.example/one",
        "https://c.example/three",
        "https://d.example/four",
    ]
    assert reply["results"][1] == {"title": "c.example", "url": "https://c.example/three", "snippet": "third", "score": 0.95}
    assert reply["results"][0]["score"] == 1.0
    url, key, timeout = get.calls[0]
    assert key == "test-key"
    assert timeout == 29.0
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    assert url.startswith("https://api.specstream.ai/v1/web-search?")
    assert query == {"q": "rust async", "num": "8", "speed": "fast"}


def test_num_is_capped_and_news_intent_asks_for_news():
    get = Recorder()
    run(dict(REQUEST, max_results=50, intent="news"), argv=["--speed", "default"], get=get)
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(get.calls[0][0]).query))
    assert query == {"q": "rust async", "num": "10", "news": "true"}


def test_key_file(tmp_path):
    key_file = tmp_path / "api-key"
    key_file.write_text("file-key\n")
    get = Recorder()
    run(argv=["--key-file", str(key_file)], env={}, get=get)
    assert get.calls[0][1] == "file-key"
    get = Recorder()
    run(env={"SPECSTREAM_API_KEY_FILE": str(key_file)}, get=get)
    assert get.calls[0][1] == "file-key"


def test_no_key_parks_the_plugin():
    get = Recorder()
    reply = run(env={}, get=get)
    assert reply["error_kind"] == "invalid_key"
    assert reply["retryable"] is False
    assert get.calls == []


def test_http_errors_map_to_error_kinds():
    cases = [
        (401, {"error": {"code": "invalid_api_key", "message": "Bad key."}}, "invalid_key", False),
        (402, {"error": {"code": "insufficient_balance", "message": "Add credit."}}, "credit_depleted", False),
        (429, {"error": {"code": "rate_limited", "message": "Slow down."}}, "rate_limited", True),
        (503, b"<html>", "server_error", True),
    ]
    for status, body, kind, retryable in cases:
        reply = run(get=Recorder(status, body))
        assert reply["error_kind"] == kind, status
        assert reply["retryable"] is retryable
        assert reply["error"].startswith("SpecStream: ")
    reply = run(get=Recorder(400, {"error": {"code": "invalid_request", "message": "Too long."}}))
    assert "error_kind" not in reply and reply["retryable"] is False and reply["error"] == "SpecStream: Too long."


def test_network_failure_is_retryable():
    reply = run(get=Recorder(raises=urllib.error.URLError("down")))
    assert reply == {"format": 1, "error": "could not reach SpecStream: down", "retryable": True, "error_kind": "network_error"}


def test_bad_requests():
    assert "not a JSON request" in run("nope")["error"]
    assert "unsupported format" in run(dict(REQUEST, format=2))["error"]
    assert "no query" in run(dict(REQUEST, query="  "))["error"]
    assert "--speed" in run(argv=["--speed", "turbo"])["error"]


def test_script_runs_as_donsetch_runs_it():
    done = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(REQUEST),
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
        timeout=30,
    )
    assert done.returncode == 0
    assert json.loads(done.stdout)["error_kind"] == "invalid_key"
