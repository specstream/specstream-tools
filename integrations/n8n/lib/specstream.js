"use strict";

const { createHash } = require("node:crypto");

const DEFAULT_BASE = "https://api.specstream.ai";
// Fields every row carries; a column with the same name is renamed so it can't overwrite them.
const RESERVED = new Set(["id", "list_id", "list_link", "position", "source_url", "checked_at", "list_status", "__proto__"]);

// The API key goes only to https://api.specstream.ai, so a credential pointed at plain http or another host is refused.
function resolveBase(apiBase) {
  const raw = String(apiBase || DEFAULT_BASE).trim().replace(/\/+$/, "");
  let url;
  try {
    url = new URL(raw);
  } catch {
    url = null;
  }
  if (!url || url.origin !== DEFAULT_BASE || url.username || url.password || url.pathname !== "/" || url.search || url.hash) {
    throw new Error(`The API Base URL must be ${DEFAULT_BASE}, so your API key is sent only there and always encrypted.`);
  }
  return DEFAULT_BASE;
}

// The same request, count and price within the same UTC hour share one key, so a retry after a lost response
// reaches the list that already started instead of buying another. A key typed in the node wins.
function runKey({ request, count, maxPrice, override, now = new Date() }) {
  const given = String(override == null ? "" : override).trim();
  if (given) return given;
  const hour = now.toISOString().slice(0, 13);
  const digest = createHash("sha256").update(`${request}|${count}|${maxPrice}|${hour}`).digest("hex");
  return `n8n-${digest.slice(0, 32)}`;
}

// Built-in fields always win: a column named like one, or like an earlier column, gets " (column)" added.
function columnName(label, taken) {
  if (!RESERVED.has(label) && !taken.has(label)) return label;
  let name = `${label} (column)`;
  for (let n = 2; RESERVED.has(name) || taken.has(name); n++) name = `${label} (column ${n})`;
  return name;
}

// The API's flat row for each record of a page or a delivery, by the row ID both carry.
function flatRowsById(flatRows) {
  return new Map((flatRows || []).map((flat) => [String(flat.id), flat]));
}

// Each value's page in the API's flat row: <field>_source beside the <field> it belongs to.
function sourcesOf(flat) {
  const sources = {};
  for (const [key, value] of Object.entries(flat || {})) {
    if (key.endsWith("_source") && Object.hasOwn(flat, key.slice(0, -7))) sources[key] = value;
  }
  return sources;
}

// One row as flat fields: each column's label holds what the list shows. The page of each value
// (<field>_source) and of the fact that put the row in the list (source_url, checked_at) come from
// the API's flat row, so every tool shows the same pages.
function flattenRow(listId, record, flat) {
  const row = {
    id: `${listId}:${String(record.entity_id)}`,
    list_id: listId,
    list_link: `https://specstream.ai/workspace/collections/${listId}`,
    position: record.ordinal,
  };
  const sources = sourcesOf(flat);
  const taken = new Set(Object.keys(sources));
  for (const cell of record.cells || []) {
    const label = String(cell.label || cell.column_id || "").trim();
    if (!label) continue;
    const name = columnName(label, taken);
    taken.add(name);
    row[name] = cell.display ?? cell.value ?? "";
  }
  Object.assign(row, sources);
  row.source_url = (flat && flat.source_url) || "";
  row.checked_at = (flat && flat.checked_at) || "";
  return row;
}

// True only when the API answered 404. n8n wraps the HTTP error, so the status is read from the error
// and from the errors it wraps.
function isNotFound(error) {
  for (let current = error, depth = 0; current && depth < 5; current = current.cause, depth++) {
    const status = current.httpCode ?? current.statusCode ?? current.status ?? (current.response && current.response.status);
    if (status != null) return String(status) === "404";
  }
  return false;
}

module.exports = { DEFAULT_BASE, columnName, flatRowsById, flattenRow, isNotFound, resolveBase, runKey };
