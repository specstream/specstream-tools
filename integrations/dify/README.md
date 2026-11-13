# SpecStream for Dify

SpecStream is the live web data engine for teams and agents. One platform to build, search, extract, enrich, map, and monitor data across the entire web. Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. Source URL and read time on every value.

Source: https://github.com/specstream/specstream-tools/tree/main/integrations/dify

## Setup

1. Create a SpecStream account at https://specstream.ai. New accounts get $10 of credit, no card.
2. In the SpecStream workspace, open **Agents & API** and create an API key (it starts with `ss_live_`).
3. In Dify, install the SpecStream plugin and paste the key into its authorization.

The plugin connects only to `https://api.specstream.ai` over HTTPS.

## Tools

**Web Search** (`GET /v1/web-search`, $5 per 1,000 searches of up to 10 results) answers a question from the live web in seconds, with an answer, matching rows, ranked sources and optional page passages. No quote is needed. Set **Speed** to Fast for the ranked results in about a second: a fast search costs $1 per 1,000.

**Extract Pages** (`POST /v1/extract`, $0.80 per 1,000 pages) reads the main text, title and published date of 1 to 20 web pages, PDFs, Word documents or Excel spreadsheets live. A page with no text is not charged, and no quote is needed.

**Deep Search** takes a request in plain words and returns every match on the live web, in structured rows. You pay for each row delivered: 5¢, 15¢ or $1 depending on what the row needs, plus 5¢ for a person's email and 15¢ for a phone.
- *What to find* and *Number of results* can come from the model.
- *Maximum price (USD)* is set by you in the tool form, never by the model. SpecStream prices the request first; if the list would cost more than your maximum, it doesn't start and costs nothing.
- *Wait for results* (up to 150 seconds) returns the rows found so far. The list keeps running after that.
- A retried call with the same request within the same hour returns the list it already started instead of buying it twice.

**Get List Results** returns the rows of a list by its list ID: status, number of rows, and each row's values with `source_url` and `checked_at`. It costs nothing.

**Research Report** (`POST /v1/research`) answers a question with a written report from the live web, with the page behind each cited sentence. A report costs $0.10 at quick depth, $0.30 at standard and $1.00 at deep, charged once when the report is delivered. A run that fails, is cancelled or reads no page is not charged.
- *Question* can come from the model.
- *Depth* and *Maximum price (USD)* are set by you in the tool form, never by the model. If the depth costs more than your maximum, the report doesn't start and costs nothing.
- *Wait for the report* (up to 150 seconds) returns the report when it is ready in that time. The run keeps going after that.
- A retried call with the same question and depth within the same hour returns the report it already started instead of buying it twice.

**Get Research Report** returns a report by its report ID: status, stage, the report text and its sources, each with the time the page was read. It costs nothing.

**Open Browser** (`POST /v1/browser/sessions`) opens a real browser on SpecStream's server, for pages that need clicks, forms or scripts. A session costs $0.10 an hour, charged by the second, plus $1 per 1,000 steps ($0.001 a step). A session that fails to start is not charged.
- *URL* can come from the model. The browser opens the page and returns its text with the session ID.
- *Maximum minutes* (1 to 60) is set by you in the tool form, never by the model. The browser closes on its own at that time, or after 5 minutes without a step, so 5 minutes cost at most 1¢ plus the steps.
- *Allowed hosts* limits the browser to the hosts you list, such as `example.com` or `*.example.com`.
- A page whose site opted out or whose robots.txt disallows SpecStream is refused as blocked.

**Browser Step** runs one step in an open browser by its session ID: a Playwright MCP tool name such as `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type` or `browser_take_screenshot`, with its arguments as one JSON object, or `browser_read` for the page's text. A screenshot comes back as a picture. Each step that runs costs $0.001.

**Close Browser** closes the browser and returns the seconds it ran, its steps and what it cost. Call it when the task is done: an open browser is charged until it closes.

**Create a Monitor** keeps a list current on a schedule, from every hour to every 30 days.
- *List ID* comes from Deep Search.
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
