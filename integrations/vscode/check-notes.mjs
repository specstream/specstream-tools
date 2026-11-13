// Stops a release whose notes do not name the Deep Search command.
//
//   node check-notes.mjs [folder]
//
// The Marketplace and Open VSX show CHANGELOG.md as the notes of a version. Each version's entry must exist
// and must name Deep Search with its chat command, so a reader of the notes always sees how to start it.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const COMMAND = "`@specstream /find`";
const folder = process.argv[2] ?? dirname(fileURLToPath(import.meta.url));
const { version } = JSON.parse(readFileSync(join(folder, "package.json"), "utf8"));
const sections = readFileSync(join(folder, "CHANGELOG.md"), "utf8").split(/^## /m).slice(1);
const entry = sections.find((section) => section.split("\n", 1)[0].trim() === version);

function stop(message) {
  console.error(`check-notes: ${message}`);
  process.exit(1);
}

if (entry === undefined) stop(`CHANGELOG.md has no "## ${version}" entry for the version in package.json.`);
if (sections[0] !== entry) stop(`the "## ${version}" entry must be the first entry of CHANGELOG.md.`);
if (!entry.includes("Deep Search") || !entry.includes(COMMAND)) {
  stop(`the "## ${version}" entry must name Deep Search and its command ${COMMAND}.`);
}
console.log(`check-notes: the notes of ${version} name Deep Search and ${COMMAND}.`);
