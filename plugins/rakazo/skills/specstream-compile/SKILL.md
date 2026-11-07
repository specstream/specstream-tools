---
name: specstream-compile
description: Reads a request in plain words into the conditions every row must meet and the details to bring back, before anything runs or costs. Use when someone wants to find, build or monitor data from the live web.
license: MIT
metadata:
  category: search
  author: SpecStream
---

# Read the request

SpecStream is the live web data engine for teams and agents. Use the configured MCP server at `https://api.specstream.ai/mcp`.

Use `compile` to read the person's request. Say back what it found: the kind of thing, the conditions, the details to bring back and the quantity. Separate the conditions that must hold from the details that are nice to have. Use `edit_spec` for a deliberate change. Never drop a hard condition quietly, and never treat missing evidence as a no. Reading a request does not start any work.

If someone asks for people by job title, say that results may be few. `list_request_templates` returns requests that already work for each kind.

The same saved request can be revised, branched, compared and shared, in the workspace or through this agent. Never ask for an API key in chat. Use the connector's own sign-in.
