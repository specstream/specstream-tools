# SpecStream for Obsidian

[SpecStream](https://specstream.ai) is the live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. This plugin puts the rows in your note as a Markdown table, where your cursor is.

- Source URL and read time on every value.
- You see the price first and approve it with one click. You pay for each row delivered.

## What lands in your note

A Markdown table with one column per fact you asked for, plus a Source column that links each row's page:

| Name | Website | Annual revenue | Source |
| --- | --- | --- | --- |
| *the match* | *its own site* | *the figure it published* | *[its source URL]* |

Under the table, if you leave it on, goes one line with your request, the row count, the date, and a link to the list in your SpecStream workspace. The workspace is where a list stays up to date, goes to Sheets or a CRM, and lands in your inbox when something new shows up.

## Commands

Open the command palette and type "SpecStream".

- **SpecStream: Find a list.** Type what you want and how many rows. The plugin asks SpecStream for a price and shows you the maximum. Click approve and it runs, waits for the list, and inserts the table at your cursor.
- **SpecStream: Insert a saved list.** Pick any list SpecStream already found for you and insert it. Reading a list you own is free.

Neither command sets a hotkey. Bind them in **Settings → Hotkeys** if you want one.

## Install

When the plugin is in the community directory: **Settings → Community plugins → Browse**, search for SpecStream, install, enable.

Before that, or to try a build by hand: download `main.js`, `manifest.json` and `styles.css` from the [latest release](https://github.com/specstream/obsidian-specstream/releases/latest), put them in `<your vault>/.obsidian/plugins/specstream/`, reload Obsidian, and enable SpecStream under **Community plugins**.

## Set up

1. Create a free account at [specstream.ai](https://specstream.ai). New accounts start with $10 of work free for 30 days, once, no card.
2. In your [workspace](https://specstream.ai/workspace/agents), open **Agents & API** and select **Create API key**. Give it read results and their sources, prepare work and follow-ups, authorize paid work, and read account and balance. Set a spending limit on the key too if you like. It stacks with the plugin's own limit.
3. In Obsidian, open **Settings → SpecStream**, choose the API key field, and add your key as a secret. Press **Check** to see which account it belongs to and what is left to spend.

The key is kept in Obsidian's secret storage, not in your vault and not in the plugin's `data.json`. The plugin's data holds only the name of the secret.

## How paying works

Nothing is bought without your click.

1. You write the request. The plugin asks SpecStream to read it and price it. Nothing runs, nothing is charged.
2. You see the maximum price for the row count you chose. It is a ceiling: you pay for each row delivered, and a search that finds nothing costs nothing.
3. If the maximum is above your spending limit, the approve button stays off. Ask for fewer rows or raise the limit in settings.
4. You click **Approve**. That approves exactly that quote at exactly that maximum, and the plugin starts the list.

Matches cost 5¢, 15¢ or $1 each depending on how many facts you ask for. A person's email adds 5¢ and a phone number adds 15¢ on top of the row's rate. SpecStream shows the maximum before anything runs, so there is no bill to discover afterward. Current rates are on the [pricing page](https://specstream.ai/pricing).

## Settings

| Setting | Default | What it does |
| --- | --- | --- |
| API key | none | Your SpecStream API key, kept in Obsidian's secret storage |
| Default row count | 25 | Rows to ask for each time. 1 to 1000. You can change it in the window |
| Spending limit per request | $5 | The most one list may cost. A higher price can't be approved from the plugin |
| Add a note under each table | on | The line with your request, row count, date, and a link to the list |

If your request names its own count ("50 open datasets on..."), that count wins over the default.

## Network use, accounts and privacy

This plugin needs the internet and a SpecStream account. Here is exactly what it does.

- **Network use.** The plugin talks only to `https://api.specstream.ai`, with Obsidian's own `requestUrl`. It sends the request text you type, the row count, and your API key as an authorization header. It reads back prices, run status, rows and the names of your lists. The source links in your table are plain links. The plugin never opens them.
- **What stays in your vault.** The plugin never reads your notes. It only writes the table at your cursor. It touches no files outside your vault.
- **Account required.** You need a SpecStream account and an API key to use it. Creating an account is free and takes no card.
- **Payment.** Lists cost money after the free $10 of work, priced per match as described above. You approve every price in the plugin before anything runs.
- **Telemetry and ads.** The plugin has no analytics, no tracking and no ads. SpecStream's server handles the requests you send it under its [privacy policy](https://specstream.ai/privacy).
- **Open source, hosted service.** The plugin is MIT licensed and all of its source is here. The SpecStream service it calls is a hosted product and is not open source.

## Troubleshooting

- **"SpecStream did not accept the API key."** The key was revoked, expired or pasted with a space. Create a new one and choose it again in settings.
- **"SpecStream needs a clearer request."** Add the place, or what every row must meet. "Datasets" is a category. "Open datasets on urban tree canopy published since 2020" is a request.
- **The list is still running when the window says it is taking longer than usual.** Close the window. The list keeps running, and **Insert a saved list** will find it when it's done.
- **No lists in the picker.** The picker shows lists SpecStream found for you. Lists you imported or combined stay in the workspace.

## Develop

```sh
npm install
npm run dev      # rebuilds main.js as you save
npm run build    # type-check, then the production bundle
npm run lint     # the same checks the community directory runs
npm test         # table formatting
```

Link or copy the folder into `<your vault>/.obsidian/plugins/specstream/` and reload Obsidian. The source is in `src/`: `api.ts` is the few SpecStream calls, `table.ts` builds the Markdown, and `ui/` holds the two windows.

## Release

Obsidian installs from GitHub releases, so every version needs one.

1. Run `npm version <x.y.z>`. It bumps `manifest.json` and `versions.json` and creates a tag with no `v` prefix.
2. Push the commit and the tag: `git push --follow-tags`.
3. The release workflow builds the plugin and drafts a release with `main.js`, `manifest.json` and `styles.css` attached. Publish the draft.

The first version goes through the [Obsidian Community directory](https://community.obsidian.md): sign in, link GitHub, and add this repository from **Plugins → New plugin**. After that, a new release is all an update takes.

## License

[MIT](LICENSE). Copyright SpecStream SAS.
