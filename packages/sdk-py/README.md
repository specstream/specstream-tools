# specstream-client

`pip install specstream-client` (the `specstream` package on PyPI is a different project)

Python client and command line for [SpecStream](https://specstream.ai), the live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change.

- Source URL and read time on every value.
- You pay for each row delivered.

The client has no dependencies and needs Python 3.12 or newer. It uses the same account, permissions, projects and balance as the workspace.

```sh
pip install specstream-client
```

The package installs the import name `specstream` and the command `specstream`.

Create an API key under **Agents & API** in your SpecStream workspace and keep it in the environment:

```sh
export SPECSTREAM_API_KEY="ss_live_..."
```

## Read a request, get the price

```python
import os
from specstream_client import Client

client = Client(os.environ["SPECSTREAM_API_KEY"])

read = client.compile("Open-source document-signing tools I can self-host. Include the license and latest release.")
offer = client.quote_capacity_work({
    "ast_hash": read["ast_hash"],
    "operation": "find",
    "requested_units": read["ast"]["limit"]["max"],
})
print(offer["maximum_cents"], offer["expires_at"])
```

Nothing has run yet. Review the quote: what will be found, the facts that come back, the most the work can cost, and when the price expires. A price lasts 30 minutes.

## Approve it, then read the results

After a person approves, send the approved maximum in cents and a request key you saved first:

```python
run = client.authorize_capacity_work({
    "quote_id": offer["quote_id"],
    "quote_hash": offer["quote_hash"],
    "confirm_max_cents": approved_maximum_cents,
    "idempotency_key": saved_request_key,
})
find_id = run["find_id"]

page = client.rows(find_id)
for row in page["rows"]:
    print(row)
```

If the response is lost, `get_capacity_request(saved_request_key)` returns the same work. Keep the original key when you retry, and you will not pay twice. `get_find` reports progress, and `rows` pages through results with `next_cursor`. Reading, exporting and sharing results you own cost nothing.

`authorize_capacity_work` refuses to send anything unless the quote, its signature, the maximum and the key are all present.

## More than a first request

- `quote_capacity_work` also prices `extend` (more results), `add_facts` and `refresh` (a recheck, at half price) on a finished run. Pass the original `parent_find_id`.
- `spec_options(kind)` lists the facts you can ask for, per kind of thing. `edit_spec` changes a request without rereading it.
- `create_capacity_schedule` keeps a request up to date, hourly to yearly, inside per-run and per-period limits.
- `export` and `download_export` give CSV, XLSX, JSON or HTML. `create_customer_webhook` sends signed events.
- Projects, members, shares and starred items have their own methods.

Kinds of thing include local businesses, companies, people, creators, products, apps, job postings, papers, clinical trials, grants, tenders, regulations, vulnerabilities, software packages, repositories, datasets, books and podcasts.

## Command line

```sh
specstream compile "Open-source vector databases on GitHub with more than 5,000 stars, with their license."
specstream get-capacity-balance
specstream quote-capacity-work --body quote-request.json
specstream authorize-capacity-work --body approved-execution.json
specstream rows --find-id FIND_ID
```

`--body` takes a JSON file or `-` for stdin. Every command's `--help` describes its parameters. The command line exposes the same operations as the client.

## Pricing

New accounts start with $10 of work for 30 days, no card. A delivered result costs 5 cents, 15 cents or $1 depending on how many facts it carries. No result, no charge. Rechecks cost half. People and agents share one balance. See [pricing](https://specstream.ai/pricing).

## Links

- [SDK docs](https://specstream.ai/docs/sdk) and [API docs](https://specstream.ai/docs/api)
- [Source and issues](https://github.com/specstream/specstream-tools)
- [TypeScript client](https://www.npmjs.com/package/@specstream/sdk)
- Support: support@specstream.ai

MIT license.
