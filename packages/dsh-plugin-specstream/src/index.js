// SpecStream as the search and fetch provider of DeepSeek Harness's web seam (ctx.web).
//
// The harness's own web_search and web_fetch tools call ctx.web, which runs the provider
// that the `web` row's config names. This plugin registers a search provider and a fetch
// provider under the id `specstream`, and its bundle patch (cordis.patch.yml) selects the
// search provider, so web_search answers from GET /v1/web-search once the plugin is added.
// Fetch stays on the harness's local fetcher unless the user selects `specstream` for it.
//
// It also registers two tools with the tool registry (ctx.tools): specstream_research starts a
// research report (POST /v1/research) and waits for it, and specstream_research_result reads a
// report by its id when the wait ended first.
//
// The plugin imports nothing: the seam's provider contract and a registry-ready tool definition
// are plain objects, so it loads in every harness build that has ctx.web and ctx.tools, whatever
// the version of its packages.

export const name = 'specstream'

export const inject = ['web', 'tools']

export const PROVIDER_ID = 'specstream'
export const DEFAULT_BASE_URL = 'https://api.specstream.ai'
export const DEFAULT_KEY_REF = 'SPECSTREAM_API_KEY'
export const USER_AGENT = '@specstream/dsh-plugin/0.3.0'
/** One search of up to 10 results is one charged search. */
export const MAX_NUM = 10
export const RESEARCH_TOOL = 'specstream_research'
export const RESEARCH_RESULT_TOOL = 'specstream_research_result'
/** What one delivered report costs, by depth. A run that fails or is cancelled is not charged. */
export const RESEARCH_PRICE_USD = Object.freeze({ quick: 0.1, standard: 0.3, deep: 1 })
export const DEFAULT_RESEARCH_DEPTH = 'quick'
/** How long one tool call waits for the report before it hands back the run's id. */
export const DEFAULT_RESEARCH_WAIT_SECONDS = 300
export const MOST_RESEARCH_WAIT_SECONDS = 1800
const RESEARCH_POLL_MS = 3000
const RESEARCH_INPUT_MOST_CHARS = 15000

/** The credential the user stores once; `label` and `url` are what to show next to it. */
export const credential = Object.freeze({
  ref: DEFAULT_KEY_REF,
  label: 'SpecStream API key',
  url: 'https://specstream.ai/?utm_source=deepseek-harness',
})

/** A failure the web tools report with a machine-readable code, like the seam's own WebError. */
export class SpecStreamWebError extends Error {
  constructor(message, code, options) {
    super(message, options)
    this.name = 'WebError'
    this.code = code
  }
}

const KEY_REF = /^[A-Za-z_][A-Za-z0-9_]*$/

/** A config field is a plain value, or a reactive cell with get() on harness builds that wrap config. */
function read(value) {
  return value !== null && typeof value === 'object' && typeof value.get === 'function' ? value.get() : value
}

function text(value) {
  const v = read(value)
  return typeof v === 'string' ? v.trim() : ''
}

/** Read the plugin's config into the options the providers use. */
export function resolveOptions(config = {}) {
  const keyRef = text(config.apiKeyEnv) || DEFAULT_KEY_REF
  const speed = text(config.speed)
  const depth = text(config.researchDepth)
  const wait = read(config.researchWaitSeconds)
  return {
    apiKey: text(config.apiKey),
    keyRef: KEY_REF.test(keyRef) ? keyRef : DEFAULT_KEY_REF,
    baseURL: (text(config.baseURL) || DEFAULT_BASE_URL).replace(/\/+$/, ''),
    speed: speed === 'fast' ? 'fast' : 'default',
    research: read(config.research) !== false,
    researchDepth: Object.hasOwn(RESEARCH_PRICE_USD, depth) ? depth : DEFAULT_RESEARCH_DEPTH,
    researchWaitSeconds:
      Number.isFinite(wait) && wait >= 0 ? Math.min(wait, MOST_RESEARCH_WAIT_SECONDS) : DEFAULT_RESEARCH_WAIT_SECONDS,
  }
}

/**
 * Find the API key: a literal key in the config, then the harness's credentials store
 * (managed credentials, the launching environment, .env files), then the process environment.
 */
export async function resolveApiKey(ctx, options) {
  if (options.apiKey) return options.apiKey
  const credentials = typeof ctx?.get === 'function' ? ctx.get('credentials') : undefined
  if (credentials && typeof credentials.resolve === 'function') {
    const resolved = await credentials.resolve(options.keyRef)
    const value = typeof resolved === 'string' ? resolved : resolved?.value
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  const ambient = process.env[options.keyRef]
  return typeof ambient === 'string' && ambient.trim() ? ambient.trim() : undefined
}

function aborted(signal, cause) {
  return new SpecStreamWebError('SpecStream request aborted', 'WEB_ABORTED', { cause: signal?.reason ?? cause })
}

function isAbort(error, signal) {
  return signal?.aborted === true || (error instanceof Error && error.name === 'AbortError')
}

async function call(ctx, options, method, path, body, signal) {
  if (signal?.aborted) throw aborted(signal)
  const apiKey = await resolveApiKey(ctx, options)
  if (!apiKey) {
    throw new SpecStreamWebError(
      `SpecStream has no API key: store it as the credential ${options.keyRef} or export ${options.keyRef} before you start dsh. ` +
        `Get one at ${credential.url}`,
      'WEB_PROVIDER_CREDENTIAL_MISSING',
    )
  }
  let response
  try {
    response = await fetch(`${options.baseURL}${path}`, {
      method,
      redirect: 'error',
      headers: {
        authorization: `Bearer ${apiKey}`,
        accept: 'application/json',
        'user-agent': USER_AGENT,
        ...(body === undefined ? {} : { 'content-type': 'application/json' }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      ...(signal === undefined ? {} : { signal }),
    })
  } catch (error) {
    if (isAbort(error, signal)) throw aborted(signal, error)
    throw new SpecStreamWebError(`SpecStream request failed: ${String(error)}`, 'WEB_PROVIDER_ERROR', { cause: error })
  }
  let parsed
  try {
    parsed = await response.json()
  } catch (error) {
    if (isAbort(error, signal)) throw aborted(signal, error)
    parsed = undefined
  }
  if (!response.ok) {
    const detail = parsed?.error?.message ?? parsed?.message ?? parsed?.detail
    const message = `SpecStream API error (HTTP ${response.status})${typeof detail === 'string' && detail ? `: ${detail}` : ''}`
    throw new SpecStreamWebError(message, 'WEB_PROVIDER_ERROR')
  }
  if (parsed === null || typeof parsed !== 'object') {
    throw new SpecStreamWebError('SpecStream returned a body that is not JSON', 'WEB_PROVIDER_ERROR')
  }
  return parsed
}

function nonEmpty(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

/** Map GET /v1/web-search's answer to the seam's search result. */
export function mapSearchPage(page) {
  const seen = new Set()
  const sources = []
  for (const source of Array.isArray(page?.sources) ? page.sources : []) {
    const url = nonEmpty(source?.url)
    if (!url || seen.has(url)) continue
    seen.add(url)
    const title = nonEmpty(source.title)
    const snippet = nonEmpty(source.snippet)
    const summary = nonEmpty(source.excerpt)
    const publishedAt = nonEmpty(source.published_at) ?? nonEmpty(source.published)
    sources.push({
      url,
      ...(title ? { title } : {}),
      ...(snippet ? { snippet } : {}),
      ...(summary && summary !== snippet ? { summary } : {}),
      ...(publishedAt ? { publishedAt } : {}),
    })
  }
  const answer = nonEmpty(page?.answer?.value)
  const page_ = nonEmpty(page?.answer?.page)
  return {
    ...(answer ? { content: page_ ? `${answer}\n\nSource of the answer: ${page_}` : answer } : {}),
    sources,
    truncated: false,
  }
}

/** Map one page of POST /v1/extract to the seam's fetch result; a page that failed is a result, not a throw. */
export function mapExtractPage(requestUrl, page) {
  if (!page || typeof page !== 'object') {
    throw new SpecStreamWebError('SpecStream returned no page for the URL', 'WEB_PROVIDER_ERROR')
  }
  if (page.status === 'invalid_url') {
    throw new SpecStreamWebError(page.reason || 'not a public http(s) URL', 'WEB_URL_INVALID')
  }
  const statusCode =
    Number.isInteger(page.status_code) ? page.status_code
      : page.status === 'ok' || page.status === 'empty' ? 200
        : page.status === 'not_found' ? 404
          : page.status === 'blocked' ? 403
            : page.status === 'unsupported' ? 415
              : 502
  const content = typeof page.text === 'string' && page.text ? page.text : (page.reason ?? '')
  return {
    url: nonEmpty(page.url) ?? requestUrl,
    statusCode,
    body: { kind: 'text', content },
    truncated: page.text_truncated === true,
  }
}

/** The search provider: one GET /v1/web-search per query, up to 10 results. */
export function createSearchProvider(ctx, config) {
  return {
    id: PROVIDER_ID,
    available() {
      const options = resolveOptions(config)
      if (options.apiKey) return true
      const credentials = typeof ctx?.get === 'function' ? ctx.get('credentials') : undefined
      return Boolean(credentials) || Boolean(nonEmpty(process.env[options.keyRef]))
    },
    async ready() {
      return (await resolveApiKey(ctx, resolveOptions(config))) !== undefined
    },
    async search(request, signal) {
      const options = resolveOptions(config)
      const query = nonEmpty(request?.query)
      if (!query) throw new SpecStreamWebError('the search query is empty', 'WEB_PROVIDER_ERROR')
      const asked = Number.isInteger(request.maxResults) && request.maxResults > 0 ? request.maxResults : MAX_NUM
      const params = new URLSearchParams({ q: query.slice(0, 2000), num: String(Math.min(asked, MAX_NUM)) })
      if (options.speed === 'fast') params.set('speed', 'fast')
      return mapSearchPage(await call(ctx, options, 'GET', `/v1/web-search?${params}`, undefined, signal))
    },
  }
}

/** The fetch provider: one POST /v1/extract per URL, the page's main text as markdown. */
export function createFetchProvider(ctx, config) {
  const search = createSearchProvider(ctx, config)
  return {
    id: PROVIDER_ID,
    available: search.available,
    ready: search.ready,
    async fetch(request, signal) {
      const url = nonEmpty(request?.url)
      if (!url) throw new SpecStreamWebError('the URL is empty', 'WEB_URL_INVALID')
      const page = await call(ctx, resolveOptions(config), 'POST', '/v1/extract', { urls: [url], format: 'markdown' }, signal)
      return mapExtractPage(url, Array.isArray(page.results) ? page.results[0] : undefined)
    },
  }
}

function abortError(signal) {
  if (signal?.reason instanceof Error) return signal.reason
  const error = new Error('SpecStream research was stopped')
  error.name = 'AbortError'
  return error
}

/** Wait, and end at once when the call is stopped. */
function sleep(ms, signal) {
  return new Promise((resolve) => {
    if (signal?.aborted) {
      resolve()
      return
    }
    const done = () => {
      clearTimeout(timer)
      signal?.removeEventListener('abort', done)
      resolve()
    }
    const timer = setTimeout(done, ms)
    signal?.addEventListener('abort', done, { once: true })
  })
}

function usd(value) {
  return `$${Number(value).toFixed(2)}`
}

/** The text the model reads for a research run: the report with its sources, or where the run stands. */
export function renderResearchRun(run) {
  const id = nonEmpty(run?.id) ?? 'unknown'
  const status = nonEmpty(run?.status) ?? 'unknown'
  if (status === 'completed' && run.report) {
    const report = run.report
    const lines = []
    const title = nonEmpty(report.title)
    if (title) lines.push(`# ${title}`, '')
    lines.push(typeof report.content === 'string' ? report.content.trim() : '')
    if (report.structured !== null && report.structured !== undefined) {
      lines.push('', 'Structured answer:', JSON.stringify(report.structured, null, 2))
    }
    const sources = (Array.isArray(report.sources) ? report.sources : []).filter((source) => nonEmpty(source?.url))
    if (sources.length > 0) {
      lines.push('', 'Sources:')
      for (const source of sources) {
        const label = nonEmpty(source.title)
        lines.push(`[${source.n}] ${label ? `${label} ` : ''}${source.url}`)
      }
    }
    const charged = run.usage?.charged_usd
    lines.push('', `SpecStream research run ${id}${Number.isFinite(charged) ? `, charged ${usd(charged)}` : ''}.`)
    return lines.join('\n')
  }
  if (status === 'queued' || status === 'running') {
    const progress = run.progress ?? {}
    const stage = nonEmpty(run.stage)
    return (
      `The report is not ready yet: run ${id} is ${status} (${stage ? `stage ${stage}, ` : ''}` +
      `${progress.searches ?? 0} searches, ${progress.pages_read ?? 0} pages read). ` +
      `Call ${RESEARCH_RESULT_TOOL} with id "${id}" to read it when it is completed. ` +
      'Do not start the same question again: that would be a second charged report.'
    )
  }
  const detail = nonEmpty(run?.error?.message)?.replace(/\.+$/, '')
  if (status === 'payment_required') {
    throw new SpecStreamWebError(
      `SpecStream research run ${id} needs credit${detail ? `: ${detail}` : ''}. ` +
        'Add credit at https://specstream.ai and start it again. Nothing was charged.',
      'WEB_PROVIDER_ERROR',
    )
  }
  throw new SpecStreamWebError(
    `SpecStream research run ${id} ended as ${status}${detail ? `: ${detail}` : ''}. Nothing was charged.`,
    'WEB_PROVIDER_ERROR',
  )
}

/**
 * Read a run until it ends or the wait is over. When the call is stopped, the run is cancelled
 * (a cancelled run is not charged) and the stop goes on to the harness as an AbortError.
 */
async function awaitResearch(ctx, options, id, signal, clock) {
  const path = `/v1/research/${encodeURIComponent(id)}`
  const until = clock.now() + options.researchWaitSeconds * 1000
  try {
    for (;;) {
      const run = await call(ctx, options, 'GET', path, undefined, signal)
      if (run.status !== 'queued' && run.status !== 'running') return run
      const left = until - clock.now()
      if (left <= 0) return run
      await clock.sleep(Math.min(RESEARCH_POLL_MS, left), signal)
      if (signal?.aborted) throw abortError(signal)
    }
  } catch (error) {
    if (!signal?.aborted) throw error
    try {
      await call(ctx, options, 'POST', `${path}/cancel`, undefined, undefined)
    } catch {
      // The run may have ended already; the stop is what the harness must see.
    }
    throw abortError(signal)
  }
}

const TEXT_OUTPUT = Object.freeze({
  schema: Object.freeze({ type: 'string' }),
  render: (_args, value) => [{ type: 'text', text: value }],
})

/**
 * The two research tools, as registry-ready definitions (what defineTool of dsh-tools returns).
 * `clock` is for tests: now() in milliseconds and sleep(ms, signal).
 */
export function createResearchTools(ctx, config, clock = { now: () => Date.now(), sleep }) {
  const first = resolveOptions(config)
  const timeoutMs = (first.researchWaitSeconds + 60) * 1000
  const start = {
    name: RESEARCH_TOOL,
    description:
      'Write a research report on a question from the live web with SpecStream: it plans the question, searches, ' +
      'reads the pages and writes a report in Markdown in which each cited sentence carries the number of the page ' +
      'it was read from. Use it for a question that needs many pages; for one fact use web_search. ' +
      `Each delivered report is charged to the user's SpecStream credit: quick ${usd(RESEARCH_PRICE_USD.quick)} ` +
      `(about 2 minutes), standard ${usd(RESEARCH_PRICE_USD.standard)}, deep ${usd(RESEARCH_PRICE_USD.deep)} ` +
      `(about 15 minutes). Without depth the report is ${first.researchDepth}. ` +
      'Choose a higher depth only when the user asked for it. ' +
      `The call waits for the report; when the report takes longer, it returns the run's id for ${RESEARCH_RESULT_TOOL}.`,
    parameters: {
      type: 'object',
      properties: {
        question: {
          type: 'string',
          description: 'The question the report answers, in full sentences, with every condition the user gave.',
        },
        depth: {
          type: 'string',
          enum: ['quick', 'standard', 'deep'],
          description: 'How far the research goes, and its price.',
        },
      },
      required: ['question'],
      additionalProperties: false,
    },
    output: TEXT_OUTPUT,
    timeoutMs,
    async execute(args, exec) {
      const options = resolveOptions(config)
      const signal = exec?.signal
      const question = nonEmpty(args?.question)
      if (!question) throw new SpecStreamWebError('the research question is empty', 'WEB_PROVIDER_ERROR')
      const depth = Object.hasOwn(RESEARCH_PRICE_USD, args.depth ?? '') ? args.depth : options.researchDepth
      let created
      try {
        created = await call(
          ctx,
          options,
          'POST',
          '/v1/research',
          { input: question.slice(0, RESEARCH_INPUT_MOST_CHARS), depth },
          signal,
        )
      } catch (error) {
        if (signal?.aborted) throw abortError(signal)
        throw error
      }
      const id = nonEmpty(created.id)
      if (!id) throw new SpecStreamWebError('SpecStream started no research run', 'WEB_PROVIDER_ERROR')
      return renderResearchRun(await awaitResearch(ctx, options, id, signal, clock))
    },
  }
  const result = {
    name: RESEARCH_RESULT_TOOL,
    description:
      `Read a SpecStream research report by the run id that ${RESEARCH_TOOL} returned when the report was not ready. ` +
      'The call waits for the report and costs nothing itself.',
    parameters: {
      type: 'object',
      properties: { id: { type: 'string', description: 'The research run id.' } },
      required: ['id'],
      additionalProperties: false,
    },
    output: TEXT_OUTPUT,
    timeoutMs,
    async execute(args, exec) {
      const id = nonEmpty(args?.id)
      if (!id) throw new SpecStreamWebError('the research run id is empty', 'WEB_PROVIDER_ERROR')
      return renderResearchRun(await awaitResearch(ctx, resolveOptions(config), id, exec?.signal, clock))
    },
  }
  return [start, result]
}

export function apply(ctx, config = {}) {
  ctx.web.registerSearchProvider(createSearchProvider(ctx, config ?? {}))
  ctx.web.registerFetchProvider(createFetchProvider(ctx, config ?? {}))
  if (!resolveOptions(config ?? {}).research) return
  try {
    for (const tool of createResearchTools(ctx, config ?? {})) ctx.tools.register(tool)
  } catch (error) {
    // Search and fetch stay in place when a harness build refuses the tools.
    ctx.logger?.warn?.(`SpecStream research tools were not registered: ${String(error)}`)
  }
}
