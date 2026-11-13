# specstream (Go)

SpecStream: the live web data engine.
One platform to build, search, extract, enrich, map, and monitor data across the entire web.

This module is the Go client for the Deep Search API, the Search API and the Extract API.
It has no dependencies outside Go's standard library and needs Go 1.21 or newer.

```sh
go get github.com/specstream/specstream-tools/packages/specstream-go
```

Create an API key under **Agents & API** in your SpecStream workspace and keep it in the environment:

```sh
export SPECSTREAM_API_KEY="ss_live_..."
```

## Search the web

`Search` calls the Search API, `GET /v1/web-search`, at $5 per 1,000 searches of up to 10 results, or $1 on the fast tier.

```go
package main

import (
	"context"
	"fmt"
	"log"
	"os"

	specstream "github.com/specstream/specstream-tools/packages/specstream-go"
)

func main() {
	client, err := specstream.NewClient(os.Getenv("SPECSTREAM_API_KEY"))
	if err != nil {
		log.Fatal(err)
	}
	found, err := client.Search(context.Background(), "What is the population of Japan?", nil)
	if err != nil {
		log.Fatal(err)
	}
	if found.Answer != nil {
		fmt.Println(found.Answer.Value, found.Answer.Page)
	}
	for _, source := range found.Sources {
		fmt.Println(source.Title, source.URL)
	}
}
```

`SearchOptions` holds the optional parameters:

```go
found, err := client.Search(ctx, "vector database release notes", &specstream.SearchOptions{
	Speed:    specstream.SpeedFast, // the fast tier
	Num:      20,                   // 1 to 100 results
	Passages: true,                 // the text of the closest pages
})
```

`Extra` sends any other parameter of the route, and `Raw` on the result holds the whole reply.

## Extract pages

`Extract` calls the Extract API, `POST /v1/extract`, at $0.80 per 1,000 pages; a page with no text is not charged.
One call reads at most 20 pages.

```go
pages, err := client.Extract(ctx, specstream.ExtractRequest{
	URLs: []string{"https://example.com"},
})
if err != nil {
	log.Fatal(err)
}
for _, page := range pages.Results {
	if page.OK() {
		fmt.Println(page.Title, page.Text)
	}
}
```

The text is Markdown; set `Format: specstream.FormatText` for plain text.
To read HTML you already hold, fill `Pages` instead of `URLs`.

## Deep Search: every match, in rows

Ask in plain words and get every match on the live web, in structured rows with their sources.
`Compile` reads the request and `QuoteCapacityWork` prices it; nothing runs and nothing is charged yet. A price lasts 30 minutes.

```go
reading, err := client.Compile(ctx, "Open-source vector databases on GitHub, with their license.", "")
if err != nil {
	log.Fatal(err)
}
offer, err := client.QuoteCapacityWork(ctx, specstream.Data{
	"ast_hash":        reading["ast_hash"],
	"operation":       "find",
	"requested_units": 25,
})
if err != nil {
	log.Fatal(err)
}
fmt.Println(offer["maximum_cents"], offer["expires_at"])
```

After a person approves the price, send the approved maximum in cents and a request key you saved first:

```go
run, err := client.AuthorizeCapacityWork(ctx, specstream.Authorization{
	QuoteID:         offer["quote_id"].(string),
	QuoteHash:       offer["quote_hash"].(string),
	ConfirmMaxCents: approvedMaximumCents,
	IdempotencyKey:  savedRequestKey,
})
if err != nil {
	log.Fatal(err)
}
findID := run["find_id"].(string)

progress, err := client.GetFind(ctx, findID) // the progress of the run

err = client.EachRow(ctx, findID, func(row specstream.Data) error { // every row, page after page
	fmt.Println(row)
	return nil
})
```

`AuthorizeCapacityWork` sends nothing unless the quote, its signature, the maximum and the key are all present.
If the reply is lost, `GetCapacityRequest(ctx, savedRequestKey, "")` returns the same run; the same key never starts or charges a second run.
Each delivered row costs 5 cents, 15 cents or $1 depending on what it needs, plus 5 cents for a person's email and 15 cents for a phone.
Duplicates and rows you already own are not charged, and reading or exporting (`Export`) your rows costs nothing.
`EditSpec` changes a condition or a fact of the reading before you quote it.

## Errors, retries and timeouts

A call the API refuses, or the client refuses before sending (`Status` 0), returns a `*specstream.Error` with `Status`, `Code`, `Message` and `Details` from the API:

```go
var failure *specstream.Error
if errors.As(err, &failure) {
	fmt.Println(failure.Status, failure.Code)
}
```

A `503` that names a `Retry-After` of 10 seconds or less is asked once more; nothing else is retried.
Every call takes a `context.Context`, and the default timeout is 150 seconds (`specstream.WithTimeout`).
Redirects are not followed and no proxy from the environment is used, so the key goes only to the base address.
`specstream.WithHTTPClient` brings your own `*http.Client`, and `specstream.WithBaseURL` another address.

## Pricing

New accounts start with $10 of credit, no card.
See [pricing](https://specstream.ai/pricing), the [API docs](https://specstream.ai/docs/api) and [source and issues](https://github.com/specstream/specstream-tools).
