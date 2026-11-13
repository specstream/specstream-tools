#!/usr/bin/env python3
"""SpecStream research agent for one server: ask a question, get a written report from the live
web with the page behind each cited sentence, and keep every report on this server's disk.

    research_agent.py serve                     the web page (behind nginx, see ../files/nginx.conf)
    research_agent.py ask "question" --depth quick
                                                one report as Markdown on standard output

It needs only Python's standard library. It talks to one outside address, the SpecStream API, with
the owner's own API key. The key and the page's password are read from files, are never written to
a log and never appear in a page.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import html
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = "1.0.0"
SIGN_UP = "https://specstream.ai/workspace?utm_source=vultr"
USER = "research"
DEPTHS = {
    "quick": ("$0.10", "about a minute"),
    "standard": ("$0.30", "about four minutes"),
    "deep": ("$1.00", "about five minutes"),
}
ENDED = {"completed", "failed", "cancelled", "payment_required"}
MAX_INPUT = 15000
MAX_BODY = 64 * 1024
RUN_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
KEY_SHAPE = re.compile(r"[\x21-\x7e]{8,512}")


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class Settings:
    """Where the agent reads and writes. Every value comes from the environment, so the service
    file and a test set them the same way."""

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self.env = dict(os.environ if env is None else env)
        env = self.env
        self.api = env.get("SPECSTREAM_API_BASE", "https://api.specstream.ai").rstrip("/")
        self.data = Path(env.get("RESEARCH_DATA_DIR", "/var/lib/specstream-research"))
        self.password_file = Path(env.get("RESEARCH_PASSWORD_FILE", "/etc/specstream-research/web-password"))
        self.key_file = Path(env.get("RESEARCH_KEY_FILE", str(self.data / "api-key")))
        self.bind = env.get("RESEARCH_BIND", "127.0.0.1")
        self.port = int(env.get("RESEARCH_PORT", "8080"))

    @property
    def reports(self) -> Path:
        return self.data / "reports"

    def password(self) -> str:
        return _read_secret(self.password_file)

    def key(self) -> str:
        return self.env.get("SPECSTREAM_API_KEY", "").strip() or _read_secret(self.key_file)


def _read_secret(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _write_private(path: Path, text: str) -> None:
    """Write a file only its owner reads, whole or not at all."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(text)
        os.replace(name, path)
    except BaseException:
        if os.path.exists(name):
            os.unlink(name)
        raise


# ---- the SpecStream API ----


def explain(status: int, body: object) -> str:
    """What the owner reads when the API refuses, in words that say what to do next."""
    said = ""
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        message = body["error"].get("message")
        said = message if isinstance(message, str) else ""
    if status in (401, 403):
        return "This API key was not accepted. Copy it again from your SpecStream workspace."
    if status == 402:
        return "The balance does not hold this report's price. Add credit in your SpecStream workspace."
    if status == 429:
        return "Too many calls for now. Try again in a minute."
    return said or f"SpecStream answered with status {status}."


def call(settings: Settings, method: str, path: str, key: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "Accept": "application/json",
        "Authorization": "Bearer " + key,
        "User-Agent": "specstream-vultr-research/" + VERSION,
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(settings.api + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as reply:  # noqa: S310 (the address is the API's)
            return _json(reply.read())
    except urllib.error.HTTPError as err:
        raise ApiError(err.code, explain(err.code, _json(err.read()))) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ApiError(0, "The SpecStream API could not be reached. Check the connection and try again.") from None


def _json(raw: bytes) -> dict:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def check_input(key: str, question: str, depth: str) -> str | None:
    if not key:
        return "Save your SpecStream API key first."
    if not question.strip():
        return "Write the question first."
    if len(question.strip()) > MAX_INPUT:
        return "The question holds up to 15,000 characters."
    if depth not in DEPTHS:
        return "Choose quick, standard or deep."
    return None


def start(settings: Settings, question: str, depth: str) -> dict:
    """Start one report and keep its record on disk. The API charges for a delivered report only."""
    key = settings.key()
    problem = check_input(key, question, depth)
    if problem:
        raise ApiError(0, problem)
    created = call(settings, "POST", "/v1/research", key, {"input": question.strip(), "depth": depth})
    run_id = str(created.get("id", ""))
    if not RUN_ID.fullmatch(run_id):
        raise ApiError(502, "SpecStream did not return a report id.")
    record = {
        "id": run_id,
        "input": question.strip(),
        "depth": depth,
        "status": created.get("status") or "queued",
        "price_usd": created.get("price_usd"),
        "asked_at": int(time.time()),
    }
    save(settings, record)
    return record


def save(settings: Settings, record: dict) -> None:
    _write_private(settings.reports / (record["id"] + ".json"), json.dumps(record))


def load(settings: Settings, run_id: str) -> dict | None:
    if not RUN_ID.fullmatch(run_id):
        return None
    try:
        record = json.loads((settings.reports / (run_id + ".json")).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) and record.get("id") == run_id else None


def refresh(settings: Settings, record: dict) -> dict:
    """Read a report that has not ended from the API once, and keep what came back."""
    if record.get("status") in ENDED:
        return record
    run = call(settings, "GET", "/v1/research/" + record["id"], settings.key())
    for name in ("status", "stage", "progress", "usage", "error"):
        if name in run:
            record[name] = run[name]
    # The written report arrives under "report": its text with [n] markers, and the pages behind them.
    report = run.get("report") if isinstance(run.get("report"), dict) else {}
    for name in ("title", "content", "sources", "citations"):
        if name in report:
            record[name] = report[name]
    save(settings, record)
    return record


def cancel(settings: Settings, record: dict) -> dict:
    if record.get("status") in ENDED:
        return record
    call(settings, "POST", "/v1/research/" + record["id"] + "/cancel", settings.key())
    return refresh(settings, record)


def history(settings: Settings, limit: int = 50) -> list[dict]:
    records = []
    try:
        names = [p.stem for p in settings.reports.glob("*.json")]
    except OSError:
        names = []
    for name in names:
        record = load(settings, name)
        if record:
            records.append(record)
    records.sort(key=lambda r: r.get("asked_at") or 0, reverse=True)
    return records[:limit]


# ---- a report as Markdown and as HTML ----


def safe_url(url: object) -> str | None:
    """Only web addresses become links; anything else (javascript:, data:) stays plain text."""
    text = url if isinstance(url, str) else ""
    return text if re.match(r"https?://", text, re.I) else None


def _sources(record: dict) -> list[dict]:
    return [s for s in record.get("sources") or [] if isinstance(s, dict) and safe_url(s.get("url"))]


def to_markdown(record: dict) -> str:
    lines = []
    if record.get("title"):
        lines += ["# " + str(record["title"]), ""]
    lines.append(str(record.get("content") or "").strip())
    sources = _sources(record)
    if sources:
        lines += ["", "## Pages read", ""]
        for source in sources:
            read = f" (read {source['read_at']})" if source.get("read_at") else ""
            lines.append(f"{source.get('n', '')}. [{source.get('title') or source['url']}]({source['url']}){read}")
    return "\n".join(lines).strip() + "\n"


def _link(url: object, label: str, title: object = None) -> str:
    safe = safe_url(url)
    if not safe:
        return label
    tip = f' title="{html.escape(str(title))}"' if title else ""
    return f'<a href="{html.escape(safe)}"{tip} target="_blank" rel="noopener noreferrer">{label}</a>'


def _pages(record: dict) -> dict[int, dict]:
    pages = {}
    for item in list(record.get("sources") or []) + list(record.get("citations") or []):
        if isinstance(item, dict) and isinstance(item.get("n"), int) and safe_url(item.get("url")):
            pages[item["n"]] = item
    return pages


def _inline(text: str, pages: dict[int, dict]) -> str:
    out = html.escape(text)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    # The label and the address were escaped with the rest of the line, above.
    out = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>',
        out,
    )

    def marker(match: re.Match) -> str:
        page = pages.get(int(match.group(1)))
        return f"<sup>{_link(page['url'], match.group(0), page.get('title'))}</sup>" if page else match.group(0)

    return re.sub(r"\[(\d{1,4})\]", marker, out)


def render_markdown(content: object, pages: dict[int, dict]) -> str:
    """A small Markdown reader: headings, lists, tables as fixed text, paragraphs. Every character
    of the report is escaped before any tag is added, so a page's text cannot add markup."""
    out: list[str] = []
    state: dict = {"list": None, "para": [], "fixed": []}

    def close() -> None:
        if state["para"]:
            out.append("<p>" + " ".join(state["para"]) + "</p>")
        if state["list"]:
            out.append(f"</{state['list']}>")
        if state["fixed"]:
            out.append("<pre>" + "\n".join(state["fixed"]) + "</pre>")
        state.update(list=None, para=[], fixed=[])

    for raw in str(content or "").splitlines():
        line = raw.strip()
        heading = re.match(r"(#{1,6})\s+(.*)$", line)
        bullet = re.match(r"[-*]\s+(.*)$", line)
        numbered = re.match(r"\d+[.)]\s+(.*)$", line)
        if not line:
            close()
        elif heading:
            close()
            level = min(len(heading.group(1)) + 1, 6)
            out.append(f"<h{level}>{_inline(heading.group(2), pages)}</h{level}>")
        elif bullet or numbered:
            kind = "ul" if bullet else "ol"
            if state["list"] != kind:
                close()
                state["list"] = kind
                out.append(f"<{kind}>")
            out.append("<li>" + _inline((bullet or numbered).group(1), pages) + "</li>")
        elif line.startswith("|"):
            if not state["fixed"]:
                close()
            state["fixed"].append(html.escape(line))
        else:
            if state["list"] or state["fixed"]:
                close()
            state["para"].append(_inline(line, pages))
    close()
    return "\n".join(out)


def render_report(record: dict) -> str:
    parts = []
    if record.get("title"):
        parts.append("<h1>" + html.escape(str(record["title"])) + "</h1>")
    parts.append(render_markdown(record.get("content"), _pages(record)))
    sources = _sources(record)
    if sources:
        parts.append("<h2>Pages read</h2>")
        parts.append('<ol class="sources">')
        for source in sources:
            read = f' <span class="read">read {html.escape(str(source["read_at"]))}</span>' if source.get("read_at") else ""
            number = source.get("n") if isinstance(source.get("n"), int) else 0
            label = html.escape(str(source.get("title") or source["url"]))
            parts.append(f'<li value="{number}">{_link(source["url"], label)}{read}</li>')
        parts.append("</ol>")
    return "\n".join(parts)


def progress_line(record: dict) -> str:
    progress = record.get("progress") if isinstance(record.get("progress"), dict) else {}
    return (
        f"Stage: {record.get('stage') or record.get('status')}. {progress.get('searches', 0)} searches, "
        f"{progress.get('pages_read', 0)} pages read, {progress.get('sources', 0)} sources."
    )


def end_line(record: dict) -> str:
    status = record.get("status")
    if status == "completed":
        usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
        charged = usage.get("charged_usd")
        if isinstance(charged, (int, float)) and not isinstance(charged, bool):
            return f"Report delivered. Charged ${charged:.2f}."
        return "Report delivered."
    if status == "cancelled":
        return "Stopped. A stopped report is not charged."
    if status == "payment_required":
        return "The balance does not hold this report's price. Add credit in your SpecStream workspace."
    error = record.get("error") if isinstance(record.get("error"), dict) else {}
    why = " " + str(error["message"]) if error.get("message") else ""
    return "The report did not finish, so it is not charged." + why


# ---- the web page ----

STYLE = """
body{font:16px/1.55 system-ui,sans-serif;color:#15171a;background:#fff;max-width:46rem;margin:2rem auto;padding:0 1rem}
h1{font-size:1.6rem}h2{font-size:1.25rem;margin-top:2rem}a{color:#0b57d0}
textarea,input[type=password]{width:100%;box-sizing:border-box;font:inherit;padding:.6rem;border:1px solid #9aa0a6;border-radius:6px}
button{font:inherit;padding:.55rem 1rem;border:0;border-radius:6px;background:#15171a;color:#fff;cursor:pointer}
button.quiet{background:#fff;color:#15171a;border:1px solid #9aa0a6}
label{display:block;margin:.8rem 0 .3rem;font-weight:600}.depth label{display:inline;font-weight:400;margin-right:1rem}
.note{color:#4a4f57;font-size:.92rem}.problem{background:#fdecea;border-left:4px solid #b3261e;padding:.6rem .8rem}
.state{background:#f1f3f4;padding:.6rem .8rem;border-radius:6px}pre{overflow:auto;background:#f1f3f4;padding:.6rem}
.read{color:#4a4f57;font-size:.85rem}li{margin:.25rem 0}
"""


def page(title: str, body: str, refresh_seconds: int = 0) -> str:
    again = f'<meta http-equiv="refresh" content="{refresh_seconds}">' if refresh_seconds else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="robots" content="noindex">{again}<title>{html.escape(title)}</title>'
        f"<style>{STYLE}</style></head><body>{body}"
        '<p class="note"><a href="/">All reports</a> · Reports are written by '
        '<a href="https://specstream.ai/" target="_blank" rel="noopener noreferrer">SpecStream</a> '
        "and kept on this server.</p></body></html>"
    )


def home(settings: Settings, token: str, problem: str = "", question: str = "") -> str:
    parts = ["<h1>Research agent</h1>"]
    parts.append(
        "<p>Ask a question. SpecStream searches the live web, reads the pages and writes a report "
        "with the page behind each cited sentence.</p>"
    )
    if problem:
        parts.append(f'<p class="problem">{html.escape(problem)}</p>')
    hidden = f'<input type="hidden" name="token" value="{token}">'
    has_key = bool(settings.key())
    if has_key:
        depths = "".join(
            f'<label><input type="radio" name="depth" value="{name}"{" checked" if name == "quick" else ""}> '
            f"{name}, {price}, {takes}</label>"
            for name, (price, takes) in DEPTHS.items()
        )
        parts.append(
            f'<form method="post" action="/reports">{hidden}'
            '<label for="question">Question</label>'
            f'<textarea id="question" name="question" rows="5" maxlength="{MAX_INPUT}" required>'
            f"{html.escape(question)}</textarea>"
            f'<p class="depth">{depths}</p>'
            "<p><button>Write the report</button></p>"
            '<p class="note">The price is charged to your SpecStream account when the report is '
            "delivered. A stopped or failed report is not charged.</p></form>"
        )
    else:
        parts.append(
            f'<p>This server has no SpecStream API key yet. <a href="{SIGN_UP}" target="_blank" '
            'rel="noopener noreferrer">Create a SpecStream account</a>, which starts with $10 of credit, '
            "copy an API key from the workspace and save it here.</p>"
        )
    parts.append(
        f'<form method="post" action="/key">{hidden}'
        f'<label for="key">{"Replace the" if has_key else "SpecStream"} API key</label>'
        '<input id="key" name="key" type="password" autocomplete="off" required>'
        '<p><button class="quiet">Save the key</button></p>'
        '<p class="note">The key is kept in a file on this server that only the agent reads. '
        "It is sent to api.specstream.ai and nowhere else.</p></form>"
    )
    records = history(settings)
    if records:
        parts.append("<h2>Reports on this server</h2><ul>")
        for record in records:
            label = html.escape(str(record.get("title") or record.get("input") or record["id"])[:140])
            when = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(record.get("asked_at") or 0))
            parts.append(
                f'<li><a href="/reports/{record["id"]}">{label}</a> '
                f'<span class="read">{html.escape(str(record.get("status")))}, {when}</span></li>'
            )
        parts.append("</ul>")
    return page("Research agent", "\n".join(parts))


def report_page(record: dict, token: str, problem: str = "") -> str:
    parts = []
    if problem:
        parts.append(f'<p class="problem">{html.escape(problem)}</p>')
    running = record.get("status") not in ENDED
    if running:
        parts.append("<h1>" + html.escape(str(record.get("input"))[:300]) + "</h1>")
        parts.append(f'<p class="state">{html.escape(progress_line(record))} This page reads again every five seconds.</p>')
        parts.append(
            f'<form method="post" action="/reports/{record["id"]}/cancel">'
            f'<input type="hidden" name="token" value="{token}"><button class="quiet">Stop</button></form>'
        )
    else:
        parts.append(f'<p class="state">{html.escape(end_line(record))}</p>')
        if record.get("status") == "completed":
            parts.append(render_report(record))
            parts.append(f'<p><a href="/reports/{record["id"]}.md">Download as Markdown</a></p>')
        else:
            parts.append("<h1>" + html.escape(str(record.get("input"))[:300]) + "</h1>")
    title = str(record.get("title") or record.get("input") or "Report")[:80]
    return page(title, "\n".join(parts), refresh_seconds=5 if running and not problem else 0)


def csrf_token(password: str) -> str:
    """A value only a page of this server holds, so another site cannot post a form here with the
    browser's saved password."""
    return hmac.new(password.encode("utf-8"), b"specstream-research-form", hashlib.sha256).hexdigest()


class Handler(BaseHTTPRequestHandler):
    settings: Settings
    server_version = "specstream-research/" + VERSION
    sys_version = ""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        # One line a request, without headers or bodies: no key and no password reaches the journal.
        sys.stderr.write("%s %s\n" % (self.command, self.path.split("?")[0]))

    def _send(self, status: int, body: str, kind: str = "text/html; charset=utf-8", extra: dict | None = None) -> None:
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

    def _redirect(self, where: str) -> None:
        self._send(303, "", extra={"Location": where})

    def _signed_in(self) -> str | None:
        """The page's password when the request carries it, else None after the refusal is sent."""
        password = self.settings.password()
        if not password:
            self._send(503, "The agent is still being set up. Try again in a minute.", "text/plain; charset=utf-8")
            return None
        given = ""
        header = self.headers.get("Authorization", "")
        if header.startswith("Basic "):
            try:
                user, _, given = base64.b64decode(header[6:], validate=True).decode("utf-8").partition(":")
            except (ValueError, UnicodeDecodeError):
                user, given = "", ""
            if user != USER:
                given = ""
        if not given or not hmac.compare_digest(given.encode("utf-8"), password.encode("utf-8")):
            if given:
                time.sleep(0.5)  # slows a guesser; each request has its own thread
            self._send(
                401,
                "Sign in with the user name research and the password from your Vultr application instructions.",
                "text/plain; charset=utf-8",
                {"WWW-Authenticate": 'Basic realm="Research agent", charset="UTF-8"'},
            )
            return None
        return password

    def _form(self, password: str) -> dict[str, str] | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self._send(413, "The form is too large.", "text/plain; charset=utf-8")
            return None
        fields = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", "replace"), keep_blank_values=True)
        form = {name: values[0] for name, values in fields.items()}
        if not hmac.compare_digest(form.get("token", "").encode("utf-8"), csrf_token(password).encode("utf-8")):
            self._send(403, "This form is out of date. Open the page again.", "text/plain; charset=utf-8")
            return None
        return form

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/healthz":
            self._send(200, "ok\n", "text/plain; charset=utf-8")
            return
        password = self._signed_in()
        if password is None:
            return
        token = csrf_token(password)
        if path == "/":
            self._send(200, home(self.settings, token))
            return
        match = re.fullmatch(r"/reports/([A-Za-z0-9_-]{1,128}?)(\.md)?", path)
        record = load(self.settings, match.group(1)) if match else None
        if not record:
            self._send(404, page("Not found", "<h1>No such report on this server</h1>"))
            return
        problem = ""
        try:
            record = refresh(self.settings, record)
        except ApiError as err:
            problem = str(err)
        if match.group(2):
            if record.get("status") != "completed":
                self._send(404, "The report is not written yet.\n", "text/plain; charset=utf-8")
                return
            self._send(
                200,
                to_markdown(record),
                "text/markdown; charset=utf-8",
                {"Content-Disposition": f'attachment; filename="report-{record["id"][:40]}.md"'},
            )
            return
        self._send(200, report_page(record, token, problem))

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        password = self._signed_in()
        if password is None:
            return
        form = self._form(password)
        if form is None:
            return
        token = csrf_token(password)
        if path == "/key":
            key = form.get("key", "").strip()
            if not KEY_SHAPE.fullmatch(key):
                self._send(400, home(self.settings, token, "That does not look like an API key. Copy it again."))
                return
            _write_private(self.settings.key_file, key + "\n")
            self._redirect("/")
            return
        if path == "/reports":
            question = form.get("question", "")
            try:
                record = start(self.settings, question, form.get("depth", ""))
            except ApiError as err:
                self._send(400 if err.status == 0 else 502, home(self.settings, token, str(err), question))
                return
            self._redirect("/reports/" + record["id"])
            return
        match = re.fullmatch(r"/reports/([A-Za-z0-9_-]{1,128})/cancel", path)
        record = load(self.settings, match.group(1)) if match else None
        if not record:
            self._send(404, page("Not found", "<h1>No such report on this server</h1>"))
            return
        try:
            cancel(self.settings, record)
        except ApiError as err:
            self._send(502, report_page(record, token, str(err)))
            return
        self._redirect("/reports/" + record["id"])


def make_server(settings: Settings) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"settings": settings})
    server = ThreadingHTTPServer((settings.bind, settings.port), handler)
    server.daemon_threads = True
    return server


def ask(settings: Settings, question: str, depth: str, every: float = 3.0, out=None, err=None) -> int:
    """One report from the command line: progress on standard error, the report on standard output."""
    out = out or sys.stdout
    err = err or sys.stderr
    try:
        record = start(settings, question, depth)
        print(f"Report {record['id']} started ({DEPTHS[depth][0]} when delivered).", file=err)
        while record.get("status") not in ENDED:
            time.sleep(every)
            record = refresh(settings, record)
            print(progress_line(record), file=err)
    except ApiError as problem:
        print(str(problem), file=err)
        return 1
    print(end_line(record), file=err)
    if record.get("status") != "completed":
        return 1
    out.write(to_markdown(record))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SpecStream research agent")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="run the web page")
    one = commands.add_parser("ask", help="write one report as Markdown on standard output")
    one.add_argument("question")
    one.add_argument("--depth", choices=sorted(DEPTHS), default="quick")
    args = parser.parse_args(argv)
    settings = Settings()
    if args.command == "ask":
        return ask(settings, args.question, args.depth)
    settings.reports.mkdir(parents=True, exist_ok=True)
    server = make_server(settings)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
