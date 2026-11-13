// Builds the single binary: this machine's Node with bin/specstream.js inside it (a Node single executable
// application). Run it on each system the binary is for; the result is dist/specstream-<system>-<cpu>[.exe].
//   npm ci && node scripts/build-binary.js
"use strict";

const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const dist = path.join(root, "dist");
const system = { linux: "linux", darwin: "macos", win32: "windows" }[process.platform];
if (!system) throw new Error("No binary for " + process.platform);
const name = `specstream-${system}-${process.arch}${process.platform === "win32" ? ".exe" : ""}`;
const target = path.join(dist, name);
const blob = path.join(dist, "sea-prep.blob");
const config = path.join(dist, "sea-config.json");
const run = (file, args) => execFileSync(file, args, { stdio: "inherit" });

fs.rmSync(dist, { recursive: true, force: true });
fs.mkdirSync(dist);
fs.writeFileSync(
  config,
  JSON.stringify({ main: path.join(root, "bin", "specstream.js"), output: blob, disableExperimentalSEAWarning: true }),
);
run(process.execPath, ["--experimental-sea-config", config]);
fs.copyFileSync(process.execPath, target);
fs.chmodSync(target, 0o755);
// macOS refuses a changed binary that carries its old signature: take it off, and sign again after.
if (process.platform === "darwin") run("codesign", ["--remove-signature", target]);
const inject = [
  path.join(root, "node_modules", "postject", "dist", "cli.js"),
  target,
  "NODE_SEA_BLOB",
  blob,
  "--sentinel-fuse",
  "NODE_SEA_FUSE_fce680ab2cc467b6e072b8b5df1996b2",
];
if (process.platform === "darwin") inject.push("--macho-segment-name", "NODE_SEA");
run(process.execPath, inject);
if (process.platform === "darwin") run("codesign", ["--sign", "-", target]);
fs.rmSync(blob);
fs.rmSync(config);
console.log(target);
