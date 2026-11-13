"""Claude reads a page in a browser that SpecStream hosts.

Needs ANTHROPIC_API_KEY, SPECSTREAM_API_KEY and ANTHROPIC_MODEL (a model that supports the browser
toolset). The session costs $0.10 an hour, charged by the second,
and ends when the `with` block does.
"""

import os

from anthropic import Anthropic

from specstream_claude_toolset import SpecStreamBrowser


def main() -> None:
    client = Anthropic()
    # The session opens only these hosts: links, redirects and page requests included.
    with SpecStreamBrowser(allowed_domains=["example.com", "*.iana.org"]) as browser:
        runner = client.beta.messages.tool_runner(
            model=os.environ["ANTHROPIC_MODEL"],
            max_tokens=1024,
            tools=[browser],
            messages=[{"role": "user", "content": "Open example.com and tell me its heading."}],
        )
        for message in runner:
            for block in message.content:
                if block.type == "text":
                    print(block.text)


if __name__ == "__main__":
    main()
