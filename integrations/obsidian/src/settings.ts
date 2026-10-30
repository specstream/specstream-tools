import { Notice, PluginSettingTab, type SettingDefinitionItem } from "obsidian";
import type SpecStreamPlugin from "./main";
import { API_KEYS_URL, money } from "./api";

export const MAX_ROWS = 1000;

export type SpecStreamSettings = {
	/** The name of the secret that holds the API key. The key itself lives in Obsidian's secret storage. */
	apiKeySecret: string;
	defaultRows: number;
	/** The most one list may cost, in whole dollars. A price above it can't be approved. */
	spendingLimit: number;
	addNote: boolean;
};

export const DEFAULT_SETTINGS: SpecStreamSettings = {
	apiKeySecret: "specstream-api-key",
	defaultRows: 25,
	spendingLimit: 5,
	addNote: true,
};

export function clampRows(value: number): number {
	if (!Number.isFinite(value)) return DEFAULT_SETTINGS.defaultRows;
	return Math.min(MAX_ROWS, Math.max(1, Math.trunc(value)));
}

export function cleanLimit(value: number): number {
	return Number.isFinite(value) && value > 0 ? value : DEFAULT_SETTINGS.spendingLimit;
}

export class SpecStreamSettingTab extends PluginSettingTab {
	constructor(private readonly plugin: SpecStreamPlugin) {
		super(plugin.app, plugin);
	}

	getSettingDefinitions(): SettingDefinitionItem[] {
		const keyHelp = new DocumentFragment();
		keyHelp.append("Create a key in your workspace under ");
		keyHelp.createEl("a", { text: "Agents & API", href: API_KEYS_URL });
		keyHelp.append(". New accounts start with $10 of work free for 30 days, no card.");

		return [
			{
				name: "API key",
				desc: keyHelp,
				control: { type: "secret", key: "apiKeySecret", defaultValue: DEFAULT_SETTINGS.apiKeySecret },
			},
			{
				name: "Check the key",
				desc: "Shows which account the key belongs to and what is left to spend.",
				render: (setting) => {
					setting.addButton((button) =>
						button.setButtonText("Check").onClick(async () => {
							button.setDisabled(true);
							try {
								const account = await this.plugin.client().account();
								const left = account.availableCents === null ? "" : ` ${money(account.availableCents)} available.`;
								new Notice(`Connected as ${account.email ?? "your account"}.${left}`);
							} catch (error) {
								new Notice(error instanceof Error ? error.message : "Could not check the key.");
							} finally {
								button.setDisabled(false);
							}
						}),
					);
				},
			},
			{
				name: "Default row count",
				desc: `How many rows to ask for when you find a list, from 1 to ${MAX_ROWS}. You can change it each time.`,
				control: {
					type: "number",
					key: "defaultRows",
					defaultValue: DEFAULT_SETTINGS.defaultRows,
					min: 1,
					max: MAX_ROWS,
					step: 1,
				},
			},
			{
				name: "Spending limit per request",
				desc: "The most one list may cost, in dollars. The maximum price is shown before anything runs, and a price above this limit can't be approved here. You pay for each row delivered.",
				control: {
					type: "number",
					key: "spendingLimit",
					defaultValue: DEFAULT_SETTINGS.spendingLimit,
					min: 0.01,
					step: "any",
					validate: (value) => (Number.isFinite(value) && value > 0 ? undefined : "Enter an amount above zero."),
				},
			},
			{
				name: "Add a note under each table",
				desc: "A line with your request, the row count, the date, and a link to the list in your workspace.",
				control: { type: "toggle", key: "addNote", defaultValue: DEFAULT_SETTINGS.addNote },
			},
		];
	}
}
