# SpecStream for Webflow

A Webflow Data Client app that fills CMS collections with live web data. A designer installs it, authorizes Webflow once, connects a SpecStream API key, then on the app page picks a site and a collection (or names a new one), asks in plain words, sees how SpecStream read it and the most it can cost, approves up to a maximum, and adds the results as items. Every item carries the page it was read from (**Source**), the date it was read (**Read on**) and SpecStream's ID for the result, so adding the same results again updates items instead of duplicating them.

Docs for people using it: https://specstream.ai/docs/integrations/webflow

## Where it runs

SpecStream hosts the whole app on `api.specstream.ai`; nothing is installed in a Webflow site.

| URL | What it is |
| --- | --- |
| `https://api.specstream.ai/integrations/webflow/install` | Install URL: starts Webflow's OAuth with a `state` cookie |
| `https://api.specstream.ai/integrations/webflow/oauth/callback` | Redirect URI: exchanges the code, stores the token encrypted, opens the app |
| `https://api.specstream.ai/integrations/webflow/app` | The app page, signed in with its own session cookie or a SpecStream API key |

Scopes: `authorized_user:read`, `sites:read`, `cms:read`, `cms:write`.

## How it follows Webflow's Marketplace rules

- OAuth once: after the first authorization the app keeps its own session (180 days) and signs back in with the SpecStream API key, never by sending the person through Webflow's authorization again.
- `state` on every authorization, checked against an HttpOnly cookie.
- The Webflow token and the SpecStream key are encrypted at rest (Fernet, `SPECSTREAM_INTEGRATION_ENCRYPTION_KEYS`) and never reach the browser.
- A 401 from Webflow means access was removed: the token is deleted and the page asks to connect again. **Disconnect Webflow** revokes the token at Webflow and deletes everything stored for the connection.
- Every site and collection ID is checked against what the token can see before any write.
- Rate limits: 429 and 5xx answers are retried with `Retry-After` and backoff.
- No CORS on any of these routes; state-changing calls need an `X-SpecStream-App: webflow` header, which a cross-site form can't send.
- The page has a strict Content Security Policy (`script-src 'self'`, `frame-ancestors 'none'`).

## Code

| Path | What it holds |
| --- | --- |
| `finder/native_webflow.py` | OAuth, sessions, the Webflow Data API client, pricing and approval through the public API, field planning, and the background write job |
| `finder/native_webflow_app.{html,css,js}` | The app page |
| `finder/migrations/0170_webflow_app.sql` | `webflow_connection`, `webflow_session`, `webflow_write` |
| `tests/finder/test_native_webflow.py` | Install, deny, forged state, encryption, header guard, sites, price and maximum, new and existing collections, updates instead of duplicates, revoked token, sign-out and sign-in, disconnect, slugs, page headers |

Field types: whole numbers become Number fields; ratings and decimals stay Plain text; dates become Date/Time; values that are all links or all emails become Link or Email; the rest is Plain text. Items are written 100 per call, as drafts unless the person queues them for the next publish.

The server needs `WEBFLOW_CLIENT_ID` and `WEBFLOW_CLIENT_SECRET`. `WEBFLOW_REDIRECT_URI` is optional and defaults to the callback above.
