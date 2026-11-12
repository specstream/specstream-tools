# SpecStream for Dify

SpecStream is the live web data engine for teams and agents. One platform to build, search, extract, enrich, map, and monitor data across the entire web. Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. Source URL and read time on every value.

Source: https://github.com/specstream/specstream-tools/tree/main/integrations/dify

## Setup

1. Create a SpecStream account at https://specstream.ai. New accounts get $10 of credit, no card.
2. In the SpecStream workspace, open **Agents & API** and create an API key (it starts with `ss_live_`).
3. In Dify, install the SpecStream plugin and paste the key into its authorization.

The plugin connects only to `https://api.specstream.ai` over HTTPS.

## Tools

**Web Search** (`GET /v1/web-search`, $5 per 1,000 searches of up to 10 results, or $1 on the fast tier) answers a question from the live web in seconds, with an answer, matching rows, ranked sources and optional page passages. No quote is needed.

**Extract Pages** (`POST /v1/extract`, $0.80 per 1,000 pages) reads the main text, title and published date of 1 to 20 web pages, PDFs, Word documents or Excel spreadsheets live. A page with no text is not charged, and no quote is needed.

**Find a List** starts a list from a plain-English request.
- *What to find* and *Number of results* can come from the model.
- *Maximum price (USD)* is set by you in the tool form, never by the model. SpecStream prices the request first; if the list would cost more than your maximum, it doesn't start and costs nothing.
- *Wait for results* (up to 150 seconds) returns the rows found so far. The list keeps running after that.
- A retried call with the same request within the same hour returns the list it already started instead of buying it twice.

**Get List Results** returns the rows of a list by its list ID: status, number of rows, and each row's values with `source_url` and `checked_at`. It costs nothing.

**Create a Monitor** keeps a list current on a schedule, from every hour to every 30 days.
- *List ID* comes from Find a List.
- *Watch for* is either changes to the rows you have (a changed row costs half its row rate, an unchanged row 1¢) or new matching rows.
- *Maximum price per run* and *Maximum price per month* are set by you in the tool form, never by the model. SpecStream prices one run first; if it would cost more than your maximum per run, no monitor is made and nothing is charged. A later run above the maximum is skipped.
- *Run for* sets how many months the monitor runs before it stops on its own. Pause or delete it any time in the SpecStream workspace under **Schedules**.
- Your first monitor is on every plan, Free included.

**Get Monitor Runs** returns the latest runs of a monitor: when each ran, its status, the reason when it did not run, and the list ID of its results for Get List Results. It costs nothing.

**Find Public Records** searches the public-records lists SpecStream rebuilds every day from official sources (SEC Form D filings, nonprofits, UK and France companies, carriers and more) by words in their title. It returns each list's page, title, family and number of rows. It costs nothing.

**Get Public Records** returns the rows of one of those lists, dated on or after a day you choose, oldest first.
- *List page* comes from Find Public Records, for example `/data/form-d/state/texas`.
- Each row has a stable `_id`, its date `_date`, and one field per column.
- A row costs 5¢ the first time your account gets it from that list. A row you already had comes back free.
- *Maximum price per call* is set by you in the tool form, never by the model. Nothing is charged above it. At 0, the call only counts the rows waiting and prices them.
- *New rows only* returns only the rows your account has not had yet, for a daily check that costs nothing when nothing is new.
- Follow `next_cursor` to get the rest.

## Pricing

Each matching row costs 5¢, 15¢ or $1, depending on how much it needs, plus 5¢ for a person's email and 15¢ for a phone. A row that is left out costs nothing, and a search that finds nothing costs nothing. See https://specstream.ai/pricing.

## Support

support@specstream.ai · Docs: https://specstream.ai/docs/api
