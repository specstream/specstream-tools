# SpecStream

The live web data engine.

One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. It runs through the API and MCP, and inside Sheets, CRMs, Slack, n8n, Zapier and the other tools teams already use.

Source URL and read time on every value.

## What it adds

- The SpecStream MCP server at `https://api.specstream.ai/mcp` (Streamable HTTP).
- `specstream-compile`: reads your request into the conditions every row must meet and the details to bring back. Nothing runs yet.
- `specstream-review-work`: gets the exact price and the maximum for that request. Nothing runs yet.
- `specstream-approve-work`: starts the run once you approve that exact maximum.
- `specstream-continue-work`: reads the rows with their sources, sends them to Google Sheets, Excel, Airtable, Notion, HubSpot or Salesforce, and prices more rows, more details or a refresh.

## Sign in

Press Sign in on the SpecStream connector. Your browser opens SpecStream's sign-in page, where you sign in or create an account. There is no key to paste. A new account gets $10 of credit with no card, to use within 30 days.

## Prices

- A matching row costs 5 cents, 15 cents or $1, depending on how much each row needs.
- An email adds 5 cents and a phone 15 cents.
- A company left out and a run that finds nothing cost nothing.
- The price and the exact maximum are shown before anything runs, and nothing runs until you approve.
- A refresh costs half the rate for a new or changed row and 1 cent for an unchanged one.

Full prices: https://specstream.ai/pricing?utm_source=rakazo

## What it sends

The plugin sends your request, your edits and your approvals to api.specstream.ai over HTTPS, and the rows come back from the same server. It reads no local files.

## Links

- SpecStream: https://specstream.ai/?utm_source=rakazo
- MCP docs: https://specstream.ai/docs/mcp?utm_source=rakazo
- Source: https://github.com/specstream/specstream-tools

## License

MIT
