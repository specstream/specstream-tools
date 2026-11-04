# LangChain example

A LangChain agent that connects to the SpecStream MCP server at `https://api.specstream.ai/mcp` with `langchain-mcp-adapters`, reads a request, and brings back the price. Python 3.10 or newer.

```sh
pip install -r requirements.txt langchain-openai      # or langchain-anthropic
export SPECSTREAM_API_KEY="ss_live_..."
export MODEL="openai:<model id>"                      # or "anthropic:<model id>"
python agent.py "Open-source vector databases on GitHub with more than 5,000 stars, with their license."
```

By default the agent cannot approve a price. The tools that start paid work are left out of its tool list, so it reads the request, quotes it and stops for you. To let it run work, pass `--allow-spend`, and use a key whose spending limit you set on purpose (**Agents & API** in the workspace).

One connection is enough: `MultiServerMCPClient` holds a single `specstream` entry. The key goes in the `Authorization` header and never in a prompt.
