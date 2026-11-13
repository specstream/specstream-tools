"""Ask Claude for a page's heading. Needs ANTHROPIC_API_KEY, SPECSTREAM_API_KEY and CLAUDE_MODEL.

A run opens one SpecStream browser session ($0.10 an hour by the second, plus $1 per 1,000 steps).
"""

import os

from anthropic import Anthropic

from specstream_claude_browser import SpecStreamBrowser

client = Anthropic()
with SpecStreamBrowser(allowed_domains=["example.com"]) as browser:
    runner = client.beta.messages.tool_runner(
        model=os.environ["CLAUDE_MODEL"],  # a model the browser toolset supports
        max_tokens=1024,
        tools=[browser],
        messages=[{"role": "user", "content": "Open example.com and tell me its heading."}],
    )
    for message in runner:
        print(message)
