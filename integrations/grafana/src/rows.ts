import { createDataFrame, DataFrame, FieldType } from '@grafana/data';

type Json = Record<string, any>;

function cellValue(v: any): { value: string; source: string } {
  if (v && typeof v === 'object' && !Array.isArray(v)) {
    const shown = v.display ?? v.value;
    return { value: shown == null ? '' : String(shown), source: String(v.page ?? v.source_url ?? '') };
  }
  return { value: v == null ? '' : String(v), source: '' };
}

/** Search API reply to one table: a row per result, the page each value was read from in "Source". */
export function searchFrame(refId: string, reply: Json): DataFrame {
  // The API wraps its answer in `data`.
  const body: Json = reply?.data ?? reply;
  let rows: Json[] = Array.isArray(body?.rows) ? body.rows : [];
  // A fast search reads no rows from the pages: its ranked results are the table.
  if (!rows.length && Array.isArray(body?.sources)) {
    rows = body.sources
      .filter((s: Json) => s && typeof s.url === 'string')
      .map((s: Json) => ({ name: s.title ?? s.url, snippet: s.snippet, page: s.url }));
  }
  const factNames: string[] = [];
  for (const row of rows) {
    for (const key of Object.keys(row.fields ?? {})) {
      if (!factNames.includes(key)) {
        factNames.push(key);
      }
    }
  }
  const fields = [
    { name: 'Name', type: FieldType.string, values: rows.map((r) => String(r.name ?? '')) },
    ...factNames.map((key) => ({
      name: key,
      type: FieldType.string,
      values: rows.map((r) => cellValue(r.fields?.[key]).value),
    })),
    {
      name: 'Match',
      type: FieldType.number,
      values: rows.map((r) => (typeof r.probability === 'number' ? r.probability : null)),
    },
    { name: 'Snippet', type: FieldType.string, values: rows.map((r) => String(r.snippet ?? '')) },
    {
      name: 'Source',
      type: FieldType.string,
      values: rows.map((r) => String(r.page ?? (Array.isArray(r.sources) ? (r.sources[0] ?? '') : ''))),
    },
  ];
  return createDataFrame({ refId, name: 'SpecStream search', fields });
}

/** Rows of a saved list to one table: a column per list column, and one "Source" column with the first source page. */
export function listFrame(refId: string, detail: Json): DataFrame {
  const rows: Json[] = Array.isArray(detail?.rows) ? detail.rows : [];
  const labels: string[] = [];
  const perRow = rows.map((row) => {
    const values: Record<string, string> = {};
    const sources: string[] = [];
    let cells: Json[] = row.cells ?? [];
    if (!row.cells && row.field_values) {
      cells = Object.entries<Json[]>(row.field_values)
        .filter(([, entries]) => entries && entries.length)
        .map(([id, entries]) => ({ column_id: id, ...entries[0] }));
    }
    for (const cell of cells) {
      const label = String(cell.label ?? cell.column_id ?? '');
      if (!label) {
        continue;
      }
      if (!labels.includes(label)) {
        labels.push(label);
      }
      values[label] = cell.absence ? '' : String(cell.display ?? cell.value ?? '');
      const url = cell.provenance?.source_url;
      if (url && !sources.includes(url)) {
        sources.push(url);
      }
    }
    return { values, source: sources[0] ?? '' };
  });
  const fields = [
    ...labels.map((label) => ({
      name: label,
      type: FieldType.string,
      values: perRow.map((r) => r.values[label] ?? ''),
    })),
    { name: 'Source', type: FieldType.string, values: perRow.map((r) => r.source) },
  ];
  return createDataFrame({ refId, name: String(detail?.name ?? 'SpecStream list'), fields });
}
