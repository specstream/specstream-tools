package ai.specstream.kafka.connect;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import org.apache.kafka.connect.errors.ConnectException;
import org.apache.kafka.connect.errors.RetriableException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Reads lists from the SpecStream API. It sends only GET requests. */
class SpecStreamClient {
    private static final Logger log = LoggerFactory.getLogger(SpecStreamClient.class);
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final int LISTS_PAGE_SIZE = 100;
    private static final int MAX_ATTEMPTS = 5;
    private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(60);
    private static final long MAX_RETRY_DELAY_MS = 60_000L;

    private final String baseUrl;
    private final String apiKey;
    private final long retryBaseDelayMs;
    private final HttpClient http;

    SpecStreamClient(String baseUrl, String apiKey) {
        this(baseUrl, apiKey, 2_000L);
    }

    SpecStreamClient(String baseUrl, String apiKey, long retryBaseDelayMs) {
        this.baseUrl = baseUrl;
        this.apiKey = apiKey;
        this.retryBaseDelayMs = retryBaseDelayMs;
        this.http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(20)).build();
    }

    /**
     * The summaries of the lists created after {@code syncedThrough}, oldest first.
     * The API answers newest first, so paging stops at the first list that was already read.
     */
    List<JsonNode> listsCreatedAfter(String syncedThrough) throws InterruptedException {
        List<JsonNode> lists = new ArrayList<>();
        String after = null;
        paging:
        while (true) {
            String path = "/v1/workspace/collections?limit=" + LISTS_PAGE_SIZE + "&sort=recent";
            if (after != null) {
                path += "&after=" + URLEncoder.encode(after, StandardCharsets.UTF_8);
            }
            JsonNode page = get(path);
            for (JsonNode summary : page.path("collections")) {
                String createdAt = summary.path("created_at").asText("");
                if (syncedThrough != null && !syncedThrough.isEmpty() && createdAt.compareTo(syncedThrough) <= 0) {
                    break paging;
                }
                lists.add(summary);
            }
            JsonNode next = page.path("next_after");
            if (next.isMissingNode() || next.isNull() || next.asText().isEmpty()) {
                break;
            }
            after = next.asText();
        }
        lists.sort(Comparator.comparing(summary -> summary.path("created_at").asText("")));
        return lists;
    }

    /** One list with its records. */
    JsonNode list(String listId) throws InterruptedException {
        return get("/v1/workspace/collections/" + URLEncoder.encode(listId, StandardCharsets.UTF_8));
    }

    /**
     * Calls the API and returns the {@code data} object of its answer. A rate limit or a server error is tried
     * again with a growing wait. A refused key fails at once, because another try cannot fix it.
     */
    JsonNode get(String path) throws InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(URI.create(baseUrl + path))
            .timeout(REQUEST_TIMEOUT)
            .header("Authorization", "Bearer " + apiKey)
            .header("Accept", "application/json")
            .header("User-Agent", "kafka-connect-specstream/" + Version.get())
            .GET()
            .build();
        String lastProblem = "no answer";
        for (int attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
            long delayMs = Math.min(MAX_RETRY_DELAY_MS, retryBaseDelayMs << attempt);
            try {
                HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
                int status = response.statusCode();
                if (status == 401 || status == 403) {
                    throw new ConnectException("SpecStream refused the API key. Create a key under Agents & API "
                        + "in SpecStream and update " + SpecStreamSourceConfig.API_KEY + ".");
                }
                if (status == 429 || status >= 500) {
                    lastProblem = "status " + status;
                    String retryAfter = response.headers().firstValue("Retry-After").orElse("");
                    if (retryAfter.matches("\\d{1,4}")) {
                        delayMs = Math.min(MAX_RETRY_DELAY_MS, Long.parseLong(retryAfter) * 1_000L);
                    }
                } else if (status >= 400) {
                    throw new ConnectException("SpecStream answered " + status + " for " + pathOnly(path) + ".");
                } else {
                    JsonNode data = JSON.readTree(response.body()).path("data");
                    if (!data.isObject()) {
                        throw new ConnectException(
                            "SpecStream's answer for " + pathOnly(path) + " has no data object.");
                    }
                    return data;
                }
            } catch (IOException error) {
                lastProblem = error.getClass().getSimpleName() + ": " + error.getMessage();
            }
            if (attempt < MAX_ATTEMPTS - 1) {
                log.warn("SpecStream did not answer {} ({}); the next try is in {} ms",
                    pathOnly(path), lastProblem, delayMs);
                Thread.sleep(delayMs);
            }
        }
        // The worker calls poll() again, so the read continues when SpecStream answers again.
        throw new RetriableException("SpecStream did not answer " + pathOnly(path) + " (" + lastProblem + ").");
    }

    private static String pathOnly(String path) {
        int query = path.indexOf('?');
        return query < 0 ? path : path.substring(0, query);
    }
}
