const BASE = "https://api.specstream.ai";

async function call(fetchImpl, key, method, path, body, extraHeaders) {
  const res = await fetchImpl(BASE + path, {
    method,
    headers: {
      Authorization: "Bearer " + key,
      Accept: "application/json",
      "User-Agent": "specstream-node-red/1.0.0",
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(extraHeaders || {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch (e) { data = { raw: text }; }
  if (!res.ok) {
    const err = new Error("SpecStream " + res.status);
    err.status = res.status;
    err.body = data;
    throw err;
  }
  return data;
}

// speed "fast" returns the first ranked results in about a second, at $1 per 1,000 searches;
// left out, the API's default search runs ($5 per 1,000).
function search(fetchImpl, key, query, limit, speed) {
  if (speed && speed !== "fast" && speed !== "default") {
    return Promise.reject(new Error('speed must be "fast" or "default"'));
  }
  const p = new URLSearchParams({ q: query });
  if (limit) p.set("limit", String(limit));
  if (speed) p.set("speed", speed);
  return call(fetchImpl, key, "GET", "/v1/web-search?" + p.toString());
}

function extract(fetchImpl, key, urls) {
  return call(fetchImpl, key, "POST", "/v1/extract", { urls: urls.slice(0, 20) });
}

const DEPTHS = ["quick", "standard", "deep"];
const ENDED = ["completed", "failed", "cancelled", "payment_required"];
const QUESTION_MOST_CHARS = 15000;

// The body of POST /v1/research. A field left empty is not sent, so the API's own default holds.
function researchBody(question, depth) {
  const input = String(question == null ? "" : question).trim();
  if (!input) throw new Error("No question: set msg.payload or the Question field");
  if (input.length > QUESTION_MOST_CHARS) {
    throw new Error("The question holds " + input.length + " characters. The most is " + QUESTION_MOST_CHARS + ".");
  }
  const chosen = depth || "standard";
  if (!DEPTHS.includes(chosen)) throw new Error("Depth must be one of: " + DEPTHS.join(", ") + ".");
  return { input, depth: chosen };
}

// One key per message and node: the same message sent again gets the same report, never a second one.
function idempotencyKey(msgId, nodeId) {
  const parts = [msgId, nodeId].map((part) => String(part == null ? "" : part).replace(/[^A-Za-z0-9_.-]/g, "_"));
  return ("node-red-" + parts.join("-")).slice(0, 128);
}

function startResearch(fetchImpl, key, body, idempotency) {
  return call(fetchImpl, key, "POST", "/v1/research", body, idempotency ? { "Idempotency-Key": idempotency } : undefined);
}

function getResearch(fetchImpl, key, id) {
  return call(fetchImpl, key, "GET", "/v1/research/" + encodeURIComponent(id));
}

// Why a report that ended has no text, in words for the person who built the flow.
function endedWithoutReport(run) {
  const id = String(run.id);
  if (run.status === "payment_required") {
    return "Your SpecStream balance does not hold the price of report " + id + ". Add credit in your SpecStream workspace, then send the message again.";
  }
  if (run.status === "cancelled") return "Report " + id + " was cancelled. A cancelled report is not charged.";
  const reason = run.error && run.error.message ? " " + run.error.message : "";
  return "Report " + id + " failed." + reason;
}

const pauseFor = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Reads the report until it ends or the wait is over. A report still being written after the wait is not lost:
// the error names its ID, and a message with msg.reportId reads it later.
async function waitForResearch(fetchImpl, key, id, waitMinutes, everySeconds, sleep) {
  const minutes = Math.max(1, Number(waitMinutes) || 15);
  const pause = Math.max(1, Number(everySeconds) || 5) * 1000;
  const until = Date.now() + minutes * 60000;
  for (;;) {
    const run = await getResearch(fetchImpl, key, id);
    if (ENDED.includes(String(run && run.status))) {
      if (run.status !== "completed") throw new Error(endedWithoutReport(run));
      return run;
    }
    if (Date.now() + pause > until) {
      const err = new Error("Report " + id + " is still being written after " + minutes + " minutes. Read it later: send a message with msg.reportId set to " + id + ".");
      err.reportId = id;
      throw err;
    }
    await (sleep || pauseFor)(pause);
  }
}

module.exports = {
  DEPTHS, search, extract, researchBody, idempotencyKey, startResearch, getResearch, waitForResearch, endedWithoutReport,
};
