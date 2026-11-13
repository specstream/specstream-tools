"use strict";

const DEFAULT_BASE = "https://api.specstream.ai";

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

module.exports = { DEFAULT_BASE, resolveBase };
