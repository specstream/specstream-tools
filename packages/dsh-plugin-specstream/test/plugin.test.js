import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { afterEach, test } from 'node:test'
import * as plugin from '../src/index.js'

const manifest = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'))
const patch = readFileSync(new URL('../cordis.patch.yml', import.meta.url), 'utf8')

const SEARCH_PAGE = {
  request_id: 'r1',
  query: 'who makes dsh',
  kind: 'fact',
  columns: [],
  rows: [],
  answer: { value: 'DeepSeek makes it.', page: 'https://example.com/a' },
  sources: [
    { url: 'https://example.com/a', title: 'A page', site: 'example.com', snippet: 'first', cited: true, published_at: '2026-11-06T00:00:00Z' },
    { url: 'https://example.com/a', title: 'Again', site: 'example.com', snippet: 'dupe', cited: false },
    { url: 'https://example.com/b', title: '', site: 'example.com', snippet: '', cited: false, excerpt: 'longer text' },
  ],
  took_ms: 5,
  price_usd: 0.005,
}

function fakeWeb() {
  const search = []
  const fetch = []
  return {
    search,
    fetch,
    web: {
      registerSearchProvider(p) { search.push(p); return () => {} },
      registerFetchProvider(p) { fetch.push(p); return () => {} },
    },
  }
}

function ctxWith({ credentials } = {}) {
  const fake = fakeWeb()
  const ctx = { web: fake.web, tools: { register() { return () => {} } }, get: (name) => (name === 'credentials' ? credentials : undefined) }
  return { ctx, ...fake }
}

const realFetch = globalThis.fetch
const savedEnv = process.env.SPECSTREAM_API_KEY
afterEach(() => {
  globalThis.fetch = realFetch
  if (savedEnv === undefined) delete process.env.SPECSTREAM_API_KEY
  else process.env.SPECSTREAM_API_KEY = savedEnv
})

function scriptFetch(body, status = 200) {
  const calls = []
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init })
    return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
  }
  return calls
}

test('apply registers a search and a fetch provider with the web seam, and injects web and tools', () => {
  const { ctx, search, fetch } = ctxWith()
  plugin.apply(ctx, {})
  assert.deepEqual(plugin.inject, ['web', 'tools'])
  assert.equal(search.length, 1)
  assert.equal(fetch.length, 1)
  assert.equal(search[0].id, 'specstream')
  assert.equal(fetch[0].id, 'specstream')
})

test('the bundle patch mounts the plugin and selects it for search, fetch stays on the local fetcher', () => {
  assert.ok(patch.includes(`name: '${manifest.name}'`))
  assert.match(patch, /- id: web\n {2}config:\n {4}searchProvider: specstream\n {4}fetchProvider: http\n/)
  assert.equal(manifest.dsh.bundle.patch, './cordis.patch.yml')
  assert.ok(manifest.files.includes('cordis.patch.yml'))
  assert.ok(manifest.keywords.includes('dsh-plugin'))
  assert.equal(manifest.dependencies, undefined)
  assert.equal(manifest.peerDependencies, undefined)
})

test('web_search calls GET /v1/web-search with the stored key and maps the answer and sources', async () => {
  const resolved = []
  const { ctx, search } = ctxWith({ credentials: { resolve: async (ref) => { resolved.push(ref); return { value: 'sk_test_store' } } } })
  plugin.apply(ctx, {})
  const calls = scriptFetch(SEARCH_PAGE)
  const result = await search[0].search({ query: 'who makes dsh', maxResults: 8 })
  assert.deepEqual(resolved, ['SPECSTREAM_API_KEY'])
  assert.equal(calls.length, 1)
  const url = new URL(calls[0].url)
  assert.equal(url.origin + url.pathname, 'https://api.specstream.ai/v1/web-search')
  assert.equal(url.searchParams.get('q'), 'who makes dsh')
  assert.equal(url.searchParams.get('num'), '8')
  assert.equal(url.searchParams.get('speed'), null)
  assert.equal(calls[0].init.method, 'GET')
  assert.equal(calls[0].init.headers.authorization, 'Bearer sk_test_store')
  assert.deepEqual(result, {
    content: 'DeepSeek makes it.\n\nSource of the answer: https://example.com/a',
    sources: [
      { url: 'https://example.com/a', title: 'A page', snippet: 'first', publishedAt: '2026-11-06T00:00:00Z' },
      { url: 'https://example.com/b', summary: 'longer text' },
    ],
    truncated: false,
  })
})

test('one search asks for at most 10 results, and speed fast is passed on', async () => {
  const { ctx, search } = ctxWith()
  process.env.SPECSTREAM_API_KEY = 'sk_test_env'
  plugin.apply(ctx, { speed: 'fast' })
  const calls = scriptFetch({ sources: [] })
  const result = await search[0].search({ query: 'x', maxResults: 50 })
  const url = new URL(calls[0].url)
  assert.equal(url.searchParams.get('num'), '10')
  assert.equal(url.searchParams.get('speed'), 'fast')
  assert.equal(calls[0].init.headers.authorization, 'Bearer sk_test_env')
  assert.deepEqual(result, { sources: [], truncated: false })
})

test('config fields given as reactive cells are read through get()', async () => {
  const { ctx, search } = ctxWith()
  plugin.apply(ctx, { apiKey: { get: () => 'sk_test_cell' }, baseURL: { get: () => 'http://127.0.0.1:9/' } })
  const calls = scriptFetch({ sources: [] })
  await search[0].search({ query: 'x' })
  assert.ok(calls[0].url.startsWith('http://127.0.0.1:9/v1/web-search?'))
  assert.equal(calls[0].init.headers.authorization, 'Bearer sk_test_cell')
})

test('without a key, available() is false and a search says where to put the key', async () => {
  delete process.env.SPECSTREAM_API_KEY
  const { ctx, search } = ctxWith()
  plugin.apply(ctx, {})
  assert.equal(search[0].available(), false)
  assert.equal(await search[0].ready(), false)
  const calls = scriptFetch({})
  await assert.rejects(search[0].search({ query: 'x' }), (error) => {
    assert.equal(error.code, 'WEB_PROVIDER_CREDENTIAL_MISSING')
    assert.match(error.message, /SPECSTREAM_API_KEY/)
    return true
  })
  assert.equal(calls.length, 0)
})

test('an API error becomes a WEB_PROVIDER_ERROR with the status and message, never the key', async () => {
  const { ctx, search } = ctxWith()
  plugin.apply(ctx, { apiKey: 'sk_test_secret' })
  scriptFetch({ error: { message: 'Invalid API key' } }, 401)
  await assert.rejects(search[0].search({ query: 'x' }), (error) => {
    assert.equal(error.code, 'WEB_PROVIDER_ERROR')
    assert.match(error.message, /HTTP 401.*Invalid API key/)
    assert.doesNotMatch(error.message, /sk_test_secret/)
    return true
  })
})

test('an aborted search fails as WEB_ABORTED without a request', async () => {
  const { ctx, search } = ctxWith()
  plugin.apply(ctx, { apiKey: 'sk_test_x' })
  const calls = scriptFetch({})
  const controller = new AbortController()
  controller.abort()
  await assert.rejects(search[0].search({ query: 'x' }, controller.signal), (error) => error.code === 'WEB_ABORTED')
  assert.equal(calls.length, 0)
})

test('fetch reads one URL through POST /v1/extract as markdown', async () => {
  const { ctx, fetch } = ctxWith()
  plugin.apply(ctx, { apiKey: 'sk_test_x' })
  const calls = scriptFetch({ request_id: 'r', took_ms: 1, price_usd: 0.0008, results: [{ url: 'https://example.com/', status: 'ok', title: 'Example', text: '# Example', text_truncated: true }] })
  const result = await fetch[0].fetch({ url: 'https://example.com/' })
  assert.equal(calls[0].url, 'https://api.specstream.ai/v1/extract')
  assert.equal(calls[0].init.method, 'POST')
  assert.deepEqual(JSON.parse(calls[0].init.body), { urls: ['https://example.com/'], format: 'markdown' })
  assert.deepEqual(result, { url: 'https://example.com/', statusCode: 200, body: { kind: 'text', content: '# Example' }, truncated: true })
})

test('a page that did not read is a result with its status, an invalid URL is an error', () => {
  assert.deepEqual(plugin.mapExtractPage('https://x.test/', { url: 'https://x.test/', status: 'not_found', text: 'Gone', status_code: 410 }), {
    url: 'https://x.test/', statusCode: 410, body: { kind: 'text', content: 'Gone' }, truncated: false,
  })
  assert.equal(plugin.mapExtractPage('https://x.test/', { url: null, status: 'blocked', text: '', reason: 'robots.txt' }).statusCode, 403)
  assert.throws(() => plugin.mapExtractPage('ftp://x', { url: null, status: 'invalid_url', text: '' }), (error) => error.code === 'WEB_URL_INVALID')
})

test('the credential to store is named for the user', () => {
  assert.equal(plugin.credential.ref, 'SPECSTREAM_API_KEY')
  assert.equal(plugin.credential.url, 'https://specstream.ai/?utm_source=deepseek-harness')
  assert.equal(plugin.USER_AGENT, `${manifest.name}/${manifest.version}`)
})
