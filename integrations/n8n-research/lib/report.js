"use strict";

const INPUT_MOST_CHARS = 15000;
const DEPTHS = ["quick", "standard", "deep"];
const LENGTHS = ["short", "standard", "long"];
const ENDED = ["completed", "failed", "cancelled", "payment_required"];

function domains(value) {
  const list = Array.isArray(value) ? value : String(value || "").split(/[\s,]+/);
  return list.map((item) => String(item).trim().toLowerCase()).filter(Boolean);
}

// The body of POST /v1/research. A field left empty is not sent, so the API's own default holds.
function reportBody(input, depth, options) {
  const question = String(input || "").trim();
  if (!question) throw new Error("Write the question the report answers.");
  if (question.length > INPUT_MOST_CHARS) {
    throw new Error(`The question holds ${question.length} characters. The most is ${INPUT_MOST_CHARS}.`);
  }
  if (!DEPTHS.includes(depth)) throw new Error(`Depth must be one of: ${DEPTHS.join(", ")}.`);
  const body = { input: question, depth };
  const chosen = options || {};
  if (chosen.length) {
    if (!LENGTHS.includes(chosen.length)) throw new Error(`Length must be one of: ${LENGTHS.join(", ")}.`);
    body.length = chosen.length;
  }
  const language = String(chosen.language || "").trim();
  if (language) body.language = language;
  const include = domains(chosen.includeDomains);
  if (include.length) body.include_domains = include;
  const exclude = domains(chosen.excludeDomains);
  if (exclude.length) body.exclude_domains = exclude;
  const after = String(chosen.afterDate || "").trim();
  if (after) {
    const day = after.slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) throw new Error("Pages Published After must be a date, such as 2026-01-31.");
    body.after_date = day;
  }
  let schema = typeof chosen.jsonSchema === "string" ? chosen.jsonSchema.trim() : chosen.jsonSchema;
  if (typeof schema === "string" && schema) {
    try {
      schema = JSON.parse(schema);
    } catch {
      throw new Error("JSON Schema is not valid JSON.");
    }
  }
  if (schema) {
    if (typeof schema !== "object" || Array.isArray(schema)) throw new Error("JSON Schema must be a JSON object.");
    if (Object.keys(schema).length) body.output = { type: "json", schema };
  }
  return body;
}

// One key per execution, node and item: n8n's retry of a failed step gets the same report, never a second one.
function idempotencyKey(executionId, nodeId, itemIndex) {
  const parts = [executionId, nodeId, itemIndex].map((part) => String(part == null ? "" : part).replace(/[^A-Za-z0-9_.-]/g, "_"));
  return ("n8n-" + parts.join("-")).slice(0, 128);
}

function hasEnded(run) {
  return ENDED.includes(String(run && run.status));
}

// Why a report that ended has no text, in words for the person who built the workflow.
function endedWithoutReport(run) {
  const id = String(run.id);
  if (run.status === "payment_required") {
    return `Your SpecStream balance does not hold the price of report ${id}. Add credit in your SpecStream workspace, then run the step again.`;
  }
  if (run.status === "cancelled") return `Report ${id} was cancelled. A cancelled report is not charged.`;
  const reason = run.error && run.error.message ? ` ${run.error.message}` : "";
  return `Report ${id} failed.${reason}`;
}

module.exports = { DEPTHS, ENDED, INPUT_MOST_CHARS, LENGTHS, endedWithoutReport, hasEnded, idempotencyKey, reportBody };
