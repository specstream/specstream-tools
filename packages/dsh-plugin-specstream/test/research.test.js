import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import * as plugin from '../src/index.js'

const RUNNING = {
  id: 'res_1',
  status: 'running',
  stage: 'reading',
  depth: 'quick',
  progress: { searches: 4, pages_read: 9, sources: 3 },
  usage: { searches: 4, pages_read: 9, charged_usd: 0 },
}

const COMPLETED = {
  id: 'res_1',
  status: 'completed',
  stage: 'done',
  depth: 'quick',
  progress: { searches: 6, pages_read: 14, sources: 2 },
  report: {
    title: 'Who makes dsh',
    format: 'markdown',
    content: 'DeepSeek makes it [1]. It is open source [2].',
    structured: null,
    citations: [],
    sources: [
      { n: 1, url: 'https://example.com/a', title: 'A page', read_at: '2026-11-13T00:00:00Z', cited: true },
      { n: 2, url: 'https://example.com/b', title: '', read_at: '2026-11-13T00:00:00Z', cited: true },
    ],
    basis: [],
  },
  usage: { searches: 6, pages_read: 14, charged_usd: 0.1 },
}

const CREATED = { id: 'res_1', status: 'queued', depth: 'quick', price_usd: 0.1 }

const realFetch = globalThis.fetch

afterEach(() => {
  globalThis.fetch = realFetch
})

/** Answer each request with the next scripted body; the last one repeats. */
function scriptFetch(bodies) {
  const calls = []
  globalThis.fetch = async (url, init) => {
    const [body, status = 200] = bodies[Math.min(calls.length, bodies.length - 1)]
    calls.push({ url: String(url), method: init.method, body: init.body ? JSON.parse(init.body) : undefined, init })
    return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
  }
  return calls
}

function harness() {
  const tools = []
  const warnings = []
  const ctx = {
    web: { registerSearchProvider() {}, registerFetchProvider() {} },
    tools: { register(tool) { tools.push(tool); return () => {} } },
    logger: { warn: (message) => warnings.push(message) },
    get: () => undefined,
  }
  return { ctx, tools, warnings }
}

/** A clock that never waits: each sleep moves time on by what was asked. */
function fakeClock() {
  const clock = { at: 0, slept: [], now: () => clock.at, sleep: async (ms) => { clock.slept.push(ms); clock.at += ms } }
  return clock
}

function tools(config = { apiKey: 'sk_test_secret' }, clock = fakeClock()) {
  const { ctx } = harness()
  const [start, result] = plugin.createResearchTools(ctx, config, clock)
  return { start, result, clock }
}

test('apply registers the two research tools as registry-ready definitions', () => {
  const { ctx, tools: registered } = harness()
  plugin.apply(ctx, {})
  assert.deepEqual(registered.map((tool) => tool.name), ['specstream_research', 'specstream_research_result'])
  for (const tool of registered) {
    assert.equal(tool.parameters.type, 'object')
    assert.equal(tool.parameters.additionalProperties, false)
    assert.deepEqual(tool.output.schema, { type: 'string' })
    assert.deepEqual(tool.output.render({}, 'text'), [{ type: 'text', text: 'text' }])
    assert.equal(typeof tool.execute, 'function')
    assert.equal(tool.timeoutMs, 360000)
  }
  assert.deepEqual(registered[0].parameters.required, ['question'])
  assert.deepEqual(registered[0].parameters.properties.depth.enum, ['quick', 'standard', 'deep'])
  assert.match(registered[0].description, /quick \$0\.10/)
  assert.match(registered[0].description, /standard \$0\.30/)
  assert.match(registered[0].description, /deep \$1\.00/)
})

test('research: false registers no tool, and a registry that refuses leaves search in place', () => {
  const off = harness()
  plugin.apply(off.ctx, { research: false })
  assert.equal(off.tools.length, 0)

  const refused = harness()
  refused.ctx.tools.register = () => { throw new Error('unsupported JSON schema') }
  assert.doesNotThrow(() => plugin.apply(refused.ctx, {}))
  assert.match(refused.warnings[0], /research tools were not registered/)
})

test('the research tool starts a quick report, waits for it and returns it with its sources', async () => {
  const { start, clock } = tools()
  const calls = scriptFetch([[CREATED, 202], [RUNNING], [RUNNING], [COMPLETED]])
  const text = await start.execute({ question: '  Who makes dsh?  ' }, {})
  assert.equal(calls[0].method, 'POST')
  assert.equal(calls[0].url, 'https://api.specstream.ai/v1/research')
  assert.deepEqual(calls[0].body, { input: 'Who makes dsh?', depth: 'quick' })
  assert.equal(calls[0].init.headers.authorization, 'Bearer sk_test_secret')
  assert.equal(calls[0].init.headers['user-agent'], plugin.USER_AGENT)
  assert.deepEqual(calls.slice(1).map((c) => `${c.method} ${c.url}`), [
    'GET https://api.specstream.ai/v1/research/res_1',
    'GET https://api.specstream.ai/v1/research/res_1',
    'GET https://api.specstream.ai/v1/research/res_1',
  ])
  assert.deepEqual(clock.slept, [3000, 3000])
  assert.equal(
    text,
    [
      '# Who makes dsh',
      '',
      'DeepSeek makes it [1]. It is open source [2].',
      '',
      'Sources:',
      '[1] A page https://example.com/a',
      '[2] https://example.com/b',
      '',
      'SpecStream research run res_1, charged $0.10.',
    ].join('\n'),
  )
})

test('the depth the model asks for is sent, and the config sets the depth when it asks for none', async () => {
  const asked = tools()
  let calls = scriptFetch([[CREATED, 202], [COMPLETED]])
  await asked.start.execute({ question: 'q', depth: 'deep' }, {})
  assert.equal(calls[0].body.depth, 'deep')

  const configured = tools({ apiKey: 'k', researchDepth: { get: () => 'standard' } })
  calls = scriptFetch([[CREATED, 202], [COMPLETED]])
  await configured.start.execute({ question: 'q' }, {})
  assert.equal(calls[0].body.depth, 'standard')
  assert.match(configured.start.description, /Without depth the report is standard/)
})

test('when the wait ends first, the tool returns the run id, and the result tool reads the report', async () => {
  const { start, result, clock } = tools({ apiKey: 'k', researchWaitSeconds: 7 })
  let calls = scriptFetch([[CREATED, 202], [RUNNING]])
  const waiting = await start.execute({ question: 'q' }, {})
  assert.deepEqual(clock.slept, [3000, 3000, 1000])
  assert.equal(calls.length, 5)
  assert.match(waiting, /run res_1 is running \(stage reading, 4 searches, 9 pages read\)/)
  assert.match(waiting, /Call specstream_research_result with id "res_1"/)
  assert.equal(calls.filter((c) => c.method === 'POST').length, 1)

  calls = scriptFetch([[COMPLETED]])
  const text = await result.execute({ id: 'res_1' }, {})
  assert.deepEqual(calls.map((c) => `${c.method} ${c.url}`), ['GET https://api.specstream.ai/v1/research/res_1'])
  assert.match(text, /^# Who makes dsh/)
})

test('a run that failed or needs credit is an error that says nothing was charged', async () => {
  const { start, result } = tools()
  scriptFetch([[CREATED, 202], [{ ...RUNNING, status: 'failed', error: { code: 'no_sources', message: 'No page answered.' } }]])
  await assert.rejects(start.execute({ question: 'q' }, {}), (error) => {
    assert.equal(error.code, 'WEB_PROVIDER_ERROR')
    assert.match(error.message, /run res_1 ended as failed: No page answered\. Nothing was charged\./)
    return true
  })
  scriptFetch([[{ ...RUNNING, status: 'payment_required' }]])
  await assert.rejects(result.execute({ id: 'res_1' }, {}), /needs credit\. Add credit at https:\/\/specstream\.ai/)
})

test('an API refusal at the start is an error with its status and no key, and no run is read', async () => {
  const { start } = tools()
  const calls = scriptFetch([[{ error: { message: 'Send a question in input' } }, 422]])
  await assert.rejects(start.execute({ question: 'q' }, {}), (error) => {
    assert.match(error.message, /HTTP 422\): Send a question in input/)
    assert.ok(!error.message.includes('sk_test_secret'))
    return true
  })
  assert.equal(calls.length, 1)
})

test('without a key the research tool says where to put it and sends nothing', async () => {
  const saved = process.env.SPECSTREAM_API_KEY
  delete process.env.SPECSTREAM_API_KEY
  try {
    const { start } = tools({})
    const calls = scriptFetch([[CREATED, 202]])
    await assert.rejects(start.execute({ question: 'q' }, {}), /SPECSTREAM_API_KEY/)
    assert.equal(calls.length, 0)
  } finally {
    if (saved !== undefined) process.env.SPECSTREAM_API_KEY = saved
  }
})

test('an empty question or id is refused before any request', async () => {
  const { start, result } = tools()
  const calls = scriptFetch([[CREATED, 202]])
  await assert.rejects(start.execute({ question: '   ' }, {}), /question is empty/)
  await assert.rejects(result.execute({ id: '' }, {}), /run id is empty/)
  assert.equal(calls.length, 0)
})

test('stopping the call cancels the run, so it is not charged, and the stop reaches the harness as an abort', async () => {
  const controller = new AbortController()
  const clock = fakeClock()
  clock.sleep = async () => { controller.abort() }
  const { start } = tools({ apiKey: 'k' }, clock)
  const calls = scriptFetch([[CREATED, 202], [RUNNING], [{ ...RUNNING, status: 'cancelled' }]])
  await assert.rejects(start.execute({ question: 'q' }, { signal: controller.signal }), (error) => {
    assert.equal(error.name, 'AbortError')
    return true
  })
  assert.deepEqual(calls.map((c) => `${c.method} ${c.url}`), [
    'POST https://api.specstream.ai/v1/research',
    'GET https://api.specstream.ai/v1/research/res_1',
    'POST https://api.specstream.ai/v1/research/res_1/cancel',
  ])
  assert.equal(calls[2].init.signal, undefined)
})

test('a call that is already stopped starts no run', async () => {
  const controller = new AbortController()
  controller.abort()
  const { start } = tools()
  const calls = scriptFetch([[CREATED, 202]])
  await assert.rejects(start.execute({ question: 'q' }, { signal: controller.signal }), { name: 'AbortError' })
  assert.equal(calls.length, 0)
})
