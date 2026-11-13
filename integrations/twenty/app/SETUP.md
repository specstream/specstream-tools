# Develop the app

The app was scaffolded with `twenty app init` (the command `create-twenty-app` became) and keeps that layout.

Use Node.js from `.nvmrc` and Yarn 4. Install the standalone CLI globally:

```bash
npm install -g twenty@2.58.0
yarn install
```

Connect to a Twenty workspace, or start a server with the [local-server guide](https://docs.twenty.com/developers/extend/apps/getting-started/local-server):

```bash
twenty auth login --url https://your-workspace.twenty.com --name dev
twenty app apply --create
twenty app dev
```

## Where things are

- `src/specstream/` holds the behaviour, free of Twenty: the request for a company (`request.ts`), the SpecStream calls (`api.ts`), starting and collecting the research (`enrich.ts`), the text written to the record (`result.ts`), and the Twenty records through GraphQL (`twenty.ts`).
- `src/logic-functions/` holds the four entry points: `research-company` (AI tool and workflow action), `research-new-company` (a new company, when the setting is on), `collect-research` (every five minutes) and `health-check`.
- `src/fields/` holds the four fields added to Company.

## Checks

- `yarn test` (or `yarn test:unit`, or `npm install && npm test`) runs the unit tests. They script SpecStream's answers and call nothing outside.
- `yarn typecheck` and `yarn lint`.
- `twenty app build` builds the manifest without a server.
- `yarn test:integration` runs the integration test against a disposable workspace set with `TWENTY_API_URL` and `TWENTY_API_KEY`. It installs and uninstalls the app. It never calls SpecStream.

## Publish

The public copy is `integrations/twenty/app` in github.com/specstream/specstream-tools. Its workflow `publish.yml`, started with the package `twenty-app`, runs `twenty app publish`, which publishes `@specstream/twenty-app` to npm with provenance. Raise `version` in `package.json` and add a `CHANGELOG.md` entry first. After the first publish, claim the app in Twenty (Settings > Developers > Apps > Claim with GitHub) and ask for the marketplace review.
