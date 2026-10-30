// Bundles the extension the way `block release` does, so a broken import or JSX error fails
// here before a release. The released bundle itself is built and uploaded by the Airtable CLI.
import { build } from "esbuild";

const result = await build({
	entryPoints: ["frontend/index.tsx"],
	bundle: true,
	minify: true,
	format: "iife",
	platform: "browser",
	target: ["es2020"],
	jsx: "transform",
	outfile: "build/bundle.js",
	metafile: true,
	logLevel: "warning",
});
const bytes = Object.values(result.metafile.outputs).reduce((sum, output) => sum + output.bytes, 0);
console.log(`build/bundle.js ${(bytes / 1024).toFixed(0)} KB`);
