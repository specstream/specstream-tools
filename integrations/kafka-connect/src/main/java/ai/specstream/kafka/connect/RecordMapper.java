package ai.specstream.kafka.connect;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.apache.kafka.connect.data.Schema;
import org.apache.kafka.connect.data.SchemaBuilder;
import org.apache.kafka.connect.data.Struct;

/** Turns one SpecStream list, as the API returns it, into the rows of the three topics. */
final class RecordMapper {
    static final Schema LIST_SCHEMA = SchemaBuilder.struct().name("ai.specstream.List").version(1)
        .field("id", Schema.STRING_SCHEMA)
        .field("name", Schema.OPTIONAL_STRING_SCHEMA)
        .field("project_id", Schema.OPTIONAL_STRING_SCHEMA)
        .field("imported", Schema.BOOLEAN_SCHEMA)
        .field("created_at", Schema.OPTIONAL_STRING_SCHEMA)
        .field("row_count", Schema.INT32_SCHEMA)
        .build();

    static final Schema RECORD_SCHEMA = SchemaBuilder.struct().name("ai.specstream.Record").version(1)
        .field("list_id", Schema.STRING_SCHEMA)
        .field("record_id", Schema.STRING_SCHEMA)
        .field("entity_id", Schema.OPTIONAL_STRING_SCHEMA)
        .field("values", SchemaBuilder.string().doc("A JSON object of label to value.").build())
        .field("sources", SchemaBuilder.array(Schema.STRING_SCHEMA).doc("The pages the values were read from.").build())
        .build();

    static final Schema RECORD_VALUE_SCHEMA = SchemaBuilder.struct().name("ai.specstream.RecordValue").version(1)
        .field("list_id", Schema.STRING_SCHEMA)
        .field("record_id", Schema.STRING_SCHEMA)
        .field("column_id", Schema.STRING_SCHEMA)
        .field("label", Schema.OPTIONAL_STRING_SCHEMA)
        .field("value", Schema.OPTIONAL_STRING_SCHEMA)
        .field("raw_value", SchemaBuilder.string().optional().doc("The value as JSON.").build())
        .field("source_url", Schema.OPTIONAL_STRING_SCHEMA)
        .field("observed_at", Schema.OPTIONAL_STRING_SCHEMA)
        .build();

    /** Columns the SpecStream workspace shows as buttons, not facts. */
    private static final Set<String> BUTTON_COLUMNS = Set.of("matches", "open");

    private RecordMapper() {
    }

    /** The rows of one list: its records and their values. */
    static final class Rows {
        final List<Struct> records = new ArrayList<>();
        final List<Struct> values = new ArrayList<>();
    }

    static Struct list(JsonNode summary, int rowCount) {
        return new Struct(LIST_SCHEMA)
            .put("id", summary.path("id").asText())
            .put("name", text(summary.get("name")))
            .put("project_id", text(summary.get("project_id")))
            .put("imported", summary.path("imported").asBoolean(false))
            .put("created_at", text(summary.get("created_at")))
            .put("row_count", rowCount);
    }

    static Rows rows(String listId, JsonNode detail) {
        Rows rows = new Rows();
        for (JsonNode row : detail.path("rows")) {
            if (row.has("provided")) {
                imported(listId, row, rows);
            } else {
                found(listId, row, rows);
            }
        }
        return rows;
    }

    /** A record SpecStream found: each cell carries the page its value came from. */
    private static void found(String listId, JsonNode row, Rows rows) {
        boolean combined = row.has("field_values");
        String recordId = combined ? row.path("id").asText() : row.path("ordinal").asText();
        String entityId = combined ? combinedEntityId(row) : text(row.get("entity_id"));
        ObjectNode values = JsonNodeFactory.instance.objectNode();
        List<String> sources = new ArrayList<>();
        for (JsonNode cell : combined ? combinedCells(row) : row.path("cells")) {
            String columnId = text(cell.get("column_id"));
            if (columnId == null || columnId.isEmpty() || BUTTON_COLUMNS.contains(columnId)) {
                continue;
            }
            // A value SpecStream could not read is written as null.
            boolean missing = truthy(cell.get("absence"));
            JsonNode provenance = cell.path("provenance");
            String sourceUrl = text(provenance.get("source_url"));
            String label = text(cell.get("label"));
            if (label == null || label.isEmpty()) {
                label = columnId;
            }
            String display = missing ? null : text(cell.get("display"));
            values.put(values.has(label) ? columnId : label, display);
            if (sourceUrl != null && !sourceUrl.isEmpty() && !sources.contains(sourceUrl)) {
                sources.add(sourceUrl);
            }
            rows.values.add(new Struct(RECORD_VALUE_SCHEMA)
                .put("list_id", listId)
                .put("record_id", recordId)
                .put("column_id", columnId)
                .put("label", label)
                .put("value", display)
                .put("raw_value", missing ? null : json(cell.get("value")))
                .put("source_url", sourceUrl)
                .put("observed_at", text(provenance.get("observed_at"))));
        }
        rows.records.add(new Struct(RECORD_SCHEMA)
            .put("list_id", listId)
            .put("record_id", recordId)
            .put("entity_id", entityId)
            .put("values", values.toString())
            .put("sources", sources));
    }

    /** A list made by combining lists keeps each column's values under field_values, the shown value first. */
    private static List<JsonNode> combinedCells(JsonNode row) {
        List<JsonNode> cells = new ArrayList<>();
        Iterator<Map.Entry<String, JsonNode>> fields = row.path("field_values").fields();
        while (fields.hasNext()) {
            Map.Entry<String, JsonNode> field = fields.next();
            JsonNode shown = field.getValue().path(0);
            if (!shown.isObject()) {
                continue;
            }
            ObjectNode cell = JsonNodeFactory.instance.objectNode();
            cell.put("column_id", field.getKey());
            for (String name : new String[] {"label", "value", "display", "absence", "provenance"}) {
                cell.set(name, shown.get(name));
            }
            cells.add(cell);
        }
        return cells;
    }

    private static String combinedEntityId(JsonNode row) {
        for (JsonNode source : row.path("sources")) {
            String entityId = text(source.path("row").get("entity_id"));
            if (entityId != null && !entityId.isEmpty()) {
                return entityId;
            }
        }
        return null;
    }

    /** A row of a list the user imported, with the columns the user provided. */
    private static void imported(String listId, JsonNode row, Rows rows) {
        String recordId = row.path("id").asText();
        JsonNode provided = row.path("provided");
        Iterator<Map.Entry<String, JsonNode>> fields = provided.fields();
        while (fields.hasNext()) {
            Map.Entry<String, JsonNode> field = fields.next();
            JsonNode value = field.getValue();
            rows.values.add(new Struct(RECORD_VALUE_SCHEMA)
                .put("list_id", listId)
                .put("record_id", recordId)
                .put("column_id", field.getKey())
                .put("label", field.getKey())
                .put("value", text(value))
                .put("raw_value", json(value))
                .put("source_url", null)
                .put("observed_at", null));
        }
        rows.records.add(new Struct(RECORD_SCHEMA)
            .put("list_id", listId)
            .put("record_id", recordId)
            .put("entity_id", null)
            .put("values", provided.isObject() ? provided.toString() : "{}")
            .put("sources", new ArrayList<String>()));
    }

    private static boolean truthy(JsonNode node) {
        if (node == null || node.isNull() || node.isMissingNode()) {
            return false;
        }
        if (node.isBoolean()) {
            return node.asBoolean();
        }
        if (node.isTextual()) {
            return !node.asText().isEmpty();
        }
        if (node.isNumber()) {
            return node.asDouble() != 0;
        }
        return node.size() > 0;
    }

    private static String text(JsonNode node) {
        if (node == null || node.isNull() || node.isMissingNode()) {
            return null;
        }
        return node.isValueNode() ? node.asText() : node.toString();
    }

    private static String json(JsonNode node) {
        return node == null || node.isNull() || node.isMissingNode() ? null : node.toString();
    }
}
