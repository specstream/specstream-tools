# specstream (Ruby)

SpecStream: the live web data engine.
One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change.

This gem is the Ruby client for the Deep Search API (with monitors that keep a list current on a schedule), the Search API and the Extract API.
It has no dependencies outside Ruby's standard library and needs Ruby 3.1 or newer.

```sh
gem install specstream
```

Create an API key under **Agents & API** in your SpecStream workspace and keep it in the environment:

```sh
export SPECSTREAM_API_KEY="ss_live_..."
```

## Deep Search: read a request, get the price

```ruby
require "specstream"

client = Specstream::Client.new(ENV.fetch("SPECSTREAM_API_KEY"))

reading = client.compile("Open-source vector databases on GitHub, with their license.")
offer = client.quote_capacity_work({
  "ast_hash" => reading["ast_hash"],
  "operation" => "find",
  "requested_units" => reading["ast"]["limit"]["max"]
})
puts offer["maximum_cents"], offer["expires_at"]
```

Nothing has run yet. A price lasts 30 minutes.

## Approve it, then read the results

After a person approves, send the approved maximum in cents and a request key you saved first:

```ruby
run = client.authorize_capacity_work({
  "quote_id" => offer["quote_id"],
  "quote_hash" => offer["quote_hash"],
  "confirm_max_cents" => approved_maximum_cents,
  "idempotency_key" => saved_request_key
})

client.get_find(run["find_id"])                  # progress
client.each_row(run["find_id"]) { |row| p row }  # every row, page after page
```

`authorize_capacity_work` sends nothing unless the quote, its signature, the maximum and the key are all present.
If the response is lost, `get_capacity_request(saved_request_key)` returns the same run; keep the original key when you retry and you do not pay twice.
Reading and exporting results you own costs nothing.

## Keep a list current on a schedule

A monitor checks a list again on the live web every hour, day, week or month ("month" is every 30 days).
Each check is a refresh: half the row rate for a row that changed or is new, and 1 cent for a row that comes back unchanged.

```ruby
monitor = client.monitor_list(run["find_id"],
  every: "week",
  max_price_per_run_usd: 2,
  max_price_per_month_usd: 8)

if monitor["status"] == "saved"
  puts monitor["monitor_id"], monitor["next_run_at"]
else
  puts monitor["message"] # "over_maximum": one check costs more than max_price_per_run_usd, nothing was saved
end
```

The client prices one check before it saves anything.
When one check can cost more than `max_price_per_run_usd`, nothing is saved.
`max_price_per_month_usd` is the most the monitor spends in one UTC calendar month, checks run on demand included.
Without it, the limit is `max_price_per_run_usd` times the checks in 31 days.
The first check runs one interval after the current hour began, and the monitor ends a year after it, unless you set `first_run_at:` and `ends_at:` (a `Time` or an ISO 8601 string).
The same call again in the same hour returns the monitor already saved, not a second one.

| Call | What it does | Cost |
| --- | --- | --- |
| `monitor_list(list_id, ...)` | Prices one check of the list and saves the schedule within your limits | Each check, within the limits |
| `monitors` | Every monitor of the account, with its state, next check and last list | Free |
| `monitor_runs(monitor_id)` | The recent checks, newest first: when, the outcome, the reason and the list each one made | Free |
| `run_monitor_now(monitor_id)` | One check now, inside the monitor's limits. The regular times stay as they are | One check |
| `pause_monitor(monitor_id)`, `resume_monitor(monitor_id)` | Stops and starts the checks. A missed check is never bought later | Free |
| `delete_monitor(monitor_id)` | Ends the monitor. The lists it made stay yours | Free |
| `revisit(list_id)` | Each record of a refreshed list: still matches, no longer matches, unresolved or unavailable | Free |

A blocked or missed check is not an unchanged result, and it is not bought later.
For a calendar schedule (for example Mondays at 9:00 in your time zone), call `create_capacity_schedule` with the API's own fields, including `calendar_schedule`; `list_capacity_schedules`, `update_capacity_schedule`, `list_capacity_occurrences` and `run_capacity_schedule_now` are there too.

### Send new and changed records to a webhook

```ruby
delivery = client.set_monitor_delivery(monitor["monitor_id"], webhook: "https://example.com/hooks/specstream")
signing_secret = delivery["webhook_secret"] # shown once: store it, never log it
```

`set_monitor_delivery` also takes `slack:` (a channel of your connected Slack workspace), `send_to:` (a connected tool) and `notify:` (SpecStream notifications). Nothing runs when you set it.
Slack and webhook delivery need a plan that includes deliveries.

Each delivery is a JSON POST with the headers `Specstream-Event-Id` and `Specstream-Signature: t=<unix time>,v1=<hex>`.
Check it before you trust the body, and use the event id to drop repeats:

```ruby
# In a Rack or Rails endpoint
body = request.body.read
Specstream::Webhook.verify!(
  secret: ENV.fetch("SPECSTREAM_WEBHOOK_SECRET"),
  signature: request.get_header("HTTP_SPECSTREAM_SIGNATURE"),
  body: body
) # raises Specstream::Error when the signature is wrong or older than 5 minutes
event = JSON.parse(body)
```

## Search the web

`web_search` calls the Search API, `GET /v1/web-search`, at $5 per 1,000 searches of up to 10 results, or $1 on the fast tier.

```ruby
search = client.web_search(q: "What is the population of Japan?")
search["sources"].first(1).each { |s| puts s["title"], s["url"] }
```

## Extract pages

`extract_pages` calls the Extract API, `POST /v1/extract`, at $0.80 per 1,000 pages; a page with no text is not charged.

```ruby
pages = client.extract_pages({ "urls" => ["https://example.com"] })
pages["results"].first(1).each { |page| puts page["title"], page["text"] }
```

## Errors, retries and timeouts

Every failure raises `Specstream::Error` with `status`, `code` and `details` from the API.
A `503` that names a `Retry-After` of 10 seconds or less is asked once more; nothing else is retried.
The default timeout is 150 seconds (`timeout:`). Redirects are not followed and no proxy from the environment is used, so the key goes only to `base_url`.

## Pricing

New accounts start with $10 of credit, no card.
A Deep Search result costs 5 cents, 15 cents or $1 depending on what the row needs. No result, no charge.
See [pricing](https://specstream.ai/pricing), the [API docs](https://specstream.ai/docs/api) and [source and issues](https://github.com/specstream/specstream-tools).
