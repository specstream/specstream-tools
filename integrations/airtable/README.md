# SpecStream for Airtable

An Airtable extension that adds live web data to a base. Ask in plain words ("coffee shops in Austin with their website and Google rating"), see how SpecStream read the request and the most it can cost, approve up to your maximum, and the results land in a table: a new one, or an existing one with fields created as needed. Every record carries the page it was read from (**Source**), the date it was read (**Read on**) and SpecStream's ID for the result, so adding the same results again updates records instead of duplicating them.

Docs for people using it: https://specstream.ai/docs/integrations/airtable

## How it works

- Built on the Blocks SDK (`@airtable/blocks` 1.19, React 17) with Airtable's own UI components.
- The API key lives in the extension's `globalConfig` (Airtable's per-base settings), set from the settings button. Everyone who opens the extension in that base uses it; the settings screen says so.
- Calls go straight from the extension to `https://api.specstream.ai` with `Authorization: Bearer <key>`, never with cookies: `POST /v1/parse`, `POST /v1/capacity/quotes`, `POST /v1/capacity/executions`, `GET /v1/finds/{id}`, `GET /v1/finds/{id}/rows`, `POST /v1/finds/{id}/cancel`, `GET /v1/me`, `GET /v1/capacity/balance`, `GET /v1/workspace/collections`. The API answers these from `*.airtableblocks.com` origins only (`finder/native_app_cors.py`).
- Approving refuses any quote above the maximum the person set, and each quote has one idempotency key, so a double click starts one run.
- A run in progress is saved in `globalConfig`, so closing and reopening the extension picks it back up.
- Records are written 50 per call (Airtable's limit), after permission checks for creating tables, fields and records.

| Path | What it holds |
| --- | --- |
| `frontend/core/specstream.ts` | The API client: read, price, approve, progress, rows, cancel, account, earlier results |
| `frontend/core/records.ts` | Turns result rows into typed columns and records, with each record's source page |
| `frontend/plan.ts` | Which field each column goes to, which fields to create, and the cell values |
| `frontend/write.ts` | Creates the table or fields and writes or updates the records |
| `frontend/App.tsx` | The extension's screens |

## Develop

```sh
npm install
npm install -g @airtable/blocks-cli
npm run check        # typecheck, unit tests, bundle
```

To run it in a base:

1. In the base, open **Extensions**, click **Add an extension**, then **Build a custom extension**. Name it SpecStream. Airtable shows a command with the base and extension IDs (`appXXXXXXXX/blkXXXXXXXX`).
2. `block add-remote appXXXXXXXX/blkXXXXXXXX specstream`
3. `block set-api-key` and paste a personal access token with the `block:manage` scope (created at https://airtable.com/create/tokens).
4. `block run --remote specstream`, then in the base click **Edit extension** and paste `https://localhost:9000`.

`block release --remote specstream` uploads a build to the base. `block submit --remote specstream` starts a Marketplace submission.

Unit tests run without Airtable or the network: `npm test`.
