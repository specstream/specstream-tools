# specstream (Rust)

SpecStream: the live web data engine.
One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change.

This crate is the Rust client for the Deep Search API, the Search API and the Extract API.
It is blocking, depends only on `ureq` (with rustls) and `serde_json`, and returns each reply's `data` as a `serde_json::Value`.

```sh
cargo add specstream
```

Create an API key under **Agents & API** in your SpecStream workspace and keep it in the environment:

```sh
export SPECSTREAM_API_KEY="ss_live_..."
```

## Deep Search: read a request, get the price

```rust
use specstream::Client;
use serde_json::json;

let client = Client::from_env()?;
let reading = client.compile("Open-source vector databases on GitHub, with their license.")?;
let offer = client.quote_capacity_work(&json!({
    "ast_hash": reading["ast_hash"],
    "operation": "find",
    "requested_units": reading["ast"]["limit"]["max"],
}))?;
println!("{} {}", offer["maximum_cents"], offer["expires_at"]);
```

Nothing has run yet. A price lasts 30 minutes.

## Approve it, then read the results

After a person approves, send the approved maximum in cents and a request key you saved first:

```rust
let run = client.authorize_capacity_work(&json!({
    "quote_id": offer["quote_id"],
    "quote_hash": offer["quote_hash"],
    "confirm_max_cents": approved_maximum_cents,
    "idempotency_key": saved_request_key,
}))?;
let find_id = run["find_id"].as_str().unwrap();

client.get_find(find_id)?;                  // progress
for row in client.all_rows(find_id)? {      // every row, page after page
    println!("{row}");
}
```

`authorize_capacity_work` sends nothing unless the quote, its signature, the maximum and the key are all present.
If the response is lost, `get_capacity_request(saved_request_key, None)` returns the same run; keep the original key when you retry and you do not pay twice.
Reading and exporting results you own costs nothing.

## Search the web

`web_search` calls the Search API, `GET /v1/web-search`, at $5 per 1,000 searches of up to 10 results.

```rust
use specstream::WebSearch;

let answer = client.web_search(&WebSearch::new("What is the population of Japan?"))?;
println!("{}", answer["sources"][0]["url"]);
```

## Extract pages

`extract_pages` calls the Extract API, `POST /v1/extract`, at $0.80 per 1,000 pages; a page with no text is not charged.

```rust
let pages = client.extract_pages(&json!({ "urls": ["https://example.com"] }))?;
println!("{}", pages["results"][0]["title"]);
```

## Errors, retries and timeouts

Every failure is a `specstream::Error` with `kind()`, `status()`, `code()` and `details()` from the API.
A `503` that names a `Retry-After` of 10 seconds or less is asked once more; nothing else is retried.
The default timeout is 150 seconds (`Client::builder(key).timeout(...)`). Redirects are not followed and no proxy from the environment is used, so the key goes only to the base address.
`Client::builder(key).transport(...)` takes your own HTTP stack.

## Pricing

New accounts start with $10 of credit, no card.
A Deep Search result costs 5 cents, 15 cents or $1 depending on what the row needs. No result, no charge.
See [pricing](https://specstream.ai/pricing), the [API docs](https://specstream.ai/docs/api) and [source and issues](https://github.com/specstream/specstream-tools).
