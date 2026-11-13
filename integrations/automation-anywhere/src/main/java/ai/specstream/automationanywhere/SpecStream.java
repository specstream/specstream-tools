package ai.specstream.automationanywhere;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * The calls to the SpecStream API behind the two actions. It uses only the JDK, so it compiles and
 * runs without the Automation Anywhere SDK and its tests need no Control Room.
 */
public final class SpecStream {
  public static final String API = "https://api.specstream.ai";
  static final String USER_AGENT = "specstream-automation-anywhere/1.0.0";

  private final String base;
  private final String key;
  private final HttpClient http =
      HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(15)).build();

  public SpecStream(String apiKey) {
    this(API, apiKey);
  }

  /** A second base address is for tests only: a bot always calls {@link #API}. */
  public SpecStream(String base, String apiKey) {
    String cleaned = apiKey == null ? "" : apiKey.trim();
    if (cleaned.isEmpty()) {
      throw new IllegalArgumentException(
          "Enter a SpecStream API key. Create one at https://specstream.ai/workspace/agents?tab=keys");
    }
    this.base = base;
    this.key = cleaned;
  }

  /** Search API. Returns "answer" (the answer, or the first result's name) and "json" (the whole reply). */
  public Map<String, String> search(String question, boolean fast) {
    String q = question == null ? "" : question.trim();
    if (q.isEmpty() || q.length() > 2000) {
      throw new IllegalArgumentException("Write the question in 1 to 2,000 characters.");
    }
    String path = "/v1/web-search?q=" + URLEncoder.encode(q, StandardCharsets.UTF_8);
    if (fast) {
      path += "&speed=fast";
    }
    String data = send(HttpRequest.newBuilder(URI.create(base + path)).GET());
    Map<String, String> out = new LinkedHashMap<>();
    out.put("answer", answerOf(Json.parse(data)));
    out.put("json", data);
    return out;
  }

  /** Extract API. Returns the text of one page, PDF, Word or Excel file as Markdown. */
  public String read(String url) {
    String cleaned = url == null ? "" : url.trim();
    if (!cleaned.startsWith("http://") && !cleaned.startsWith("https://")) {
      throw new IllegalArgumentException("Enter an http or https URL to read.");
    }
    String body = "{\"urls\":[" + Json.quote(cleaned) + "],\"format\":\"markdown\"}";
    String data =
        send(
            HttpRequest.newBuilder(URI.create(base + "/v1/extract"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8)));
    Object results = field(Json.parse(data), "results");
    if (results instanceof List && !((List<?>) results).isEmpty()) {
      Object text = field(((List<?>) results).get(0), "text");
      return text == null ? "" : Json.text(text);
    }
    return "";
  }

  static String answerOf(Object data) {
    Object value = field(field(data, "answer"), "value");
    if (value != null && !String.valueOf(value).isEmpty()) {
      return Json.text(value);
    }
    Object rows = field(data, "rows");
    if (rows instanceof List && !((List<?>) rows).isEmpty()) {
      Object name = field(((List<?>) rows).get(0), "name");
      return name == null ? "" : Json.text(name);
    }
    return "";
  }

  /** Sends one call and returns the JSON text of the reply's "data" member. */
  private String send(HttpRequest.Builder request) {
    HttpResponse<String> response;
    try {
      response =
          http.send(
              request
                  .timeout(Duration.ofSeconds(120))
                  .header("Authorization", "Bearer " + key)
                  .header("Accept", "application/json")
                  .header("User-Agent", USER_AGENT)
                  .build(),
              HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    } catch (IOException error) {
      throw new IllegalStateException("SpecStream did not answer: " + error.getMessage(), error);
    } catch (InterruptedException error) {
      Thread.currentThread().interrupt();
      throw new IllegalStateException("The call to SpecStream was interrupted.", error);
    }
    int status = response.statusCode();
    Object parsed;
    try {
      parsed = Json.parse(response.body());
    } catch (IllegalArgumentException error) {
      throw new IllegalStateException("SpecStream answered HTTP " + status + " without JSON.");
    }
    if (status < 200 || status > 299) {
      Object message = field(field(parsed, "error"), "message");
      throw new IllegalStateException(
          message == null ? "SpecStream answered HTTP " + status + "." : String.valueOf(message));
    }
    return Json.write(field(parsed, "data"));
  }

  private static Object field(Object object, String name) {
    return object instanceof Map ? ((Map<?, ?>) object).get(name) : null;
  }

  /** A small JSON reader and writer, so the package ships no library of its own. */
  static final class Json {
    private final String s;
    private int i;

    private Json(String s) {
      this.s = s;
    }

    static Object parse(String text) {
      Json json = new Json(text == null ? "" : text);
      Object value = json.value();
      json.space();
      if (json.i != json.s.length()) {
        throw new IllegalArgumentException("Unexpected text after JSON at " + json.i);
      }
      return value;
    }

    /** A value as a person reads it: text without quotes, a whole number without ".0". */
    static String text(Object value) {
      return value instanceof String ? (String) value : write(value);
    }

    static String write(Object value) {
      StringBuilder out = new StringBuilder();
      write(value, out);
      return out.toString();
    }

    private static void write(Object value, StringBuilder out) {
      if (value instanceof String) {
        out.append(quote((String) value));
      } else if (value instanceof Double) {
        double d = (Double) value;
        if (d == Math.rint(d) && Math.abs(d) < 1e15) {
          out.append((long) d);
        } else {
          out.append(d);
        }
      } else if (value instanceof Map) {
        out.append('{');
        boolean first = true;
        for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) {
          if (!first) {
            out.append(',');
          }
          first = false;
          out.append(quote(String.valueOf(entry.getKey()))).append(':');
          write(entry.getValue(), out);
        }
        out.append('}');
      } else if (value instanceof List) {
        out.append('[');
        boolean first = true;
        for (Object item : (List<?>) value) {
          if (!first) {
            out.append(',');
          }
          first = false;
          write(item, out);
        }
        out.append(']');
      } else {
        out.append(value);
      }
    }

    static String quote(String text) {
      StringBuilder out = new StringBuilder("\"");
      for (int k = 0; k < text.length(); k++) {
        char c = text.charAt(k);
        if (c == '"' || c == '\\') {
          out.append('\\').append(c);
        } else if (c == '\n') {
          out.append("\\n");
        } else if (c == '\r') {
          out.append("\\r");
        } else if (c == '\t') {
          out.append("\\t");
        } else if (c < 0x20) {
          out.append(String.format("\\u%04x", (int) c));
        } else {
          out.append(c);
        }
      }
      return out.append('"').toString();
    }

    private void space() {
      while (i < s.length() && Character.isWhitespace(s.charAt(i))) {
        i++;
      }
    }

    private IllegalArgumentException bad() {
      return new IllegalArgumentException("Not JSON at " + i);
    }

    private Object value() {
      space();
      if (i >= s.length()) {
        throw bad();
      }
      char c = s.charAt(i);
      if (c == '{') {
        return object();
      }
      if (c == '[') {
        return array();
      }
      if (c == '"') {
        return string();
      }
      if (s.startsWith("true", i)) {
        i += 4;
        return Boolean.TRUE;
      }
      if (s.startsWith("false", i)) {
        i += 5;
        return Boolean.FALSE;
      }
      if (s.startsWith("null", i)) {
        i += 4;
        return null;
      }
      int start = i;
      while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) {
        i++;
      }
      try {
        return Double.valueOf(s.substring(start, i));
      } catch (NumberFormatException error) {
        throw bad();
      }
    }

    private Map<String, Object> object() {
      Map<String, Object> map = new LinkedHashMap<>();
      i++;
      space();
      if (i < s.length() && s.charAt(i) == '}') {
        i++;
        return map;
      }
      while (true) {
        space();
        if (i >= s.length() || s.charAt(i) != '"') {
          throw bad();
        }
        String name = string();
        space();
        if (i >= s.length() || s.charAt(i++) != ':') {
          throw bad();
        }
        map.put(name, value());
        space();
        if (i >= s.length()) {
          throw bad();
        }
        char c = s.charAt(i++);
        if (c == '}') {
          return map;
        }
        if (c != ',') {
          throw bad();
        }
      }
    }

    private List<Object> array() {
      List<Object> list = new ArrayList<>();
      i++;
      space();
      if (i < s.length() && s.charAt(i) == ']') {
        i++;
        return list;
      }
      while (true) {
        list.add(value());
        space();
        if (i >= s.length()) {
          throw bad();
        }
        char c = s.charAt(i++);
        if (c == ']') {
          return list;
        }
        if (c != ',') {
          throw bad();
        }
      }
    }

    private String string() {
      StringBuilder out = new StringBuilder();
      i++;
      while (true) {
        if (i >= s.length()) {
          throw bad();
        }
        char c = s.charAt(i++);
        if (c == '"') {
          return out.toString();
        }
        if (c != '\\') {
          out.append(c);
          continue;
        }
        if (i >= s.length()) {
          throw bad();
        }
        char e = s.charAt(i++);
        switch (e) {
          case 'n':
            out.append('\n');
            break;
          case 't':
            out.append('\t');
            break;
          case 'r':
            out.append('\r');
            break;
          case 'b':
            out.append('\b');
            break;
          case 'f':
            out.append('\f');
            break;
          case 'u':
            if (i + 4 > s.length()) {
              throw bad();
            }
            try {
              out.append((char) Integer.parseInt(s.substring(i, i + 4), 16));
            } catch (NumberFormatException error) {
              throw bad();
            }
            i += 4;
            break;
          default:
            out.append(e);
        }
      }
    }
  }
}
