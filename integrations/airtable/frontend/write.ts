import type { Base, Field, FieldType, Table } from "@airtable/blocks/models";
import { type AcceptedRow } from "./core/specstream";
import { nameColumn, tableOf } from "./core/records";
import { type AirtableType, batches, cellsFor, ID_FIELD, planFields, type Target } from "./plan";

export type WriteProgress = { done: number; total: number };

export type WriteResult = { table: Table; added: number; updated: number; createdFields: string[] };

export class WriteError extends Error {}

function existingFields(table: Table) {
	return table.fields.map((field) => ({ id: field.id, name: field.name, type: field.type as string, computed: field.isComputed }));
}

/** The table name Airtable will accept: unique in the base and not empty. */
export function freeTableName(base: Base, wanted: string): string {
	const taken = new Set(base.tables.map((table) => table.name.toLowerCase()));
	const name = wanted.replace(/\s+/g, " ").trim().slice(0, 80) || "SpecStream results";
	let candidate = name;
	for (let n = 2; taken.has(candidate.toLowerCase()); n += 1) candidate = `${name} (${n})`;
	return candidate;
}

async function createTable(base: Base, name: string, targets: Target[], nameKey: string | null): Promise<Table> {
	const ordered = [...targets].sort((a, b) => (a.key === nameKey ? -1 : b.key === nameKey ? 1 : 0));
	const fields = ordered.flatMap((target) =>
		target.create ? [{ name: target.create.name, type: target.create.type as FieldType, options: target.create.options }] : [],
	);
	const check = base.checkPermissionsForCreateTable(name, fields);
	if (!check.hasPermission) throw new WriteError(`You can't create tables in this base. ${check.reasonDisplayString}`);
	return base.createTableAsync(name, fields);
}

async function createFields(table: Table, targets: Target[]): Promise<string[]> {
	const created: string[] = [];
	for (const target of targets) {
		if (!target.create) continue;
		const { name, type, options } = target.create;
		const check = table.checkPermissionsForCreateField(name, type as FieldType, options);
		if (!check.hasPermission) {
			throw new WriteError(`The extension needs to add the field "${name}" to ${table.name}. ${check.reasonDisplayString}`);
		}
		await table.createFieldAsync(name, type as FieldType, options);
		created.push(name);
	}
	return created;
}

function resolve(table: Table, targets: Target[]): Array<{ key: string; fieldId: string; type: AirtableType }> {
	return targets.flatMap((target) => {
		const name = target.field?.name ?? target.create?.name;
		const field: Field | null = target.field ? table.getFieldByIdIfExists(target.field.id) : name ? table.getFieldByNameIfExists(name) : null;
		return field ? [{ key: target.key, fieldId: field.id, type: field.type as AirtableType }] : [];
	});
}

/**
 * Adds every result to the table, creating the fields it needs first. A result already in the
 * table (same SpecStream ID) is updated in place, so adding the same results again refreshes
 * them instead of duplicating them.
 */
export async function writeResults(
	base: Base,
	destination: { table: Table } | { newTableName: string },
	rows: AcceptedRow[],
	onProgress: (progress: WriteProgress) => void,
): Promise<WriteResult> {
	const result = tableOf(rows);
	if (!result.records.length) throw new WriteError("This run has no results to add.");
	const nameKey = nameColumn(result)?.id ?? null;

	let table: Table;
	let createdFields: string[];
	if ("table" in destination) {
		table = destination.table;
		const primary = table.primaryField;
		const plan = planFields(result, existingFields(table), {
			primary: { id: primary.id, name: primary.name, type: primary.type as string, computed: primary.isComputed },
		});
		createdFields = await createFields(table, plan.targets);
		table = base.getTableById(table.id);
		const targets = resolve(table, plan.targets);
		return { ...(await fill(table, targets, result.records, onProgress)), table, createdFields };
	}
	const plan = planFields(result, []);
	table = await createTable(base, freeTableName(base, destination.newTableName), plan.targets, nameKey);
	createdFields = plan.targets.flatMap((target) => (target.create ? [target.create.name] : []));
	const targets = resolve(table, plan.targets);
	return { ...(await fill(table, targets, result.records, onProgress)), table, createdFields };
}

async function fill(
	table: Table,
	targets: Array<{ key: string; fieldId: string; type: AirtableType }>,
	records: ReturnType<typeof tableOf>["records"],
	onProgress: (progress: WriteProgress) => void,
): Promise<{ added: number; updated: number }> {
	const idField = table.getFieldByNameIfExists(ID_FIELD);
	const known = new Map<string, string>();
	if (idField) {
		const query = await table.selectRecordsAsync({ fields: [idField] });
		try {
			for (const record of query.records) {
				const id = record.getCellValueAsString(idField);
				if (id) known.set(id, record.id);
			}
		} finally {
			query.unloadData();
		}
	}

	const creates: Array<{ fields: Record<string, unknown> }> = [];
	const updates: Array<{ id: string; fields: Record<string, unknown> }> = [];
	for (const record of records) {
		const fields = cellsFor(record, targets);
		const existing = known.get(record.id);
		if (existing) updates.push({ id: existing, fields });
		else creates.push({ fields });
	}

	if (creates.length && !table.hasPermissionToCreateRecords()) {
		throw new WriteError(`You can't add records to ${table.name}. Ask a base creator for editor access.`);
	}
	if (updates.length && !table.hasPermissionToUpdateRecords()) {
		throw new WriteError(`You can't edit records in ${table.name}. Ask a base creator for editor access.`);
	}

	const total = creates.length + updates.length;
	let done = 0;
	onProgress({ done, total });
	for (const batch of batches(creates)) {
		await table.createRecordsAsync(batch);
		done += batch.length;
		onProgress({ done, total });
	}
	for (const batch of batches(updates)) {
		await table.updateRecordsAsync(batch);
		done += batch.length;
		onProgress({ done, total });
	}
	return { added: creates.length, updated: updates.length };
}
