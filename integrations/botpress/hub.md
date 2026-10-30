# SpecStream

Live web data for your bot. A user asks for many real things at once (every roofer in Columbus rated 4.5 or better, US companies that filed to raise $5M or more this week, food banks in Texas with their revenue) and your bot answers with every match from the live web as rows. Every value carries the page it came from.

The user sees the price before anything runs, and pays for each result delivered.

## Configuration

1. Create a SpecStream account at [specstream.ai](https://specstream.ai). New accounts start with $10 of work, no card.
2. Open **Agents & API** and create an API key (it starts with `ss_live_`).
3. Paste it into **API key** and set **Most one list may cost (USD)**. Approve and run refuses any price above it.

## Usage

Three actions, in this order:

1. **Get a price**: the request in plain words and how many rows. Returns how SpecStream read the request and the most it can cost (`price`, `maximumCents`). Nothing runs and nothing is charged.
2. **Approve and run**: only after the user says yes to that price, with `quoteId`, `quoteHash` and `approvedCents` = `maximumCents`. Returns `findId`.
3. **Get rows**: `findId`. Each row has its cells, each cell its value and `sourceUrl`. Call again with `nextCursor` for more; reading is free.

A typical flow: the user asks → Get a price → the bot says "10 coffee roasters in Portland with their websites, up to $1.00. Go ahead?" → on yes, Approve and run → Get rows → the bot lists them with their sources.

## Limitations

- A run takes from a few seconds to a few minutes. If Get rows says `running`, read again a little later; rows already found are there.
- Approve and run never costs more than the approved price, and approving the same quote twice doesn't charge twice.
- One request finds one kind of thing. For a different list, get a new price.

## Changelog

- 1.0.1: Get a price reads the request back in plain words.
- 1.0.0: First release: Get a price, Approve and run, Get rows.
