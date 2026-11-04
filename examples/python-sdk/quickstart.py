"""Read a request, show the price, ask, run it, and print the first results.

    export SPECSTREAM_API_KEY="ss_live_..."
    python quickstart.py "Open-source vector databases on GitHub with more than 5,000 stars, with their license."

Nothing runs until you type yes. The request key is derived from the quote, so running
this twice on the same quote never pays twice.
"""

from __future__ import annotations

import json
import os
import sys
import time

from specstream_client import Client

DONE = {"completed", "partial"}
STOPPED = {"failed", "canceled", "expired"}


def main(request: str) -> int:
    client = Client(
        os.environ["SPECSTREAM_API_KEY"],
        base_url=os.environ.get("SPECSTREAM_BASE_URL", "https://api.specstream.ai"),
    )

    read = client.compile(request)
    quote = client.quote_capacity_work(
        {
            "ast_hash": read["ast_hash"],
            "operation": "find",
            "requested_units": read["ast"]["limit"]["max"],
        }
    )
    maximum = quote["maximum_cents"]
    print(f"Up to {maximum / 100:.2f} {quote.get('currency', 'USD')}. The price is good until {quote['expires_at']}.")
    if input("Run it? Type yes to approve that maximum: ").strip().lower() != "yes":
        print("Nothing was run.")
        return 0

    run = client.authorize_capacity_work(
        {
            "quote_id": quote["quote_id"],
            "quote_hash": quote["quote_hash"],
            "confirm_max_cents": maximum,
            "idempotency_key": f"quickstart-{quote['quote_id']}",
        }
    )
    find_id = run["find_id"]

    while True:
        state = client.get_find(find_id)
        if state["status"] in DONE:
            break
        if state["status"] in STOPPED:
            print(f"The run ended as {state['status']}. What it found is kept.", file=sys.stderr)
            return 1
        time.sleep(3)

    shown, cursor = 0, None
    while shown < 5:
        page = client.rows(find_id, cursor=cursor)
        for row in page["rows"][: 5 - shown]:
            print(json.dumps(row)[:400])
            shown += 1
        cursor = page.get("next_cursor")
        if not cursor:
            break
    print(f"Run {find_id}: open it in the workspace to see the source behind each fact.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit('usage: python quickstart.py "what you need, in your own words"')
    raise SystemExit(main(sys.argv[1]))
