// The part of the extension that knows SpecStream. It has no Netlify import, so its tests run with plain Node.

export const API_BASE = "https://api.specstream.ai";
export const KEY_VARIABLE = "SPECSTREAM_API_KEY";
export const KEY_PREFIX = "ss_live_";
export const USER_AGENT = "specstream-netlify-extension/0.1.0";
const CHECK_TIMEOUT_MS = 10_000;

export type KeyCheck = { ok: true; email: string | null } | { ok: false; message: string };

type FetchLike = (url: string, init: Record<string, unknown>) => Promise<{
  status: number;
  json: () => Promise<unknown>;
}>;

/** What is wrong with the text a person pasted as a key, or null when it has the shape of a key. */
export function keyProblem(key: string): string | null {
  const text = key.trim();
  if (text === "") {
    return "Paste a SpecStream API key.";
  }
  if (!text.startsWith(KEY_PREFIX) || text.length <= KEY_PREFIX.length || /\s/.test(text)) {
    return `A SpecStream API key starts with ${KEY_PREFIX}. Copy it again from Agents & API in your workspace.`;
  }
  return null;
}

/** The last four characters, the only part of a key the extension keeps or shows. */
export function keyHint(key: string): string {
  return `${KEY_PREFIX}...${key.trim().slice(-4)}`;
}

/**
 * Ask SpecStream who the key belongs to. GET /v1/me is free: it runs no search and reads no page.
 * The key goes only to api.specstream.ai, in the Authorization header.
 */
export async function checkKey(key: string, fetchImpl: FetchLike = fetch as unknown as FetchLike): Promise<KeyCheck> {
  const problem = keyProblem(key);
  if (problem !== null) {
    return { ok: false, message: problem };
  }
  let response;
  try {
    response = await fetchImpl(`${API_BASE}/v1/me`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${key.trim()}`,
        Accept: "application/json",
        "User-Agent": USER_AGENT,
      },
      signal: AbortSignal.timeout(CHECK_TIMEOUT_MS),
    });
  } catch {
    return { ok: false, message: "SpecStream did not answer. The key was not saved. Try again in a minute." };
  }
  if (response.status === 401 || response.status === 403) {
    return { ok: false, message: "SpecStream did not accept this key. Make a new one under Agents & API." };
  }
  if (response.status !== 200) {
    return {
      ok: false,
      message: `SpecStream answered with status ${response.status}. The key was not saved. Try again in a minute.`,
    };
  }
  let email: string | null = null;
  try {
    const body = (await response.json()) as { data?: { email?: unknown }; email?: unknown } | null;
    const found = body?.data?.email ?? body?.email;
    email = typeof found === "string" && found !== "" ? found : null;
  } catch {
    email = null;
  }
  return { ok: true, email };
}

/** The one line the build log shows, or null when the team has not connected a key. */
export function buildLine(env: Record<string, string | undefined>): string | null {
  if (!env[KEY_VARIABLE]) {
    return null;
  }
  return `SpecStream: this build and the site's functions can read the API key from ${KEY_VARIABLE}.`;
}
