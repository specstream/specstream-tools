"""SpecStream starter for Railway: one small web service that searches the live web and reads pages.

    GET  /            a page with a search box
    GET  /health      {"status": "ok"}, for Railway's health check
    GET  /search?q=   the Search API's answer for q (add speed=fast for the fast tier)
    POST /read        {"urls": [...]}: the Extract API's text of up to 20 pages

Environment:
    SPECSTREAM_API_KEY   your key, from https://specstream.ai. It stays on the server.
    APP_TOKEN            the password of this service. /search and /read answer only a request
                         that carries it (Authorization: Bearer <APP_TOKEN>), so a stranger who
                         finds the address cannot spend your balance. The template generates one.
    PORT                 set by Railway.

Only the Python standard library is used, so there is nothing to install.
"""

from __future__ import annotations

import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_URL = os.environ.get("SPECSTREAM_BASE_URL", "https://api.specstream.ai").rstrip("/")
USER_AGENT = "specstream-railway-starter/1.0"
MAX_QUERY = 2000
MAX_BODY = 64 * 1024
MAX_URLS = 20

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SpecStream starter</title>
<style>
body{font:16px/1.5 system-ui,sans-serif;max-width:720px;margin:48px auto;padding:0 16px;color:#111}
input,button{font:inherit;padding:8px 10px;border:1px solid #bbb;border-radius:6px}
input{width:100%;box-sizing:border-box;margin:4px 0 12px}
button{background:#111;color:#fff;border-color:#111;cursor:pointer}
pre{background:#f5f5f5;padding:12px;border-radius:6px;white-space:pre-wrap;word-break:break-word}
label{font-weight:600}
</style>
</head>
<body>
<h1>SpecStream starter</h1>
<p>Ask a question. The answer comes from the live web, with its sources.</p>
<form id="f">
<label for="q">Question</label>
<input id="q" required maxlength="2000" placeholder="What is the population of Japan?">
<label for="t">App token</label>
<input id="t" type="password" required autocomplete="off" placeholder="The APP_TOKEN variable of this service">
<button>Search</button>
</form>
<pre id="out" hidden></pre>
<script>
document.getElementById("f").addEventListener("submit", async (event) => {
  event.preventDefault();
  const out = document.getElementById("out");
  out.hidden = false;
  out.textContent = "Searching...";
  try {
    const response = await fetch("/search?q=" + encodeURIComponent(document.getElementById("q").value), {
      headers: { Authorization: "Bearer " + document.getElementById("t").value },
    });
    out.textContent = JSON.stringify(await response.json(), null, 2);
  } catch (error) {
    out.textContent = String(error);
  }
});
</script>
</body>
</html>
"""


def call_specstream(method: str, path: str, body: dict | None = None) -> tuple[int, bytes]:
    """Send one request to SpecStream with the server's key. Return the status and the JSON body."""
    request = urllib.request.Request(
        BASE_URL + path,
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={
            "Authorization": "Bearer " + os.environ["SPECSTREAM_API_KEY"],
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except (urllib.error.URLError, TimeoutError) as error:
        return 502, json.dumps({"error": f"SpecStream did not answer: {error}"}).encode()


class Handler(BaseHTTPRequestHandler):
    server_version = "specstream-railway-starter"

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

    def do_GET(self) -> None:
        url = urllib.parse.urlsplit(self.path)
        if url.path == "/":
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif url.path == "/health":
            self._send(200, b'{"status": "ok"}')
        elif url.path == "/search":
            if not self._ready():
                return
            query = urllib.parse.parse_qs(url.query)
            q = (query.get("q") or [""])[0].strip()
            if not q or len(q) > MAX_QUERY:
                self._error(400, f"Give q, a question of at most {MAX_QUERY} characters.")
                return
            params = {"q": q}
            if (query.get("speed") or [""])[0] == "fast":
                params["speed"] = "fast"
            self._send(*call_specstream("GET", "/v1/web-search?" + urllib.parse.urlencode(params)))
        else:
            self._error(404, "Not found.")

    def do_POST(self) -> None:
        if urllib.parse.urlsplit(self.path).path != "/read":
            self._error(404, "Not found.")
            return
        if not self._ready():
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self._error(413, "The body is too large.")
            return
        try:
            urls = json.loads(self.rfile.read(length) or b"{}").get("urls")
        except (ValueError, AttributeError):
            urls = None
        if (
            not isinstance(urls, list)
            or not 1 <= len(urls) <= MAX_URLS
            or not all(isinstance(item, str) and item.startswith(("http://", "https://")) for item in urls)
        ):
            self._error(400, f'Send {{"urls": [...]}} with 1 to {MAX_URLS} http or https addresses.')
            return
        self._send(*call_specstream("POST", "/v1/extract", {"urls": urls}))


def make_server(port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


if __name__ == "__main__":
    server = make_server(int(os.environ.get("PORT", "8080")))
    print(f"SpecStream starter listens on port {server.server_port}", flush=True)
    server.serve_forever()
