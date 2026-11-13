// The SpecStream calls this app makes. The API key is sent only to https://api.specstream.ai.

export const SPECSTREAM_API = 'https://api.specstream.ai';
const TIMEOUT_MS = 20_000;

export type Fetch = typeof globalThis.fetch;

export class SpecStreamError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export type Reading = {
  status?: string;
  ast_hash?: string;
  read_back?: string;
  canonical_sentence?: string;
};
export type Quote = { quote_id: string; quote_hash: string; maximum_cents: number };
export type Run = { find_id?: string; state?: string; maximum_cents?: number };
export type Cell = { label?: string; column_id?: string; display?: unknown; value?: unknown };
export type RowsPage = {
  find_id: string;
  status: string;
  entitlement?: string;
  rows?: { entity_id?: string; cells?: Cell[] }[];
  flat_rows?: Record<string, unknown>[];
};

const messageOf = (status: number, body: unknown): string => {
  const error = (body as { error?: { message?: unknown } } | null)?.error;
  if (typeof error?.message === 'string' && error.message) return error.message;
  if (status === 401 || status === 403) {
    return 'SpecStream refused the API key. Paste a current key in the app settings.';
  }
  if (status === 402) return 'The SpecStream account has no credit left.';
  if (status === 429) return 'SpecStream is limiting requests for this account. Try again in a minute.';
  return `SpecStream answered ${status}.`;
};

export const createSpecStream = (apiKey: string, fetchImpl: Fetch = globalThis.fetch) => {
  const call = async <T>(method: string, path: string, body?: unknown): Promise<T> => {
    const response = await fetchImpl(`${SPECSTREAM_API}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${apiKey}`,
        Accept: 'application/json',
        'User-Agent': 'specstream-twenty-app',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    const parsed: unknown = await response.json().catch(() => null);
    if (!response.ok) throw new SpecStreamError(response.status, messageOf(response.status, parsed));
    return parsed as T;
  };

  return {
    // The key's account. Used by the health check only; nothing is charged.
    account: () => call<unknown>('GET', '/v1/account'),
    read: (q: string) => call<Reading>('POST', '/v1/parse', { q, locale: 'en-US' }),
    quote: (astHash: string) =>
      call<Quote>('POST', '/v1/capacity/quotes', {
        ast_hash: astHash,
        operation: 'find',
        requested_units: 1,
      }),
    run: (quote: Quote, key: string) =>
      call<Run>('POST', '/v1/capacity/executions', {
        quote_id: quote.quote_id,
        quote_hash: quote.quote_hash,
        confirm_max_cents: quote.maximum_cents,
        idempotency_key: key,
      }),
    // The run a key already started, or null when the key never ran (404).
    started: async (key: string): Promise<Run | null> => {
      try {
        return await call<Run>('GET', `/v1/capacity/requests/${encodeURIComponent(key)}`);
      } catch (error) {
        if (error instanceof SpecStreamError && error.status === 404) return null;
        throw error;
      }
    },
    rows: (findId: string) =>
      call<RowsPage>('GET', `/v1/finds/${encodeURIComponent(findId)}/rows?limit=1`),
  };
};

export type SpecStream = ReturnType<typeof createSpecStream>;
