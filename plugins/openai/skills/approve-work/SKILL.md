---
name: approve-work
description: Start paid work only after the user approves the price and its ceiling.
---

# Approve a price

Use the SpecStream MCP server at `https://api.specstream.ai/mcp`.

Each job has its own run tool: `run_new_list`, `run_imported_list`, `run_more_results`, `run_more_facts` and `run_refresh`. A run tool starts paid work, so it is a write. Use the one for the job the price is for, and only after the user says yes to the price you showed, or set a ceiling that the price fits under. Send the price's `quote_id` and `quote_hash`, the ceiling the user approved in cents as `confirm_max_cents`, and an `idempotency_key` that you create once and keep.

If the reply is lost, call the same run tool again with the same `idempotency_key`. SpecStream returns the same run and doesn't start a second one. If the price expired or the request changed, get a new price and ask again.

SpecStream never charges more than the approved ceiling. If the balance or a spending limit stops the work, say so plainly and keep the request as it is. Balance and payment stay in the user's SpecStream workspace. Don't open a payment sheet from chat.

Follow progress with `get_find`. To stop a run, call `cancel_find`. The run keeps what it already found.

While a run is going, keep the user on it. Open the Lists app with `open_specstream` so they watch the rows arrive, and tell them a run can take a few minutes. Don't answer the request from your own search or browsing while the run is going, and never show your own findings as SpecStream's rows. If the user asks for a quick answer in the meantime, use `search_web` and say that it is a quick search, not the run. When `get_find` shows the run finished, show its rows with `show_specstream_records`.

A run can take up to five minutes, and a long run is still working. Keep calling `get_find` until it shows the run finished, and keep the user on the Lists app the whole time. Never stop waiting to do the research yourself. When the run finishes with fewer rows than asked, show the rows it delivered: each one meets every condition on a page SpecStream read. Then offer more results with `quote_more_results`. Never add rows from your own research to the run's rows, and never show your own table as the run's result.
