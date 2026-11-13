"""The Kong plugin, run in LuaJIT with a scripted Kong and a scripted SpecStream API.

Each test sends one request through the plugin's access phase and reads two things: what the
gateway answered, and which calls it made to SpecStream. No test opens a connection.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

try:  # Kong runs LuaJIT 2.1; the wheel carries it beside the newer Lua versions.
    from lupa import luajit21 as lupa
except ImportError:  # pragma: no cover - a platform whose wheel has no LuaJIT
    import lupa

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "rr_0123456789abcdef01234567"
KEY = "test-key-not-real"

HARNESS = r"""
local array_mt = {}
local null = setmetatable({}, { __tostring = function() return "null" end })

function is_array(t) return getmetatable(t) == array_mt or t[1] ~= nil end
function is_null(v) return v == null end
function new_array() return setmetatable({}, array_mt) end
function get_null() return null end

-- lua-cjson as Kong ships it, as far as the plugin uses it.
local array_with_mt = false
local cjson = {}
function cjson.new() return cjson end
function cjson.decode_array_with_array_mt(on) array_with_mt = on end
function cjson.decode(text)
  if type(text) ~= "string" then return nil, "not a string" end
  local ok, value = py_decode(text, array_with_mt)
  if not ok then return nil, "not JSON" end
  return value
end
function cjson.encode(value) return py_encode(value) end
package.preload["cjson.safe"] = function() return cjson end

calls, responses, sleeps, logs = {}, {}, {}, {}
exit, request = nil, {}
local clock = 1000

package.preload["resty.http"] = function()
  return {
    new = function()
      local client = { timeout = nil }
      function client:set_timeout(ms) self.timeout = ms end
      function client:request_uri(uri, options)
        calls[#calls + 1] = {
          uri = uri, method = options.method, body = options.body, headers = options.headers,
          ssl_verify = options.ssl_verify, timeout = self.timeout,
        }
        local res = table.remove(responses, 1)
        if res == nil then error("the plugin made a call the test did not script: " .. uri) end
        if res.err then return nil, res.err end
        return { status = res.status, body = res.body }
      end
      return client
    end,
  }
end

ngx = {
  now = function() return clock end,
  sleep = function(seconds) sleeps[#sleeps + 1] = seconds; clock = clock + seconds end,
}

local function log(level)
  return function(...)
    local parts = {}
    for i = 1, select("#", ...) do parts[#parts + 1] = tostring((select(i, ...))) end
    logs[#logs + 1] = level .. ": " .. table.concat(parts)
  end
end

kong = {
  request = {
    get_method = function() return request.method end,
    get_path = function() return request.path end,
    get_raw_body = function() return request.body end,
    get_header = function(name) return request.headers and request.headers[name] end,
  },
  response = {
    -- In Kong this call ends the request; nothing after it runs.
    exit = function(status, body, headers)
      exit = { status = status, body = body, headers = headers }
      error({ ended = true })
    end,
  },
  log = { err = log("err"), warn = log("warn") },
}

function run(conf)
  local handler = require "kong.plugins.specstream-research.handler"
  local ok, why = pcall(handler.access, handler, conf)
  if not ok and not (type(why) == "table" and why.ended) then error(why) end
  return ok
end
"""


class Gateway:
    """One Lua state that holds the plugin, a scripted Kong and a scripted SpecStream API."""

    def __init__(self) -> None:
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        g = self.lua.globals()
        g.py_decode = self._decode
        g.py_encode = lambda value: json.dumps(self.to_py(value))
        self.lua.execute(HARNESS)
        g.package.path = f"{ROOT}/?.lua;" + g.package.path
        self.conf = {
            "api_key": KEY,
            "default_depth": "standard",
            "max_depth": "deep",
            "wait_seconds": 0,
            "poll_seconds": 3,
            "timeout_ms": 30000,
            "ssl_verify": True,
        }

    def _decode(self, text: str, array_with_mt: bool) -> tuple[bool, Any]:
        try:
            return True, self.to_lua(json.loads(text), array_with_mt)
        except ValueError:
            return False, None

    def to_lua(self, value: Any, array_with_mt: bool = True) -> Any:
        g = self.lua.globals()
        if value is None:
            return g.get_null()
        if isinstance(value, list):
            # Without the array metatable an empty array decodes to a plain table, as in lua-cjson.
            table = g.new_array() if array_with_mt else self.lua.table()
            for index, item in enumerate(value, 1):
                table[index] = self.to_lua(item, array_with_mt)
            return table
        if isinstance(value, dict):
            table = self.lua.table()
            for name, item in value.items():
                table[name] = self.to_lua(item, array_with_mt)
            return table
        return value

    def to_py(self, value: Any) -> Any:
        g = self.lua.globals()
        if lupa.lua_type(value) != "table":
            if isinstance(value, float) and value.is_integer():
                return int(value)
            return value
        if g.is_null(value):
            return None
        if g.is_array(value):
            return [self.to_py(value[index]) for index in range(1, len(value) + 1)]
        return {name: self.to_py(item) for name, item in value.items()}

    def script(self, *responses: tuple[int, Any] | str) -> None:
        """What SpecStream answers, in order. A string is a network failure."""
        g = self.lua.globals()
        for response in responses:
            if isinstance(response, str):
                entry = self.lua.table(err=response)
            else:
                status, body = response
                entry = self.lua.table(status=status, body=body if isinstance(body, str) else json.dumps(body))
            g.table.insert(g.responses, entry)

    def send(
        self, method: str, path: str = "/research", body: Any = None, headers: dict[str, str] | None = None
    ) -> tuple[int, Any]:
        g = self.lua.globals()
        text = body if isinstance(body, str) or body is None else json.dumps(body)
        g.request = self.lua.table(
            method=method, path=path, body="" if text is None else text, headers=self.lua.table_from(headers or {})
        )
        g.exit = None
        g.run(self.lua.table_from(self.conf))
        assert g.exit is not None, "the plugin let the request through to the service"
        assert len(g.responses) == 0, "the plugin did not make every scripted call"
        assert "application/json" in g.exit.headers["Content-Type"]
        return g.exit.status, json.loads(g.exit.body)

    @property
    def calls(self) -> list[dict[str, Any]]:
        return [self.to_py(call) for call in self.lua.globals().calls.values()]

    @property
    def sleeps(self) -> list[float]:
        return list(self.lua.globals().sleeps.values())

    @property
    def logs(self) -> list[str]:
        return list(self.lua.globals().logs.values())

    @property
    def exit_headers(self) -> dict[str, str]:
        return dict(self.lua.globals().exit.headers.items())


@pytest.fixture
def gateway() -> Gateway:
    return Gateway()


def created(status: str = "queued", depth: str = "standard") -> dict[str, Any]:
    return {
        "id": RUN_ID,
        "status": status,
        "depth": depth,
        "price_usd": 0.3,
        "created_at": "2026-11-13T03:00:00Z",
        "links": {"self": f"/v1/research/{RUN_ID}", "events": f"/v1/research/{RUN_ID}/events"},
    }


def run(status: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": RUN_ID,
        "status": status,
        "stage": "done" if status == "completed" else "reading",
        "depth": "standard",
        "progress": {"searches": 4, "pages_read": 9, "sources": 2},
        "created_at": "2026-11-13T03:00:00Z",
        "usage": {"searches": 4, "pages_read": 9, "charged_usd": 0.3 if status == "completed" else 0.0},
        "metadata": {},
    }
    if status == "completed":
        body["report"] = {
            "title": "Sugar taxes in the EU",
            "format": "markdown",
            "content": "France taxes sugary drinks [1].",
            "structured": None,
            "citations": [
                {
                    "n": 1,
                    "url": "https://example.org/tax",
                    "title": "Tax",
                    "read_at": "2026-11-13T03:01:00Z",
                    "excerpt": "France taxes sugary drinks.",
                    "start": 0,
                    "end": 30,
                    "supported": True,
                }
            ],
            "sources": [
                {"n": 1, "url": "https://example.org/tax", "title": "Tax", "read_at": "2026-11-13T03:01:00Z", "cited": True}
            ],
            "basis": [],
        }
    return body


def test_post_starts_a_report_and_answers_with_its_id(gateway: Gateway) -> None:
    gateway.script((202, created()))
    status, body = gateway.send("POST", body={"input": "  Which EU countries tax sugary drinks?  "})

    assert (status, body) == (202, created())
    (call,) = gateway.calls
    assert (call["method"], call["uri"]) == ("POST", "https://api.specstream.ai/v1/research")
    assert json.loads(call["body"]) == {"input": "Which EU countries tax sugary drinks?", "depth": "standard"}
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["headers"]["User-Agent"] == "kong-plugin-specstream-research/0.1.0"
    assert "Idempotency-Key" not in call["headers"]
    assert (call["ssl_verify"], call["timeout"]) == (True, 30000)
    assert gateway.sleeps == []


def test_the_request_fields_reach_the_api_and_an_empty_list_stays_a_list(gateway: Gateway) -> None:
    asked = {
        "question": "Who makes heat pumps in Poland?",
        "depth": "quick",
        "length": "short",
        "language": "pl",
        "include_domains": [],
        "exclude_domains": ["example.com"],
        "after_date": "2026-01-31",
        "output": {"type": "json", "schema": {"type": "object", "properties": {}, "required": []}},
        "metadata": {"team": "sales"},
        "webhook": {"url": "https://attacker.example/hook"},
    }
    gateway.script((202, created(depth="quick")))
    status, _ = gateway.send("POST", body=asked, headers={"Idempotency-Key": "order-17"})

    assert status == 202
    (call,) = gateway.calls
    sent = json.loads(call["body"])
    expected = {name: value for name, value in asked.items() if name not in ("question", "webhook")}
    expected["input"] = "Who makes heat pumps in Poland?"
    assert sent == expected
    assert call["headers"]["Idempotency-Key"] == "order-17"


@pytest.mark.parametrize(
    ("body", "words"),
    [
        ("not json", 'Send a JSON object with the question in "input".'),
        ("[1, 2]", 'Write the question the report answers in "input".'),
        ({}, 'Write the question the report answers in "input".'),
        ({"input": "   "}, 'Write the question the report answers in "input".'),
        ({"input": 7}, 'Write the question the report answers in "input".'),
        ({"input": "x" * 15001}, "The question holds 15001 bytes. The most is 15000."),
        ({"input": "q", "depth": "deepest"}, "depth must be one of: quick, standard, deep."),
        ({"input": "q", "depth": 3}, "depth must be one of: quick, standard, deep."),
    ],
)
def test_a_request_the_api_would_refuse_never_leaves_the_gateway(gateway: Gateway, body: Any, words: str) -> None:
    assert gateway.send("POST", body=body) == (400, {"message": words})
    assert gateway.calls == []


def test_the_route_sets_the_default_depth_and_its_ceiling(gateway: Gateway) -> None:
    gateway.conf.update(default_depth="quick", max_depth="standard")
    gateway.script((202, created(depth="quick")))
    gateway.send("POST", body={"input": "q"})
    assert json.loads(gateway.calls[0]["body"])["depth"] == "quick"

    status, body = gateway.send("POST", body={"input": "q", "depth": "deep"})
    assert (status, body) == (400, {"message": 'This route allows reports up to depth "standard".'})
    assert len(gateway.calls) == 1


def test_get_reads_a_report_with_its_sources(gateway: Gateway) -> None:
    gateway.script((200, run("completed")))
    status, body = gateway.send("GET", f"/research/{RUN_ID}")

    assert status == 200
    assert body == run("completed")
    assert body["report"]["citations"][0]["url"] == "https://example.org/tax"
    (call,) = gateway.calls
    assert (call["method"], call["uri"]) == ("GET", f"https://api.specstream.ai/v1/research/{RUN_ID}")
    assert "body" not in call
    assert "Content-Type" not in call["headers"]


@pytest.mark.parametrize(("state", "status"), [("queued", 202), ("running", 202), ("failed", 200), ("cancelled", 200), ("payment_required", 402)])
def test_the_status_of_a_read_follows_the_state_of_the_report(gateway: Gateway, state: str, status: int) -> None:
    gateway.script((200, run(state)))
    assert gateway.send("GET", f"/research/{RUN_ID}/")[0] == status


@pytest.mark.parametrize("path", ["/research", "/research/", "/research/abc", "/research/rr_", "/research/rr_12/../x", "/research/rr_a.b", "/research/rr_" + "a" * 70])
def test_a_path_without_a_report_id_calls_nothing(gateway: Gateway, path: str) -> None:
    for method in ("GET", "DELETE"):
        status, body = gateway.send(method, path)
        assert status == 400
        assert body == {"message": "Put the report ID at the end of the path, such as /rr_0123abcd."}
    assert gateway.calls == []


def test_delete_cancels_a_report(gateway: Gateway) -> None:
    gateway.script((200, run("cancelled")))
    status, body = gateway.send("DELETE", f"/research/{RUN_ID}")

    assert (status, body["status"]) == (200, "cancelled")
    (call,) = gateway.calls
    assert (call["method"], call["uri"]) == ("POST", f"https://api.specstream.ai/v1/research/{RUN_ID}/cancel")


def test_another_method_is_refused(gateway: Gateway) -> None:
    status, body = gateway.send("PUT", f"/research/{RUN_ID}")
    assert status == 405
    assert body == {"message": "Use POST to start a report, GET to read one and DELETE to stop one."}
    assert gateway.exit_headers["Allow"] == "POST, GET, DELETE"
    assert gateway.calls == []


def test_a_route_that_waits_returns_the_finished_report(gateway: Gateway) -> None:
    gateway.conf.update(wait_seconds=60, poll_seconds=5)
    gateway.script((202, created()), (200, run("queued")), (200, run("running")), (503, "busy"), "timeout", (200, run("completed")))
    status, body = gateway.send("POST", body={"input": "q"})

    assert status == 200
    assert body["report"]["content"] == "France taxes sugary drinks [1]."
    assert [call["method"] for call in gateway.calls] == ["POST", "GET", "GET", "GET", "GET", "GET"]
    assert gateway.sleeps == [5, 5, 5, 5]
    assert len(gateway.logs) == 2 and all(line.startswith("warn: ") for line in gateway.logs)


def test_a_wait_that_runs_out_returns_the_report_id_and_the_report_is_not_lost(gateway: Gateway) -> None:
    gateway.conf.update(wait_seconds=10, poll_seconds=4)
    gateway.script((202, created()), (200, run("queued")), (200, run("running")), (200, run("running")))
    status, body = gateway.send("POST", body={"input": "q"})

    assert (status, body["id"], body["status"]) == (202, RUN_ID, "running")
    assert gateway.sleeps == [4, 4]


def test_an_idempotent_repeat_of_a_finished_report_returns_it_without_a_wait(gateway: Gateway) -> None:
    gateway.conf.update(wait_seconds=60)
    gateway.script((202, created(status="completed")), (200, run("completed")))
    status, body = gateway.send("POST", body={"input": "q"}, headers={"Idempotency-Key": "k"})

    assert (status, body["report"]["title"]) == (200, "Sugar taxes in the EU")
    assert gateway.sleeps == []


@pytest.mark.parametrize("refused", [401, 403])
def test_a_refused_gateway_key_is_a_gateway_fault_not_the_callers(gateway: Gateway, refused: int) -> None:
    gateway.script((refused, {"error": {"code": "unauthorized", "message": "Bad key"}}))
    status, body = gateway.send("POST", body={"input": "q"})

    assert status == 502
    assert body == {"message": "The gateway's SpecStream API key was refused. Tell the owner of this gateway."}
    assert KEY not in json.dumps(body) and not any(KEY in line for line in gateway.logs)


@pytest.mark.parametrize("refusal", [402, 404, 409, 422, 429])
def test_the_apis_own_refusal_reaches_the_caller_unchanged(gateway: Gateway, refusal: int) -> None:
    words = {"error": {"code": "refused", "message": "The API's own words."}}
    gateway.script((refusal, words))
    assert gateway.send("POST", body={"input": "q"}) == (refusal, words)

    gateway.script((refusal, words))
    assert gateway.send("GET", f"/research/{RUN_ID}") == (refusal, words)


@pytest.mark.parametrize("answer", ["connection refused", (500, "<html>oops</html>"), (502, ""), (200, "not json"), (202, {"id": "../admin", "status": "queued"})])
def test_no_answer_or_a_broken_answer_is_a_502(gateway: Gateway, answer: Any) -> None:
    gateway.script(answer)
    status, body = gateway.send("POST", body={"input": "q"})
    assert status == 502
    assert body["message"].startswith("SpecStream ")
    assert len(gateway.calls) == 1


def test_the_rockspec_installs_every_lua_file_of_the_plugin() -> None:
    (rockspec,) = ROOT.glob("*.rockspec")
    spec = lupa.LuaRuntime()
    spec.execute(rockspec.read_text())
    g = spec.globals()
    assert rockspec.name == f"{g.package}-{g.version}.rockspec"
    modules = dict(g.build.modules.items())
    files = sorted((ROOT / "kong" / "plugins" / "specstream-research").glob("*.lua"))
    assert sorted(modules) == [f"kong.plugins.specstream-research.{path.stem}" for path in files]
    # The source is the public repository, so each path starts at its root.
    assert sorted(modules.values()) == [f"integrations/kong/{path.relative_to(ROOT)}" for path in files]
    assert g.source.url == "git+https://github.com/specstream/specstream-tools.git"


def test_the_schema_holds_the_settings_the_handler_reads() -> None:
    lua = lupa.LuaRuntime()
    lua.execute(
        'package.preload["kong.db.schema.typedefs"] = function() return { protocols_http = { type = "set" } } end'
    )
    lua.globals().package.path = f"{ROOT}/?.lua;" + lua.globals().package.path
    schema = lua.eval('require "kong.plugins.specstream-research.schema"')
    assert schema.name == "specstream-research"
    config = schema.fields[2].config
    fields = {name: field for entry in config.fields.values() for name, field in entry.items()}
    assert sorted(fields) == sorted(Gateway().conf)
    assert fields["api_key"].required and fields["api_key"].encrypted and fields["api_key"].referenceable
    assert (fields["default_depth"].default, fields["max_depth"].default, fields["wait_seconds"].default) == ("standard", "deep", 0)
    assert all(field.description for field in fields.values())

    check = config.custom_validator
    assert check(lua.table(default_depth="quick", max_depth="quick")) is True
    refused = lua.eval("function(check) return check({ default_depth = 'deep', max_depth = 'quick' }) end")(check)
    assert refused == (None, "default_depth must not be deeper than max_depth")
