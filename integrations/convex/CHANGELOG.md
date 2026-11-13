# Changelog

## 0.4.0

- Browser sessions: `openBrowser`, `browserStep`, `browserSession` and `closeBrowser` on the component and on `SpecStreamClient` (`POST /v1/browser/sessions`, $0.10 an hour by the second, $0.001 a step). Opening sends an Idempotency-Key, so a retried call opens one browser. `connect_url` is returned only with `includeConnectUrl`.
- The example app has `readPageInBrowser`: open, go to the page, read it, close.

## 0.3.0

- `webSearch` takes `speed` (`"fast"` or `"default"`). A fast search costs $1 per 1,000. Left out, the API's default search runs.

## 0.2.2

- README: the sign-up credit has no time limit.

## 0.2.1

- README: the request examples are removed.

## 0.2.0

- Search the web and read pages: `webSearch` (Search API) and `extractPages` (Extract API) on the component and on `SpecStreamClient`. No quote is needed.

## 0.1.1

- Published from GitHub Actions with a provenance statement. No code changes.

## 0.1.0

- First release: read a request, quote it, approve the exact quote, follow the list to the end, store its rows with the page behind each one, run `onComplete` once, and an optional signed webhook route.
