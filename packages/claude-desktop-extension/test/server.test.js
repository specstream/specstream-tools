'use strict'
const assert = require('node:assert/strict')
const http = require('node:http')
const path = require('node:path')
const { spawn } = require('node:child_process')
const { test } = require('node:test')

const SERVER = path.join(__dirname, '..', 'server', 'index.js')
const { mcpUrl, headerValue } = require(SERVER)

function run(env, messages) {
    return new Promise((resolve, reject) => {
        const child = spawn(process.execPath, [SERVER], { env: { PATH: process.env.PATH, ...env } })
        let out = ''
        let err = ''
        child.stdout.on('data', (chunk) => (out += chunk))
        child.stderr.on('data', (chunk) => (err += chunk))
        child.on('error', reject)
        child.on('close', (code) =>
            resolve({ code, err, replies: out.split('\n').filter(Boolean).map((line) => JSON.parse(line)) })
        )
        const lines = messages.map((message) => (typeof message === 'string' ? message : JSON.stringify(message)))
        child.stdin.end(lines.map((line) => line + '\n').join(''))
    })
}

async function upstream(answer) {
    const seen = []
    const server = http.createServer((request, response) => {
        let raw = ''
        request.on('data', (chunk) => (raw += chunk))
        request.on('end', () => {
            const body = JSON.parse(raw)
            seen.push({ headers: request.headers, body })
            const { status = 200, headers = {}, text } = answer(body)
            response.writeHead(status, { 'Content-Type': 'application/json', ...headers })
            response.end(text === undefined ? '' : typeof text === 'string' ? text : JSON.stringify(text))
        })
    })
    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
    return {
        url: `http://127.0.0.1:${server.address().port}/mcp`,
        seen,
        close: () => new Promise((resolve) => server.close(resolve)),
    }
}

const init = { jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-06-18', capabilities: {} } }

test('without a key it lists the tools and a call says how to get a key', async () => {
    for (const key of [undefined, '', '${user_config.api_key}']) {
        const env = key === undefined ? {} : { SPECSTREAM_API_KEY: key }
        const { code, replies, err } = await run(env, [
            init,
            { jsonrpc: '2.0', method: 'notifications/initialized' },
            { jsonrpc: '2.0', id: 2, method: 'tools/list' },
            { jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'search_web', arguments: { q: 'x' } } },
        ])
        assert.equal(code, 0, err)
        assert.equal(replies.length, 3)
        assert.equal(replies[0].result.protocolVersion, '2025-06-18')
        assert.equal(replies[0].result.serverInfo.name, 'specstream')
        const names = replies[1].result.tools.map((tool) => tool.name)
        assert.ok(names.includes('search_web') && names.includes('read_pages') && names.includes('compile'))
        assert.equal(replies[2].result.isError, true)
        assert.match(replies[2].result.content[0].text, /Agents & API/)
    }
})

test('with a key it forwards with the session and the key, and never prints the key', async () => {
    const up = await upstream((body) => {
        if (body.method === 'initialize') {
            return {
                headers: { 'Mcp-Session-Id': 'sess-1' },
                text: { jsonrpc: '2.0', id: body.id, result: { protocolVersion: '2025-06-18' } },
            }
        }
        return body.id === undefined ? { status: 202 } : { text: { jsonrpc: '2.0', id: body.id, result: { ok: true } } }
    })
    try {
        const { code, replies, err } = await run({ SPECSTREAM_API_KEY: 'offline-key', SPECSTREAM_MCP_URL: up.url }, [
            init,
            { jsonrpc: '2.0', method: 'notifications/initialized' },
            { jsonrpc: '2.0', id: 2, method: 'tools/list' },
        ])
        assert.equal(code, 0, err)
        assert.deepEqual(
            replies.map((reply) => reply.id),
            [1, 2]
        )
        assert.equal(up.seen.length, 3)
        assert.equal(up.seen[0].headers.authorization, 'Bearer offline-key')
        assert.equal(up.seen[0].headers['mcp-session-id'], undefined)
        assert.equal(up.seen[2].headers['mcp-session-id'], 'sess-1')
        assert.equal(up.seen[2].headers['mcp-protocol-version'], '2025-06-18')
        assert.ok(!err.includes('offline-key') && !JSON.stringify(replies).includes('offline-key'))
    } finally {
        await up.close()
    }
})

test('a stateless request carries its version, method and name', async () => {
    const up = await upstream((body) => ({ text: { jsonrpc: '2.0', id: body.id, result: {} } }))
    try {
        const meta = { 'io.modelcontextprotocol/protocolVersion': '2026-07-28' }
        const { replies } = await run({ SPECSTREAM_API_KEY: 'k', SPECSTREAM_MCP_URL: up.url }, [
            { jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'café', arguments: {}, _meta: meta } },
            { jsonrpc: '2.0', method: 'notifications/cancelled', params: { requestId: 1 } },
        ])
        assert.equal(replies[0].id, 1)
        assert.equal(up.seen.length, 1)
        assert.equal(up.seen[0].headers['mcp-protocol-version'], '2026-07-28')
        assert.equal(up.seen[0].headers['mcp-method'], 'tools/call')
        assert.equal(up.seen[0].headers['mcp-name'], '=?base64?Y2Fmw6k=?=')
    } finally {
        await up.close()
    }
})

test('a refused key and a broken answer give an error and the server keeps running', async () => {
    const up = await upstream((body) => {
        if (body.id === 1) {
            return { status: 401, text: 'no' }
        }
        return body.id === 2 ? { text: 'not json' } : { text: { jsonrpc: '2.0', id: body.id, result: {} } }
    })
    try {
        const { code, replies } = await run({ SPECSTREAM_API_KEY: 'k', SPECSTREAM_MCP_URL: up.url }, [
            { jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'search_web', arguments: {} } },
            { jsonrpc: '2.0', id: 2, method: 'tools/list' },
            'this is not json',
            { jsonrpc: '2.0', id: 3, method: 'ping' },
        ])
        assert.equal(code, 0)
        assert.equal(replies[0].result.isError, true)
        assert.match(replies[0].result.content[0].text, /refused the API key/)
        assert.equal(replies[1].error.code, -32603)
        assert.equal(replies[2].error.code, -32700)
        assert.deepEqual(replies[3].result, {})
    } finally {
        await up.close()
    }
})

test('a JSON-RPC error on a 4xx reaches the client', async () => {
    const error = { code: -32022, message: 'Unsupported protocol version' }
    const up = await upstream((body) => ({ status: 400, text: { jsonrpc: '2.0', id: body.id, error } }))
    try {
        const { replies } = await run({ SPECSTREAM_API_KEY: 'k', SPECSTREAM_MCP_URL: up.url }, [
            { jsonrpc: '2.0', id: 7, method: 'tools/list' },
        ])
        assert.equal(replies[0].error.code, -32022)
    } finally {
        await up.close()
    }
})

test('the address must be HTTPS or loopback, with nothing attached', async () => {
    assert.equal(mcpUrl({}), 'https://api.specstream.ai/mcp')
    assert.equal(mcpUrl({ SPECSTREAM_MCP_URL: 'http://localhost:8000/mcp' }), 'http://localhost:8000/mcp')
    const refused = [
        'http://example.com/mcp',
        'https://u:p@example.com/mcp',
        'https://example.com/mcp?x=1',
        'ftp://example.com',
        'nope',
    ]
    for (const bad of refused) {
        assert.throws(() => mcpUrl({ SPECSTREAM_MCP_URL: bad }))
    }
    assert.equal((await run({ SPECSTREAM_MCP_URL: 'http://example.com/mcp' }, [])).code, 2)
    assert.equal(headerValue('search_web'), 'search_web')
})
