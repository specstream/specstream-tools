import { framer, type ManagedCollection, useIsAllowedTo } from "@framer/plugin";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { type ResultTable, tableOf } from "./core/records";
import {
	API_KEYS_URL,
	PRIVACY_URL,
	isFinished,
	isStopped,
	money,
	type PastResult,
	type Quote,
	type Reading,
	resultLink,
	SpecStreamError,
	WORKSPACE_URL,
} from "./core/specstream";
import { accessNeeded, clientFor, storedKey, storeKey, type SyncMethod, type SyncSettings, type SyncStop, syncCollection, syncMethods } from "./data";
import { type FieldChoice, fieldsFor, itemsFor } from "./sync";

const POLL_MS = 3000;
const MAX_RESULTS = 10000;
const DEFAULT_RESULTS = 25;
const DOCS_URL = "https://specstream.ai/docs/integrations/framer";

type Step =
	| { name: "connect" }
	| { name: "ask" }
	| { name: "price"; reading: Reading; quote: Quote }
	| { name: "running"; findId: string; request: string; found: number; requested: number }
	| { name: "fields"; findId: string; request: string; table: ResultTable };

function errorText(error: unknown): string {
	if (error instanceof SpecStreamError) return error.message;
	if (error instanceof Error && error.message) return error.message;
	return "Something stopped this from finishing. Try again.";
}

function plural(n: number, one: string, many = `${one}s`): string {
	return `${n.toLocaleString("en-US")} ${n === 1 ? one : many}`;
}

function clampResults(value: number): number {
	if (!Number.isFinite(value)) return DEFAULT_RESULTS;
	return Math.min(Math.max(Math.round(value), 1), MAX_RESULTS);
}

function Mark() {
	return (
		<svg className="mark" viewBox="236 286 800 580" aria-hidden="true" focusable="false">
			<defs>
				<mask id="specstream-mark-light">
					<rect x="236" y="286" width="800" height="580" fill="#fff" />
					<g transform="translate(874 722) scale(1.6) translate(-874 -722)">
						<path
							fill="#000"
							d="M848 722C849 712 852 704 849 696C846 690 843 684 842 676C837 670 836 660 838 652L836 641L846 649C852 647 858 647 862 649L870 640L871 655C873 663 872 668 868 672C884 678 897 692 900 722Z"
						/>
						<path fill="#000" d="M852 719L900 720L1004 735L950 792Z" />
					</g>
				</mask>
			</defs>
			<path
				fill="currentColor"
				mask="url(#specstream-mark-light)"
				d="M470 298C420 300 330 312 290 334C265 348 272 368 305 382C360 405 440 432 455 472C468 510 420 545 350 590C285 632 248 668 250 712C253 790 390 850 610 851C820 852 960 810 1000 740C1022 700 1018 672 996 640C950 585 850 530 700 480C560 440 420 408 345 380C318 370 312 356 330 346C370 325 430 306 470 298Z"
			/>
		</svg>
	);
}

function listOf(items: string[]): string {
	if (items.length < 2) return items.join("");
	return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

// One hook per method so the notice can name exactly what this person's project role is missing.
function useMissingAccess(): string[] {
	const fields = useIsAllowedTo("ManagedCollection.setFields");
	const add = useIsAllowedTo("ManagedCollection.addItems");
	const remove = useIsAllowedTo("ManagedCollection.removeItems");
	const settings = useIsAllowedTo("ManagedCollection.setPluginData");
	return useMemo(() => {
		const allowed: Record<SyncMethod, boolean> = {
			"ManagedCollection.setFields": fields,
			"ManagedCollection.addItems": add,
			"ManagedCollection.removeItems": remove,
			"ManagedCollection.setPluginData": settings,
		};
		return syncMethods.filter((method) => !allowed[method]).map((method) => accessNeeded[method]);
	}, [fields, add, remove, settings]);
}

function AccessNotice({ missing }: { missing: string[] }) {
	if (!missing.length) return null;
	return (
		<div className="notice" role="alert">
			<strong>You can't sync this collection</strong>
			<p>
				Syncing needs permission to {listOf(missing)}. Your permissions on this project don't include that, so syncing and new requests are turned off in
				this plugin.
			</p>
			<p>Ask a project owner or admin for Content or Design permission, then open the plugin again. Anyone on the project who has it can also click Sync on this collection.</p>
		</div>
	);
}

function Disclosure() {
	return (
		<div className="disclosure">
			<span className="label">What this plugin sends</span>
			<p>
				SpecStream reads the live web to answer your request, so the request you type is sent to SpecStream's API (api.specstream.ai) with your API key. The results
				come back from SpecStream and are written into this collection.
			</p>
			<p>
				Nothing else from your project is sent. Your pages, other collections, existing items and the people on the project stay in Framer.{" "}
				<a href={PRIVACY_URL} target="_blank" rel="noreferrer">
					Privacy policy
				</a>
			</p>
		</div>
	);
}

function Tokens({ title, items }: { title: string; items: string[] }) {
	if (!items.length) return null;
	return (
		<div className="tokens">
			<span className="tokens-title">{title}</span>
			<div className="tokens-list">
				{items.map((item) => (
					<span key={item} className="token">
						{item}
					</span>
				))}
			</div>
		</div>
	);
}

export function App({ collection, settings, stop }: { collection: ManagedCollection; settings: SyncSettings | null; stop: SyncStop | null }) {
	const [apiKey, setApiKey] = useState(storedKey);
	const [step, setStep] = useState<Step>(() => (storedKey() ? { name: "ask" } : { name: "connect" }));
	const [request, setRequest] = useState(settings?.request ?? "");
	const [results, setResults] = useState(DEFAULT_RESULTS);
	const [maxDollars, setMaxDollars] = useState("");
	const [message, setMessage] = useState<string | null>(() =>
		stop === "error" ? "The last sync from the CMS didn't finish. Use Sync it again below, and if it stops again, open Help from the plugin menu." : null,
	);
	const missing = useMissingAccess();
	const canSync = missing.length === 0;
	const [busy, setBusy] = useState(false);
	const [past, setPast] = useState<PastResult[] | null>(null);
	const alive = useRef(true);
	const client = useMemo(() => (apiKey ? clientFor(apiKey) : null), [apiKey]);

	useLayoutEffect(() => {
		const wide = step.name === "fields" || step.name === "price";
		void framer.showUI({ width: 320, height: wide ? 560 : 480, minWidth: 320, minHeight: 420, resizable: true });
	}, [step.name]);

	useEffect(() => {
		alive.current = true;
		return () => {
			alive.current = false;
		};
	}, []);

	const openResults = useCallback(
		async (findId: string, label: string) => {
			if (!client) return;
			const rows = await client.rows(findId);
			if (!alive.current) return;
			setStep({ name: "fields", findId, request: label, table: tableOf(rows) });
		},
		[client],
	);

	useEffect(() => {
		if (!client || step.name !== "running") return;
		let timer: ReturnType<typeof setTimeout> | undefined;
		const { findId, request: label } = step;
		const tick = async () => {
			try {
				const progress = await client.progress(findId);
				if (!alive.current) return;
				if (isFinished(progress.status) || (isStopped(progress.status) && progress.found > 0)) {
					await openResults(findId, label);
					return;
				}
				if (isStopped(progress.status)) {
					setStep({ name: "ask" });
					setMessage("This run stopped before it found anything, so nothing was charged. Try a wider request.");
					return;
				}
				setStep({ name: "running", findId, request: label, found: progress.found, requested: progress.requested });
			} catch (error) {
				if (alive.current) setMessage(errorText(error));
			}
			timer = setTimeout(tick, POLL_MS);
		};
		timer = setTimeout(tick, POLL_MS);
		return () => clearTimeout(timer);
		// The poll restarts only when the run changes, not on each progress update.
	}, [client, step.name === "running" ? step.findId : null]);

	const signOut = useCallback(() => {
		storeKey(null);
		setApiKey("");
		setMessage(null);
		setStep({ name: "connect" });
	}, []);

	// Framer's plugin header menu: help is always there, the workspace and sign-out once connected.
	useEffect(() => {
		const help = { label: "Help", onAction: () => window.open(DOCS_URL, "_blank", "noopener") };
		const privacy = { label: "Privacy policy", onAction: () => window.open(PRIVACY_URL, "_blank", "noopener") };
		void framer.setMenu(
			apiKey
				? [
						{ label: "Open SpecStream", onAction: () => window.open(WORKSPACE_URL, "_blank", "noopener") },
						help,
						privacy,
						{ type: "separator" },
						{ label: "Log out", onAction: signOut },
					]
				: [help, privacy],
		);
	}, [apiKey, signOut]);

	const connect = async (key: string) => {
		setBusy(true);
		setMessage(null);
		try {
			const account = await clientFor(key).account();
			storeKey(key.trim());
			setApiKey(key.trim());
			framer.notify(`Connected${account.email ? ` as ${account.email}` : ""}`, { variant: "success" });
			setStep({ name: "ask" });
		} catch (error) {
			setMessage(errorText(error));
		} finally {
			setBusy(false);
		}
	};

	const getPrice = async () => {
		if (!client || busy) return;
		setBusy(true);
		setMessage(null);
		try {
			const reading = await client.read(request);
			if (!reading.runnable) {
				const readAs = reading.sentence ? ` It read: "${reading.sentence}".` : "";
				setMessage(`SpecStream needs a clearer request before it can price it.${readAs} Add the place, or what every result must meet.`);
				return;
			}
			const rows = reading.statedRows ? clampResults(reading.statedRows) : results;
			if (rows !== results) setResults(rows);
			const quote = await client.quote(reading, rows);
			if (!alive.current) return;
			if (!maxDollars) setMaxDollars((quote.maximumCents / 100).toFixed(2));
			setStep({ name: "price", reading, quote });
		} catch (error) {
			setMessage(errorText(error));
		} finally {
			if (alive.current) setBusy(false);
		}
	};

	const approve = async (quote: Quote, label: string) => {
		if (!client || busy) return;
		const maxCents = Math.round(Number(maxDollars) * 100);
		if (!Number.isFinite(maxCents) || maxCents <= 0) {
			setMessage("Set the most you want to spend on this request.");
			return;
		}
		setBusy(true);
		setMessage(null);
		try {
			const run = await client.approve(quote, maxCents);
			if (!alive.current) return;
			setStep({ name: "running", findId: run.findId, request: label, found: 0, requested: quote.rows });
		} catch (error) {
			setMessage(errorText(error));
		} finally {
			if (alive.current) setBusy(false);
		}
	};

	const chooseResults = async (item: PastResult) => {
		setBusy(true);
		setMessage(null);
		try {
			await openResults(item.findId, item.name);
		} catch (error) {
			setMessage(errorText(error));
		} finally {
			if (alive.current) setBusy(false);
		}
	};

	const showPast = async () => {
		if (!client) return;
		try {
			setPast(await client.pastResults());
		} catch (error) {
			setMessage(errorText(error));
		}
	};

	if (step.name === "connect" || !client) {
		return <Connect busy={busy} message={message} missing={missing} keyElsewhere={stop === "key"} onConnect={connect} />;
	}

	return (
		<main className="framer-hide-scrollbar">
			<header className="bar">
				<span className="brand">
					<Mark />
					SpecStream
				</span>
				<button type="button" className="link-button" onClick={signOut}>
					Log out
				</button>
			</header>

			{step.name === "ask" ? (
				<section className="stack">
					<AccessNotice missing={missing} />
					{settings ? (
						<div className="note">
							This collection syncs "{settings.request || "your SpecStream results"}".{" "}
							<button
								type="button"
								className="link-button"
								onClick={() => void chooseResults({ name: settings.request, findId: settings.findId, rows: 0, createdAt: "" })}
								disabled={!canSync}
							>
								Sync it again
							</button>
						</div>
					) : null}
					<label className="field">
						<span className="label">What do you want to find?</span>
						<textarea
							value={request}
							rows={4}
							placeholder="Coffee shops in Austin with their website and Google rating"
							onChange={(event) => setRequest(event.target.value)}
							onKeyDown={(event) => {
								if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) void getPrice();
							}}
						/>
					</label>
					<div className="row">
						<label className="field grow">
							<span className="label">Results</span>
							<input type="number" min={1} max={MAX_RESULTS} value={results} onChange={(event) => setResults(clampResults(Number(event.target.value)))} />
						</label>
					</div>
					<p className="hint">You pay for each result delivered. Nothing runs until you approve the price.</p>
					<p className="hint">
						Your request is sent to SpecStream's API (api.specstream.ai), which reads the live web to answer it. Nothing else from this project leaves Framer.{" "}
						<a href={PRIVACY_URL} target="_blank" rel="noreferrer">
							Privacy policy
						</a>
					</p>
					{message ? <p className="error">{message}</p> : null}
					<button type="button" className="framer-button-primary" onClick={getPrice} disabled={busy || !canSync || !request.trim()}>
						{busy ? <div className="framer-spinner" /> : "Get the price"}
					</button>
					<hr />
					{past === null ? (
						<button type="button" onClick={showPast}>
							Use results you already have
						</button>
					) : past.length ? (
						<div className="past">
							<span className="label">Results in your SpecStream workspace</span>
							{past.slice(0, 12).map((item) => (
								<button key={item.findId} type="button" className="past-item" onClick={() => void chooseResults(item)} disabled={busy || !canSync}>
									<span className="past-name">{item.name}</span>
									<span className="past-count">{item.rows ? plural(item.rows, "result") : ""}</span>
								</button>
							))}
						</div>
					) : (
						<p className="hint">Your SpecStream workspace has no results yet.</p>
					)}
				</section>
			) : null}

			{step.name === "price" ? (
				<Price
					step={step}
					maxDollars={maxDollars}
					setMaxDollars={setMaxDollars}
					busy={busy}
					message={message}
					onBack={() => {
						setStep({ name: "ask" });
						setMessage(null);
					}}
					onApprove={() => approve(step.quote, step.reading.request)}
				/>
			) : null}

			{step.name === "running" ? (
				<section className="stack center">
					<div className="framer-spinner" />
					<h2>Reading the live web</h2>
					<p className="hint">{step.request}</p>
					<p className="count">{step.found ? `${plural(step.found, "match", "matches")} so far` : "Starting the run"}</p>
					{step.requested ? (
						<div className="meter" role="progressbar" aria-valuemin={0} aria-valuemax={step.requested} aria-valuenow={step.found}>
							<span style={{ width: `${Math.min((step.found / step.requested) * 100, 100)}%` }} />
						</div>
					) : null}
					<p className="hint">This usually takes a few minutes. If you close the plugin, the run keeps going and its results wait in your SpecStream workspace.</p>
					{message ? <p className="error">{message}</p> : null}
					<div className="row">
						<a className="button-link" href={resultLink(step.findId)} target="_blank" rel="noreferrer">
							Open in SpecStream
						</a>
						<button type="button" className="danger" onClick={() => void client.cancel(step.findId).catch((error) => setMessage(errorText(error)))}>
							Stop the run
						</button>
					</div>
				</section>
			) : null}

			{step.name === "fields" ? (
				<Fields
					collection={collection}
					step={step}
					previous={settings}
					onBack={() => {
						setStep({ name: "ask" });
						setMessage(null);
					}}
				/>
			) : null}
		</main>
	);
}

function Connect({
	busy,
	message,
	missing,
	keyElsewhere,
	onConnect,
}: {
	busy: boolean;
	message: string | null;
	missing: string[];
	keyElsewhere: boolean;
	onConnect: (key: string) => void;
}) {
	const [draft, setDraft] = useState("");
	return (
		<main className="framer-hide-scrollbar">
			<section className="stack intro">
				<div className="intro-mark">
					<Mark />
				</div>
				<h1>SpecStream</h1>
				<p className="hint">Ask for data in plain words and sync the results into this collection. Every item keeps the page it was read from.</p>
				<AccessNotice missing={missing} />
				{keyElsewhere ? (
					<p className="note">
						Someone on this project set up this collection with SpecStream. API keys stay in each person's own browser and are never saved in the project, so connect
						your own key to sync it.
					</p>
				) : null}
				<label className="field">
					<span className="label">API key</span>
					<input type="password" value={draft} placeholder="ss_live_..." onChange={(event) => setDraft(event.target.value)} autoFocus />
				</label>
				{message ? <p className="error">{message}</p> : null}
				<button type="button" className="framer-button-primary" onClick={() => onConnect(draft)} disabled={busy || !draft.trim()}>
					{busy ? <div className="framer-spinner" /> : "Connect"}
				</button>
				<p className="hint">
					Create a key under Agents &amp; API in your{" "}
					<a href={API_KEYS_URL} target="_blank" rel="noreferrer">
						SpecStream workspace
					</a>
					. New accounts get $10 of credit. The key stays in this browser.
				</p>
				<Disclosure />
				</section>
		</main>
	);
}

function Price({
	step,
	maxDollars,
	setMaxDollars,
	busy,
	message,
	onBack,
	onApprove,
}: {
	step: { reading: Reading; quote: Quote };
	maxDollars: string;
	setMaxDollars: (value: string) => void;
	busy: boolean;
	message: string | null;
	onBack: () => void;
	onApprove: () => void;
}) {
	const { reading, quote } = step;
	const maxCents = Math.round(Number(maxDollars) * 100);
	const over = maxCents > 0 && quote.maximumCents > maxCents;
	const rate = quote.unitCents === null ? "" : ` Results start at ${money(quote.unitCents, quote.currency)} each.`;
	return (
		<section className="stack">
			<span className="label">How SpecStream read it</span>
			<div className="card">
				<p className="reading">{reading.sentence && reading.statedRows === null ? reading.sentence.replace(/^\d[\d,]*(?=\s)/, String(step.quote.rows)) : (reading.sentence ?? reading.request)}</p>
				<Tokens title="Looking for" items={reading.lookingFor} />
				<Tokens title="Every result must" items={reading.mustMeet} />
				<Tokens title="Brings back" items={reading.bringsBack} />
			</div>
			{reading.notice ? <p className="note">{reading.notice}</p> : null}
			<div className="price">
				<span className="label">The most this can cost</span>
				<span className="amount">{money(quote.maximumCents, quote.currency)}</span>
				<span className="hint">
					For up to {plural(quote.rows, "result")}. You pay for each result delivered, and a search that finds nothing costs nothing.{rate}
				</span>
			</div>
			<label className="field">
				<span className="label">Your maximum (USD)</span>
				<input type="number" min={0} step={0.01} value={maxDollars} onChange={(event) => setMaxDollars(event.target.value)} />
			</label>
			{over ? <p className="error">This can cost up to {money(quote.maximumCents, quote.currency)}, above your maximum. Raise the maximum or ask for fewer results.</p> : null}
			{!quote.canAuthorize ? <p className="error">This request can't start from here. Open your SpecStream workspace to see why.</p> : null}
			{message ? <p className="error">{message}</p> : null}
			<div className="row">
				<button type="button" onClick={onBack} disabled={busy}>
					Back
				</button>
				<button type="button" className="framer-button-primary grow" onClick={onApprove} disabled={busy || over || !quote.canAuthorize || !(maxCents > 0)}>
					{busy ? <div className="framer-spinner" /> : `Approve up to ${money(quote.maximumCents, quote.currency)}`}
				</button>
			</div>
		</section>
	);
}

function Fields({
	collection,
	step,
	previous,
	onBack,
}: {
	collection: ManagedCollection;
	step: { findId: string; request: string; table: ResultTable };
	previous: SyncSettings | null;
	onBack: () => void;
}) {
	const missing = useMissingAccess();
	const isAllowed = missing.length === 0;
	const { choices, dropped } = useMemo(() => fieldsFor(step.table), [step.table]);
	const sameResults = previous?.findId === step.findId;
	const [ignored, setIgnored] = useState<Set<string>>(() => new Set(sameResults ? previous?.ignored : []));
	const [names, setNames] = useState<Record<string, string>>({});
	const textColumns = step.table.columns.filter((column) => column.kind === "text" || column.kind === "longText");
	const [slugColumnId, setSlugColumnId] = useState<string>((sameResults ? previous?.slugColumnId : null) ?? textColumns[0]?.id ?? "");
	const [syncing, setSyncing] = useState(false);

	useEffect(() => {
		let active = true;
		void collection.getFields().then((existing) => {
			if (!active) return;
			setNames(Object.fromEntries(existing.map((field) => [field.id, field.name])));
		});
		return () => {
			active = false;
		};
	}, [collection]);

	if (!step.table.records.length) {
		return (
			<section className="stack">
				<h2>No results to sync</h2>
				<p className="hint">This run finished without matches, so nothing was charged.</p>
				<button type="button" onClick={onBack}>
					Back
				</button>
			</section>
		);
	}

	const sync = async () => {
		setSyncing(true);
		try {
			const kept: FieldChoice[] = choices
				.filter((choice) => !ignored.has(choice.field.id))
				.map((choice) => ({ ...choice, field: { ...choice.field, name: (names[choice.field.id] ?? choice.field.name).trim() || choice.field.name } }));
			const items = itemsFor(step.table, kept, slugColumnId || null);
			const { synced } = await syncCollection(collection, kept, items, {
				findId: step.findId,
				request: step.request,
				slugColumnId: slugColumnId || null,
				ignored: [...ignored],
			});
			await framer.closePlugin(`Synced ${plural(synced, "item")} from SpecStream`, { variant: "success" });
		} catch (error) {
			console.error(error);
			framer.notify(errorText(error), { variant: "error" });
			setSyncing(false);
		}
	};

	return (
		<section className="stack">
			<h2>{plural(step.table.records.length, "result")} ready</h2>
			<p className="hint">{step.request}</p>
			<label className="field">
				<span className="label">Slug from</span>
				<select value={slugColumnId} onChange={(event) => setSlugColumnId(event.target.value)} disabled={!isAllowed}>
					{textColumns.map((column) => (
						<option key={column.id} value={column.id}>
							{column.label}
						</option>
					))}
					<option value="">SpecStream ID</option>
				</select>
			</label>
			<div className="mapping">
				<span className="label">Column</span>
				<span className="label">Field</span>
				{choices.map((choice) => {
					const off = ignored.has(choice.field.id);
					return (
						<div key={choice.field.id} className="mapping-row">
							<button
								type="button"
								className={`source-field${off ? " off" : ""}`}
								onClick={() =>
									setIgnored((current) => {
										const next = new Set(current);
										if (next.has(choice.field.id)) next.delete(choice.field.id);
										else next.add(choice.field.id);
										return next;
									})
								}
								disabled={!isAllowed}
							>
								<input type="checkbox" checked={!off} readOnly tabIndex={-1} />
								<span>{choice.column?.label ?? choice.field.name}</span>
							</button>
							<input
								type="text"
								value={names[choice.field.id] ?? choice.field.name}
								disabled={off || !isAllowed}
								onChange={(event) => setNames((current) => ({ ...current, [choice.field.id]: event.target.value }))}
							/>
						</div>
					);
				})}
			</div>
			{dropped.length ? <p className="note">Framer allows 30 fields, so these columns were left out: {dropped.join(", ")}.</p> : null}
			<p className="hint">Use Sync in the CMS to bring these results in again. Reading results you already have costs nothing.</p>
			<AccessNotice missing={missing} />
			<div className="row footer">
				<button type="button" onClick={onBack} disabled={syncing}>
					Back
				</button>
				<button
					type="button"
					className="framer-button-primary grow"
					onClick={sync}
					disabled={syncing || !isAllowed}
				>
					{syncing ? <div className="framer-spinner" /> : `Sync ${plural(step.table.records.length, "item")}`}
				</button>
			</div>
		</section>
	);
}
