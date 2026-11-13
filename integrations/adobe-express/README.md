# SpecStream for Adobe Express

An Adobe Express add-on that puts live web data into a design. Ask a question and add the results to the page as text, with the source URL on every row. Or paste up to 20 URLs and add the text of those pages.

It uses two SpecStream APIs with your own API key:

- Search API: `GET /v1/web-search`, $5 per 1,000 searches of up to 10 results. Tick **Fast** and the search sends `speed=fast`: ranked results in about a second, and a fast search costs $1 per 1,000. Unticked, no speed is sent and the API's default search runs.
- Extract API: `POST /v1/extract`, up to 20 URLs a call, $0.80 per 1,000 pages. A page with no text is not charged.

New SpecStream accounts start with $10 of credit and no card. Create a key at https://specstream.ai.

## What is in the folder

| File | What it does |
|---|---|
| `src/manifest.json` | The add-on manifest (version 2): one panel, one document sandbox file. |
| `src/index.html`, `src/styles.css`, `src/ui.js` | The panel. |
| `src/api.js` | The calls to `https://api.specstream.ai` and the text layout. No Adobe code, so Node tests it. |
| `src/code.js` | The document sandbox. It adds one text block to the current page and makes no network call. |
| `package.mjs` | Writes `dist/specstream-adobe-express.zip` for the upload step. |
| `tests/addon.test.mjs` | The tests. |

There is no build step and no dependency. Node 22 or later runs the tests and makes the package.

## Test and package

```sh
npm test
npm run package
```

`npm run package` writes `dist/specstream-adobe-express.zip` with `manifest.json` at the root of the zip. The development fields `testId` and `name` are left out of the packaged manifest.

## Load it in Adobe Express

1. In Adobe Express, open your account settings and turn on add-on development.
2. Serve `src/` on `https://localhost:5241` with Adobe's CLI, run in this folder: `npx @adobe/ccweb-add-on-scripts start`. The first run asks to make a local certificate.
3. Open a design, open Add-ons, turn on "Add-on testing" and connect to `https://localhost:5241`.
4. Paste your SpecStream API key, search, tick rows and select "Add to design".

## What it sends and keeps

- Your key, your question and your URLs go only to `https://api.specstream.ai`.
- The key is kept in the add-on's client storage in Adobe Express on your device. "Change API key" removes it.
- The add-on reads nothing from your design. It only adds a text block.

Support: support@specstream.ai
