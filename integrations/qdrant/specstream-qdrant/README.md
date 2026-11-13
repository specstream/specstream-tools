# specstream-qdrant

SpecStream: the live web data engine. One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. It runs through the API and MCP, and inside Sheets, CRMs, Slack, n8n, Zapier and the other tools teams already use.

<!-- The text below is a draft. It waits for the writer agent before the package is published. -->

This package fills a Qdrant collection from the live web, through the official Python client (`qdrant-client`):

- `specstream-qdrant pages`: reads web pages with the SpecStream Extract API and writes their main text, one point per chunk. $0.80 per 1,000 pages read; a page that gives no text is not charged.
- `specstream-qdrant load`: writes your SpecStream Deep Search lists, one point per record. It only reads lists you already have: it never starts a request or spends from your balance.

## Pages

```bash
pip install 'specstream-qdrant[fastembed]'
export SPECSTREAM_API_KEY=...            # Agents & API at specstream.ai
export QDRANT_URL=http://localhost:6333

specstream-qdrant pages https://qdrant.tech/documentation/ https://example.com/blog/post
specstream-qdrant pages --file urls.txt  # one URL a line; - reads stdin
specstream-qdrant pages --file urls.txt --chunk-size 1500 --overlap 150 --format text
```

Collection `specstream_pages` (change it with `--collection`), cosine distance, a payload index on `url`. Up to 20 URLs go in one Extract call.

| Payload key | Value |
| --- | --- |
| `url`, `final_url` | the page sent, and where it ended after redirects when SpecStream says so |
| `title`, `published`, `modified` | as the page gives them |
| `read_from` | `live`, `site` (the site's own API or feed) or `archive` (its newest public web archive capture) |
| `chunk`, `chunks` | this chunk's number from 0, and how many the page has |
| `text` | the chunk's text; the title and the text are embedded |
| `loaded_at` | when the point was written |

- Chunks are cut between paragraphs, at most `--chunk-size` characters (2,000). A longer paragraph is cut into windows that share `--overlap` characters (200).
- The point id is derived from the URL and the chunk number. Reading a page again deletes its old chunks and writes the new ones.
- A page that gives no text (blocked, not found, empty, not a document SpecStream reads) writes nothing and is printed with its reason.

From Python:

```python
from qdrant_client import QdrantClient
from specstream_qdrant.api import SpecStreamAPI
from specstream_qdrant.load import fastembed
from specstream_qdrant.pages import load_pages

result = load_pages(QdrantClient(url="http://localhost:6333"), SpecStreamAPI(api_key="..."),
                    fastembed("BAAI/bge-small-en-v1.5"), ["https://qdrant.tech/documentation/"])
print(result.pages, result.chunks, result.skipped, result.price_usd)
```

## Lists

Collection `specstream` (change it with `--collection`). It is made on the first load, with cosine distance and the vector size of the embedding model, and payload indexes on `list_id` and `entity_id`.

| Payload key | Value |
| --- | --- |
| `list_id`, `list_name`, `list_kind`, `list_created_at`, `link` | the list the record is in |
| `record_id`, `entity_id` | the record; `entity_id` is the same for a company, place, person or posting in every list |
| `fields` | `{label: value}`; a value SpecStream could not find is null |
| `sources` | `{label: source_url}`: the page each value was read from |
| `cells` | each value with its `source_url` and `observed_at` |
| `text` | the embedded text: the list name and one `Label: value` line per value |
| `loaded_at` | when the point was written |

- The point id is derived from the list and the record. Loading a list again deletes its old points and writes the new ones.

```bash
export SPECSTREAM_API_KEY=...            # a $0 spending limit is enough for lists
export QDRANT_URL=http://localhost:6333  # Qdrant Cloud: https://<cluster>.cloud.qdrant.io:6333
export QDRANT_API_KEY=...                # Qdrant Cloud only

specstream-qdrant load                   # every list not yet in the collection
specstream-qdrant load --list <id>       # one list, again
specstream-qdrant load --full            # every list again
specstream-qdrant load --model BAAI/bge-small-en-v1.5   # any FastEmbed text model (this one is the default)
```

From Python, with any embedding function (texts in, one vector per text out):

```python
from qdrant_client import QdrantClient, models
from specstream_qdrant.api import SpecStreamAPI
from specstream_qdrant.load import fastembed, load

client = QdrantClient(url="http://localhost:6333")
embed = fastembed("BAAI/bge-small-en-v1.5")
load(client, SpecStreamAPI(api_key="..."), embed, collection="specstream")

hits = client.query_points(
    "specstream",
    query=embed(["<your question>"])[0],
    query_filter=models.Filter(must=[models.FieldCondition(key="list_id", match=models.MatchValue(value="<id>"))]),
    limit=5,
).points
```

## Known limits

- One dense vector per point, unnamed. Use a new collection to change the model.
- A load reads lists newest first and stops at the first list already in the collection. A list that was still running when loaded, or a list a SpecStream schedule changed, is read again with `--list <id>` or `--full`.
- Each list is read in one API response and written in batches of 64 points.
- Pages and lists go in separate collections by default; they can share one if the same model embeds both.

## Test

```bash
uv run --frozen pytest -q                                          # Qdrant local mode, scripted API, no network, no spend
QDRANT_URL=http://localhost:6333 uv run --frozen pytest -q         # also against a real Qdrant server
```

Questions: support@specstream.ai or the [API reference](https://specstream.ai/docs/api).
