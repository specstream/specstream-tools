"""What the two research report tools share: the price of each depth and the run as a tool shows it."""

from typing import Any

# The price of one report by depth, in cents, charged once when the report is delivered
# (https://specstream.ai/pricing).
PRICE_CENTS = {"quick": 10, "standard": 30, "deep": 100}
ENDED = {"completed", "failed", "cancelled", "payment_required"}


def shown(run: dict[str, Any]) -> dict[str, Any]:
    """The run without the report text: the text goes out as its own message."""
    report = run.get("report") or {}
    error = run.get("error") or {}
    return {
        "report_id": run.get("id"),
        "status": run.get("status"),
        "stage": run.get("stage"),
        "depth": run.get("depth"),
        "title": report.get("title"),
        "sources": [
            {
                "n": source.get("n"),
                "url": source.get("url"),
                "title": source.get("title"),
                "read_at": source.get("read_at"),
                "cited": source.get("cited"),
            }
            for source in report.get("sources") or []
        ],
        "charged_usd": (run.get("usage") or {}).get("charged_usd", 0),
        "error": error.get("message"),
    }


def report_text(run: dict[str, Any]) -> str:
    """The report's markdown when the run is completed, else what the reader does next."""
    status = run.get("status")
    if status == "completed":
        return str((run.get("report") or {}).get("content") or "")
    if status == "payment_required":
        return (
            "The report is written, but the balance cannot pay for it. Add credit in the "
            "SpecStream workspace, then call Get Research Report with report ID "
            f"{run.get('id')}."
        )
    if status in ENDED:
        reason = (run.get("error") or {}).get("message") or status
        return f"The report did not finish and costs nothing: {reason}"
    return (
        f"The report is still in work (stage: {run.get('stage')}). Call Get Research Report "
        f"with report ID {run.get('id')} for the finished report."
    )
