package ai.specstream.kafka.connect;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import org.apache.kafka.common.config.ConfigException;
import org.apache.kafka.connect.data.Struct;
import org.apache.kafka.connect.errors.ConnectException;
import org.apache.kafka.connect.errors.RetriableException;
import org.apache.kafka.connect.source.SourceRecord;
import org.apache.kafka.connect.source.SourceTaskContext;
import org.apache.kafka.connect.storage.OffsetStorageReader;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/** The task against a scripted SpecStream API on a local port. No test calls the real API. */
class SpecStreamSourceTaskTest {
    private static final String KEY = "test-key";
    private static final String FOUND_LIST = "{\"data\":{\"rows\":[{\"ordinal\":1,\"entity_id\":\"ent_1\",\"cells\":["
        + "{\"column_id\":\"name\",\"label\":\"Name\",\"display\":\"Acme\",\"value\":\"Acme\","
        + "\"provenance\":{\"source_url\":\"https://acme.example/about\",\"observed_at\":\"2026-11-01T10:00:00Z\"}},"
        + "{\"column_id\":\"employees\",\"label\":\"Employees\",\"display\":\"120\",\"value\":120,"
        + "\"provenance\":{\"source_url\":\"https://acme.example/team\",\"observed_at\":\"2026-11-01T10:00:01Z\"}},"
        + "{\"column_id\":\"phone\",\"label\":\"Phone\",\"display\":\"not found\",\"absence\":{\"reason\":\"none\"}},"
        + "{\"column_id\":\"open\",\"label\":\"Open\",\"display\":\"Open\"}]}]}}";
    private static final String IMPORTED_LIST =
        "{\"data\":{\"rows\":[{\"id\":\"row_9\",\"provided\":{\"Company\":\"Globex\",\"Size\":40}}]}}";
    private static final String COMBINED_LIST = "{\"data\":{\"rows\":[{\"id\":\"m_1\","
        + "\"sources\":[{\"row\":{}},{\"row\":{\"entity_id\":\"ent_7\"}}],"
        + "\"field_values\":{\"name\":[{\"label\":\"Name\",\"display\":\"Initech\",\"value\":\"Initech\","
        + "\"provenance\":{\"source_url\":\"https://initech.example\"}},{\"label\":\"Name\",\"display\":\"Other\"}],"
        + "\"empty\":[]}}]}}";

    private HttpServer server;
    private final Map<String, String> bodies = new ConcurrentHashMap<>();
    private final Map<String, Integer> statuses = new ConcurrentHashMap<>();
    private final List<String> requests = new CopyOnWriteArrayList<>();
    private final List<String> methods = new CopyOnWriteArrayList<>();
    private final AtomicInteger failuresLeft = new AtomicInteger();
    private volatile String lastAuthorization;

    @BeforeEach
    void startApi() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            String target = exchange.getRequestURI().toString();
            requests.add(target);
            methods.add(exchange.getRequestMethod());
            lastAuthorization = exchange.getRequestHeaders().getFirst("Authorization");
            int status = statuses.getOrDefault(target, 200);
            String body = bodies.getOrDefault(target, "{\"error\":\"not scripted\"}");
            if (!bodies.containsKey(target) && status == 200) {
                status = 404;
            }
            if (status == 200 && failuresLeft.getAndUpdate(left -> Math.max(0, left - 1)) > 0) {
                status = 503;
            }
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(status, bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
        });
        server.start();
    }

    @AfterEach
    void stopApi() {
        server.stop(0);
    }

    private String listsPath(String after) {
        return "/v1/workspace/collections?limit=100&sort=recent" + (after == null ? "" : "&after=" + after);
    }

    private Map<String, String> settings() {
        Map<String, String> settings = new HashMap<>();
        settings.put(SpecStreamSourceConfig.API_KEY, KEY);
        settings.put(SpecStreamSourceConfig.API_URL, "http://127.0.0.1:" + server.getAddress().getPort() + "/");
        settings.put(SpecStreamSourceConfig.POLL_INTERVAL_MS, "60000");
        return settings;
    }

    private SpecStreamSourceTask task(Map<String, Object> storedOffset) {
        SpecStreamSourceTask task = new SpecStreamSourceTask() {
            @Override
            SpecStreamClient newClient(SpecStreamSourceConfig settings) {
                return new SpecStreamClient(settings.apiUrl(), settings.apiKey(), 1L);
            }
        };
        task.initialize(new FakeContext(storedOffset));
        task.start(settings());
        return task;
    }

    private static List<SourceRecord> onTopic(List<SourceRecord> records, String topic) {
        List<SourceRecord> matching = new ArrayList<>();
        for (SourceRecord record : records) {
            if (record.topic().equals(topic)) {
                matching.add(record);
            }
        }
        return matching;
    }

    @Test
    void firstPollsReadEveryListOldestFirstAcrossPages() throws Exception {
        bodies.put(listsPath(null), "{\"data\":{\"collections\":["
            + "{\"id\":\"col_b\",\"name\":\"Imported\",\"imported\":true,\"created_at\":\"2026-11-02T00:00:00Z\"}],"
            + "\"next_after\":\"cur 1\"}}");
        bodies.put(listsPath("cur+1"), "{\"data\":{\"collections\":["
            + "{\"id\":\"col_a\",\"name\":\"Found\",\"project_id\":\"p1\",\"created_at\":\"2026-11-01T00:00:00Z\"}],"
            + "\"next_after\":null}}");
        bodies.put("/v1/workspace/collections/col_a", FOUND_LIST);
        bodies.put("/v1/workspace/collections/col_b", IMPORTED_LIST);
        SpecStreamSourceTask task = task(null);

        List<SourceRecord> first = task.poll();
        List<SourceRecord> second = task.poll();

        assertEquals("Bearer " + KEY, lastAuthorization);
        assertEquals(Collections.singletonList("GET"), new ArrayList<>(new java.util.HashSet<>(methods)));

        // The older list comes first: three values (the button column is left out), one record, then the list.
        assertEquals(5, first.size());
        List<SourceRecord> values = onTopic(first, "specstream.record_value");
        assertEquals(3, values.size());
        Struct employees = (Struct) values.get(1).value();
        assertEquals("col_a/1/employees", values.get(1).key());
        assertEquals("120", employees.getString("value"));
        assertEquals("120", employees.getString("raw_value"));
        assertEquals("https://acme.example/team", employees.getString("source_url"));
        assertEquals("2026-11-01T10:00:01Z", employees.getString("observed_at"));
        Struct phone = (Struct) values.get(2).value();
        assertNull(phone.getString("value"));
        assertNull(phone.getString("raw_value"));

        Struct record = (Struct) onTopic(first, "specstream.record").get(0).value();
        assertEquals("1", record.getString("record_id"));
        assertEquals("ent_1", record.getString("entity_id"));
        assertEquals("{\"Name\":\"Acme\",\"Employees\":\"120\",\"Phone\":null}", record.getString("values"));
        assertEquals(List.of("https://acme.example/about", "https://acme.example/team"), record.getArray("sources"));

        SourceRecord list = first.get(first.size() - 1);
        assertEquals("specstream.list", list.topic());
        assertEquals("col_a", list.key());
        Struct listValue = (Struct) list.value();
        assertEquals("Found", listValue.getString("name"));
        assertEquals("p1", listValue.getString("project_id"));
        assertFalse(listValue.getBoolean("imported"));
        assertEquals(1, listValue.getInt32("row_count"));

        // Only the list's own row moves the offset, so a list cut off by a restart is read again.
        for (SourceRecord earlier : first.subList(0, first.size() - 1)) {
            assertEquals("", earlier.sourceOffset().get(SpecStreamSourceTask.OFFSET_KEY));
        }
        assertEquals("2026-11-01T00:00:00Z", list.sourceOffset().get(SpecStreamSourceTask.OFFSET_KEY));

        // The imported list: the columns the user provided.
        assertEquals(4, second.size());
        Struct imported = (Struct) onTopic(second, "specstream.record").get(0).value();
        assertEquals("row_9", imported.getString("record_id"));
        assertNull(imported.getString("entity_id"));
        assertEquals("{\"Company\":\"Globex\",\"Size\":40}", imported.getString("values"));
        Struct size = (Struct) onTopic(second, "specstream.record_value").get(1).value();
        assertEquals("40", size.getString("value"));
        assertNull(size.getString("source_url"));
        assertTrue(((Struct) second.get(3).value()).getBoolean("imported"));
        assertEquals("2026-11-01T00:00:00Z", second.get(0).sourceOffset().get(SpecStreamSourceTask.OFFSET_KEY));
        assertEquals("2026-11-02T00:00:00Z", second.get(3).sourceOffset().get(SpecStreamSourceTask.OFFSET_KEY));

        // Nothing new: the task waits for the poll interval and does not call the API again.
        int callsBefore = requests.size();
        task.stop();
        assertNull(task.poll());
        assertEquals(callsBefore, requests.size());
    }

    @Test
    void aRestartReadsOnlyListsCreatedAfterTheStoredOffset() throws Exception {
        bodies.put(listsPath(null), "{\"data\":{\"collections\":["
            + "{\"id\":\"col_c\",\"created_at\":\"2026-11-03T00:00:00Z\"},"
            + "{\"id\":\"col_b\",\"created_at\":\"2026-11-02T00:00:00Z\"},"
            + "{\"id\":\"col_a\",\"created_at\":\"2026-11-01T00:00:00Z\"}],\"next_after\":\"more\"}}");
        bodies.put("/v1/workspace/collections/col_c", COMBINED_LIST);
        SpecStreamSourceTask task = task(
            Collections.singletonMap(SpecStreamSourceTask.OFFSET_KEY, "2026-11-02T00:00:00Z"));

        List<SourceRecord> records = task.poll();

        // The paging stops at the first list that was already read, so the next page is never asked for.
        assertEquals(List.of(listsPath(null), "/v1/workspace/collections/col_c"), requests);
        assertEquals(3, records.size());
        Struct record = (Struct) onTopic(records, "specstream.record").get(0).value();
        assertEquals("m_1", record.getString("record_id"));
        assertEquals("ent_7", record.getString("entity_id"));
        assertEquals("{\"Name\":\"Initech\"}", record.getString("values"));
        assertEquals(List.of("https://initech.example"), record.getArray("sources"));
        assertEquals("2026-11-02T00:00:00Z", records.get(0).sourceOffset().get(SpecStreamSourceTask.OFFSET_KEY));
        assertEquals("2026-11-03T00:00:00Z", records.get(2).sourceOffset().get(SpecStreamSourceTask.OFFSET_KEY));
        task.stop();
        assertNull(task.poll());
    }

    @Test
    void aServerErrorIsTriedAgainAndAListThatFailsStaysQueued() throws Exception {
        bodies.put(listsPath(null), "{\"data\":{\"collections\":["
            + "{\"id\":\"col_a\",\"created_at\":\"2026-11-01T00:00:00Z\"}]}}");
        bodies.put("/v1/workspace/collections/col_a", FOUND_LIST);
        SpecStreamSourceTask task = task(null);

        // The lists call fails twice and then answers; the list itself keeps failing, so the poll gives up for now.
        failuresLeft.set(2);
        statuses.put("/v1/workspace/collections/col_a", 500);
        assertThrows(RetriableException.class, task::poll);
        assertEquals(1 + 2 + 5, requests.size());

        // The list is still queued: the next poll reads it without asking for the lists again.
        statuses.remove("/v1/workspace/collections/col_a");
        List<SourceRecord> records = task.poll();
        assertEquals(5, records.size());
        assertEquals(1 + 2 + 5 + 1, requests.size());
    }

    @Test
    void aRefusedKeyFailsAtOnceWithoutTheKeyInTheMessage() {
        statuses.put(listsPath(null), 401);
        SpecStreamSourceTask task = task(null);

        ConnectException error = assertThrows(ConnectException.class, task::poll);

        assertFalse(error instanceof RetriableException);
        assertTrue(error.getMessage().contains("refused the API key"));
        assertFalse(error.getMessage().contains(KEY));
        assertEquals(1, requests.size());
    }

    @Test
    void theConnectorRefusesAMissingKeyAndHandsItsSettingsToOneTask() {
        SpecStreamSourceConnector connector = new SpecStreamSourceConnector();
        Map<String, String> missing = settings();
        missing.put(SpecStreamSourceConfig.API_KEY, "<YOUR_SPECSTREAM_API_KEY>");
        assertThrows(ConfigException.class, () -> connector.start(missing));
        Map<String, String> badUrl = settings();
        badUrl.put(SpecStreamSourceConfig.API_URL, "ftp://example");
        assertThrows(ConfigException.class, () -> connector.start(badUrl));

        connector.start(settings());
        assertEquals(SpecStreamSourceTask.class, connector.taskClass());
        assertEquals(Collections.singletonList(settings()), connector.taskConfigs(4));
        assertEquals("1.0.0", connector.version());

        SpecStreamSourceConfig config = new SpecStreamSourceConfig(settings());
        assertEquals("specstream.record_value", config.recordValueTopic());
        assertFalse(config.apiUrl().endsWith("/"));
        assertFalse(config.toString().contains(KEY));
        assertFalse(config.values().toString().contains(KEY));
    }

    private static final class FakeContext implements SourceTaskContext {
        private final Map<String, Object> offset;

        FakeContext(Map<String, Object> offset) {
            this.offset = offset;
        }

        @Override
        public Map<String, String> configs() {
            return Collections.emptyMap();
        }

        @Override
        public OffsetStorageReader offsetStorageReader() {
            return new OffsetStorageReader() {
                @Override
                public <T> Map<String, Object> offset(Map<String, T> partition) {
                    return offset;
                }

                @Override
                public <T> Map<Map<String, T>, Map<String, Object>> offsets(Collection<Map<String, T>> partitions) {
                    return Collections.emptyMap();
                }
            };
        }
    }
}
