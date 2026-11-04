# SpecStream

The live web data engine for teams and agents. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask in plain words for companies, local businesses, grants, tenders, clinical trials, papers, regulations, apps, repositories or packages. You get structured rows from the live web.

Source URL and read time on every value.

## What it adds

- The SpecStream MCP server at `https://api.specstream.ai/mcp` (Streamable HTTP).
- `specstream-compile`: reads your request back as the conditions every row must meet and the details to bring back. Nothing runs yet.
- `specstream-review-work`: gets the exact price and the maximum for that request. Nothing runs yet.
- `specstream-approve-work`: starts the run once you approve that exact maximum.
- `specstream-continue-work`: reads the rows with their sources, sends them to Google Sheets, Excel, Airtable, Notion, HubSpot or Salesforce, and prices more rows, more details or a refresh.

## Sign in

Press Sign in on the SpecStream connector. Your browser opens SpecStream's sign-in page, where you sign in or create an account. There is no key to paste. A new account gets $10 of work with no card, to use within 30 days.

## Prices

- A matching row costs 5 cents, 15 cents or $1, depending on how much each row needs.
- An email adds 5 cents and a phone 15 cents.
- A company left out and a run that finds nothing cost nothing.
- The price and the exact maximum are shown before anything runs, and nothing runs until you approve.
- A refresh costs half the rate for a new or changed row and 1 cent for an unchanged one.

Full prices: https://specstream.ai/pricing?utm_source=rakazo

## Example requests

- Independent bookstores in Oregon with a website
- Open grants for community solar projects in New England, with deadline and amount
- Clinical trials recruiting for type 1 diabetes in Germany
- Seed-funded software companies in France this year, with the founders' names
- Open tenders from city governments in Texas for school transport, with due date and link

## What it sends

The plugin sends your request, your edits and your approvals to api.specstream.ai over HTTPS, and the rows come back from the same server. It reads no local files.

## Links

- SpecStream: https://specstream.ai/?utm_source=rakazo
- MCP docs: https://specstream.ai/docs/mcp?utm_source=rakazo
- Source: https://github.com/specstream/specstream-tools

## License

MIT
