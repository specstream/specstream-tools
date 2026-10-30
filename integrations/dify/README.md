# SpecStream for Dify

SpecStream is the live web data engine for teams and agents. Describe the data you need in plain words, for example "roofing companies in Columbus, Ohio with their website and phone", and get structured records from the live web, every value with the page it was read from. The price is shown before anything runs, and you pay for each result delivered.

Source: https://github.com/specstream/specstream-tools/tree/main/integrations/dify

## Setup

1. Create a SpecStream account at https://specstream.ai. New accounts get $10 of work free, no card.
2. In the SpecStream workspace, open **Agents & API** and create an API key (it starts with `ss_live_`).
3. In Dify, install the SpecStream plugin and paste the key into its authorization.

The plugin connects only to `https://api.specstream.ai` over HTTPS.

## Tools

**Find a List** starts a list from a plain-English request.
- *What to find* and *Number of results* can come from the model.
- *Maximum price (USD)* is set by you in the tool form, never by the model. SpecStream prices the request first; if the list would cost more than your maximum, it doesn't start and costs nothing.
- *Wait for results* (up to 150 seconds) returns the rows found so far. The list keeps running after that.
- A retried call with the same request within the same hour returns the list it already started instead of buying it twice.

**Get List Results** returns the rows of a list by its list ID: status, number of rows, and each row's values with `source_url` and `checked_at`. It costs nothing.

## Pricing

Each matching row costs from 10¢ (Standard, up to five facts a row). Searches that find nothing cost nothing. See https://specstream.ai/pricing.

## Support

support@specstream.ai · Docs: https://specstream.ai/docs/api
