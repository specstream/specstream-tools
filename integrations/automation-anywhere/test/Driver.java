import ai.specstream.automationanywhere.SpecStream;
import java.util.Map;

/**
 * Runs one call of the package's client against the address a test gives it and prints the result,
 * one "name=value" line per value. tests/distribution/test_automation_anywhere_package.py starts it.
 */
public final class Driver {
  public static void main(String[] args) {
    String base = args[0];
    String key = args[1];
    try {
      if ("search".equals(args[2])) {
        Map<String, String> found = new SpecStream(base, key).search(args[3], "fast".equals(args[4]));
        System.out.println("answer=" + found.get("answer"));
        System.out.println("json=" + found.get("json"));
      } else {
        System.out.println("text=" + new SpecStream(base, key).read(args[3]));
      }
    } catch (IllegalArgumentException | IllegalStateException error) {
      System.out.println("error=" + error.getMessage());
    }
  }
}
