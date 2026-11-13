# SpecStream web search for Tessl

SpecStream is the live web data engine for teams and agents.

This plugin gives your agent the SpecStream Search API, the most accurate web search API in the world. The proof is at https://specstream.ai/benchmarks?utm_source=tessl.

## What it adds

- The SpecStream MCP server at `https://api.specstream.ai/mcp` (Streamable HTTP).
- `search-web`: answers a question from the live web in seconds, with the ranked sources of the answer.

## Install

```bash
tessl install specstream/search-web
```

## Sign in

The first call opens SpecStream's sign-in page in your browser, where you sign in or create an account. There is no key to paste. A new account gets $10 of credit with no card.

## Prices

- A search costs $5 per 1,000 searches of up to 10 results.
- On the fast tier (`"speed": "fast"`) a search costs $1 per 1,000.
- A search needs no quote and no approval.

Full prices: https://specstream.ai/pricing?utm_source=tessl

## What it sends

The plugin sends your question to api.specstream.ai over HTTPS, and the answer comes back from the same server. It reads no local files.

## Links

- SpecStream: https://specstream.ai/?utm_source=tessl
- MCP docs: https://specstream.ai/docs/mcp?utm_source=tessl
- Source: https://github.com/specstream/specstream-tools/tree/main/plugins/tessl
