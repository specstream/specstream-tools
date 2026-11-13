// Documentation: https://developers.netlify.com/sdk/
import { NetlifyExtension } from "@netlify/sdk";
import { buildLine } from "./lib/specstream.js";
import type { SiteConfig, TeamConfig } from "./schema/team-config.js";

const extension = new NetlifyExtension<SiteConfig, TeamConfig>();

// One log line, no network call, and never a failed build: the extension only tells the reader of the
// build log that the key is there. A team that has not connected a key sees nothing.
extension.addBuildEventHandler("onPreBuild", () => {
  const line = buildLine(process.env);
  if (line === null) {
    return;
  }
  console.log(line);
});

export { extension };
