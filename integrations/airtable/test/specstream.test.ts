import assert from "node:assert/strict";
import { test } from "node:test";
import { type Fetch, SpecStreamClient, SpecStreamError } from "../frontend/core/specstream";

type Call = { url: string; method: string; headers: Record<string, string>; body: unknown };

function mockApi(routes: Record<string, (call: Call) => { status?: number; body: unknown }>) {
	const calls: Call[] = [];
	const fetcher: Fetch = async (url, init) => {
		const call: Call = {
			url,
			method: String(init.method),
			headers: init.headers as Record<string, string>,
			body: init.body ? JSON.parse(String(init.body)) : undefined,
		};
		calls.push(call);
		const path = url.replace("https://api.specstream.ai", "");
		const key = `${call.method} ${path.split("?")[0]}`;
		const route = routes[key];
		if (!route) return new Response(JSON.stringify({ error: { code: "not_found", message: `No route ${key}` } }), { status: 404 });
		const answer = route(call);
		return new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 });
	};
	return { calls, fetcher };
}

const READING = {
	data: {
		status: "runnable",
		ast_hash: "h_1",
		canonical_sentence: "25 coffee shops in Austin, TX with website and Google rating",
		ast: { limit: { max: 25, inferred: true } },
		chips: [
			{ chip_id: "c1", category: "type", label: "Coffee shops", status: "resolved" },
			{ chip_id: "c2", category: "place", label: "Austin, TX", status: "resolved" },
			{ chip_id: "c3", category: "predicate", label: "Rated 4.5 or better", status: "resolved" },
			{ chip_id: "c4", category: "output", label: "Website", status: "resolved" },
			{ chip_id: "c5", category: "output", label: "Google rating", status: "resolved" },
		],
	},
};

const QUOTE = {
	data: {
		quote_id: "q_1",
		quote_hash: "qh_1",
		currency: "USD",
		maximum_cents: 250,
		expires_at: new Date(Date.now() + 600_000).toISOString(),
		terms: { unit_cents: 10 },
		can_authorize: true,
	},
};

test("read, price, approve and follow a run through the public API", async () => {
	const { calls, fetcher } = mockApi({
		"POST /v1/parse": () => ({ body: READING }),
		"POST /v1/capacity/quotes": () => ({ body: QUOTE }),
		"POST /v1/capacity/executions": () => ({ status: 202, body: { data: { find_id: "fnd_1", state: "reserved", maximum_cents: 250 } } }),
		"GET /v1/finds/fnd_1": () => ({ body: { data: { status: "running", requested_count: 25, accepted_count: 7 } } }),
	});
	const client = new SpecStreamClient("ss_live_abc", { app: "airtable", fetch: fetcher });

	const reading = await client.read("  coffee shops in Austin with website and rating ");
	assert.equal(reading.runnable, true);
	assert.equal(reading.statedRows, null);
	assert.deepEqual(reading.lookingFor, ["Coffee shops", "Austin, TX"]);
	assert.deepEqual(reading.mustMeet, ["Rated 4.5 or better"]);
	assert.deepEqual(reading.bringsBack, ["Website", "Google rating"]);

	const quote = await client.quote(reading, 25);
	assert.equal(quote.maximumCents, 250);
	assert.equal(quote.unitCents, 10);

	const run = await client.approve(quote, 300);
	assert.equal(run.findId, "fnd_1");

	const progress = await client.progress("fnd_1");
	assert.deepEqual(progress, { status: "running", requested: 25, found: 7 });

	assert.equal(calls[0]?.headers.Authorization, "Bearer ss_live_abc");
	assert.deepEqual(calls[0]?.body, { q: "coffee shops in Austin with website and rating", locale: "en-US" });
	assert.deepEqual(calls[1]?.body, { ast_hash: "h_1", operation: "find", requested_units: 25 });
	assert.deepEqual(calls[2]?.body, { quote_id: "q_1", quote_hash: "qh_1", confirm_max_cents: 250, idempotency_key: "airtable-q_1" });
	for (const call of calls) assert.ok(call.url.startsWith("https://api.specstream.ai/v1/"));
});

test("a count written in the request wins over the default", async () => {
	const stated = { data: { ...READING.data, ast: { limit: { max: 40, inferred: false } } } };
	const { fetcher } = mockApi({ "POST /v1/parse": () => ({ body: stated }) });
	const reading = await new SpecStreamClient("ss_live_abc", { app: "airtable", fetch: fetcher }).read("40 coffee shops in Austin");
	assert.equal(reading.statedRows, 40);
});

test("never approves a price above the person's maximum", async () => {
	const { calls, fetcher } = mockApi({});
	const client = new SpecStreamClient("ss_live_abc", { app: "airtable", fetch: fetcher });
	const quote = {
		quoteId: "q_1",
		quoteHash: "qh_1",
		currency: "USD",
		maximumCents: 500,
		unitCents: 10,
		expiresAt: new Date(Date.now() + 60_000).toISOString(),
		canAuthorize: true,
		rows: 50,
	};
	await assert.rejects(client.approve(quote, 499), /above your maximum of \$4\.99/);
	await assert.rejects(client.approve({ ...quote, expiresAt: new Date(Date.now() - 1000).toISOString() }, 500), /price expired/);
	assert.equal(calls.length, 0);
});

test("an unclear request is never priced", async () => {
	const { calls, fetcher } = mockApi({
		"POST /v1/parse": () => ({ body: { data: { ...READING.data, status: "needs_edit" } } }),
	});
	const client = new SpecStreamClient("ss_live_abc", { app: "airtable", fetch: fetcher });
	const reading = await client.read("stuff");
	assert.equal(reading.runnable, false);
	await assert.rejects(client.quote(reading, 25), SpecStreamError);
	assert.equal(calls.length, 1);
});

test("rows follow every page until the cursor runs out", async () => {
	const row = (n: number) => ({ entity_id: `ent_${n}`, cells: [{ column_id: "name", label: "Name", value: `Shop ${n}` }] });
	const { calls, fetcher } = mockApi({
		"GET /v1/finds/fnd_1/rows": (call) =>
			call.url.includes("cursor=c2")
				? { body: { data: { find_id: "fnd_1", status: "completed", rows: [row(3)], next_cursor: null } } }
				: { body: { data: { find_id: "fnd_1", status: "completed", rows: [row(1), row(2), { bad: true }], next_cursor: "c2" } } },
	});
	const rows = await new SpecStreamClient("ss_live_abc", { app: "airtable", fetch: fetcher }).rows("fnd_1");
	assert.deepEqual(
		rows.map((r) => r.entity_id),
		["ent_1", "ent_2", "ent_3"],
	);
	assert.equal(calls.length, 2);
	assert.ok(calls[0]?.url.includes("limit=100"));
});

test("errors read as next steps", async () => {
	const { fetcher } = mockApi({
		"GET /v1/me": () => ({ status: 401, body: { error: { code: "unauthorized", message: "bad key" } } }),
		"POST /v1/capacity/executions": () => ({ status: 402, body: { error: { code: "insufficient_balance" } } }),
	});
	const client = new SpecStreamClient("ss_live_abc", { app: "airtable", fetch: fetcher });
	await assert.rejects(client.account(), /didn't accept this API key/);
	const guest = new SpecStreamClient("ss_live_abc", {
		app: "airtable",
		fetch: mockApi({ "GET /v1/me": () => ({ status: 200, body: { data: { guest: true } } }) }).fetcher,
	});
	await assert.rejects(guest.account(), /didn't accept this API key/);
	const quote = { quoteId: "q", quoteHash: "h", currency: "USD", maximumCents: 1, unitCents: null, expiresAt: "", canAuthorize: true, rows: 1 };
	await assert.rejects(client.approve(quote, 1), /balance can't cover this/);
	assert.throws(() => new SpecStreamClient("  ", { app: "airtable", fetch: fetcher }), /API key/);
});

test("past results keep only runs that can be read", async () => {
	const { fetcher } = mockApi({
		"GET /v1/workspace/collections": () => ({
			body: {
				data: {
					collections: [
						{ id: "fnd_9", name: "Austin coffee", row_count: 31, created_at: "2026-10-01T00:00:00Z" },
						{ id: "col_imported", name: "My upload", row_count: 4 },
						{ id: "col_2", find_id: "fnd_8", name: "Dentists", total: 12 },
					],
				},
			},
		}),
	});
	const past = await new SpecStreamClient("ss_live_abc", { app: "airtable", fetch: fetcher }).pastResults();
	assert.deepEqual(
		past.map((item) => [item.findId, item.rows]),
		[
			["fnd_9", 31],
			["fnd_8", 12],
		],
	);
});
