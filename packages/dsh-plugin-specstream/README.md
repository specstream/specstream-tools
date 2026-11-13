# SpecStream for DeepSeek Harness

The live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web. Source URL and read time on every value. Nothing runs until you approve the quote's maximum.

After you install this plugin, the harness's own `web_search` tool answers from SpecStream: an answer with its page, and the sources with their titles and snippets. The agent also gets a research tool: it asks a question and gets a report written from the live web, with the page behind each cited sentence.

## Install

Name the profile you run. For the web app:

```
dsh plugin --profile web add @specstream/dsh-plugin
```

For one-shot tasks, `dsh plugin --profile headless add @specstream/dsh-plugin`. On the desktop app: Settings, Plugin Market, search for SpecStream, Install.

Then store your key as the credential `SPECSTREAM_API_KEY`, or export `SPECSTREAM_API_KEY` before you start `dsh`. Get one at [specstream.ai](https://specstream.ai/?utm_source=deepseek-harness); new accounts start with $10 of credit, no card.

## What it does

The plugin registers SpecStream as a search provider and a fetch provider of the harness's web seam (`ctx.web`), both with the id `specstream`. Its bundle patch selects SpecStream for search, so `web_search` calls `GET /v1/web-search` with up to 10 results a query.

`web_fetch` stays on the harness's local fetcher. To read pages through SpecStream (`POST /v1/extract`, the main text as Markdown), set the fetch provider to `specstream` on the Web search and fetch settings page, or in your profile's `cordis.patch.yml`:

```yaml
- id: web
  config:
    searchProvider: specstream
    fetchProvider: specstream
```

## Research reports

The plugin registers two tools with the harness's tool registry (`ctx.tools`):

- `specstream_research` takes a `question` and an optional `depth` (`quick`, `standard` or `deep`). It starts a report (`POST /v1/research`), waits for it, and returns the report in Markdown with its numbered sources.
- `specstream_research_result` takes the run `id` and reads the report. The agent calls it when a report took longer than one call waits.

Ask for one in plain words: `Research which EU countries tax battery storage, with sources.`

A report is charged once, when it is delivered. A run that fails is not charged. When you stop the call, the plugin cancels the run, and a cancelled run is not charged.

## Config

Set these on the `specstream` row of your profile's `cordis.patch.yml`. All are optional.

- `apiKeyEnv`: the credential that holds the key. Default `SPECSTREAM_API_KEY`.
- `speed`: `fast` for the fast tier (results with snippets in about a second, no answer). Default: the default tier, with an answer.
- `baseURL`: default `https://api.specstream.ai`.
- `research`: `false` to register no research tool. Default `true`.
- `researchDepth`: the depth of a report when the agent names none: `quick`, `standard` or `deep`. Default `quick`.
- `researchWaitSeconds`: how long one call waits for a report before it returns the run id. Default 300, at most 1800.

## Prices

- Search: $5 per 1,000 searches of up to 10 results, and $1 per 1,000 with `speed: fast`.
- Fetch through SpecStream: $0.80 per 1,000 pages. A page with no text is not charged.
- Research report: $0.10 quick, $0.30 standard, $1.00 deep, for each delivered report.

## Category

Tools & Capabilities.

## Permissions and external services

- The plugin needs the harness services `web` and `tools` and nothing else. It has no dependencies, runs no local process and reads no files.
- It talks to one outside service, `api.specstream.ai`, only when the agent searches the web, starts or reads a research report, or fetches a page (when you select SpecStream for fetch).
- A research report spends your SpecStream credit. Your harness's tool approval policy decides whether the agent asks you before it calls `specstream_research`.
- The key is read from the harness's credentials provider at each request and is never written to settings.

## Compatibility

- DeepSeek Harness with the web seam (`ctx.web`) and the tool registry (`ctx.tools`), checked on 0.2.2-rc.1 (the tool definitions also against the schema check of 0.2.2-rc.2), profiles `web`, `headless` and `desktop`.
- Node.js 22.19 or later, or 24 and later.
- Every platform the harness runs on. The plugin is plain JavaScript with no dependencies.

## Develop

```
npm test
```

## License

MIT. See [LICENSE](LICENSE).

The same code is kept in [specstream/specstream-tools](https://github.com/specstream/specstream-tools/tree/main/packages/dsh-plugin-specstream), which publishes [@specstream/dsh-plugin](https://www.npmjs.com/package/@specstream/dsh-plugin) to npm.
