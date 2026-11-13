"""What the three browser tools share: the price of a session and how a session and a step show."""

import base64
import binascii
import json
import re
from typing import Any

# The price of a browser session (https://specstream.ai/pricing): the time it runs, charged by
# the second, and each step that runs.
HOUR_USD = 0.10
STEP_USD = 0.001
# The API's own limits on a session's length, in minutes.
MIN_MINUTES = 1
MAX_MINUTES = 60
# Seconds without a step before the session ends on its own (the API's maximum is 600).
IDLE_SECONDS = 300
# A Playwright MCP tool name, or browser_read for the page's text.
STEP_NAME = re.compile(r"^browser_[a-z][a-z0-9_]{0,62}$")
# Playwright MCP's browser_close does not end the session: Close Browser does.
NOT_A_STEP = {"browser_close"}
_LABEL = r"(?!-)[a-z0-9-]{1,63}(?<!-)"
_HOST = re.compile(rf"^(\*\.)?{_LABEL}(\.{_LABEL})+$")


def time_usd(minutes: int) -> float:
    """The most the time of a session of this many minutes costs."""
    return round(minutes * HOUR_USD / 60, 4)


def hosts(text: str) -> tuple[list[str], str | None]:
    """The hosts of a list separated by commas or spaces, and the first entry that is not one."""
    found: list[str] = []
    for item in re.split(r"[,\s]+", text.strip()):
        host = item.strip().lower().rstrip(".")
        if not host:
            continue
        if not _HOST.match(host):
            return [], item
        if host not in found:
            found.append(host)
    return found, None


def arguments(text: Any) -> dict[str, Any] | None:
    """A step's arguments from the JSON object the model wrote; None when it is not one."""
    if isinstance(text, dict):
        return text
    text = str(text or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def shown_session(session: dict[str, Any]) -> dict[str, Any]:
    """The session without connect_url: its token drives the browser, so it stays out of a
    workflow's output."""
    return {
        "session_id": session.get("id"),
        "status": session.get("status"),
        "ended_reason": session.get("ended_reason"),
        "live_url": session.get("live_url"),
        "expires_at": session.get("expires_at"),
        "timeout_s": session.get("timeout_s"),
        "idle_timeout_s": session.get("idle_timeout_s"),
        "allowed_domains": session.get("allowed_domains") or [],
        "seconds": session.get("seconds", 0),
        "steps": session.get("actions", 0),
        "charged_usd": session.get("charged_usd", 0),
    }


def shown_step(step: str, answer: dict[str, Any]) -> dict[str, Any]:
    """The step's facts without its content: text and pictures go out as their own messages."""
    error = answer.get("error") or {}
    return {
        "step": step,
        "ok": not error,
        "url": answer.get("url"),
        "title": answer.get("title"),
        "read_at": answer.get("read_at"),
        "took_ms": answer.get("took_ms"),
        "price_usd": answer.get("price_usd", 0),
        "error": error.get("message"),
        "error_code": error.get("code"),
        "blocked_reason": error.get("reason"),
    }


def step_text(answer: dict[str, Any]) -> str:
    """The text parts of a step's result, after the reason when the step did not work."""
    error = answer.get("error") or {}
    parts = [
        str(part.get("text") or "")
        for part in answer.get("result") or []
        if part.get("type") == "text" and part.get("text")
    ]
    if error:
        reason = f" ({error['reason']})" if error.get("reason") else ""
        parts.insert(0, f"The step did not work{reason}: {error.get('message')}")
    return "\n\n".join(parts)


def step_images(answer: dict[str, Any]) -> list[tuple[bytes, str]]:
    """The pictures of a step's result (a screenshot), each with its type."""
    images: list[tuple[bytes, str]] = []
    for part in answer.get("result") or []:
        if part.get("type") != "image" or not part.get("data"):
            continue
        try:
            data = base64.b64decode(part["data"], validate=True)
        except (binascii.Error, ValueError):
            continue
        images.append((data, str(part.get("mime_type") or "image/png")))
    return images
