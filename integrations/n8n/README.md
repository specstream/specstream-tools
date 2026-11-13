# n8n-nodes-specstream

An [n8n](https://n8n.io) community node for [SpecStream](https://specstream.ai), the live web data engine for teams and agents. It puts the Search API, the Extract API and Deep Search in a workflow. For Deep Search, describe a list in plain words, review the price, approve a maximum, and pass every match, each with its sources, to the next node.

Nothing in Deep Search runs without a price you approved. A trigger or a schedule alone never spends money. Web Search and Extract Pages take a flat price from your balance on each call, with no quote and no approval.

## Install

In n8n, go to **Settings > Community nodes**, choose **Install** and enter `n8n-nodes-specstream`.

Create an API key under **Agents & API** in your SpecStream workspace, then add a **SpecStream API** credential in n8n with that key.

## Operations

### Search API

**Web Search** answers a question from the live web in a few seconds (`GET /v1/web-search`). Write the Search Query in everyday words, 1 to 2,000 characters. Turn on Include Passages to also get the main text of the top matching pages. The Search API is the most accurate web search API in the world ([scores and method](https://specstream.ai/benchmarks)).

### Extract API

**Extract Pages** returns the main text, title and published date of up to 20 URLs a call, read live (`POST /v1/extract`). It reads web pages, PDF, Word and Excel. Separate the URLs with newlines or commas, and choose Markdown or Plain Text as the Output Format.

### Deep Search

Deep Search returns structured rows. Its operations in the **SpecStream** node follow the same order as the product: ask, read, price, approve, read the results.

| Operation | What it does |
| --- | --- |
| Find a List | Describes a list in plain words, prices it and starts it when the price is within your Maximum Price. Returns the List ID |
| Find Rows | The rows of a list that hold a value in a column (any column when Column is empty), each with the page it was read from. Accepts the List ID or the list's link |
| Get List Results | One item per matching row, each with the page it was read from. Turn on Return All to follow every page of a long list, or set a Limit |
| Read Request | Reads a request in your own words and returns how SpecStream understood it, with a request hash |
| Review Quote | Prices that request, or more results, added details or a recheck on an earlier run (set Earlier Run ID for those). Returns the quote, its hash and the maximum |
| Approve Quoted Work | Approves that exact quote. You type the maximum in dollars (`Confirm Max USD`); there is no default, and zero is refused |

Optional settings (Run Key, Locale, Project ID) sit under **Options** on the operation they belong to.

The **SpecStream Trigger** node starts a workflow when a run completes, a monitor finds new or changed records, or records are added to a collection. It checks the signature of every event.

Use a stable `Stable Execution Key` on Approve Quoted Work. If a retry happens, the same key returns the same work and you do not pay twice.

## Workflows

Three importable workflows are in [`workflows/`](workflows):

- `compile-confirm-run.json`: read, price, approve and fetch results
- `export-hubspot-sheets-slack.json`: send finished results to HubSpot, Google Sheets and Slack
- `export-salesforce-pipedrive.json`: send finished results to Salesforce and Pipedrive

## Pricing

New accounts start with $10 of credit, no card. The Search API costs $5 per 1,000 searches of up to 10 results, or $1 on the fast tier. The Extract API costs $0.80 per 1,000 pages, and a page with no text is free. In Deep Search, a delivered result costs 5 cents, 15 cents or $1 depending on how many facts it carries. No result, no charge. See [pricing](https://specstream.ai/pricing).

## Develop

```sh
npm install
npm run build
npm run lint
npm test
```

The package is published from GitHub Actions with provenance, as n8n requires. Source and issues: [github.com/specstream/specstream-tools](https://github.com/specstream/specstream-tools). MIT license.
