---
name: specstream-research
description: Answer a question with a written research report from the live web, with the page behind each cited sentence ($0.10 quick, $0.30 standard, $1.00 deep a report; nothing runs before the person approves the price). Use it when one search is not enough and the person wants a sourced report, not rows.
---

# Research a question from the live web

SpecStream is the live web data engine for teams and agents. Use the configured MCP server at `https://api.specstream.ai/mcp`.

A research report answers a question in plain words with written text from the live web. Each cited sentence carries the page it came from, the time that page was read and the passage. Use it when the person wants a sourced report on a question. For one fact, use `search_web`. For rows with the same facts on each row, use `compile`.

1. Call `research_price` with `{"depth": "<depth>"}`, or with no arguments for all three depths. It is free. A report costs $0.10 (`quick`, the question as one part, about a minute), $0.30 (`standard`, the question in 3 to 5 parts, about four minutes) or $1.00 (`deep`, the question in 6 to 10 parts, about five minutes).
2. Show the person the depth and its price, and ask them to approve it. A balance or an earlier approval is never permission to spend.
3. After the person approves, call `start_research` with `{"question": "<the question>", "depth": "<depth>", "confirm_max_cents": <the approved price in cents>, "idempotency_key": "<a new key of 8 characters or more>"}`. Send the same key again on a retry, so that the report starts once. A price above the approved amount runs nothing.
4. Call `get_research` with `{"id": "<the report's id>"}` until `status` is `completed`. One call can end before the report does: call it again.
5. Give the person `report.content` with its `[1]` markers, and under it the page of each citation from `report.citations`. Do not add a claim the report does not make.

The price is taken from the account balance once, when the report is delivered. A cancelled report is not charged, and `cancel_research` stops one. `include_domains` and `exclude_domains` choose the sites, `length` is `short`, `standard` or `long`, and `output_schema` (a JSON Schema) returns JSON in place of text.
