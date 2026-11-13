package ai.specstream.kafka.connect;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.connect.data.Schema;
import org.apache.kafka.connect.data.Struct;
import org.apache.kafka.connect.source.SourceRecord;
import org.apache.kafka.connect.source.SourceTask;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Reads the lists the API key can open and writes them to three topics.
 *
 * <p>The first poll reads every list. Later polls read only the lists created since the last one: a SpecStream
 * schedule delivers new and changed records as a new list, so new lists are where new data arrives.
 *
 * <p>Each call to {@link #poll()} returns one whole list. The list's own row comes last and is the only row that
 * moves the offset, so a list that was cut off by a restart is read again from its start.
 */
public class SpecStreamSourceTask extends SourceTask {
    static final String OFFSET_KEY = "lists_created_through";
    private static final Logger log = LoggerFactory.getLogger(SpecStreamSourceTask.class);
    private static final long MAX_WAIT_MS = 1_000L;

    private final Deque<JsonNode> pending = new ArrayDeque<>();
    private final CountDownLatch stopped = new CountDownLatch(1);
    private SpecStreamSourceConfig config;
    private SpecStreamClient client;
    private Map<String, String> sourcePartition;
    private String syncedThrough = "";
    private long nextCheckAtMs;

    @Override
    public String version() {
        return Version.get();
    }

    @Override
    public void start(Map<String, String> props) {
        config = new SpecStreamSourceConfig(props);
        client = newClient(config);
        sourcePartition = Collections.singletonMap("api", config.apiUrl());
        Map<String, Object> offset = context == null || context.offsetStorageReader() == null
            ? null
            : context.offsetStorageReader().offset(sourcePartition);
        Object stored = offset == null ? null : offset.get(OFFSET_KEY);
        syncedThrough = stored == null ? "" : stored.toString();
        nextCheckAtMs = 0L;
        log.info("SpecStream source task started; lists are read from {}",
            syncedThrough.isEmpty() ? "the beginning" : syncedThrough);
    }

    /** A separate method so that a test can shorten the wait between tries. */
    SpecStreamClient newClient(SpecStreamSourceConfig settings) {
        return new SpecStreamClient(settings.apiUrl(), settings.apiKey());
    }

    @Override
    public List<SourceRecord> poll() throws InterruptedException {
        if (pending.isEmpty()) {
            long waitMs = nextCheckAtMs - System.currentTimeMillis();
            if (waitMs > 0) {
                // A short wait keeps stop() quick.
                stopped.await(Math.min(waitMs, MAX_WAIT_MS), TimeUnit.MILLISECONDS);
                return null;
            }
            pending.addAll(client.listsCreatedAfter(syncedThrough));
            nextCheckAtMs = System.currentTimeMillis() + config.pollIntervalMs();
            if (pending.isEmpty()) {
                return null;
            }
            log.info("{} new SpecStream list(s) to read", pending.size());
        }

        // The list stays in the queue until its records are read, so a failed read is tried again.
        JsonNode summary = pending.peekFirst();
        String listId = summary.path("id").asText();
        String createdAt = summary.path("created_at").asText("");
        JsonNode detail = client.list(listId);
        RecordMapper.Rows rows = RecordMapper.rows(listId, detail);

        Map<String, String> before = Collections.singletonMap(OFFSET_KEY, syncedThrough);
        Map<String, String> after = Collections.singletonMap(OFFSET_KEY, createdAt);
        List<SourceRecord> records = new ArrayList<>(rows.records.size() + rows.values.size() + 1);
        for (Struct value : rows.values) {
            String key = listId + "/" + value.getString("record_id") + "/" + value.getString("column_id");
            records.add(record(before, config.recordValueTopic(), key, value));
        }
        for (Struct record : rows.records) {
            records.add(record(before, config.recordTopic(), listId + "/" + record.getString("record_id"), record));
        }
        records.add(record(after, config.listTopic(), listId, RecordMapper.list(summary, rows.records.size())));

        pending.removeFirst();
        syncedThrough = createdAt;
        log.info("Read SpecStream list {} with {} record(s)", listId, rows.records.size());
        return records;
    }

    private SourceRecord record(Map<String, String> offset, String topic, String key, Struct value) {
        return new SourceRecord(sourcePartition, offset, topic, Schema.STRING_SCHEMA, key, value.schema(), value);
    }

    @Override
    public void stop() {
        stopped.countDown();
    }
}
