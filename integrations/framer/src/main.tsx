import "@framer/plugin/framer.css";
import "./App.css";

import { framer } from "@framer/plugin";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { savedSettings, syncExisting } from "./data";

const collection = await framer.getActiveManagedCollection();
const { didSync, stop } = await syncExisting(collection);

if (!didSync) {
	const settings = await savedSettings(collection);
	const root = document.getElementById("root");
	if (!root) throw new Error("Root element not found");
	createRoot(root).render(
		<StrictMode>
			<App collection={collection} settings={settings} stop={stop ?? null} />
		</StrictMode>,
	);
}
