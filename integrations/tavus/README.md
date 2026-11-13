# SpecStream in Tavus PALs

Tavus PALs call remote MCP servers through connectors. This folder makes a connector for the SpecStream tool server (`https://api.specstream.ai/mcp`) and attaches it to a PAL, with `setup_connector.py` (Python 3.10+, no dependencies).

## With an API key

Create a SpecStream key under Agents & API at https://specstream.ai/workspace, and a Tavus key in the Tavus Developer Portal. Then:

```
export TAVUS_API_KEY=...
export SPECSTREAM_API_KEY=...
python setup_connector.py --face-id <face_id>     # a new PAL with the connector
python setup_connector.py --pal-id <pal_id>       # or attach it to a PAL you have
```

Tavus sends the SpecStream key as a bearer token. The script runs Tavus's runtime check and prints the connector and PAL ids. It exits with 1 when the check fails.

## With OAuth

Leave `SPECSTREAM_API_KEY` unset. The connector then uses OAuth, and the script prints an `authorize_url`: open it and sign in to SpecStream. Then attach the connector as above.

`--dry-run` prints the requests (keys masked) and sends nothing.

## Prices

A search costs $5 per 1,000 ($1 per 1,000 with speed=fast), Extract $0.80 per 1,000 pages. A matching row of a list costs 5 cents, 15 cents or $1. Nothing that costs money runs until the price is approved.
