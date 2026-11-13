import type { RowsPage } from './api';

const MAX_LENGTH = 6000;
const text = (value: unknown): string =>
  value == null ? '' : typeof value === 'string' ? value.trim() : JSON.stringify(value);

// One line per fact, with the page it was read from: "Employees: 120 (https://acme.com/about)".
// Null when the list holds no row or the row holds no value.
export const researchText = (page: RowsPage, now: Date = new Date()): string | null => {
  const row = page.rows?.[0];
  if (!row) return null;
  const flat = page.flat_rows?.[0] ?? {};
  const lines: string[] = [];
  for (const cell of row.cells ?? []) {
    const label = text(cell.label ?? cell.column_id);
    const value = text(cell.display ?? cell.value);
    if (!label || !value) continue;
    const source = text(flat[`${label}_source`] ?? flat[`${text(cell.column_id)}_source`]);
    lines.push(source ? `${label}: ${value} (${source})` : `${label}: ${value}`);
  }
  if (lines.length === 0) return null;
  const rowSource = text(flat.source_url);
  if (rowSource) lines.push(`Source: ${rowSource}`);
  lines.push(`Checked by SpecStream on ${now.toISOString().slice(0, 10)}`);
  const joined = lines.join('\n');
  return joined.length > MAX_LENGTH ? `${joined.slice(0, MAX_LENGTH - 1)}…` : joined;
};
