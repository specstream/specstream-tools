# SpecStream (.NET)

SpecStream: the live web data engine.
One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change.

This package is the .NET client for the Deep Search API, monitors, the Search API, the Extract API and browser sessions.
It has no dependencies outside .NET and needs .NET 8 or newer.

```sh
dotnet add package SpecStream
```

Create an API key under **Agents & API** in your SpecStream workspace and keep it in the environment:

```sh
export SPECSTREAM_API_KEY="ss_live_..."
```

## Deep Search: read a request, get the price

```csharp
using SpecStream;

using var client = SpecStreamClient.FromEnvironment();

var reading = await client.CompileAsync("Open-source vector databases on GitHub, with their license.");
var offer = await client.QuoteCapacityWorkAsync(new
{
    ast_hash = reading.GetProperty("ast_hash").GetString(),
    operation = "find",
    requested_units = reading.GetProperty("ast").GetProperty("limit").GetProperty("max").GetInt32(),
});
Console.WriteLine($"{offer.GetProperty("maximum_cents")} cents, until {offer.GetProperty("expires_at")}");
```

Nothing has run yet. A price lasts 30 minutes.

## Approve it, then read the results

After a person approves, send the approved maximum in cents and a request key you saved first:

```csharp
var run = await client.AuthorizeCapacityWorkAsync(new
{
    quote_id = offer.GetProperty("quote_id").GetString(),
    quote_hash = offer.GetProperty("quote_hash").GetString(),
    confirm_max_cents = approvedMaximumCents,
    idempotency_key = savedRequestKey,
});
var findId = run.GetProperty("find_id").GetString()!;

await client.GetFindAsync(findId);                       // progress
await foreach (var row in client.EachRowAsync(findId))   // every row, page after page
    Console.WriteLine(row);
```

`AuthorizeCapacityWorkAsync` sends nothing unless the quote, its signature, the maximum and the key are all present.
If the answer is lost, `GetCapacityRequestAsync(savedRequestKey)` returns the same run; keep the original key when you retry and you do not pay twice.
Reading and exporting results you own costs nothing.

## Monitors: run the same request again on a schedule

A monitor approves future runs of one exact request, within a limit per run and a limit per period:

```csharp
var monitor = await client.CreateMonitorAsync(new
{
    idempotency_key = savedMonitorKey,
    scope = new { ast_hash = reading.GetProperty("ast_hash").GetString(), operation = "find", requested_units = 25 },
    cadence_seconds = 86400,
    first_due_at = "2026-12-01T08:00:00Z",
    per_run_cents = 500,
    period_cents = 5000,
    valid_until = "2027-06-01T00:00:00Z",
});
var scheduleId = monitor.GetProperty("schedule_id").GetString()!;

await client.ListMonitorsAsync();                         // your monitors and their state
await client.ListMonitorRunsAsync(scheduleId);            // completed, blocked and missed runs
await client.RunMonitorNowAsync(scheduleId);              // once now, inside its own limits
await client.SetMonitorDeliveryAsync(scheduleId, new { expected_version = 1, webhook = "https://example.com/hook" });
await client.PauseMonitorAsync(scheduleId, expectedVersion: 1);
await client.GetRevisitAsync(findId);                     // which saved results a refresh reached
```

`CreateMonitorAsync` sends nothing unless the request key and both limits are present. A paused monitor does not buy the runs it missed.

## Search the web

`WebSearchAsync` calls the Search API, `GET /v1/web-search`, at $5 per 1,000 searches of up to 10 results, or $1 on the fast tier.

```csharp
var search = await client.WebSearchAsync("What is the population of Japan?");
```

## Extract pages

`ExtractPagesAsync` calls the Extract API, `POST /v1/extract`, at $0.80 per 1,000 pages; a page with no text is not charged.

```csharp
var pages = await client.ExtractPagesAsync(new { urls = new[] { "https://example.com" } });
```

## Browser sessions: a real browser for pages that need one

Some pages show nothing until a button is clicked, a form is filled in or their JavaScript runs.
`CreateBrowserSessionAsync` calls `POST /v1/browser/sessions` and opens a real Chromium browser that SpecStream runs.
Browser time costs $0.10 an hour, charged by the second. A step sent with `BrowserActionAsync` costs $1 per 1,000 steps.

```csharp
var session = await client.CreateBrowserSessionAsync(
    new { timeout_s = 300, allowed_domains = new[] { "example.com" } },
    idempotencyKey: savedSessionKey);
var sessionId = session.GetProperty("id").GetString()!;
try
{
    await client.BrowserActionAsync(sessionId, "browser_navigate", new { url = "https://example.com" });
    var page = await client.BrowserActionAsync(sessionId, "browser_read");    // the page's text
    Console.WriteLine(page.GetProperty("result")[0].GetProperty("text").GetString());
}
finally
{
    await client.ReleaseBrowserSessionAsync(sessionId);                        // the time stops here
}
```

The tool names are those of Playwright MCP (`browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_take_screenshot` and the others), plus `browser_read` for the page's text.
To drive the browser with Playwright or Puppeteer instead, connect to the session's `connect_url`; steps sent that way are not charged, only the time.
`GetBrowserSessionAsync` shows the seconds, the steps and the cost so far, `ListBrowserSessionsAsync` lists your sessions, and `BrowserDownloadsAsync` returns the files the browser downloaded as one zip.
A session ends on its own at `timeout_s` (60 to 3,600 seconds), and a repeated create with the same key returns the same session.

## Errors, retries and timeouts

Every failure throws `SpecStreamException` with `Status`, `Code` and `Details` from the API.
A `503` that names a `Retry-After` of 10 seconds or less is asked once more; nothing else is retried.
The default timeout is 150 seconds. Redirects are not followed and no proxy from the environment is used, so the key goes only to the base address.

## Pricing

New accounts start with $10 of credit, no card.
A Deep Search result costs 5 cents, 15 cents or $1 depending on what the row needs. No result, no charge.
See [pricing](https://specstream.ai/pricing), the [API docs](https://specstream.ai/docs/api) and [source and issues](https://github.com/specstream/specstream-tools).
