// Turns SpecStream list rows into Coda rows: one column per fact, each with the page it was read from.

// Workspace buttons, not facts.
const BUTTON_COLUMNS = new Set(["matches", "open"]);

export interface Column {
  id: string;
  key: string;
  label: string;
}

export interface Cell {
  value: string | null;
  source: string | null;
}

export interface Record {
  recordId: string;
  entityId: string | null;
  cells: Map<string, Cell & { label: string }>;
}

// A Coda property key for a SpecStream column ID: "job.location_countries" becomes "job_location_countries".
export function columnKey(columnId: string): string {
  const key = columnId.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  return key && !/^[0-9]/.test(key) ? key : `column_${key}`;
}

function plainCell(cell: any): Cell & { label: string } {
  const provenance = (cell && cell.provenance) || {};
  const shown = cell.display ?? (cell.value == null ? null : String(cell.value));
  return {
    label: String(cell.label || cell.column_id || ""),
    value: cell.absence ? null : shown,
    source: typeof provenance.source_url === "string" ? provenance.source_url : null,
  };
}

// Records SpecStream found have an `ordinal` and `cells`; rows of a list you imported have an `id` and the
// columns you `provided`; rows of a combined list have an `id` and each column's values in `field_values`,
// the value the list shows first.
export function readRecord(row: any): Record {
  const cells = new Map<string, Cell & { label: string }>();
  if (row.provided && typeof row.provided === "object") {
    for (const [key, value] of Object.entries(row.provided)) {
      cells.set(key, { label: key, value: value == null ? null : String(value), source: null });
    }
  } else if (row.field_values && typeof row.field_values === "object") {
    for (const [key, values] of Object.entries(row.field_values as { [key: string]: any[] })) {
      if (Array.isArray(values) && values.length && !BUTTON_COLUMNS.has(key)) cells.set(key, plainCell(values[0]));
    }
  } else {
    for (const cell of row.cells || []) {
      if (cell && cell.column_id && !BUTTON_COLUMNS.has(cell.column_id)) cells.set(cell.column_id, plainCell(cell));
    }
  }
  const fromSource = (row.sources || []).map((s: any) => s && s.row && s.row.entity_id).find(Boolean);
  return {
    recordId: String(row.ordinal != null ? row.ordinal : row.id),
    entityId: row.entity_id || fromSource || null,
    cells,
  };
}

// The list's columns in the order its records first show them.
export function columnsOf(rows: any[]): Column[] {
  const columns = new Map<string, Column>();
  const keys = new Set(["record_id", "entity_id"]);
  for (const row of rows) {
    for (const [id, cell] of readRecord(row).cells) {
      if (columns.has(id)) continue;
      let key = columnKey(id);
      while (keys.has(key)) key += "_";
      keys.add(key);
      columns.set(id, { id, key, label: cell.label || id });
    }
  }
  return [...columns.values()];
}

// The columns a new table shows: each column that has a value in some record, followed by its source
// when some value has one, up to five columns. Empty columns stay in the table, hidden.
export function shownColumns(records: Record[], columns: Column[], limit = 5): string[] {
  const has = (column: Column, part: "value" | "source") =>
    records.some((record) => {
      const cell = record.cells.get(column.id);
      return Boolean(cell && cell[part]);
    });
  return columns
    .filter((column) => has(column, "value"))
    .slice(0, limit)
    .flatMap((column) => (has(column, "source") ? [column.key, `${column.key}_source`] : [column.key]));
}

// One Coda row: the record's IDs, then each value and the page it came from.
export function codaRow(record: Record, columns: Column[]): { [key: string]: string | null } {
  const out: { [key: string]: string | null } = { record_id: record.recordId, entity_id: record.entityId };
  for (const column of columns) {
    const cell = record.cells.get(column.id);
    out[column.key] = cell ? cell.value : null;
    out[`${column.key}_source`] = cell ? cell.source : null;
  }
  return out;
}

// A list ID from its workspace address, as Coda keeps it for each synced table.
export function listIdOf(url: string): string {
  const match = /\/workspace\/collections\/([A-Za-z0-9_-]+)/.exec(url);
  if (!match) throw new Error("Choose a list from your SpecStream workspace.");
  return match[1];
}

// The same request, count and maximum within the same UTC hour get one run, so a second press never buys
// the list twice. FNV-1a, 64 bits: a key, not a secret.
export function runKey(request: string, results: number, maxCents: number, now: Date): string {
  const text = `${request}|${results}|${maxCents}|${now.toISOString().slice(0, 13)}`;
  let hash = BigInt("0xcbf29ce484222325");
  const prime = BigInt("0x100000001b3");
  const mask = (BigInt(1) << BigInt(64)) - BigInt(1);
  // UTF-8 bytes without TextEncoder, which the Pack runtime may not have.
  const utf8 = encodeURIComponent(text).replace(/%([0-9A-F]{2})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
  for (let i = 0; i < utf8.length; i++) {
    hash = ((hash ^ BigInt(utf8.charCodeAt(i))) * prime) & mask;
  }
  return `coda-${hash.toString(16).padStart(16, "0")}`;
}

export function dollars(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

// The reading with the number of results being priced: "10 roofers in Austin…", not the request's own 25.
export function withCount(said: string, results: number): string {
  return /^\d[\d,]*\s/.test(said) ? said.replace(/^\d[\d,]*/, String(results)) : said;
}
