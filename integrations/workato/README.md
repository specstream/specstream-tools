# SpecStream for Workato

Ask for any dataset in plain words inside a Workato recipe and get structured records from the live web.

## Actions

- **Find a list**: describe the list, choose how many results and the most it may cost. If the price is within your maximum the list starts; otherwise nothing runs and the step stops with the price. A retried job within the same hour gets the run it already started, so it never buys the list twice.
- **Get list results**: every row found so far for a List ID, flat fields ready to map. Free; nothing runs.
- **Custom action**: call any endpoint of the [SpecStream API](https://specstream.ai/docs/api) with the same connection.

## Trigger

- **New row**: one job for every row, when a list you asked for finishes or when a list you keep current finds new or changed rows. Deliveries are signed (HMAC-SHA256 over the timestamp and body) and checked before a job starts.

## Connect

Create an API key in SpecStream under [Agents & API](https://specstream.ai/workspace/settings) and paste it into the connection. New accounts start with $10 of work free.

Pricing: you pay for each row delivered, from 5 cents each. [specstream.ai/pricing](https://specstream.ai/pricing)
