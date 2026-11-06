# SpecStream piece for Activepieces

SpecStream is the live web data engine for teams and agents. One platform to build, search, extract, enrich, map, and monitor data across the entire web. Source URL and read time on every value.

## Install

In Activepieces, open **Platform admin → Pieces → Install piece**, choose **npm**, and enter `@specstream/piece-specstream`.

## Actions

- **Web Search**: answers a question from the live web in seconds with the Search API (`GET /v1/web-search`, $5 per 1,000 searches).
- **Extract Pages**: reads the main text, title and published date of 1 to 20 web pages, PDFs, Word or Excel files live with the Extract API (`POST /v1/extract`, $0.80 per 1,000 pages, empty pages free).
- **Find a List**: reads the request, prices it, and starts it only if the price is at or below your **Maximum Price**. Returns the list ID and link. Retries are safe: identical requests within the same UTC hour share one run, or set your own **Run Key**.
- **Get List Results**: the rows of a list, each with `source_url` and `checked_at`.
- **Custom API Call**: any endpoint on `https://api.specstream.ai`, over HTTPS only.

## Triggers

- **New Row in a Finished List**: runs once for every row when a list finishes.
- **New or Changed Row in a Watched List**: runs once for every new or changed row in a list you keep current.

## Connect

Create an API key in SpecStream under [Agents & API](https://specstream.ai/workspace/settings). New accounts get $10 of credit. Docs: https://specstream.ai/docs/api
