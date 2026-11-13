# SpecStream for Kafka Connect

The live web data engine.

One platform to build, search, extract, enrich, map, and monitor data across the entire web.

Ask for any dataset in plain words, and SpecStream builds it from the entire live web: every match found, extracted and enriched into structured records, then monitored for change. It runs through the API and MCP, and inside Sheets, CRMs, Slack, n8n, Zapier and the other tools teams already use.

This is a [Kafka Connect](https://kafka.apache.org/documentation/#connect) source connector. It writes your SpecStream lists to Kafka topics: each list, each record, and each value with the page it was read from and the time it was read. It only reads. It never starts a request and never spends from your balance.

## Topics

| Topic | One message per | Key | Fields |
| --- | --- | --- | --- |
| `specstream.list` | list | `<list_id>` | `id`, `name`, `project_id`, `imported`, `created_at`, `row_count` |
| `specstream.record` | record | `<list_id>/<record_id>` | `list_id`, `record_id`, `entity_id`, `values` (a JSON object of label to value), `sources` (the pages) |
| `specstream.record_value` | value | `<list_id>/<record_id>/<column_id>` | `list_id`, `record_id`, `column_id`, `label`, `value`, `raw_value` (JSON), `source_url`, `observed_at` |

Keys are strings and values are structs with a schema, so each converter works: JSON, Avro, Protobuf or JSON Schema.

The first run reads every list your API key can open. After that, the connector reads only the lists created since the last one. A SpecStream schedule delivers new and changed records as a new list, so they arrive on the next poll.

A list's records and values are written before the list's own message. When you see a message on `specstream.list`, all of that list's records are already in Kafka. Delivery is at least once: after a restart in the middle of a list, that list is written again with the same keys.

## Install

With the Confluent CLI, after the connector is on Confluent Hub:

```bash
confluent connect plugin install specstream/kafka-connect-specstream:latest
```

From the source:

```bash
mvn package
```

This builds `target/components/packages/specstream-kafka-connect-specstream-1.0.0.zip`. Unzip it into a folder on the worker's `plugin.path` and restart the worker. The build needs JDK 11 or later and Maven. The connector runs on Java 11 or later with Apache Kafka 2.8 or later, and on Confluent Platform.

## Configure

1. Create an API key in SpecStream under **Agents & API**. The connector only reads, so the key can have a spending limit of $0.
2. Create the connector:

   ```json
   {
     "name": "specstream-source",
     "config": {
       "connector.class": "ai.specstream.kafka.connect.SpecStreamSourceConnector",
       "tasks.max": "1",
       "specstream.api.key": "<YOUR_SPECSTREAM_API_KEY>",
       "topic.prefix": "specstream.",
       "poll.interval.ms": "300000"
     }
   }
   ```

| Setting | Default | What it does |
| --- | --- | --- |
| `specstream.api.key` | (required) | Your SpecStream API key. Kafka Connect stores it as a password and does not print it in logs. |
| `topic.prefix` | `specstream.` | The prefix of the three topics. |
| `poll.interval.ms` | `300000` | The wait, in milliseconds, before the connector asks for new lists again. |
| `specstream.api.url` | `https://api.specstream.ai` | The address of the SpecStream API. |

The connector runs one task, because one offset tracks the lists in the order they were created.

## Errors

- A rate limit or a server error is tried again up to five times with a growing wait. If SpecStream still does not answer, the worker calls the task again and the read continues from the same list.
- A refused API key stops the task with a clear message. Update `specstream.api.key` and restart the task.

## Tests

```bash
mvn test
```

The tests run the task against a scripted API on a local port. They never call SpecStream.

## License

MIT
