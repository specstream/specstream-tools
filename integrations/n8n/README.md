# n8n-nodes-specstream

An [n8n](https://n8n.io) community node for [SpecStream](https://specstream.ai), the live web data engine for teams and agents. Describe a list in plain words, review the price, approve a maximum, and pass every match, each with its sources, to the next node.

Nothing runs without a price you approved. A trigger or a schedule alone never spends money.

## Install

In n8n, go to **Settings > Community nodes**, choose **Install** and enter `n8n-nodes-specstream`.

Create an API key under **Agents & API** in your SpecStream workspace, then add a **SpecStream API** credential in n8n with that key.

## Operations

The **SpecStream** node has five operations. Together they follow the same order as the product: ask, read, price, approve, read the results.

| Operation | What it does |
| --- | --- |
| Find a List | Describes a list in plain words, prices it and starts it when the price is within your Maximum Price. Returns the List ID |
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

New accounts start with $10 of credit for 30 days, no card. A delivered result costs 5 cents, 15 cents or $1 depending on how many facts it carries. No result, no charge. See [pricing](https://specstream.ai/pricing).

## Develop

```sh
npm install
npm run build
npm run lint
npm test
```

The package is published from GitHub Actions with provenance, as n8n requires. Source and issues: [github.com/specstream/specstream-tools](https://github.com/specstream/specstream-tools). MIT license.
