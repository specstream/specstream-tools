# SpecStream

SpecStream is the live web data engine for teams and agents. It turns a plain-English request into a list of matching rows from the live web, each with the page it was read from. Use the `specstream` MCP server.

1. **Read the request** with `compile`. Say back what it found: the kind of thing, the conditions every row must meet, the details to bring back and the quantity. Reading costs nothing.
2. **Get the price** with `quote_capacity_work` for that reading. Quoting costs nothing.
3. **Show the price and wait.** Tell the person the most it can cost and ask for a clear yes. Never call `authorize_capacity_work` without that yes, and never approve more than the quoted maximum.
4. **Read the rows** with `list_find_rows`. Each value carries its source page. Rows in `possible` are unconfirmed and unbilled; never count them as results.

Requests that work well: local businesses with ratings, companies from registries, companies that use a tool, funding and new-executive signals, grants, tenders, clinical trials, papers, datasets, regulations, vulnerabilities, apps, repositories, packages, podcasts and books. `list_request_templates` returns requests that already work.

Set `SPECSTREAM_API_KEY` to a key from **Agents & API** in the SpecStream workspace (https://specstream.ai/workspace/settings). Never ask for the key in chat. New accounts get $10 of credit.
