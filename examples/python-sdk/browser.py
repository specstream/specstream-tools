"""Open a browser on SpecStream, read one page as Markdown, close the browser.

    pip install specstream-client
    export SPECSTREAM_API_KEY="ss_live_..."
    python browser.py https://example.com

A session costs $0.10 an hour, charged by the second, plus $1 per 1,000 steps.
This script runs 2 steps and a few seconds, so one run costs less than 1 cent.
"""

import os
import sys

from specstream_client import Client


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    client = Client(os.environ["SPECSTREAM_API_KEY"])

    # The with block closes the browser at its end, also when a step fails.
    with client.browser(timeout_s=120) as session:
        opened = client.browser_navigate(session["id"], url)
        if opened.get("error"):
            print(opened["error"]["message"], file=sys.stderr)
            return 1
        print(client.browser_read(session["id"]))

    ended = client.browser_session(session["id"])
    print(
        f"\n{ended['seconds']} seconds, {ended['actions']} steps, ${ended['charged_usd']:.4f}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
