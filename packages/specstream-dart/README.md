# specstream (Dart)

SpecStream: the live web data engine.
One platform to build, search, extract, enrich, map, and monitor data across the entire web.

This package is the Dart client for Deep Search, the Search API and the Extract API.
It works in Dart and Flutter apps on every platform, and its only dependency is [`http`](https://pub.dev/packages/http).

```sh
dart pub add specstream
```

Create an API key under **Agents & API** in your SpecStream workspace and keep it out of your source code:

```sh
export SPECSTREAM_API_KEY="ss_live_..."
```

## Build a list with Deep Search

Deep Search reads a request in everyday words and returns a list of results, each with its sources.
Nothing runs until you approve the price: `quoteCapacityWork` charges nothing, and `authorizeCapacityWork` starts the run with the maximum you approve.

```dart
final reading = await specstream.compile(
    'Open-source vector databases on GitHub, with their license.');
final quote = await specstream.quoteCapacityWork({
  'ast_hash': reading['ast_hash'],
  'operation': 'find',
  'requested_units': reading['ast']['limit']['max'],
});
print('At most ${quote['maximum_cents']} cents, until ${quote['expires_at']}');

// After a person approves that maximum, with a request key you saved first:
final run = await specstream.authorizeCapacityWork({
  'quote_id': quote['quote_id'],
  'quote_hash': quote['quote_hash'],
  'confirm_max_cents': approvedMaximumCents,
  'idempotency_key': savedRequestKey,
});

final findId = run['find_id'] as String;
print(await specstream.getFind(findId)); // progress
await for (final row in specstream.eachRow(findId)) {
  print(row); // every result, page after page
}
```

Each delivered result is charged 5¢, 15¢ or $1 depending on what it needs, plus 5¢ for a person's email and 15¢ for a phone.
Duplicates and results you already own are not charged, and reading your results costs nothing.

| Method | Call |
| --- | --- |
| `compile` | `POST /v1/parse` |
| `editSpec` | `POST /v1/parse/from-chips` |
| `specOptions` | `GET /v1/spec-options/{target}` |
| `quoteCapacityWork` | `POST /v1/capacity/quotes` |
| `getCapacityQuote` | `GET /v1/capacity/quotes/{quote_id}` |
| `authorizeCapacityWork` | `POST /v1/capacity/executions` |
| `getCapacityRequest` | `GET /v1/capacity/requests/{request_key}` |
| `getCapacityBalance` | `GET /v1/capacity/balance` |
| `getFind` | `GET /v1/finds/{id}` |
| `cancelFind` | `POST /v1/finds/{id}/cancel` |
| `rows`, `eachRow` | `GET /v1/finds/{id}/rows` |
| `export` | `POST /v1/finds/{id}/export` |

`authorizeCapacityWork` sends nothing unless the quote, its `quote_hash`, the maximum and the key are all present.
If its reply is lost, `getCapacityRequest(savedRequestKey)` shows the run; the same key never starts a second run.
The full example is [example/deep_search.dart](example/deep_search.dart).

## Search the web

`webSearch` calls the Search API, `GET /v1/web-search`, at $5 per 1,000 searches of up to 10 results, or $1 on the fast tier.

```dart
import 'dart:io';

import 'package:specstream/specstream.dart';

Future<void> main() async {
  final specstream = SpecStream(Platform.environment['SPECSTREAM_API_KEY']!);

  final search = await specstream.webSearch('What is the population of Japan?');
  for (final source in search['sources'] as List) {
    print('${source['title']}  ${source['url']}');
  }

  specstream.close();
}
```

For the fast tier, add `speed: 'fast'`.
The other parameters are `num`, `page`, `news`, `passages`, `language`, `country` and `safe`; a parameter you leave out is not sent.

## Extract pages

`extractPages` calls the Extract API, `POST /v1/extract`, at $0.80 per 1,000 pages; a page with no text is not charged.

```dart
final pages = await specstream.extractPages({
  'urls': ['https://example.com'],
});
for (final page in pages['results'] as List) {
  print('${page['title']}\n${page['text']}');
}
```

One call reads up to 20 pages.

## Monitor a Deep Search list

A list you built with Deep Search can be refreshed on a schedule, within the money limits you approve.
Nothing runs beyond `per_run_cents` for one run and `period_cents` for one period.

```dart
final now = DateTime.now().toUtc();
final schedule = await specstream.createCapacitySchedule({
  'idempotency_key': 'weekly-$findId',
  'scope': {'ast_hash': astHash, 'operation': 'refresh', 'parent_find_id': findId},
  'cadence_seconds': 7 * 24 * 3600,
  'first_due_at': now.add(const Duration(days: 7)).toIso8601String(),
  'per_run_cents': 500,
  'period_cents': 2000,
  'valid_until': now.add(const Duration(days: 90)).toIso8601String(),
});

// Which saved results the last refresh reached, and which it did not.
String? after;
do {
  final page = await specstream.revisit(findId, after: after);
  print(page);
  after = page['next_after'] as String?;
} while (after != null);
```

| Method | Call |
| --- | --- |
| `createCapacitySchedule` | `POST /v1/capacity/schedules` |
| `listCapacitySchedules` | `GET /v1/capacity/schedules` |
| `updateCapacitySchedule` | `PATCH /v1/capacity/schedules/{schedule_id}`: `active`, `paused` or `deleted` |
| `listCapacityOccurrences` | `GET /v1/capacity/schedules/{schedule_id}/occurrences` |
| `runCapacityScheduleNow` | `POST /v1/capacity/schedules/{schedule_id}/run` |
| `revisit` | `GET /v1/finds/{id}/revisit` |

`updateCapacitySchedule` takes the `expectedVersion` you last read; if another person changed the schedule, the conflict error names the current version in `details`.
The full example is [example/monitor.dart](example/monitor.dart).

## Errors, retries and timeouts

Every failed call throws `SpecStreamException` with `status`, `code` and `details` from the API.
A `503` that names a `Retry-After` of 10 seconds or less is asked once more; nothing else is retried.
The default timeout is 150 seconds (`timeout:`).
Redirects are not followed, so the key goes only to `baseUrl`.

To use your own HTTP stack, pass it as `httpClient:`; you close a client that you pass in.

## In a Flutter app

A key inside an app that you ship can be read by anyone who has the app.
Call SpecStream from your own server and keep the key there, or use this package in Dart code that runs on the server.

## Pricing

New accounts start with $10 of credit, no card.
See [pricing](https://specstream.ai/pricing), the [API docs](https://specstream.ai/docs/api) and [source and issues](https://github.com/specstream/specstream-tools).
