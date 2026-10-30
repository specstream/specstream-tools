# SpecStream for Intercom

A Canvas Kit app for the Intercom inbox. It looks up the company or person behind a conversation on the live web, shows each value with the page it was read on, and adds the results to the conversation as an internal note.

Docs for people using it: https://specstream.ai/docs/integrations/intercom

## Where it runs

SpecStream hosts the whole app on `api.specstream.ai`; nothing is installed in Intercom besides the app itself.

| URL | What it is |
| --- | --- |
| `https://api.specstream.ai/integrations/intercom/install` | Direct installation URL: starts Intercom's OAuth with a sealed `state` cookie (`?region=eu` or `au` for those regions) |
| `https://api.specstream.ai/integrations/intercom/callback` | Intercom's redirect URL: exchanges the code, reads the workspace, then sends the admin to SpecStream's consent screen |
| `https://api.specstream.ai/integrations/intercom/connect` | SpecStream's redirect: links the workspace to the approving account and returns to `/appstore/redirect?install_success=true` |
| `https://api.specstream.ai/integrations/intercom/initialize` | Canvas Kit initialize (inbox) |
| `https://api.specstream.ai/integrations/intercom/submit` | Canvas Kit submit |
| `https://api.specstream.ai/integrations/intercom/uninstall` | Uninstall notification: ends the link and its SpecStream access |

Intercom permissions: the Canvas Kit set, plus **Write conversations** for notes.

## How it works

- Install: Intercom OAuth first (which workspace), then SpecStream's OAuth consent (which account). The `state` of each step is checked against an encrypted, HttpOnly cookie that lives 30 minutes. A denied step returns `install_success=false` with a message.
- The workspace link keeps the Intercom token and a SpecStream refresh token, encrypted (Fernet, `SPECSTREAM_INTEGRATION_ENCRYPTION_KEYS`). Each link owns one token family; reinstalling replaces it and revokes the old one.
- Every Canvas Kit request is checked against `X-Body-Signature` (HMAC of the raw body with the client secret) before anything else.
- The card names the subject from the contact's company, else their email domain (personal mail providers are skipped), and writes an editable request. **Get the price** calls `POST /v1/parse` and `POST /v1/capacity/quotes` in a background worker, so a slow reading shows **Show the price** instead of timing out Intercom's request.
- **Find for at most $X** re-reads the quote, refuses a higher price, and approves it with `POST /v1/capacity/executions` and an idempotency key made from the workspace, conversation and quote, so a double click starts one run.
- **Check for results** reads `GET /v1/finds/{id}` and the rows; **Add as a note** replies to the conversation as the teammate, with `message_type: note`.
- Uninstall: a signed notification removes the link at once; an unsigned one removes it only when Intercom no longer accepts the workspace's token.

## Code

| Path | What it holds |
| --- | --- |
| `finder/native_intercom.py` | OAuth, regions, signatures, the canvases and their actions, the uninstall notice, and `python -m finder.native_intercom register` |
| `finder/native_app_link.py` | Shared with the Asana app: install flow cookies, the encrypted account link, token refresh, pricing, approval and reading records |
| `finder/migrations/0169_native_app_links.sql` | `native_app_link`, `native_app_run` |
| `tests/finder/test_native_intercom.py` | Install, regions, forged state, denied consent, signatures, unlinked workspace, price, approve, results, notes, slow pricing, unreadable request, personal email, person lookup, uninstall |

The server needs `INTERCOM_CLIENT_ID` and `INTERCOM_CLIENT_SECRET`; until both are set, every route answers 503.
