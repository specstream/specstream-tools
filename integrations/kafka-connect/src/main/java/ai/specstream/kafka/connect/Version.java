package ai.specstream.kafka.connect;

import java.io.InputStream;
import java.util.Properties;

/** The connector's version, read from the properties file Maven fills in at build time. */
final class Version {
    private static final String VERSION = read();

    private Version() {
    }

    static String get() {
        return VERSION;
    }

    private static String read() {
        try (InputStream stream = Version.class.getResourceAsStream("/kafka-connect-specstream-version.properties")) {
            if (stream == null) {
                return "unknown";
            }
            Properties properties = new Properties();
            properties.load(stream);
            return properties.getProperty("version", "unknown").trim();
        } catch (Exception error) {
            return "unknown";
        }
    }
}
