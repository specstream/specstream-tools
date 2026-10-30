# SpecStream for Framer

A Framer CMS plugin that fills a managed collection with live web data. Ask in plain words, see how SpecStream read the request and the most it can cost, approve up to your maximum, choose and rename the fields, and the results sync into the collection. Every item carries the page it was read from (**Source**) and the date it was read (**Read on**). The item IDs are SpecStream's result IDs, so syncing again updates items, adds new ones and removes ones that are gone.

Docs for people using it: https://specstream.ai/docs/integrations/framer

## How it works

- Built with `@framer/plugin` 5 and Framer's plugin styles (`framer-plugin/framer.css`), in the `configureManagedCollection` and `syncManagedCollection` modes.
- **Configure** (adding the collection, or opening the plugin on it): connect, ask, approve, map fields, sync.
- **Sync** (the Sync button on the collection): re-reads the same results, which costs nothing, and closes.
- The API key is kept in the browser's `localStorage`, not in plugin data, because Framer shares plugin data with everyone on the project. The collection's plugin data holds only the run ID, the request text, the slug column and the fields left out.
- Calls go straight to `https://api.specstream.ai` with `Authorization: Bearer <key>`, never with cookies. The API answers them from `*.plugins.framercdn.com` and from `https://localhost:5173` for development (`finder/native_app_cors.py`).
- Fields: up to 28 result columns plus Source and Read on (Framer allows 30). Columns become string, number, yes/no, date or link fields by their values.
- The plugin header menu has **Open SpecStream**, **Help**, **Privacy policy** and **Log out**.
- The connect screen says what leaves Framer: the typed request, with the key, goes to `api.specstream.ai`; results come back into the collection; nothing else from the project is sent.
- Permissions: syncing calls `setFields`, `addItems`, `removeItems` and `setPluginData`. Each is checked with `useIsAllowedTo`; when any is missing, a notice names the missing access, asks for Content or Design permission, and syncing and new requests are turned off. The CMS Sync button opens the plugin with that notice instead of failing, and with a note when the key lives in another collaborator's browser.

| Path | What it holds |
| --- | --- |
| `src/core/specstream.ts` | The API client: read, price, approve, progress, rows, cancel, account, earlier results |
| `src/core/records.ts` | Turns result rows into typed columns and records, with each record's source page |
| `src/sync.ts` | Framer fields, item IDs and slugs, and which items are stale |
| `src/data.ts` | The key, plugin data and the managed-collection writes |
| `src/App.tsx` | The plugin's screens |

## Develop

```sh
npm install
npm run check        # typecheck and unit tests
npm run dev          # https://localhost:5173
```

In a Framer project, open **Plugins**, then **Developer Tools**, and turn on **Development Plugin**; it loads from `https://localhost:5173`.

## Publish

```sh
npm run build
npm run pack         # writes plugin.zip
```

Upload `plugin.zip` at https://www.framer.com/marketplace/dashboard/plugins/ (**New Plugin**). An update is the same: change the code, pack, upload.
