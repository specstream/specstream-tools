# SpecStream Pack for Coda

Live web data in your Coda doc. Sync any SpecStream list into a table, with every value next to the page it was read from, price a request with a formula, and find a new list from a button.

## What it adds

- **Lists** table: every list you found, imported or combined in SpecStream, with its record count, when it was made and a link to it.
- **Records** table: the records of one list. Pick the list when you add the table. Each column has a matching "source" column with the page that value came from. Records keep the same Entity ID across lists, so the same company, place, person or posting can be matched between tables. A SpecStream schedule delivers new and changed records as a new list; sync the Lists table to see it.
- **Price(request, results)**: reads a request in plain words and returns how SpecStream read it, the most it can cost, and how many matches it takes before you pay anything. Nothing runs.

  `Price("Dentists in Leeds with their website and phone", 50)`

- **FindList(request, results, maximumPrice)**: an action for buttons and automations. It prices the request and starts it only if the price is within your maximum. Pressing it again with the same request, count and maximum in the same hour returns the list it already started, so nothing is bought twice.

## Connect

Sign in at [specstream.ai](https://specstream.ai) (new accounts get $10 of credit, no card), open **Agents & API**, create a key, and paste it when Coda asks. The tables and Price only read, so a key with a $0 spending limit is enough for them.

## Build and test locally

```bash
npm install
npm test
npx coda validate pack.ts
npx coda auth pack.ts
npx coda execute pack.ts Price "Roofers in Austin, Texas with their phone" 10
npx coda execute pack.ts Lists
npx coda execute pack.ts Records --dynamicUrl=https://specstream.ai/workspace/collections/<list ID>
```

`npx coda auth` keeps the key in `.coda-credentials.json`, which git ignores.

## Publish

`npx coda register` with a Coda API token, then `npx coda create pack.ts --name SpecStream`, `npx coda upload pack.ts`, and `npx coda release pack.ts`. The listing words are in `listing.md`.
