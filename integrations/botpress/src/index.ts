import * as sdk from '@botpress/sdk'
import * as bp from '.botpress'

const API = 'https://api.specstream.ai'

type Json = Record<string, any>

async function call(apiKey: string, method: 'GET' | 'POST', path: string, body?: Json): Promise<Json> {
  const response = await fetch(API + path, {
    method,
    headers: {
      Authorization: /^bearer /i.test(apiKey) ? apiKey : `Bearer ${apiKey}`,
      Accept: 'application/json',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const payload = ((await response.json().catch(() => ({}))) ?? {}) as Json
  if (!response.ok) {
    const message = payload?.error?.message ?? payload?.detail ?? `SpecStream answered ${response.status}`
    if (response.status === 401) throw new sdk.RuntimeError('SpecStream did not accept this API key. Create one under Agents & API at specstream.ai.')
    throw new sdk.RuntimeError(String(message))
  }
  return payload.data ?? payload
}

const money = (cents: number, currency = 'USD') =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(cents / 100)

export default new bp.Integration({
  register: async ({ ctx }) => {
    await call(ctx.configuration.apiKey, 'GET', '/v1/me')
  },
  unregister: async () => {},
  actions: {
    getPrice: async ({ ctx, input }) => {
      const reading = await call(ctx.configuration.apiKey, 'POST', '/v1/parse', { q: input.request, locale: 'en-US' })
      if (reading.status !== 'runnable' || !reading.ast_hash) {
        throw new sdk.RuntimeError(
          reading.notice ?? 'SpecStream needs a clearer request: add the place, or what every result must meet.'
        )
      }
      const quote = await call(ctx.configuration.apiKey, 'POST', '/v1/capacity/quotes', {
        ast_hash: reading.ast_hash,
        operation: 'find',
        requested_units: input.rows ?? 25,
      })
      return {
        reading: String(reading.read_back ?? reading.canonical_sentence ?? input.request).replace(/^\d[\d,]*(?=\s)/, String(input.rows ?? 25)),
        quoteId: String(quote.quote_id),
        quoteHash: String(quote.quote_hash),
        maximumCents: Number(quote.maximum_cents),
        price: money(Number(quote.maximum_cents), quote.currency ?? 'USD'),
        expiresAt: String(quote.expires_at ?? ''),
      }
    },
    approveAndRun: async ({ ctx, input }) => {
      const cap = Math.round((ctx.configuration.maxPriceUsd ?? 5) * 100)
      if (input.approvedCents > cap) {
        throw new sdk.RuntimeError(
          `This costs up to ${money(input.approvedCents)}, above this bot's limit of ${money(cap)}. Raise the limit in the integration settings or ask for fewer rows.`
        )
      }
      const run = await call(ctx.configuration.apiKey, 'POST', '/v1/capacity/executions', {
        quote_id: input.quoteId,
        quote_hash: input.quoteHash,
        confirm_max_cents: input.approvedCents,
        idempotency_key: `botpress-${input.quoteId}`.slice(0, 128),
      })
      return { findId: String(run.find_id), state: String(run.state ?? 'running') }
    },
    getRows: async ({ ctx, input }) => {
      const query = new URLSearchParams({ limit: String(input.limit ?? 25) })
      if (input.cursor) query.set('cursor', input.cursor)
      const page = await call(ctx.configuration.apiKey, 'GET', `/v1/finds/${encodeURIComponent(input.findId)}/rows?${query}`)
      const rows = (Array.isArray(page.rows) ? page.rows : []).map((row: Json) => ({
        id: String(row.entity_id),
        cells: (Array.isArray(row.cells) ? row.cells : []).map((cell: Json) => ({
          field: String(cell.label ?? cell.column_id ?? ''),
          value: cell.display == null && cell.value == null ? '' : String(cell.display ?? cell.value),
          sourceUrl: cell.provenance?.source_url ?? undefined,
        })),
      }))
      return {
        status: String(page.status ?? 'running'),
        acceptedCount: Number(page.accepted_count ?? rows.length),
        rows,
        nextCursor: page.next_cursor ?? undefined,
      }
    },
  },
  channels: {},
  handler: async () => {},
})
