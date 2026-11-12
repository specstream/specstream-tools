# SpecStream data source for Grafana

Live web data from SpecStream, in a Grafana table. Every row carries the page its values were read from.

## What it does

- **Search**: type a question in everyday words. The SpecStream Search API answers from the live web and returns one row per result: its name, the facts the question asks for, a match score, a snippet and the source page.
- **Saved list**: pick a list you already have in SpecStream. Its rows come back as a table with one column per list column and the source page of each row.

Use the tables in any panel, in transformations, and in alerts.

## Set up

1. Make an API key at https://specstream.ai (sign-up comes with $10 of credit, no card).
2. In Grafana, add a data source, pick SpecStream, and paste the key. The key is stored encrypted and is sent only to https://api.specstream.ai.
3. Choose Save and test.

Each search is one Search API call at $5 per 1,000 searches of up to 10 results, or $1 on the fast tier. Reading a saved list is free. The plugin never starts a Deep Search run and never spends credit on a list.

Docs: https://specstream.ai/docs.
