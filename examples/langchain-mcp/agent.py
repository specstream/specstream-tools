"""A LangChain agent that finds data on the live web with SpecStream over MCP.

    pip install -r requirements.txt
    export SPECSTREAM_API_KEY="ss_live_..."
    export MODEL="openai:<model id>"        # or "anthropic:<model id>", with that provider's key set
    python agent.py "Open-source vector databases on GitHub with more than 5,000 stars, with their license."

By default the agent can read a request and get a price, but it cannot approve one: the
tools that spend money or change anything are left out of its tool list. It shows you the
price and stops. Pass --allow-spend only for a key whose spending limit you set on purpose.
"""

from __future__ import annotations

import argparse
import asyncio
import os

from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

MCP_URL = os.environ.get("SPECSTREAM_MCP_URL", "https://api.specstream.ai/mcp")

# Tools that start paid work or change the account. The agent only gets them with --allow-spend.
SPENDS = {
    "authorize_capacity_work",
    "create_capacity_schedule",
    "update_capacity_schedule",
    "send_to_destination",
    "create_destination_sync",
    "update_destination_sync",
    "create_api_key",
    "delegate_access",
    "request_account_deletion",
}

PROMPT = """You find data on the live web with SpecStream.
1. Call compile with the person's request and say back how it was read.
2. Call quote_capacity_work and tell the person the most it can cost and when the price expires.
3. Stop and ask. Call authorize_capacity_work only after the person has said yes to that exact price.
4. Then follow progress with get_find and read results with list_find_rows, following next_cursor.
Never invent a link or a fact. Say what could not be confirmed."""


async def main(request: str, allow_spend: bool) -> None:
    client = MultiServerMCPClient(
        {
            "specstream": {
                "transport": "streamable_http",
                "url": MCP_URL,
                "headers": {"Authorization": f"Bearer {os.environ['SPECSTREAM_API_KEY']}"},
            }
        }
    )
    tools = [tool for tool in await client.get_tools() if allow_spend or tool.name not in SPENDS]
    agent = create_agent(os.environ["MODEL"], tools, system_prompt=PROMPT)
    result = await agent.ainvoke({"messages": [{"role": "user", "content": request}]})
    print(result["messages"][-1].content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("request", help="what you need, in your own words")
    parser.add_argument("--allow-spend", action="store_true", help="let the agent approve prices")
    args = parser.parse_args()
    asyncio.run(main(args.request, args.allow_spend))
