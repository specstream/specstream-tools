# SpecStream for Claude

The live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change.

Source URL and read time on every value.

## What it adds

- **The SpecStream MCP server** at `https://api.specstream.ai/mcp`. The first time you use it, Claude asks you to sign in to SpecStream in your browser (OAuth). No API key is stored in the plugin.
- **Four skills**: `compile` reads your request and shows how SpecStream understood it, `review-work` gets the price, `approve-work` starts the list after you say yes to that price, and `continue-work` brings back more rows, refreshes a list or adds details.

## What it sends

Your request and your answers to the price go to SpecStream's API over HTTPS. Results come back from the same API. Nothing else is read from your machine, and nothing runs locally.

## Price

Reading a request and getting a price are free. A list runs only after you approve its maximum price, and you pay for each row delivered, from 5 cents each. New accounts get $10 of credit. [Pricing](https://specstream.ai/pricing) · [API docs](https://specstream.ai/docs/api) · support@specstream.ai

## License

MIT
