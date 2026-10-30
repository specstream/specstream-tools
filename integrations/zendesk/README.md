# SpecStream for Zendesk

A Zendesk Support app for the ticket sidebar and the organization sidebar. It reads the live web for the company behind a ticket (website, employee count, industry, headquarters, country, year founded, LinkedIn page, latest funding round), shows each value with the page it was read on, and saves the values an agent picks to the organization's fields.

## How it works

1. The app takes the company from the ticket's organization (its first domain, else its name) or from the requester's email domain. A personal address (Gmail, Outlook and the like) names no company, so the agent types one.
2. **Get the price** sends the request to `POST /v1/parse` and `POST /v1/capacity/quotes`. Nothing runs yet.
3. **Find for at most $X** re-reads the quote (`GET /v1/capacity/quotes/{id}`), stops if the price went up, and approves it with `POST /v1/capacity/executions` and a run key kept in the browser, so a retry never starts a second run.
4. The sidebar polls `GET /v1/finds/{id}` every 4 seconds, then reads `GET /v1/finds/{id}/rows`. The lookup is remembered per organization in the agent's browser, so reopening the ticket shows the results instead of asking again.
5. **Save to this organization** matches the record's values to the organization's text and number fields by name (Website, Employees, Industry, Funding, Founded, Country, Headquarters, LinkedIn) and writes the ticked ones with `PUT /api/v2/organizations/{id}.json`, as the agent.

The API key is a secure setting (`api_key`, `secure: true`, `scopes: ["header"]`). Every SpecStream call goes through Zendesk's proxy with `secure: true`, and the proxy puts the key into `Authorization: Bearer {{setting.api_key}}`. The browser never holds the key, and the proxy sends it only to `api.specstream.ai` (`domainWhitelist`).

## Files

- `manifest.json`, `translations/en.json`: the app and its Marketplace listing text.
- `assets/iframe.html`, `assets/app.js`, `assets/app.css`: the sidebar, built from `apps/workspace/src/zendesk/` with the workspace's LemonUI components and tokens.
- `assets/logo.png` (320 x 320), `assets/logo-small.png` (128 x 128): from `growth/media/app-icon-1024.png`.
- `specstream-zendesk.zip`: the package to upload.

## Build and package

```sh
node apps/workspace/scripts/build-zendesk.mjs          # writes assets/app.js, app.css, iframe.html
cd ops/public-repo/integrations/zendesk
zip -qrX specstream-zendesk.zip manifest.json translations assets
```

`zcli apps:validate` and `zcli apps:package` do the same check and zip, signed in to a Zendesk account (`zcli login -i`). Secure settings don't work under `zcli apps:server`, so test an uploaded copy: `zcli apps:create` installs it privately in the signed-in account.

Marketplace screenshots go in `assets/` as `screenshot-0.png` to `screenshot-2.png` (1024 x 768, full bleed) before the final package.
