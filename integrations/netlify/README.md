# SpecStream for Netlify

<!-- Draft words: wait for the writer agent before the extension is made public. -->

A Netlify extension, built with the Netlify SDK, that connects a SpecStream API key to a Netlify team. The team pastes the key once, and every site reads it from the secret environment variable `SPECSTREAM_API_KEY` in builds and functions. `details.md` is the page Netlify shows to the people who install it.

## What it does

- **Team configuration surface** (`src/ui/surfaces/TeamConfiguration.tsx`): one field for the key, with Connect, Replace key and Disconnect.
- **Server** (`src/server/router.ts`): checks the key with one free `GET https://api.specstream.ai/v1/me`, then saves it with Netlify's API as a secret team variable. The team configuration keeps the last four characters and the account's email address, never the key.
- **Build event handler** (`src/index.ts`): one line in the build log when the variable is set. It makes no network call and cannot fail a build.

The extension adds no functions or pages to a site. Calls to SpecStream come from the site's own code and are charged to the SpecStream account: Search API $5 per 1,000 searches of up to 10 results ($1 per 1,000 with `speed=fast`), Extract API $0.80 per 1,000 pages.

## Develop

Node 22.18 or later.

```
npm ci --ignore-scripts
npm test                      # node --test, no network
npm run typecheck
npm run build                 # netlify-extension build, writes .ntli/
npm run dev:open              # needs the Netlify CLI and a published private extension
```

The logic that knows SpecStream is in `src/lib/specstream.ts` and has no Netlify import, so its tests run with plain Node.

## Publish as a private extension

A Team Owner does this once in the Netlify UI:

1. Team > **Extensions** > **Created by your team** > **Create an extension**.
2. Choose the repository `specstream/specstream-tools`, with base directory `integrations/netlify`. Name the project `specstream-extension` and deploy it.
3. Display name `SpecStream`, slug `specstream`, and the summary from `extension.yaml`.
4. Permission scopes: **Environment variables** read and write. Nothing else.
5. **Create extension**. Copy the slug with its suffix from the extension's **Manage** page into `extension.yaml`, commit and deploy again.
6. **Install** it on the team, paste a key under Configuration, and deploy any site: its build log shows the SpecStream line.

## Make it public

Netlify asks partners to write to its technology partner program (https://www.netlify.com/partners/technology/) for review, and not to submit the extension through the UI. Have ready what its partner page asks for:

- name and description (`extension.yaml`), and the manual (`details.md`)
- logo: a PNG that is not transparent, at least 320 px
- environment variables: `SPECSTREAM_API_KEY`, written at team level as a secret
- what the extension does and how it works: the section above
- it is a new extension, not a migration of an older build plugin
