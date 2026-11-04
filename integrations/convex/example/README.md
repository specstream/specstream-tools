# specstream-convex example

A Convex app that installs the component and uses everything it exposes: read a request, show the price, approve it, watch rows arrive with the page behind each one, and react when the list finishes.

Every function requires a signed-in caller, and lists are owned: the app keeps its own `listOwners` table and checks it before any list can be read, canceled, resumed or deleted. The component can't do this for you, because it never sees `ctx.auth`. The app also holds its own ceiling, `APP_MAX_PRICE_USD`, for the one-call `findListUnderBudget`.

The functions live in [`convex/example.ts`](convex/example.ts). The component is installed in [`convex/convex.config.ts`](convex/convex.config.ts).

## Run it against the mock

[`mock-specstream.mjs`](mock-specstream.mjs) implements the calls the component makes and fills a list in at one row a second. It delivers a signed `find.completed` webhook to any URL registered through `POST /v1/account/webhooks`, so you can watch both ways of following a list without spending anything.

From the package root:

```sh
npm install

# terminal 1: the stand-in for SpecStream
SPECSTREAM_WEBHOOK_SECRET=whsec-mock npm run dev:mock

# terminal 2: point the component at it, then start Convex
npx convex env set SPECSTREAM_API_KEY ss_mock_key
npx convex env set SPECSTREAM_API_URL http://127.0.0.1:4343
npx convex env set SPECSTREAM_WEBHOOK_SECRET whsec-mock
# The CLI calls functions unauthenticated; this lets the walkthrough run.
# Local deployments only: never set this on anything internet-reachable.
npx convex env set DEMO_ALLOW_ANONYMOUS true
npm run dev
```

## Run it against SpecStream

```sh
npx convex env remove SPECSTREAM_API_URL
npx convex env set SPECSTREAM_API_KEY ss_live_your_real_key
npx convex run example:whoAmI
```

`whoAmI` prints the account the key belongs to and what is left to spend. The mock can't reach a cloud deployment and SpecStream can't reach a local one, so on a local deployment leave lists in the default `poll` mode. On a cloud deployment, register the webhook once:

```sh
npx convex run example:registerWebhook '{"siteUrl":"https://your-name.convex.site"}'
npx convex env set SPECSTREAM_WEBHOOK_SECRET <the secret it printed>
```

## Commands

```sh
# step one: the price. Nothing runs and nothing is charged.
npx convex run example:quoteList '{"request":"open-source vector databases on GitHub","rows":10}'

# step two: approve exactly that price
npx convex run example:approveList '{"quoteId":"<quoteId>","confirmMaxCents":150,"label":"vector databases"}'

# or one call, capped by the app's own ceiling
npx convex run example:findListUnderBudget '{"request":"open-source vector databases on GitHub","rows":10}'

# then, with the listId it printed
npx convex run example:listProgress '{"listId":"<listId>"}'
npx convex run example:listRows '{"listId":"<listId>","paginationOpts":{"numItems":20,"cursor":null}}'
npx convex run example:myLists
npx convex run example:reports        # filled in by the onComplete callback
npx convex run example:cancelList '{"listId":"<listId>"}'
npx convex run example:deleteList '{"listId":"<listId>"}'
```
