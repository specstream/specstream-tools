package ai.specstream.kafka.connect;

import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.apache.kafka.common.config.ConfigDef;
import org.apache.kafka.connect.connector.Task;
import org.apache.kafka.connect.source.SourceConnector;

/**
 * Writes SpecStream lists to Kafka: each list, each record, and each value with the page it was read from.
 *
 * <p>The connector only reads from SpecStream. It never starts a request and never spends from the balance.
 */
public class SpecStreamSourceConnector extends SourceConnector {
    private Map<String, String> settings = Collections.emptyMap();

    @Override
    public String version() {
        return Version.get();
    }

    @Override
    public void start(Map<String, String> props) {
        // Fails here, before any task starts, when a setting is missing or wrong.
        new SpecStreamSourceConfig(props);
        settings = new HashMap<>(props);
    }

    @Override
    public Class<? extends Task> taskClass() {
        return SpecStreamSourceTask.class;
    }

    @Override
    public List<Map<String, String>> taskConfigs(int maxTasks) {
        // One task: lists are read in the order they were created, and one offset tracks them.
        return Collections.singletonList(new HashMap<>(settings));
    }

    @Override
    public void stop() {
    }

    @Override
    public ConfigDef config() {
        return SpecStreamSourceConfig.CONFIG_DEF;
    }
}
