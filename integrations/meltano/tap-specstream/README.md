# tap-specstream

A [Singer](https://www.singer.io/) tap for [SpecStream](https://specstream.ai), built with the [Meltano Singer SDK](https://sdk.meltano.com).

SpecStream is a live web data engine. You ask in plain words for the data you need, and it returns every match as structured data, each value with the page it was read from. Each request becomes a list in your SpecStream workspace.

This tap reads those lists into any Singer target or Meltano project. It only reads: it never starts a request or spends from your SpecStream balance.

## Streams

- `lists`: one row per list (found, imported or combined) with its name, kind, record count, creation time and link. Incremental on `created_at`: later runs read only lists made since the last run. A SpecStream schedule delivers new and changed records as a new list, so they arrive on the next run.
- `records`: one row per record, a child of `lists`. `values` maps each column's label to its value; `cells` keeps every value with its `source_url` (the page it was read from) and `observed_at`. `entity_id` is the same for a company, place, person or posting in every list, so records join across lists.

A value SpecStream couldn't find is null.

## Settings

| Setting | Required | Description |
| --- | --- | --- |
| `api_key` | yes | A SpecStream API key. Create one under **Agents & API** at specstream.ai. The tap only reads, so a key with a $0 spending limit is enough. |
| `start_date` | no | Read only lists created after this time. |
| `api_url` | no | Defaults to `https://api.specstream.ai`. |

New SpecStream accounts get $10 of credit, no card.

## Use it with Meltano

```bash
meltano add extractor tap-specstream --from-ref https://raw.githubusercontent.com/specstream/specstream-tools/main/integrations/meltano/tap-specstream.yml
meltano config tap-specstream set api_key <your key>
meltano run tap-specstream target-duckdb
```

Or install it directly:

```bash
pip install tap-specstream
tap-specstream --config config.json | target-jsonl
```

## Test

```bash
pip install -e ".[test]"
SPECSTREAM_API_KEY=<key> pytest
```

Questions: support@specstream.ai or the [API reference](https://specstream.ai/docs/api).
