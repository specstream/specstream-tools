# @specstream/cli

The `specstream` command: web search, page reading and Deep Search from the terminal, with one [SpecStream](https://specstream.ai) key.

```sh
npm install -g @specstream/cli
export SPECSTREAM_API_KEY=...   # Agents & API at https://specstream.ai/workspace
specstream search "What is the latest stable release of PostgreSQL?"
```

Or run it once without an install: `npx @specstream/cli search "..."`. The package has no dependencies and needs Node 20 or newer.

## Single binary

No Node on the machine? Each release has one file per system, with nothing else to install:

| System | File |
| --- | --- |
| Linux x64 | `specstream-linux-x64` |
| Linux arm64 | `specstream-linux-arm64` |
| macOS Apple silicon | `specstream-macos-arm64` |
| macOS Intel | `specstream-macos-x64` |
| Windows x64 | `specstream-windows-x64.exe` |

```sh
curl -fsSL -o specstream https://github.com/specstream/specstream-tools/releases/download/cli-v0.1.0/specstream-linux-x64
chmod +x specstream
./specstream --version
```

`SHA256SUMS` in the same release holds each file's checksum.

## Search

```sh
specstream search "What is the latest stable release of PostgreSQL?"
specstream search "open source vector databases" --fast --num 20
specstream search "central bank rate decision" --news --country us --json
```

The Search API answers from the live web and prints the answer, the page it stands on, and the sources. The default search costs $5 per 1,000 searches of up to 10 results; `--fast` costs $1 per 1,000.

## Read pages

```sh
specstream read https://www.postgresql.org/docs/current/release.html > release.md
specstream read https://example.com/a.pdf https://example.com/b --format text
```

The Extract API reads up to 20 addresses a call (web pages, PDF, Word and Excel) and prints each one's main text as Markdown or plain text, at $0.80 per 1,000 pages. A page with no text is free. One address prints as its text alone, so it pipes into a file.

## Deep Search

Deep Search builds a complete list: every match, with the same facts on each row and a source on every value. It is priced before it runs, and nothing starts until you approve the maximum.

```sh
specstream deep "Open-source document-signing tools I can self-host. Include the license and latest release." --results 25
#   Up to 25 results cost at most $3.75. You pay only for results delivered.
#   To start it:
#     specstream deep approve <quote_id> --max-cents 375

specstream deep approve <quote_id> --max-cents 375
specstream deep status <find_id>
specstream deep rows <find_id> --all > rows.jsonl
```

`deep approve` starts the work only when `--max-cents` equals the quote's own maximum. It prints a request key before it calls; if the answer is lost, run the same command with `--key <that key>` and you will not pay twice. A price lasts 30 minutes.

## Options

- `--json` prints the API's JSON for any command.
- `--api-key <key>` instead of `SPECSTREAM_API_KEY`.
- `--base-url <url>` or `SPECSTREAM_BASE_URL` instead of `https://api.specstream.ai`.
- Exit codes: 0 done, 1 the API refused or nothing was read, 2 the command was not understood or no key was given.

The command sends your requests to the SpecStream API and nowhere else. It writes no file and keeps no state.

## Pricing

New accounts start with $10 of credit, no card. The Search API costs $5 per 1,000 searches of up to 10 results, or $1 on the fast tier, and the Extract API $0.80 per 1,000 pages. In Deep Search, a delivered result costs 5 cents, 15 cents or $1 depending on how many facts it carries. No result, no charge. See [pricing](https://specstream.ai/pricing).

## Links

- [Search API](https://specstream.ai/docs/search-api), [Extract API](https://specstream.ai/docs/extract-api) and [API docs](https://specstream.ai/docs/api)
- [Source and issues](https://github.com/specstream/specstream-tools)
- [TypeScript client](https://www.npmjs.com/package/@specstream/sdk) and [Python client](https://pypi.org/project/specstream-client/)
- Support: support@specstream.ai

MIT license.
