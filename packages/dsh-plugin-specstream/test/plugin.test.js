import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import * as plugin from '../src/index.js'

const manifest = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8'))

function fakeCtx() {
  const calls = []
  let disposed = 0
  const ctx = {
    mcpManager: {
      register(serverName, entry) {
        calls.push({ serverName, entry })
        return () => { disposed += 1 }
      },
    },
  }
  return { ctx, calls, disposed: () => disposed }
}

test('registers the remote server with the key as a credential template', () => {
  const { ctx, calls } = fakeCtx()
  plugin.apply(ctx)
  assert.equal(calls.length, 1)
  assert.deepEqual(calls[0], {
    serverName: 'specstream',
    entry: {
      transport: 'streamable-http',
      url: 'https://api.specstream.ai/mcp',
      headers: { Authorization: 'Bearer ${credential:SPECSTREAM_API_KEY}' },
    },
  })
})

test('the entry carries the template, never a key, and no field the manager refuses', () => {
  const { ctx, calls } = fakeCtx()
  plugin.apply(ctx)
  const entry = calls[0].entry
  assert.match(entry.headers.Authorization, /^Bearer \$\{credential:[A-Z_]+\}$/)
  assert.match(calls[0].serverName, /^[A-Za-z0-9_-]{1,32}$/)
  for (const field of ['command', 'args', 'env', 'cwd', 'enabled']) assert.equal(field in entry, false)
})

test('declares the service the plugin needs and the credential to store', () => {
  assert.deepEqual(plugin.inject, ['mcpManager'])
  assert.equal(plugin.credential.ref, 'SPECSTREAM_API_KEY')
  assert.equal(plugin.credential.url, 'https://specstream.ai/?utm_source=deepseek-harness')
})

test('manifest is installable and discoverable', () => {
  assert.ok(manifest.keywords.includes('dsh-plugin'))
  assert.equal(manifest.dsh.bundle.patch, './cordis.patch.yml')
  assert.ok(manifest.files.includes('cordis.patch.yml'))
  const patch = readFileSync(new URL('../cordis.patch.yml', import.meta.url), 'utf8')
  assert.ok(patch.includes(`name: '${manifest.name}'`))
})
