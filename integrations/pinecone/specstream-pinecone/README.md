# specstream-pinecone

SpecStream: the live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. It runs through the API and MCP, and inside Sheets, CRMs, Slack, n8n, Zapier and the other tools teams already use.

<!-- The text below is a draft. It waits for the writer agent before the package is published. -->

This package loads your SpecStream Deep Search lists into a Pinecone index, one vector per record (and web pages read with the Extract API and research reports, below), through the official Python client (`pinecone`). The vectors come from an embedding model Pinecone hosts, so nothing runs on your machine. Loading lists only reads from SpecStream: it never starts a request or spends from your balance. Reading pages is charged at the Extract price, and a new research report at its own price.

## Vectors

Index `specstream` (change it with `--index`), namespace `__default__` (change it with `--namespace`). The index is made on the first load as a serverless index with cosine distance and the vector size of the model (1024 for `llama-text-embed-v2`, the default).

The vector id is `<list id>#<record id>`. Its metadata:

| Key | Value |
| --- | --- |
| `list_id`, `list_name`, `list_kind`, `list_created_at`, `link` | the list the record is in |
| `record_id`, `entity_id` | the record; `entity_id` is the same for a company, place, person or posting in every list |
| `fields` | JSON text `{label: value}`; a value SpecStream could not find is null |
| `sources` | JSON text `{label: source_url}`: the page each value was read from |
| `source_urls` | the pages the values were read from, as a list |
| `text` | the embedded text: the list name and one `Label: value` line per value |
| `loaded_at` | when the vector was written |

- Loading a list again writes its new vectors, then deletes the ones of records it no longer has.

## Use

```bash
pip install specstream-pinecone
export SPECSTREAM_API_KEY=...   # Agents & API at specstream.ai; a $0 spending limit is enough
export PINECONE_API_KEY=...

specstream-pinecone load                   # every list not yet in the namespace
specstream-pinecone load --list <id>       # one list, again
specstream-pinecone load --full            # every list again
specstream-pinecone load --model multilingual-e5-large --dimension 1024 --index specstream-e5
```

From Python, with any embedding function (texts in, one vector per text out):

```python
from pinecone import Pinecone
from specstream_pinecone.api import SpecStreamAPI
from specstream_pinecone.load import load, open_index, pinecone_embed

pc = Pinecone(api_key="...", source_tag="specstream")
index = open_index(pc, "specstream", dimension=1024)
load(index, SpecStreamAPI(api_key="..."), pinecone_embed(pc))

question = pinecone_embed(pc, input_type="query")(["<your question>"])[0]
hits = index.query(vector=question, top_k=5, include_metadata=True,
                   filter={"list_id": {"$eq": "<id>"}}, namespace="__default__").matches
```

## Public records, kept up to date

SpecStream reads public records from the official sources every day (SEC Form D filings, nonprofits, workplace safety inspections and more: https://specstream.ai/data). The `records` command keeps them in the same index, one vector per record. Run it once a day, from cron or any scheduler.

```bash
export PINECONE_API_KEY=...

# A public feed: no SpecStream key and no licence. Each run writes only the new items.
specstream-pinecone records --feed
specstream-pinecone records --feed https://specstream.ai/feeds/us-funding-rounds.json

# A licence's files (https://specstream.ai/data/licence). The link is a secret, so it is read from the environment.
export SPECSTREAM_RECORDS_LINK=https://specstream.ai/data/files/<your link>
specstream-pinecone records                    # every family of the licence
specstream-pinecone records --family formd     # one family
specstream-pinecone records --full             # each whole file again
```

With a licence, the first run loads each family's whole file. Every later run applies only the days after the last one it applied: first the day's removal list (those vectors are deleted), then the day's new records. A run with nothing new writes nothing. The day each family was applied through is kept in the index, in the namespace `specstream-state`, so the command needs no file of its own and runs from any machine.

| Vector | Id | Metadata |
| --- | --- | --- |
| A record of a licence file | `records:<family>#<digest of the record's key>` | `kind` (`record`), `family`, `family_title`, `link`, `name`, `key`, `fields` (JSON text `{column: value}`), `source_urls`, `text`, `loaded_at` |
| An item of a public feed | `feed:<feed name>#<digest of the item's id>` | `kind` (`feed_item`), `feed`, `feed_title`, `link`, `name`, `published`, `tags`, `source_urls`, `text`, `loaded_at` |

- Embedding is done by Pinecone and billed by Pinecone. A whole file can hold up to 2 million records: start with `--family`.
- A removal list also names a record that stays in the file with one value withdrawn. Its vector is deleted, and `--full` brings the record back without that value.
- A run more than 30 days after the last one loads the whole file again, because the day files are kept for 35 days.
- A family whose records have no key column is loaded whole each time its file is built again.

From Python: `sync_feed(index, embed, dimension)` and `sync_records(index, RecordFiles(link), embed, dimension)` in `specstream_pinecone.records`.

## Web pages, read with the Extract API

The `pages` command reads web pages with the SpecStream Extract API and writes their text into the same index, one vector per chunk. Extract costs $0.80 per 1,000 pages; a page that gives no text is not charged and is listed as not loaded.

```bash
export SPECSTREAM_API_KEY=...
export PINECONE_API_KEY=...

specstream-pinecone pages https://example.com/docs https://example.com/blog/launch
specstream-pinecone pages --file urls.txt            # one URL a line; a line that starts with # is skipped
specstream-pinecone pages --file urls.txt --namespace docs --chunk-size 1500 --overlap 150
```

| Id | Metadata |
| --- | --- |
| `page:<digest of the URL>#<chunk number>` | `kind` (`page`), `url`, `final_url`, `title`, `published`, `modified`, `read_from`, `chunk`, `chunks`, `text`, `loaded_at` |

- A chunk holds at most 2,000 characters (`--chunk-size`), cut between paragraphs where it can. A paragraph longer than that is cut into parts that share 200 characters (`--overlap`).
- The title and the chunk are embedded together. Reading a page again replaces its chunks, so a page that got shorter keeps no old chunks.
- Up to 20 pages go in one Extract call, and a URL given twice is read once.

From Python: `load_pages(api, embed, urls, index=index)` in `specstream_pinecone.pages`.

## Research reports

A research report answers a question in plain words with a written report from the live web, and each cited sentence carries the page it was read from. The `research` command writes reports into the same index, one vector per chunk, with the pages that chunk cites.

```bash
export SPECSTREAM_API_KEY=...
export PINECONE_API_KEY=...

specstream-pinecone research "Which companies ship solid-state batteries in 2026?" --depth quick
specstream-pinecone research --id <report id>        # a report the account already has; no spend
specstream-pinecone research --all                   # every completed report not yet in the namespace; no spend
```

A question starts a new report: $0.10 (`--depth quick`), $0.30 (`standard`, the default) or $1.00 (`deep`), charged once, when the report is delivered. `--id` and `--all` only read.

| Id | Metadata |
| --- | --- |
| `research:<report id>#<chunk number>` | `kind` (`research`), `report_id`, `title`, `question` (for a report this command started), `depth`, `completed_at`, `chunk`, `chunks`, `text`, `sources` (JSON text `{marker number: page}`), `source_urls`, `source_titles`, `loaded_at` |

- The text keeps its `[1]` markers. `sources` and `source_urls` name the page behind each marker in that chunk.
- A chunk holds at most 2,000 characters (`--chunk-size`), cut between paragraphs where it can. Writing a report again replaces its chunks.
- The command waits up to 15 minutes for a new report (`--wait`). A report that takes longer goes on at SpecStream: load it later with `--id`.
- A report that failed or was cancelled is not charged, writes nothing and is listed as not loaded.

From Python: `load_research(api, embed, index, questions=[...], depth="quick")` in `specstream_pinecone.research`.

## Known limits

- One dense vector per record. Use a new index to change the model.
- A load reads lists newest first and stops at the first list already in the namespace. A list that was still running when loaded, or a list a SpecStream schedule changed, is read again with `--list <id>` or `--full`.
- Each list is read in one API response and written in batches of 96 vectors. The `text` kept in metadata is cut at 10,000 characters.

## Test

```bash
uv run --frozen pytest -q                                          # in-memory index, scripted API, no network
docker run -d -p 5080-5090:5080-5090 ghcr.io/pinecone-io/pinecone-local
PINECONE_HOST=http://localhost:5080 uv run --frozen pytest -q      # also against Pinecone Local
```

Questions: support@specstream.ai or the [API reference](https://specstream.ai/docs/api).
