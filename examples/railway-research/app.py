"""SpecStream deep research for Railway: a small web service that writes reports from the live web.

    GET  /                       a page with a question box; it shows the report and its sources
    GET  /health                 {"status": "ok"}, for Railway's health check
    POST /research               {"question": "...", "depth": "quick"}: starts a report
    GET  /research/<id>          the run: its status, its progress and, when completed, the report
    POST /research/<id>/cancel   stops a run that is not finished

Environment:
    SPECSTREAM_API_KEY   your key, from https://specstream.ai. It stays on the server.
    APP_TOKEN            the password of this service. The /research routes answer only a request
                         that carries it (Authorization: Bearer <APP_TOKEN>), so a stranger who
                         finds the address cannot spend your balance. The template generates one.
    MAX_DEPTH            the deepest report this service starts: quick, standard or deep (default deep).
    PORT                 set by Railway.

Only the Python standard library is used, so there is nothing to install.
"""

# ruff: noqa: E501 (the page below holds long lines of HTML)
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_URL = os.environ.get("SPECSTREAM_BASE_URL", "https://api.specstream.ai").rstrip("/")
USER_AGENT = "specstream-railway-research/1.0"
DEPTHS = ("quick", "standard", "deep")
MAX_QUESTION = 15_000
MAX_BODY = 64 * 1024
RUN_PATH = re.compile(r"/research/([A-Za-z0-9_-]{1,128})(/cancel)?")

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SpecStream deep research</title>
<style>
body{font:16px/1.5 system-ui,sans-serif;max-width:760px;margin:48px auto;padding:0 16px;color:#111}
textarea,select,input,button{font:inherit;padding:8px 10px;border:1px solid #bbb;border-radius:6px}
textarea,input,select{width:100%;box-sizing:border-box;margin:4px 0 12px}
button{background:#111;color:#fff;border-color:#111;cursor:pointer}
button:disabled{opacity:.5;cursor:default}
#report{white-space:pre-wrap;word-break:break-word;background:#f5f5f5;padding:12px;border-radius:6px}
label{font-weight:600}
#status{color:#555}
li{margin:4px 0;word-break:break-word}
</style>
</head>
<body>
<h1>SpecStream deep research</h1>
<p>Ask a question. SpecStream searches the live web, reads the pages and writes a report, with the page behind each cited sentence.</p>
<form id="f">
<label for="q">Question</label>
<textarea id="q" required maxlength="15000" rows="3" placeholder="How do the prices of the main cloud GPU providers compare this month?"></textarea>
<label for="d">Depth</label>
<select id="d">
<option value="quick">Quick: $0.10 a report</option>
<option value="standard">Standard: $0.30 a report</option>
<option value="deep">Deep: $1.00 a report</option>
</select>
<label for="t">App token</label>
<input id="t" type="password" required autocomplete="off" placeholder="The APP_TOKEN variable of this service">
<button id="go">Write the report</button>
</form>
<p id="status" hidden></p>
<h2 id="title" hidden></h2>
<div id="report" hidden></div>
<h3 id="sh" hidden>Sources</h3>
<ol id="sources"></ol>
<script>
const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
function show(run) {
  const report = run.report || {};
  $("title").textContent = report.title || "";
  $("title").hidden = !report.title;
  $("report").textContent = report.content || "";
  $("report").hidden = !report.content;
  const sources = (report.sources || []).filter((s) => /^https?:\/\//.test(s.url || ""));
  $("sh").hidden = sources.length === 0;
  for (const source of sources) {
    const item = document.createElement("li");
    item.value = source.n;
    const link = document.createElement("a");
    link.href = source.url;
    link.rel = "noopener noreferrer";
    link.target = "_blank";
    link.textContent = source.title || source.url;
    item.append(link);
    $("sources").append(item);
  }
}
$("f").addEventListener("submit", async (event) => {
  event.preventDefault();
  const headers = { Authorization: "Bearer " + $("t").value, "Content-Type": "application/json" };
  const status = $("status");
  status.hidden = false;
  status.textContent = "Starting...";
  $("go").disabled = true;
  $("sources").replaceChildren();
  show({});
  try {
    let response = await fetch("/research", {
      method: "POST",
      headers,
      body: JSON.stringify({ question: $("q").value, depth: $("d").value }),
    });
    let run = await response.json();
    if (!response.ok || !run.id) throw new Error(JSON.stringify(run));
    const id = run.id;
    while (!["completed", "failed", "cancelled", "payment_required"].includes(run.status)) {
      const p = run.progress || {};
      status.textContent = "Working: " + (p.searches || 0) + " searches, " + (p.pages_read || 0) + " pages read.";
      await sleep(4000);
      response = await fetch("/research/" + encodeURIComponent(id), { headers });
      run = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(run));
    }
    if (run.status === "completed") {
      status.textContent = "Done. Charged $" + Number((run.usage || {}).charged_usd || 0).toFixed(2) + ".";
      show(run);
    } else if (run.status === "payment_required") {
      status.textContent = "The balance does not hold the price of this report. Add credit at https://specstream.ai/workspace.";
    } else {
      status.textContent = "The run ended as " + run.status + ((run.error || {}).message ? ": " + run.error.message : ".");
    }
  } catch (error) {
    status.textContent = String(error.message || error);
  }
  $("go").disabled = false;
});
</script>
</body>
</html>
"""


def max_depth() -> str:
    """The deepest report this service starts. An unknown value counts as quick, the cheapest."""
    value = os.environ.get("MAX_DEPTH", "").strip().lower() or "deep"
    return value if value in DEPTHS else "quick"


def idempotency_key(body: dict) -> str:
    # The same question at the same depth in the same hour gets the report it already started,
    # so a double click or a retry never buys the report twice.
    hour = time.strftime("%Y-%m-%dT%H", time.gmtime())
    digest = hashlib.sha256(f"{json.dumps(body, sort_keys=True)}|{hour}".encode()).hexdigest()[:32]
    return "railway-research-" + digest


def call_specstream(
    method: str, path: str, body: dict | None = None, key: str | None = None
) -> tuple[int, bytes]:
    """Send one request to SpecStream with the server's key. Return the status and the JSON body."""
    headers = {
        "Authorization": "Bearer " + os.environ["SPECSTREAM_API_KEY"],
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    if key:
        headers["Idempotency-Key"] = key
    request = urllib.request.Request(
        BASE_URL + path,
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except (urllib.error.URLError, TimeoutError) as error:
        return 502, json.dumps({"error": f"SpecStream did not answer: {error}"}).encode()


class Handler(BaseHTTPRequestHandler):
    server_version = "specstream-railway-research"

    def log_message(self, format: str, *args: object) -> None:
        # The default log prints the full request line. Print the path only: no query, no token.
        status = args[1] if len(args) > 1 else ""
        print(f"{self.command} {urllib.parse.urlsplit(self.path).path} {status}", flush=True)

    def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._send(status, json.dumps({"error": message}).encode())

    def _ready(self) -> bool:
        """True when the service is configured and the request carries the app token."""
        token = os.environ.get("APP_TOKEN", "")
        if not os.environ.get("SPECSTREAM_API_KEY") or not token:
            self._error(503, "Set the variables SPECSTREAM_API_KEY and APP_TOKEN on this service.")
            return False
        sent = self.headers.get("Authorization", "")
        if not hmac.compare_digest(sent.encode(), ("Bearer " + token).encode()):
            self._error(401, "Send the app token: Authorization: Bearer <APP_TOKEN>.")
            return False
        return True

    def _body(self) -> dict | None:
        """The JSON object of the request body, or None after the error is sent."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self._error(413, "The body is too large.")
            return None
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = None
        if not isinstance(body, dict):
            self._error(400, "Send a JSON object.")
            return None
        return body

    def do_GET(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        run = RUN_PATH.fullmatch(path)
        if path == "/":
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif path == "/health":
            self._send(200, b'{"status": "ok"}')
        elif run and not run.group(2):
            if self._ready():
                self._send(*call_specstream("GET", "/v1/research/" + run.group(1)))
        else:
            self._error(404, "Not found.")

    def do_POST(self) -> None:
        path = urllib.parse.urlsplit(self.path).path
        run = RUN_PATH.fullmatch(path)
        if path != "/research" and not (run and run.group(2)):
            self._error(404, "Not found.")
            return
        if not self._ready():
            return
        if run:
            self._send(*call_specstream("POST", f"/v1/research/{run.group(1)}/cancel"))
            return
        body = self._body()
        if body is None:
            return
        question = body.get("question")
        depth = body.get("depth", "quick")
        if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION:
            self._error(400, f"Give question, 1 to {MAX_QUESTION} characters.")
            return
        if depth not in DEPTHS:
            self._error(400, 'depth is "quick", "standard" or "deep".')
            return
        limit = max_depth()
        if DEPTHS.index(depth) > DEPTHS.index(limit):
            self._error(
                400, f'This service starts reports up to "{limit}" (the MAX_DEPTH variable).'
            )
            return
        request = {"input": question.strip(), "depth": depth}
        self._send(*call_specstream("POST", "/v1/research", request, idempotency_key(request)))


def make_server(port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


if __name__ == "__main__":
    server = make_server(int(os.environ.get("PORT", "8080")))
    print(f"SpecStream deep research listens on port {server.server_port}", flush=True)
    server.serve_forever()
