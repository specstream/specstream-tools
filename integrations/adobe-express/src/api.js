// The SpecStream calls and the text the add-on puts in a design. No Adobe code here, so Node can test it.
export const API = 'https://api.specstream.ai';
export const MAX_URLS = 20;
export const MAX_QUESTION = 2000;
// A design is not a document: a page's text is cut here before it goes on the canvas.
export const PAGE_LIMIT = 4000;
export const TIMEOUT_MS = 90000;

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function failure(status, body) {
  if (status === 401 || status === 403) {
    return new ApiError('The API key was not accepted. Check it in your SpecStream account.', status);
  }
  if (status === 402) {
    return new ApiError('The balance is empty. Add credit in your SpecStream account.', status);
  }
  if (status === 429) {
    return new ApiError('Too many calls at once. Try again in a moment.', status);
  }
  const detail = body && (body.detail || body.message || body.error);
  return new ApiError(typeof detail === 'string' ? detail : `SpecStream answered ${status}.`, status);
}

async function call(f, url, key, init) {
  const k = String(key || '').trim();
  if (!k) throw new ApiError('Paste your SpecStream API key first.', 0);
  let res;
  try {
    // One call, no retry, and it ends after TIMEOUT_MS so the panel never waits without end.
    const signal = typeof AbortSignal !== 'undefined' && AbortSignal.timeout ? AbortSignal.timeout(TIMEOUT_MS) : undefined;
    res = await f(url, { ...init, signal, headers: { Authorization: `Bearer ${k}`, ...(init.headers || {}) } });
  } catch (e) {
    throw new ApiError('SpecStream could not be reached. Check the connection and try again.', 0);
  }
  let body = null;
  try {
    body = await res.json();
  } catch (e) {
    body = null;
  }
  if (!res.ok) throw failure(res.status, body);
  return body;
}

// The Search API's speed: 'fast' returns ranked results in about a second at $1 per 1,000 searches.
// Left out, nothing is sent and the API's default search runs.
export const SPEEDS = ['fast', 'default'];

export function searchUrl(q, speed) {
  const tail = speed ? `&speed=${speed}` : '';
  return `${API}/v1/web-search?q=${encodeURIComponent(q.trim())}${tail}`;
}

export async function webSearch(f, key, q, speed) {
  const query = String(q || '').trim();
  if (!query) throw new ApiError('Type a question first.', 0);
  if (query.length > MAX_QUESTION) throw new ApiError('Keep the question under 2,000 characters.', 0);
  if (speed && SPEEDS.indexOf(speed) === -1) throw new ApiError('Speed is fast or default.', 0);
  const body = await call(f, searchUrl(query, speed), key, { method: 'GET' });
  const sources = Array.isArray(body && body.sources) ? body.sources : [];
  return sources
    .filter((s) => s && typeof s.url === 'string')
    .map((s) => ({
      title: String(s.title || s.site || s.url),
      url: s.url,
      snippet: String(s.snippet || ''),
      site: String(s.site || ''),
    }));
}

export function parseUrls(input) {
  const seen = [];
  for (const raw of String(input || '').split(/[\s,]+/)) {
    const u = raw.trim();
    if (/^https?:\/\/\S+$/i.test(u) && seen.indexOf(u) === -1) seen.push(u);
  }
  return seen;
}

export async function extract(f, key, urls) {
  if (urls.length === 0) throw new ApiError('Add at least one http or https URL.', 0);
  if (urls.length > MAX_URLS) throw new ApiError(`Send up to ${MAX_URLS} URLs at a time.`, 0);
  const body = await call(f, `${API}/v1/extract`, key, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ urls, format: 'markdown' }),
  });
  const results = Array.isArray(body && body.results) ? body.results : [];
  return results.map((r) => ({
    url: String(r.url || ''),
    title: String(r.title || ''),
    status: String(r.status || ''),
    text: String(r.text || ''),
  }));
}

// One line of the text block: `head` lines are set larger than the rest.
function line(text, head) {
  return { text: String(text).replace(/\s*[\r\n]+\s*/g, ' ').trim(), head: !!head };
}

// The search rows the user ticked, as lines: title, snippet, source URL, with an empty line between rows.
export function hitsToLines(hits) {
  const out = [];
  hits.forEach((h, i) => {
    if (i > 0) out.push(line('', false));
    out.push(line(h.title, true));
    if (h.snippet) out.push(line(h.snippet, false));
    out.push(line(h.url, false));
  });
  return out;
}

// Pages as lines: title, source URL, then the text, cut at PAGE_LIMIT characters a page.
export function pagesToLines(pages) {
  const out = [];
  pages.forEach((p, i) => {
    if (i > 0) out.push(line('', false));
    out.push(line(p.title || p.url, true));
    if (p.title) out.push(line(p.url, false));
    if (p.status !== 'ok' || !p.text) {
      out.push(line(`No text (${p.status || 'empty'}).`, false));
      return;
    }
    const text = p.text.length > PAGE_LIMIT ? `${p.text.slice(0, PAGE_LIMIT)}...` : p.text;
    for (const para of text.split(/\n+/)) {
      if (para.trim()) out.push(line(para, false));
    }
  });
  return out;
}

// What the document side needs: one string, and the character ranges of the larger lines.
export function linesToBlock(lines) {
  let text = '';
  const heads = [];
  lines.forEach((l, i) => {
    if (i > 0) text += '\n';
    if (l.head && l.text.length > 0) heads.push({ start: text.length, length: l.text.length });
    text += l.text;
  });
  return { text, heads };
}
