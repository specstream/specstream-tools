import { useBase, useGlobalConfig, useSettingsButton } from "@airtable/blocks/ui";
import { Box, Button, FormField, Heading, Input, Link, Loader, ProgressBar, Select, TablePicker, Text } from "@airtable/blocks/ui";
import type { Table } from "@airtable/blocks/models";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { nameColumn, tableOf } from "./core/records";
import {
	type AcceptedRow,
	API_KEYS_URL,
	isFinished,
	isStopped,
	money,
	type PastResult,
	type Quote,
	type Reading,
	resultLink,
	SpecStreamClient,
	SpecStreamError,
} from "./core/specstream";
import { Mark } from "./Mark";
import { usePalette } from "./palette";
import { planFields } from "./plan";
import { writeResults, WriteError } from "./write";

const KEY = "apiKey";
const RUN = "run";
const MAX = "maxCents";
const POLL_MS = 3000;
const MAX_RESULTS = 10000;
const DEFAULT_RESULTS = 25;
const DOCS_URL = "https://specstream.ai/docs/integrations/airtable";

type SavedRun = { findId: string; request: string };

type Step =
	| { name: "ask" }
	| { name: "price"; reading: Reading; quote: Quote }
	| { name: "running"; findId: string; request: string; found: number; requested: number }
	| { name: "ready"; findId: string; request: string; rows: AcceptedRow[] }
	| { name: "writing"; done: number; total: number }
	| { name: "done"; tableName: string; added: number; updated: number; findId: string };

function errorText(error: unknown): string {
	if (error instanceof SpecStreamError || error instanceof WriteError) return error.message;
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

function Message({ tone, children }: { tone: "error" | "note"; children: React.ReactNode }) {
	const palette = usePalette();
	return (
		<Box
			marginTop={2}
			padding={2}
			borderRadius="large"
			backgroundColor={tone === "error" ? palette.errorBg : palette.note}
			border="default"
			borderColor={tone === "error" ? palette.errorBorder : undefined}
		>
			<Text textColor={tone === "error" ? palette.errorText : "light"} size="small">
				{children}
			</Text>
		</Box>
	);
}

function Tokens({ title, items }: { title: string; items: string[] }) {
	const palette = usePalette();
	if (!items.length) return null;
	return (
		<Box marginTop={2}>
			<Text size="small" textColor="light" marginBottom={1}>
				{title}
			</Text>
			<Box display="flex" flexWrap="wrap">
				{items.map((item) => (
					<Box key={item} marginRight={1} marginBottom={1} paddingX={2} paddingY="2px" borderRadius="circle" backgroundColor={palette.token} border="default">
						<Text size="small">{item}</Text>
					</Box>
				))}
			</Box>
		</Box>
	);
}

function Header({ email }: { email: string | null }) {
	const palette = usePalette();
	return (
		<Box display="flex" alignItems="center" justifyContent="space-between" paddingX={3} paddingY={2} borderBottom="default">
			<Box display="flex" alignItems="center">
				<Mark size={22} dark={palette.mark} />
				<Text marginLeft={2} fontWeight="strong">
					SpecStream
				</Text>
			</Box>
			{email ? (
				<Text size="small" textColor="light">
					{email}
				</Text>
			) : null}
		</Box>
	);
}

function Settings({ apiKey, canSet, onSaved }: { apiKey: string; canSet: boolean; onSaved: (key: string, email: string | null) => void }) {
	const globalConfig = useGlobalConfig();
	const [draft, setDraft] = useState(apiKey);
	const [status, setStatus] = useState<{ tone: "error" | "note"; text: string } | null>(null);
	const [busy, setBusy] = useState(false);

	const save = async () => {
		const key = draft.trim();
		if (!key) {
			setStatus({ tone: "error", text: "Paste an API key first." });
			return;
		}
		setBusy(true);
		setStatus(null);
		try {
			const account = await new SpecStreamClient(key, { app: "airtable" }).account();
			await globalConfig.setAsync(KEY, key);
			const balance = account.availableCents === null ? "" : ` ${money(account.availableCents)} available.`;
			setStatus({ tone: "note", text: `Connected${account.email ? ` as ${account.email}` : ""}.${balance}` });
			onSaved(key, account.email);
		} catch (error) {
			setStatus({ tone: "error", text: errorText(error) });
		} finally {
			setBusy(false);
		}
	};

	const remove = async () => {
		await globalConfig.setAsync(KEY, undefined);
		setDraft("");
		setStatus({ tone: "note", text: "The key was removed from this base." });
		onSaved("", null);
	};

	return (
		<Box padding={3}>
			<Heading size="small">Connect SpecStream</Heading>
			<Text textColor="light" marginBottom={3}>
				Paste an API key from your SpecStream workspace. New accounts get $10 of work free.{" "}
				<Link href={API_KEYS_URL} target="_blank">
					Create a key
				</Link>
			</Text>
			<FormField label="API key" description="Everyone who opens this extension in this base uses this key.">
				<Input type="password" value={draft} placeholder="ss_live_..." onChange={(event) => setDraft(event.target.value)} disabled={!canSet || busy} />
			</FormField>
			{!canSet ? <Message tone="note">Only people who can edit this base can change the key.</Message> : null}
			<Box display="flex" marginTop={2}>
				<Button variant="primary" onClick={save} disabled={!canSet || busy} marginRight={2}>
					{busy ? "Checking..." : "Save and check"}
				</Button>
				{apiKey ? (
					<Button onClick={remove} disabled={!canSet || busy}>
						Remove key
					</Button>
				) : null}
			</Box>
			{status ? <Message tone={status.tone}>{status.text}</Message> : null}
			<Text textColor="light" marginTop={4} size="small">
				<Link href={DOCS_URL} target="_blank">
					How the extension works
				</Link>
				{" · "}
				<Link href="mailto:support@specstream.ai">support@specstream.ai</Link>
			</Text>
		</Box>
	);
}

export function App() {
	const base = useBase();
	const palette = usePalette();
	const globalConfig = useGlobalConfig();
	const apiKey = (globalConfig.get(KEY) as string | undefined) ?? "";
	const savedRun = (globalConfig.get(RUN) as SavedRun | undefined) ?? null;
	const savedMax = globalConfig.get(MAX) as number | undefined;
	const canSet = globalConfig.hasPermissionToSet();

	const [isShowingSettings, setShowingSettings] = useState(false);
	useSettingsButton(() => setShowingSettings((showing) => !showing));
	const [email, setEmail] = useState<string | null>(null);
	const [step, setStep] = useState<Step>({ name: "ask" });
	const [request, setRequest] = useState("");
	const [results, setResults] = useState(DEFAULT_RESULTS);
	const [maxDollars, setMaxDollars] = useState(savedMax ? (savedMax / 100).toFixed(2) : "");
	const [message, setMessage] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);
	const [table, setTable] = useState<Table | null>(null);
	const [newTable, setNewTable] = useState(true);
	const [past, setPast] = useState<PastResult[] | null>(null);
	const [pastId, setPastId] = useState<string>("");
	const alive = useRef(true);

	const client = useMemo(() => (apiKey ? new SpecStreamClient(apiKey, { app: "airtable" }) : null), [apiKey]);

	useEffect(() => {
		alive.current = true;
		return () => {
			alive.current = false;
		};
	}, []);

	useEffect(() => {
		if (!client) return;
		client
			.account()
			.then((account) => alive.current && setEmail(account.email))
			.catch(() => alive.current && setEmail(null));
	}, [client]);

	const remember = useCallback(
		async (run: SavedRun | null) => {
			if (globalConfig.hasPermissionToSet(RUN)) await globalConfig.setAsync(RUN, run ?? undefined);
		},
		[globalConfig],
	);

	const loadRows = useCallback(
		async (findId: string, label: string) => {
			if (!client) return;
			const rows = await client.rows(findId);
			if (!alive.current) return;
			setStep({ name: "ready", findId, request: label, rows });
		},
		[client],
	);

	// A run started earlier in this base, by anyone, picks up where it was when the extension opens.
	useEffect(() => {
		if (!client || !savedRun || step.name !== "ask") return;
		setStep({ name: "running", findId: savedRun.findId, request: savedRun.request, found: 0, requested: 0 });
	}, [client]);

	useEffect(() => {
		if (!client || step.name !== "running") return;
		let timer: ReturnType<typeof setTimeout> | undefined;
		const { findId, request: label } = step;
		const tick = async () => {
			try {
				const progress = await client.progress(findId);
				if (!alive.current) return;
				if (isFinished(progress.status) || (isStopped(progress.status) && progress.found > 0)) {
					await loadRows(findId, label);
					return;
				}
				if (isStopped(progress.status)) {
					await remember(null);
					setStep({ name: "ask" });
					setMessage("This run stopped before it found anything, so nothing was charged. Try a wider request.");
					return;
				}
				setStep({ name: "running", findId, request: label, found: progress.found, requested: progress.requested });
			} catch (error) {
				if (!alive.current) return;
				setMessage(errorText(error));
			}
			timer = setTimeout(tick, POLL_MS);
		};
		timer = setTimeout(tick, step.found || step.requested ? POLL_MS : 0);
		return () => clearTimeout(timer);
		// The poll restarts only when the run changes, not on each progress update.
	}, [client, step.name === "running" ? step.findId : null]);

	if (isShowingSettings || !apiKey) {
		return (
			<Box>
				<Header email={email} />
				<Settings
					apiKey={apiKey}
					canSet={canSet}
					onSaved={(key, account) => {
						setEmail(account);
						if (key) setShowingSettings(false);
					}}
				/>
			</Box>
		);
	}

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
			if (globalConfig.hasPermissionToSet(MAX)) await globalConfig.setAsync(MAX, maxCents);
			const run = await client.approve(quote, maxCents);
			await remember({ findId: run.findId, request: label });
			if (!alive.current) return;
			setStep({ name: "running", findId: run.findId, request: label, found: 0, requested: quote.rows });
		} catch (error) {
			setMessage(errorText(error));
		} finally {
			if (alive.current) setBusy(false);
		}
	};

	const stop = async (findId: string) => {
		if (!client) return;
		try {
			await client.cancel(findId);
		} catch (error) {
			setMessage(errorText(error));
		}
	};

	const showPast = async () => {
		if (!client) return;
		setMessage(null);
		try {
			const found = await client.pastResults();
			if (!alive.current) return;
			setPast(found);
			setPastId(found[0]?.findId ?? "");
		} catch (error) {
			setMessage(errorText(error));
		}
	};

	const addPast = async () => {
		const chosen = past?.find((item) => item.findId === pastId);
		if (!chosen) return;
		setBusy(true);
		setMessage(null);
		try {
			await loadRows(chosen.findId, chosen.name);
		} catch (error) {
			setMessage(errorText(error));
		} finally {
			if (alive.current) setBusy(false);
		}
	};

	const add = async (findId: string, label: string, rows: AcceptedRow[]) => {
		setMessage(null);
		if (!newTable && !table) {
			setMessage("Choose a table, or create a new one.");
			return;
		}
		setStep({ name: "writing", done: 0, total: rows.length });
		try {
			const destination = newTable || !table ? { newTableName: label } : { table };
			const written = await writeResults(base, destination, rows, ({ done, total }) => {
				if (alive.current) setStep({ name: "writing", done, total });
			});
			await remember(null);
			if (!alive.current) return;
			setStep({ name: "done", tableName: written.table.name, added: written.added, updated: written.updated, findId });
		} catch (error) {
			if (!alive.current) return;
			setStep({ name: "ready", findId, request: label, rows });
			setMessage(errorText(error));
		}
	};

	return (
		<Box>
			<Header email={email} />
			<Box padding={3}>
				{step.name === "ask" ? (
					<>
						<Heading size="small">Find data on the live web</Heading>
						<Text textColor="light" marginBottom={3}>
							Say what you need in plain words. You see the price before anything runs, and every record comes with the page it was read from.
						</Text>
						<FormField label="What do you want to find?">
							<textarea
								value={request}
								rows={4}
								placeholder="Coffee shops in Austin with their website and Google rating"
								onChange={(event) => setRequest(event.target.value)}
								onKeyDown={(event) => {
									if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) void getPrice();
								}}
								style={{
									width: "100%",
									boxSizing: "border-box",
									resize: "vertical",
									padding: "8px 10px",
									borderRadius: 3,
									border: "2px solid transparent",
									background: palette.field,
									color: "inherit",
									font: "inherit",
									fontSize: 13,
									lineHeight: 1.5,
								}}
							/>
						</FormField>
						<FormField label="Results" description="You pay for each result delivered, so this sets the most you could pay.">
							<Input
								type="number"
								min={1}
								max={MAX_RESULTS}
								value={String(results)}
								onChange={(event) => setResults(clampResults(Number(event.target.value)))}
								width="120px"
							/>
						</FormField>
						<Button variant="primary" onClick={getPrice} disabled={busy || !request.trim()} width="100%">
							{busy ? "Getting the price..." : "Get the price"}
						</Button>
						{message ? <Message tone="error">{message}</Message> : null}
						<Box marginTop={4} paddingTop={3} borderTop="default">
							{past === null ? (
								<Button variant="secondary" size="small" icon="history" onClick={showPast}>
									Add results you already have
								</Button>
							) : past.length ? (
								<>
									<FormField label="Results in your SpecStream workspace" description="Adding them again costs nothing.">
										<Select
											options={past.map((item) => ({ value: item.findId, label: `${item.name} (${plural(item.rows, "result")})` }))}
											value={pastId}
											onChange={(value) => setPastId(String(value))}
										/>
									</FormField>
									<Button onClick={addPast} disabled={busy || !pastId}>
										Choose these results
									</Button>
								</>
							) : (
								<Text textColor="light" size="small">
									Your SpecStream workspace has no results yet.
								</Text>
							)}
						</Box>
					</>
				) : null}

				{step.name === "price" ? (
					<PriceStep
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
					<>
						<Heading size="small">Reading the live web</Heading>
						<Text textColor="light" marginBottom={3}>
							{step.request}
						</Text>
						<Box display="flex" alignItems="center" marginBottom={2}>
							<Loader scale={0.3} />
							<Text marginLeft={2}>{step.found ? `${plural(step.found, "match", "matches")} so far` : "Starting the run"}</Text>
						</Box>
						{step.requested ? <ProgressBar progress={Math.min(step.found / step.requested, 1)} barColor={palette.accent} /> : null}
						<Text size="small" textColor="light" marginTop={2}>
							This usually takes a few minutes. You can close the extension; the run keeps going and its results wait here.
						</Text>
						<Box display="flex" marginTop={3}>
							<Button variant="danger" onClick={() => stop(step.findId)} marginRight={2}>
								Stop the run
							</Button>
							<Link href={resultLink(step.findId)} target="_blank" alignSelf="center">
								Open in SpecStream
							</Link>
						</Box>
						{message ? <Message tone="error">{message}</Message> : null}
					</>
				) : null}

				{step.name === "ready" ? (
					<ReadyStep
						step={step}
						table={table}
						setTable={setTable}
						newTable={newTable}
						setNewTable={setNewTable}
						message={message}
						onAdd={() => add(step.findId, step.request, step.rows)}
						onCancel={async () => {
							await remember(null);
							setStep({ name: "ask" });
							setMessage(null);
						}}
					/>
				) : null}

				{step.name === "writing" ? (
					<>
						<Heading size="small">Adding records</Heading>
						<Text textColor="light" marginBottom={2}>
							{step.total ? `${step.done.toLocaleString("en-US")} of ${plural(step.total, "record")}` : "Setting up fields"}
						</Text>
						<ProgressBar progress={step.total ? step.done / step.total : 0} barColor={palette.accent} />
					</>
				) : null}

				{step.name === "done" ? (
					<>
						<Heading size="small">Added to {step.tableName}</Heading>
						<Text marginBottom={1}>
							{plural(step.added, "new record")}
							{step.updated ? `, ${plural(step.updated, "record")} updated` : ""}. Each one has its source page in the Source field.
						</Text>
						<Box display="flex" marginTop={3} alignItems="center">
							<Button
								variant="primary"
								onClick={() => {
									setStep({ name: "ask" });
									setRequest("");
									setPast(null);
								}}
								marginRight={3}
							>
								Find more data
							</Button>
							<Link href={resultLink(step.findId)} target="_blank">
								Open in SpecStream
							</Link>
						</Box>
					</>
				) : null}
			</Box>
		</Box>
	);
}

function PriceStep({
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
	const palette = usePalette();
	const { reading, quote } = step;
	const maxCents = Math.round(Number(maxDollars) * 100);
	const over = Number.isFinite(maxCents) && maxCents > 0 && quote.maximumCents > maxCents;
	const rate = quote.unitCents === null ? "" : ` Results start at ${money(quote.unitCents, quote.currency)} each.`;
	return (
		<>
			<Heading size="small">How SpecStream read it</Heading>
			<Box padding={2} borderRadius="large" border="default" backgroundColor={palette.panel}>
				<Text>{reading.sentence ?? reading.request}</Text>
				<Tokens title="Looking for" items={reading.lookingFor} />
				<Tokens title="Every result must" items={reading.mustMeet} />
				<Tokens title="Brings back" items={reading.bringsBack} />
			</Box>
			{reading.notice ? <Message tone="note">{reading.notice}</Message> : null}

			<Box marginTop={3} padding={3} borderRadius="large" border="thick" borderColor={palette.accent}>
				<Text size="small" textColor="light">
					The most this can cost
				</Text>
				<Text size="xlarge" fontWeight="strong">
					{money(quote.maximumCents, quote.currency)}
				</Text>
				<Text size="small" textColor="light">
					For up to {plural(quote.rows, "result")}. You pay for each result delivered, and a search that finds nothing costs nothing.{rate}
				</Text>
			</Box>

			<Box marginTop={3}>
				<FormField label="Your maximum (USD)" description="The run starts only if the price is at or below this.">
					<Input type="number" min={0} step={0.01} value={maxDollars} onChange={(event) => setMaxDollars(event.target.value)} width="140px" />
				</FormField>
			</Box>
			{over ? (
				<Message tone="error">
					This can cost up to {money(quote.maximumCents, quote.currency)}, above your maximum. Raise the maximum or ask for fewer results.
				</Message>
			) : null}
			{!quote.canAuthorize ? <Message tone="error">This request can't start from here. Open your SpecStream workspace to see why.</Message> : null}
			{message ? <Message tone="error">{message}</Message> : null}
			<Box display="flex" marginTop={3}>
				<Button onClick={onBack} marginRight={2} disabled={busy}>
					Back
				</Button>
				<Button variant="primary" onClick={onApprove} disabled={busy || over || !quote.canAuthorize || !(maxCents > 0)} flexGrow={1}>
					{busy ? "Starting..." : `Approve up to ${money(quote.maximumCents, quote.currency)}`}
				</Button>
			</Box>
		</>
	);
}

function ReadyStep({
	step,
	table,
	setTable,
	newTable,
	setNewTable,
	message,
	onAdd,
	onCancel,
}: {
	step: { request: string; rows: AcceptedRow[] };
	table: Table | null;
	setTable: (table: Table | null) => void;
	newTable: boolean;
	setNewTable: (value: boolean) => void;
	message: string | null;
	onAdd: () => void;
	onCancel: () => void;
}) {
	const palette = usePalette();
	const result = useMemo(() => tableOf(step.rows), [step.rows]);
	const fields = useMemo(() => {
		const existing =
			!newTable && table ? table.fields.map((field) => ({ id: field.id, name: field.name, type: field.type as string, computed: field.isComputed })) : [];
		const primary = !newTable && table ? table.primaryField : null;
		const plan = planFields(
			result,
			existing,
			primary ? { primary: { id: primary.id, name: primary.name, type: primary.type as string, computed: primary.isComputed } } : {},
		);
		return plan.targets.map((target) => ({ name: target.field?.name ?? target.create?.name ?? target.label, created: Boolean(target.create) }));
	}, [result, table, newTable]);
	const name = nameColumn(result);

	if (!result.records.length) {
		return (
			<>
				<Heading size="small">No results to add</Heading>
				<Text textColor="light" marginBottom={3}>
					This run finished without matches, so nothing was charged.
				</Text>
				<Button onClick={onCancel}>Back</Button>
			</>
		);
	}

	return (
		<>
			<Heading size="small">{plural(result.records.length, "result")} ready</Heading>
			<Text textColor="light" marginBottom={3}>
				{step.request}
			</Text>
			<FormField label="Add them to">
				<Select
					options={[
						{ value: "new", label: "A new table" },
						{ value: "existing", label: "A table in this base" },
					]}
					value={newTable ? "new" : "existing"}
					onChange={(value) => setNewTable(value === "new")}
				/>
			</FormField>
			{!newTable ? (
				<FormField label="Table">
					<TablePicker table={table} onChange={(picked) => setTable(picked ?? null)} placeholder="Pick a table" />
				</FormField>
			) : null}
			<Box marginBottom={3}>
				<Text size="small" textColor="light" marginBottom={1}>
					Fields{name ? `, named by ${name.label}` : ""}
				</Text>
				<Box display="flex" flexWrap="wrap">
					{fields.map((field) => (
						<Box key={field.name} marginRight={1} marginBottom={1} paddingX={2} paddingY="2px" borderRadius="circle" border="default" backgroundColor={field.created ? palette.tokenNew : palette.token}>
							<Text size="small">
								{field.name}
								{field.created && !newTable ? " (new)" : ""}
							</Text>
						</Box>
					))}
				</Box>
				<Text size="small" textColor="light" marginTop={1}>
					Records already in the table from SpecStream are updated, not added twice.
				</Text>
			</Box>
			{message ? <Message tone="error">{message}</Message> : null}
			<Box display="flex" marginTop={2}>
				<Button onClick={onCancel} marginRight={2}>
					Not now
				</Button>
				<Button variant="primary" onClick={onAdd} disabled={!newTable && !table} flexGrow={1}>
					Add {plural(result.records.length, "record")}
				</Button>
			</Box>
		</>
	);
}
