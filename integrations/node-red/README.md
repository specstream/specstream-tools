# node-red-contrib-specstream

Node-RED nodes for [SpecStream](https://specstream.ai), the live web data engine for teams and agents.

| Node | What it does |
| --- | --- |
| **specstream search** | Searches the web (`GET /v1/web-search`). Set `msg.payload` to the query |
| **specstream extract** | Reads up to 20 pages or files (`POST /v1/extract`). Set `msg.payload` to a URL or an array of URLs |
| **specstream research** | Answers a question with a written report from the live web, with the page behind each cited sentence (`POST /v1/research`). Set `msg.payload` to the question |

## Install

In the Node-RED editor, open **Manage palette**, choose **Install** and search for `node-red-contrib-specstream`. Or run `npm install node-red-contrib-specstream` in your Node-RED user directory.

Create an API key under **Agents & API** in your SpecStream workspace, then add it in the SpecStream config node.

## Research reports

The **specstream research** node starts a report for the question and, by default, waits until it is written. The finished report is in `msg.payload`: `report.content` holds the text in Markdown with `[1]` markers, and `report.citations` holds the page, the time it was read and the passage behind each marker.

A report costs $0.10 (quick), $0.30 (standard) or $1.00 (deep). The price is taken from your balance once, when the report is delivered. Choose the depth in the node, or set `msg.depth`.

With **Wait for the report** off, the node returns at once and sets `msg.reportId`. To read that report later, send a message with `msg.reportId` to the node. Reading is free.

The same message sent again returns the same report. It does not start a second one.

## Pricing

A search costs $5 per 1,000 searches of up to 10 results. Extract costs $0.80 per 1,000 pages. New accounts start with $10 of credit, no card. See [pricing](https://specstream.ai/pricing).

Docs: https://specstream.ai/docs/api
