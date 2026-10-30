# SpecStream for Asana

An Asana App Components app. From a task, people ask for live web data in plain words, approve the price in the form, and get each record as a subtask with the page behind every value. Lists they already have attach by search or by link, and a widget shows the list on the task.

Docs for people using it: https://specstream.ai/docs/integrations/asana

## Where it runs

SpecStream hosts the whole app on `api.specstream.ai`.

| URL | What it is |
| --- | --- |
| `/integrations/asana/auth` | Authentication URL: Asana OAuth with PKCE and a sealed `state` cookie |
| `/integrations/asana/callback` | Asana's redirect URL: 422 for a `state` it didn't issue, then SpecStream's consent screen |
| `/integrations/asana/connect` | SpecStream's redirect: links the Asana user to the approving account and posts `success` to `https://app.asana.com` |
| `/integrations/asana/form` | Form metadata (modal form) |
| `/integrations/asana/form/change` | `on_change`: prices the request while the form is open |
| `/integrations/asana/form/submit` | `on_submit`: approves the price and attaches the list |
| `/integrations/asana/widget` | Widget metadata |
| `/integrations/asana/typeahead` | Lookup typeahead over the person's lists |
| `/integrations/asana/attach` | Lookup attach, from a pick or a pasted list link |

All are under `https://api.specstream.ai`. Asana scopes: `tasks:read`, `tasks:write`. Widget match URL pattern: `https:\/\/specstream\.ai\/workspace\/collections\/fnd_[A-Za-z0-9_-]+.*`.

## How it follows Asana's approval checklist

- Every component request is checked against `x-asana-request-signature` (HMAC-SHA256 with the client secret over the query string for GET, or the body's `data` string for POST) and refused with 400 when it doesn't match; requests past their `expires_at` are refused too.
- `state` is random, sealed in an HttpOnly cookie, and a mismatch answers 422. Deny posts `error` to `https://app.asana.com` and closes the window.
- CORS answers only `https://app.asana.com`.
- Each person's Asana token and SpecStream refresh token are encrypted (Fernet, `SPECSTREAM_INTEGRATION_ENCRYPTION_KEYS`). A refresh Asana refuses removes the link, and the next request asks to connect again.

## How a run works

- The form prices the request in a background worker, so Asana's 10-second limit is never the reading's limit; the price line says **Working out the price…** until it's ready.
- The approval checkbox's value binds the price, the quote and the request, so submitting approves exactly the price shown. The server re-reads the quote and refuses a higher price.
- The run is remembered with the task. When the widget first sees it finished, it claims the delivery once and adds up to 100 subtasks, each with its values and sources.
- Teammates who open the task see the widget through the link of the person who started the run.

## Code

| Path | What it holds |
| --- | --- |
| `finder/native_asana.py` | OAuth popup, signatures, the form, widget, lookup and subtask delivery, and `python -m finder.native_asana register` |
| `finder/native_app_link.py` | Shared with the Intercom app: flow cookies, the encrypted account link, token refresh, pricing, approval and records |
| `finder/migrations/0169_native_app_links.sql` | `native_app_link`, `native_app_run` |
| `tests/finder/test_native_asana.py` | Popup install, forged state, deny, signatures, expiry, CORS, unlinked user, pricing, stale approval, submit, widget, one delivery, teammate view, typeahead, attach, token refresh |

The server needs `ASANA_CLIENT_ID` and `ASANA_CLIENT_SECRET`; until both are set, every route answers 503.
