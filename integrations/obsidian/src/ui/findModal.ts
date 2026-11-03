import { ButtonComponent, Editor, Modal, Notice, Setting } from "obsidian";
import type SpecStreamPlugin from "../main";
import {
	isFinished,
	isStopped,
	listLink,
	money,
	SpecStreamError,
	type AcceptedRow,
	type Quote,
} from "../api";
import { insertRows } from "../insert";
import { clampRows, MAX_ROWS } from "../settings";

const POLL_MS = 3000;

const sleep = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms));
/** A list usually finishes in minutes. After this the run keeps going and can be inserted later from your saved lists. */
const WAIT_LIMIT_MS = 10 * 60 * 1000;

type Step = "ask" | "price" | "running";

/** The reading as SpecStream phrased it, without the default count it adds when the request names none. */
function readAsText(sentence: string | null, inferred: boolean, rows: number): string {
	if (!sentence) return "";
	return inferred ? sentence.replace(/^\d+\s+/, "") : sentence.replace(/^\d+\s+/, `${rows} `);
}

export class FindListModal extends Modal {
	private step: Step = "ask";
	private request = "";
	private rows: number;
	private reading = "";
	private readAs = "";
	private notice = "";
	private quote: Quote | null = null;
	private findId: string | null = null;
	private found = 0;
	private message = "";
	private busy = false;
	private closed = false;
	private statusEl: HTMLElement | null = null;

	constructor(
		private readonly plugin: SpecStreamPlugin,
		private readonly editor: Editor,
	) {
		super(plugin.app);
		this.rows = plugin.settings.defaultRows;
		this.setTitle("Find a list");
	}

	onOpen(): void {
		this.modalEl.addClass("specstream-modal");
		this.render();
	}

	onClose(): void {
		this.closed = true;
		this.contentEl.empty();
		if (this.step === "running" && this.findId) {
			new Notice("The list keeps running. Insert it later with the saved list command.");
		}
	}

	private render(): void {
		const { contentEl } = this;
		contentEl.empty();
		if (this.step === "ask") this.renderAsk();
		else if (this.step === "price") this.renderPrice();
		else this.renderRunning();
	}

	private renderAsk(): void {
		const { contentEl } = this;
		contentEl.createEl("p", {
			cls: "specstream-lede",
			text: "Say what you want in plain words. You see the price before anything runs. Source URL and read time on every value.",
		});

		new Setting(contentEl)
			.setName("What do you want to find?")
			.setDesc("Say the place and what each row needs, like roofers rated 4.5 or better with a phone number.")
			.addTextArea((area) => {
				area.setPlaceholder("Every roofer in the city rated 4.5 or better, with a phone number").setValue(this.request);
				area.inputEl.rows = 4;
				area.inputEl.addClass("specstream-request");
				area.onChange((value) => {
					this.request = value;
				});
				area.inputEl.addEventListener("keydown", (event) => {
					if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
						event.preventDefault();
						void this.getPrice();
					}
				});
				window.setTimeout(() => area.inputEl.focus(), 0);
			});

		new Setting(contentEl)
			.setName("How many rows?")
			.setDesc(`From 1 to ${MAX_ROWS}. You pay for each result delivered, so this sets the most you could pay, not what you will.`)
			.addText((text) => {
				text.inputEl.type = "number";
				text.inputEl.min = "1";
				text.inputEl.max = String(MAX_ROWS);
				text.setValue(String(this.rows)).onChange((value) => {
					this.rows = clampRows(Number(value));
				});
			});

		if (this.message) contentEl.createEl("p", { cls: "specstream-error", text: this.message });

		const actions = contentEl.createDiv({ cls: "specstream-actions" });
		new ButtonComponent(actions)
			.setButtonText(this.busy ? "Getting the price..." : "Get the price")
			.setCta()
			.setDisabled(this.busy)
			.onClick(() => void this.getPrice());
	}

	private async getPrice(): Promise<void> {
		if (this.busy) return;
		const request = this.request.trim();
		if (!request) {
			this.message = "Describe the list you want first.";
			this.render();
			return;
		}
		this.busy = true;
		this.message = "";
		this.render();
		try {
			const client = this.plugin.client();
			const reading = await client.read(request);
			if (this.closed) return;
			if (reading.status !== "runnable" || !reading.ast_hash) {
				const readAs = reading.canonical_sentence ? ` It read: "${reading.canonical_sentence}".` : "";
				this.message = `SpecStream needs a clearer request before it can price it.${readAs} Add the place, or what every row must meet.`;
				return;
			}
			// A count written in the request wins over the number box, so the price matches what the user asked for.
			if (reading.stated_rows) this.rows = clampRows(reading.stated_rows);
			const quote = await client.quote(reading.ast_hash, this.rows);
			if (this.closed) return;
			this.quote = quote;
			this.reading = request;
			this.readAs = readAsText(reading.canonical_sentence, reading.rows_inferred, this.rows);
			this.notice = reading.notice ?? "";
			this.step = "price";
		} catch (error) {
			this.message = this.errorText(error);
		} finally {
			this.busy = false;
			if (!this.closed) this.render();
		}
	}

	private renderPrice(): void {
		const { contentEl } = this;
		const quote = this.quote;
		if (!quote) return;
		const limitCents = Math.round(this.plugin.settings.spendingLimit * 100);
		const overLimit = quote.maximum_cents > limitCents;

		contentEl.createEl("p", { cls: "specstream-label", text: "Looking for" });
		contentEl.createEl("p", { cls: "specstream-reading", text: this.reading });
		if (this.readAs) contentEl.createEl("p", { cls: "specstream-muted", text: `Read as: ${this.readAs}` });
		if (this.notice) contentEl.createEl("p", { cls: "specstream-muted", text: this.notice });

		const price = contentEl.createDiv({ cls: "specstream-price" });
		price.createDiv({ cls: "specstream-price-amount", text: money(quote.maximum_cents, quote.currency) });
		price.createDiv({
			cls: "specstream-price-line",
			text: `The most this can cost, for up to ${this.rows} ${this.rows === 1 ? "row" : "rows"}.`,
		});
		const rate = quote.terms.unit_cents;
		const rateText = typeof rate === "number" ? ` Matches start at ${money(rate, quote.currency)} each.` : "";
		contentEl.createEl("p", {
			cls: "specstream-muted",
			text: `You pay for each row delivered, and never more than this maximum. A search that finds nothing costs nothing.${rateText}`,
		});

		if (overLimit) {
			contentEl.createEl("p", {
				cls: "specstream-error",
				text: `That is above your spending limit of ${money(limitCents)} per request. Ask for fewer rows, or raise the limit in the plugin settings. Nothing was run.`,
			});
		} else if (!quote.can_authorize) {
			contentEl.createEl("p", {
				cls: "specstream-error",
				text: "This one can't be started from here. Open your workspace to see why.",
			});
		}
		if (this.message) contentEl.createEl("p", { cls: "specstream-error", text: this.message });

		const actions = contentEl.createDiv({ cls: "specstream-actions" });
		new ButtonComponent(actions).setButtonText("Back").onClick(() => {
			this.step = "ask";
			this.quote = null;
			this.message = "";
			this.render();
		});
		new ButtonComponent(actions)
			.setButtonText(this.busy ? "Starting..." : `Approve up to ${money(quote.maximum_cents, quote.currency)} and run`)
			.setCta()
			.setDisabled(overLimit || !quote.can_authorize || this.busy)
			.onClick(() => void this.approve());
	}

	/** Runs only from the approve button. Nothing else in the plugin starts paid work. */
	private async approve(): Promise<void> {
		const quote = this.quote;
		if (!quote || this.busy) return;
		if (quote.expires_at && Date.parse(quote.expires_at) <= Date.now()) {
			this.step = "ask";
			this.quote = null;
			this.message = "That price expired. Get a new one to continue.";
			this.render();
			return;
		}
		this.busy = true;
		this.message = "";
		this.render();
		try {
			const run = await this.plugin.client().approve(quote);
			if (!run.find_id) throw new SpecStreamError("SpecStream accepted the approval but did not start the list. Try again.");
			this.findId = run.find_id;
			this.step = "running";
			this.busy = false;
			this.found = 0;
			this.render();
			await this.wait(run.find_id);
		} catch (error) {
			this.message = this.errorText(error);
			if (this.step !== "running") this.busy = false;
			if (!this.closed) this.render();
		}
	}

	private renderRunning(): void {
		const { contentEl } = this;
		contentEl.createEl("p", { cls: "specstream-label", text: "Working on it" });
		contentEl.createEl("p", { cls: "specstream-reading", text: this.reading });
		const status = contentEl.createDiv({ cls: "specstream-status" });
		status.createSpan({ cls: "specstream-pulse" });
		this.statusEl = status.createSpan({ text: this.statusText() });
		if (this.message) contentEl.createEl("p", { cls: "specstream-error", text: this.message });
		const actions = contentEl.createDiv({ cls: "specstream-actions" });
		new ButtonComponent(actions).setButtonText("Stop waiting").onClick(() => this.close());
		new ButtonComponent(actions)
			.setButtonText("Stop the run")
			.setDestructive()
			.onClick(() => void this.stopRun());
	}

	private statusText(): string {
		if (!this.found) return "Reading the live web. This usually takes a few minutes.";
		return `${this.found} ${this.found === 1 ? "match" : "matches"} so far.`;
	}

	private async wait(findId: string): Promise<void> {
		const client = this.plugin.client();
		const deadline = Date.now() + WAIT_LIMIT_MS;
		let status = "running";
		while (!this.closed && Date.now() < deadline) {
			try {
				const state = await client.findState(findId);
				status = state.status;
				this.found = state.accepted_count;
			} catch (error) {
				if (!(error instanceof SpecStreamError) || error.status === 401) throw error;
			}
			if (this.closed) return;
			if (isFinished(status) || isStopped(status)) break;
			this.statusEl?.setText(this.statusText());
			await sleep(POLL_MS);
		}
		if (this.closed) return;
		if (!isFinished(status) && !isStopped(status)) {
			this.message = "This one is taking longer than usual. Close this window and insert it later from your saved lists. It keeps running.";
			this.render();
			return;
		}
		await this.finish(findId, status);
	}

	private async finish(findId: string, status: string): Promise<void> {
		let rows: AcceptedRow[];
		try {
			rows = await this.plugin.client().rows(findId);
		} catch (error) {
			this.message = `The list finished, but reading it failed. ${this.errorText(error)}`;
			this.render();
			return;
		}
		if (this.closed) return;
		const inserted = rows.length
			? insertRows(this.editor, rows, {
					title: this.reading,
					link: listLink(findId),
					addNote: this.plugin.settings.addNote,
				})
			: 0;
		const stopped = isStopped(status);
		if (!inserted) {
			new Notice(stopped ? "The run stopped before anything matched. Nothing was charged." : "Nothing matched this request. Nothing was charged.");
		} else if (stopped) {
			new Notice(`The run stopped early. Inserted the ${inserted} ${inserted === 1 ? "row" : "rows"} it found.`);
		} else {
			new Notice(`Inserted ${inserted} ${inserted === 1 ? "row" : "rows"} from SpecStream.`);
		}
		this.findId = null;
		this.close();
	}

	private async stopRun(): Promise<void> {
		const findId = this.findId;
		if (!findId) return;
		try {
			await this.plugin.client().cancel(findId);
			this.message = "Stopping. What was found so far is kept.";
		} catch (error) {
			this.message = this.errorText(error);
		}
		this.render();
	}

	private errorText(error: unknown): string {
		return error instanceof Error ? error.message : "Something went wrong. Try again.";
	}
}
