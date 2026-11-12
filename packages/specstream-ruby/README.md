# specstream (Ruby)

SpecStream: the live web data engine.
One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change.

This gem is the Ruby client for the Deep Search API, the Search API and the Extract API.
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
