package ai.specstream.kafka.connect;

import java.util.Map;
import org.apache.kafka.common.config.AbstractConfig;
import org.apache.kafka.common.config.ConfigDef;
import org.apache.kafka.common.config.ConfigDef.Importance;
import org.apache.kafka.common.config.ConfigDef.Type;
import org.apache.kafka.common.config.ConfigDef.Width;
import org.apache.kafka.common.config.ConfigException;
import org.apache.kafka.common.config.types.Password;

/** The settings of the SpecStream source connector. */
public class SpecStreamSourceConfig extends AbstractConfig {
    public static final String API_KEY = "specstream.api.key";
    public static final String API_URL = "specstream.api.url";
    public static final String TOPIC_PREFIX = "topic.prefix";
    public static final String POLL_INTERVAL_MS = "poll.interval.ms";

    public static final String DEFAULT_API_URL = "https://api.specstream.ai";
    public static final String DEFAULT_TOPIC_PREFIX = "specstream.";
    public static final long DEFAULT_POLL_INTERVAL_MS = 300_000L;

    private static final String GROUP_CONNECTION = "SpecStream";
    private static final String GROUP_TOPICS = "Topics";

    public static final ConfigDef CONFIG_DEF = new ConfigDef()
        .define(API_KEY, Type.PASSWORD, ConfigDef.NO_DEFAULT_VALUE, new ApiKeyValidator(), Importance.HIGH,
            "A SpecStream API key. Create one in SpecStream under Agents & API. The connector only reads, "
                + "so the key can have a spending limit of $0.",
            GROUP_CONNECTION, 1, Width.LONG, "SpecStream API key")
        .define(API_URL, Type.STRING, DEFAULT_API_URL, new ApiUrlValidator(), Importance.LOW,
            "The address of the SpecStream API.",
            GROUP_CONNECTION, 2, Width.LONG, "SpecStream API address")
        .define(POLL_INTERVAL_MS, Type.LONG, DEFAULT_POLL_INTERVAL_MS, ConfigDef.Range.atLeast(1_000L),
            Importance.MEDIUM,
            "How long the connector waits, in milliseconds, before it asks SpecStream for new lists again.",
            GROUP_CONNECTION, 3, Width.SHORT, "Poll interval (ms)")
        .define(TOPIC_PREFIX, Type.STRING, DEFAULT_TOPIC_PREFIX, Importance.HIGH,
            "The prefix of the three topics the connector writes: <prefix>list, <prefix>record and "
                + "<prefix>record_value.",
            GROUP_TOPICS, 1, Width.MEDIUM, "Topic prefix");

    public SpecStreamSourceConfig(Map<?, ?> originals) {
        super(CONFIG_DEF, originals);
    }

    public String apiKey() {
        return getPassword(API_KEY).value().trim();
    }

    public String apiUrl() {
        String url = getString(API_URL).trim();
        return url.endsWith("/") ? url.substring(0, url.length() - 1) : url;
    }

    public long pollIntervalMs() {
        return getLong(POLL_INTERVAL_MS);
    }

    public String listTopic() {
        return getString(TOPIC_PREFIX) + "list";
    }

    public String recordTopic() {
        return getString(TOPIC_PREFIX) + "record";
    }

    public String recordValueTopic() {
        return getString(TOPIC_PREFIX) + "record_value";
    }

    private static final class ApiKeyValidator implements ConfigDef.Validator {
        @Override
        public void ensureValid(String name, Object value) {
            String key = value instanceof Password ? ((Password) value).value() : null;
            if (key == null || key.trim().isEmpty() || key.trim().startsWith("<")) {
                throw new ConfigException(name, "[hidden]",
                    "A SpecStream API key is required. Create one in SpecStream under Agents & API.");
            }
        }

        @Override
        public String toString() {
            return "a SpecStream API key";
        }
    }

    private static final class ApiUrlValidator implements ConfigDef.Validator {
        @Override
        public void ensureValid(String name, Object value) {
            String url = value == null ? "" : value.toString().trim();
            if (!url.startsWith("https://") && !url.startsWith("http://")) {
                throw new ConfigException(name, value, "The address must start with https:// or http://.");
            }
        }

        @Override
        public String toString() {
            return "an http or https address";
        }
    }
}
