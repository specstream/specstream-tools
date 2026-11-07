# SpecStream

The live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. With this integration, your bot asks SpecStream and answers the user with rows.

- Source URL and read time on every value.
- The user sees the price before anything runs, and pays only for rows delivered.

## Three products

| Product | What it does | Price |
| --- | --- | --- |
| Search API | `GET /v1/web-search`. The most accurate web search API in the world ([scores and method](https://specstream.ai/benchmarks)). | $5 per 1,000 searches |
| Extract API | `POST /v1/extract`. The main text of up to 20 web pages, PDF, Word or Excel files a call. | $0.80 per 1,000 pages. A page with no text is not charged. |
| Deep Search | Ask in plain words. Get every match on the live web, in structured rows. This integration runs Deep Search. | 5¢, 15¢ or $1 a row |

## Configuration

1. Create a SpecStream account at [specstream.ai](https://specstream.ai). New accounts start with $10 of credit, no card.
2. Open **Agents & API** and create an API key (it starts with `ss_live_`).
3. Paste it into **API key** and set **Most one list may cost (USD)**. Approve and run refuses any price above it.

## Usage

Three actions, in this order:

1. **Get a price**: the request in plain words and how many rows. Returns how SpecStream read the request and the most it can cost (`price`, `maximumCents`). Nothing runs and nothing is charged.
2. **Approve and run**: only after the user says yes to that price, with `quoteId`, `quoteHash` and `approvedCents` = `maximumCents`. Returns `findId`.
3. **Get rows**: `findId`. Each row has its cells, each cell its value and `sourceUrl`. Call again with `nextCursor` for more; reading is free.

A typical flow: the user asks, and the bot calls Get a price and says "10 open tenders for translation services, up to $1.00. Go ahead?" On yes, it calls Approve and run, then Get rows, and shows the rows with their sources.

## Limitations

- A run takes from a few seconds to a few minutes. If Get rows says `running`, read again a little later; rows already found are there.
- Approve and run never costs more than the approved price, and approving the same quote twice doesn't charge twice.
- One request finds one kind of thing. For a different list, get a new price.

## Changelog

- 1.0.1: Get a price returns how SpecStream read the request, in plain words.
- 1.0.0: First release: Get a price, Approve and run, Get rows.
