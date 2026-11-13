# n8n-nodes-specstream-research

An [n8n](https://n8n.io) community node for [SpecStream](https://specstream.ai), the live web data engine for teams and agents. It holds one node, **SpecStream Research**, which answers a question with a written report from the live web, with the page behind each cited sentence.

You write the question in plain words. SpecStream searches, reads the pages and writes the report. Each cited sentence carries a `[1]` marker, and the report lists the page, the time it was read and the passage behind each marker.

## Install

In n8n, go to **Settings > Community nodes**, choose **Install** and enter `n8n-nodes-specstream-research`.

Create an API key under **Agents & API** in your SpecStream workspace, then add a **SpecStream Research API** credential in n8n with that key.

## Use

Add the **SpecStream Research** node to a workflow, choose the credential and choose an operation.

| Operation | What it does |
| --- | --- |
| Write a Report | Starts a report for your question and, by default, waits until it is written |
| Get a Report | Reads a report by its ID. Reading is free |
| Cancel a Report | Stops a report that is being written. A cancelled report is not charged |
| Get Many Reports | Lists the reports of your account, newest first. Listing is free |

Settings of **Write a Report**:

| Setting | What it does |
| --- | --- |
| Question | The question the report answers, up to 15,000 characters |
| Depth | **Quick**, **Standard** or **Deep**. The depth sets the price |
| Wait for the Report | On: the step returns the finished report. Off: the step returns the report ID at once, and **Get a Report** reads it later |
| Length | **Short**, **Standard** or **Long** |
| Language | The language of the report, such as `en`, `fr` or `pt-BR` |
| Include Domains, Exclude Domains | The only sites the report reads, or sites it must not read |
| Pages Published After | Read only pages published after this day |
| JSON Schema | A JSON Schema for the answer. The report then also returns the answer as JSON in this shape |
| Wait Up To (Minutes) | The longest the step waits, 15 minutes by default. A report that is still being written then stops the step with its ID, and the report is not lost |

A finished report carries:

| Field | Meaning |
| --- | --- |
| `report.content` | The text, in Markdown, with `[1]` markers |
| `report.citations` | For each marker: the page, the time it was read and the passage |
| `report.sources` | Every page read |
| `report.structured` | The answer as JSON, when you set a JSON Schema |
| `usage.charged_usd` | What the report cost |

The node can also be used as a tool by an n8n AI agent.

## Pricing

A report costs $0.10 (Quick), $0.30 (Standard) or $1.00 (Deep). The price is taken from your balance once, when the report is delivered. A cancelled report is not charged. A quick report takes about a minute, a standard report about four minutes and a deep report about five.

When n8n retries a failed step, the retry returns the same report. It does not start a second one.

New accounts start with $10 of credit, no card. See [pricing](https://specstream.ai/pricing).

## Other SpecStream nodes

To search the web, read pages or build a list from a workflow, install [`n8n-nodes-specstream`](https://www.npmjs.com/package/n8n-nodes-specstream). To start a workflow when a monitor finds new or changed records, install [`n8n-nodes-specstream-monitor`](https://www.npmjs.com/package/n8n-nodes-specstream-monitor).

## Develop

```sh
npm install
npm run build
npm run lint
npm test
```

## License

MIT
