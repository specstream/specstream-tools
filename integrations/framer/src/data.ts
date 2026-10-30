import { framer, type ManagedCollection, type ManagedCollectionFieldInput, type ManagedCollectionItemInput, type ProtectedMethod } from "@framer/plugin";
import { tableOf } from "./core/records";
import { SpecStreamClient } from "./core/specstream";
import { type FieldChoice, fieldsFor, itemsFor, keepNames, PLUGIN_KEYS, staleItems } from "./sync";

const KEY_STORAGE = "specstream.apiKey";

export const syncMethods = [
	"ManagedCollection.setFields",
	"ManagedCollection.addItems",
	"ManagedCollection.removeItems",
	"ManagedCollection.setPluginData",
] as const satisfies ProtectedMethod[];

export type SyncMethod = (typeof syncMethods)[number];

// What each protected call does to the collection, in the words a person sees.
export const accessNeeded: Record<SyncMethod, string> = {
	"ManagedCollection.setFields": "change this collection's fields",
	"ManagedCollection.addItems": "add and update its items",
	"ManagedCollection.removeItems": "remove its items",
	"ManagedCollection.setPluginData": "save its sync settings",
};

/** Why the Sync button in the CMS opened the plugin instead of syncing. */
export type SyncStop = "access" | "key" | "error";

// The key stays in this browser only. Plugin data is saved in the project, where every
// collaborator could read it, so it never holds the key.
export function storedKey(): string {
	try {
		return localStorage.getItem(KEY_STORAGE) ?? "";
	} catch {
		return "";
	}
}

export function storeKey(key: string | null): void {
	try {
		if (key) localStorage.setItem(KEY_STORAGE, key);
		else localStorage.removeItem(KEY_STORAGE);
	} catch {
		// Storage can be blocked in a private window; the key then lasts for this session only.
	}
}

export function clientFor(key: string): SpecStreamClient {
	return new SpecStreamClient(key, { app: "framer" });
}

export type SyncSettings = { findId: string; request: string; slugColumnId: string | null; ignored: string[] };

export async function savedSettings(collection: ManagedCollection): Promise<SyncSettings | null> {
	const [findId, request, slugColumnId, ignored] = await Promise.all([
		collection.getPluginData(PLUGIN_KEYS.FIND_ID),
		collection.getPluginData(PLUGIN_KEYS.REQUEST),
		collection.getPluginData(PLUGIN_KEYS.SLUG_COLUMN),
		collection.getPluginData(PLUGIN_KEYS.IGNORED),
	]);
	if (!findId) return null;
	let ignoredIds: string[] = [];
	try {
		const parsed: unknown = JSON.parse(ignored ?? "[]");
		if (Array.isArray(parsed)) ignoredIds = parsed.filter((id): id is string => typeof id === "string");
	} catch {
		ignoredIds = [];
	}
	return { findId, request: request ?? "", slugColumnId: slugColumnId || null, ignored: ignoredIds };
}

/**
 * Writes the results into the collection: fields first, then every item (an upsert on
 * SpecStream's result ID), then removes items the results no longer carry.
 */
export async function syncCollection(
	collection: ManagedCollection,
	choices: FieldChoice[],
	items: ReturnType<typeof itemsFor>,
	settings: SyncSettings,
): Promise<{ synced: number; removed: number }> {
	const fields = choices.map((choice) => choice.field) as ManagedCollectionFieldInput[];
	await collection.setFields(fields);
	const removed = staleItems(await collection.getItemIds(), items);
	if (removed.length) await collection.removeItems(removed);
	await collection.addItems(items as ManagedCollectionItemInput[]);
	await Promise.all([
		collection.setPluginData(PLUGIN_KEYS.FIND_ID, settings.findId),
		collection.setPluginData(PLUGIN_KEYS.REQUEST, settings.request.slice(0, 500)),
		collection.setPluginData(PLUGIN_KEYS.SLUG_COLUMN, settings.slugColumnId ?? ""),
		collection.setPluginData(PLUGIN_KEYS.IGNORED, JSON.stringify(settings.ignored)),
	]);
	return { synced: items.length, removed: removed.length };
}

/** The Sync button in Framer's CMS: reads the same results again, which costs nothing, and updates the collection. */
export async function syncExisting(collection: ManagedCollection): Promise<{ didSync: boolean; stop?: SyncStop }> {
	if (framer.mode !== "syncManagedCollection") return { didSync: false };
	const settings = await savedSettings(collection);
	if (!settings) return { didSync: false };
	if (!framer.isAllowedTo(...syncMethods)) return { didSync: false, stop: "access" };
	const key = storedKey();
	if (!key) return { didSync: false, stop: "key" };
	try {
		const rows = await clientFor(key).rows(settings.findId);
		const table = tableOf(rows);
		const { choices } = fieldsFor(table);
		const kept = choices.filter((choice) => !settings.ignored.includes(choice.field.id));
		const named = keepNames(
			kept.map((choice) => choice.field),
			await collection.getFields(),
		);
		const final = kept.map((choice, index) => ({ ...choice, field: named[index] ?? choice.field }));
		const items = itemsFor(table, final, settings.slugColumnId);
		const { synced } = await syncCollection(collection, final, items, settings);
		await framer.closePlugin(`Synced ${synced.toLocaleString("en-US")} ${synced === 1 ? "item" : "items"} from SpecStream`, { variant: "success" });
		return { didSync: true };
	} catch (error) {
		console.error(error);
		framer.notify(error instanceof Error ? error.message : "Couldn't sync from SpecStream. Open the plugin to try again.", { variant: "error" });
		return { didSync: false, stop: "error" };
	}
}
