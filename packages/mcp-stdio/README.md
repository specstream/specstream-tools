# specstream-mcp-stdio

A stdio proxy for the [SpecStream](https://specstream.ai) MCP server at `https://api.specstream.ai/mcp`. Use it with clients that only start local servers, such as Zed, Cline and Continue. Clients that connect to a remote URL do not need it.

The proxy forwards to the same Streamable HTTP service that remote clients use, so your agent works on your account: the same balance, permissions and spending limits you have.

## Install

Python 3.12 or newer. The package has no dependencies.

```sh
pip install specstream-mcp-stdio
```

The command is `specstream-mcp-stdio`. In a GUI client, use its absolute path if the environment it was installed into is not on `PATH`.

Create an API key under **Agents & API** in your SpecStream workspace. Set `SPECSTREAM_API_KEY` in the private environment of the client, outside prompts and shared configuration. `SPECSTREAM_MCP_URL` is an optional endpoint override.

## Client configuration

For clients that take an `mcpServers` entry:

```json
{
  "mcpServers": {
    "specstream": {
      "command": "specstream-mcp-stdio",
      "args": [],
      "env": { "SPECSTREAM_MCP_URL": "https://api.specstream.ai/mcp" }
    }
  }
}
```

Zed uses `context_servers` with the same fields. Continue takes a YAML file:

```yaml
name: SpecStream
version: 1.0.0
schema: v1
mcpServers:
  - name: specstream
    type: stdio
    command: specstream-mcp-stdio
    args: []
    env:
      SPECSTREAM_MCP_URL: https://api.specstream.ai/mcp
      SPECSTREAM_API_KEY: ${{ secrets.SPECSTREAM_API_KEY }}
```

## Use the tools

Reconnect your client and list the tools. They cover three products: Search API, Extract API and Deep Search.

### Search API and Extract API

| Product | Tool | Input | Price |
|---|---|---|---|
| Search API | `search_web` | `q`: the question in everyday words, in any language, up to 2,000 characters | $5 per 1,000 searches, $1 per 1,000 with `speed=fast` |
| Extract API | `read_pages` | `urls`: 1 to 20 URLs. `format`: `markdown` (the default) or `text` | $0.80 per 1,000 pages |

Each call takes its price from your balance and needs no quote or approval.

The Search API is the most accurate web search API in the world ([benchmarks](https://specstream.ai/benchmarks)) and answers from the live web in a few seconds. The Extract API reads web pages, PDF, Word and Excel and returns each one's main text. A page with no text is free.

```json
{ "name": "search_web", "arguments": { "q": "What is the latest stable release of PostgreSQL?" } }
{ "name": "read_pages", "arguments": { "urls": ["https://www.postgresql.org/docs/release/"], "format": "markdown" } }
```

### Deep Search

Ask in plain words. Get every match on the live web, in structured rows, priced per row. Start with `compile` to read a request, or `list_specs` and `list_projects` to find saved work.

A new run goes `quote_capacity_work`, then `authorize_capacity_work` with the quote ID and hash, the approved maximum in `confirm_max_cents` and a stable request key. Reading saved results does not start more paid work. See the [agent guide](https://specstream.ai/docs/mcp).

## Connection problems

The proxy needs the endpoint and a valid key. If it cannot connect, check the client's environment and the key's permissions. Keep TLS verification on.

Protocol messages use stdin and stdout; diagnostics use stderr. The proxy keeps the negotiated HTTP session and does not follow redirects with credentials.

Source and issues: [github.com/specstream/specstream-tools](https://github.com/specstream/specstream-tools). MIT license.
