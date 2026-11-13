#!/usr/bin/env node
// SpecStream for Claude Desktop: a stdio server that forwards each MCP message to the hosted
// SpecStream MCP server over HTTPS. No dependencies: Node's own fetch, readline and fs.
//
// The key comes from the environment only (Claude Desktop keeps it in the OS keychain and
// sets SPECSTREAM_API_KEY). Without a key the server still starts: it answers `initialize`
// and `tools/list` from the tool list shipped in this folder, and every tool call says how
// to get a key. A failed request answers with an error and the server keeps running.
'use strict'

const fs = require('node:fs')
const path = require('node:path')
const readline = require('node:readline')

const DEFAULT_MCP_URL = 'https://api.specstream.ai/mcp'
const PROTOCOL_VERSION = '2025-11-25'
const KNOWN_VERSIONS = ['2024-11-05', '2025-03-26', '2025-06-18', PROTOCOL_VERSION]
const VERSION_KEY = 'io.modelcontextprotocol/protocolVersion'
const NAMED_METHODS = { 'tools/call': 'name', 'prompts/get': 'name', 'resources/read': 'uri' }
const TIMEOUT_MS = 150000
const VERSION = require('../manifest.json').version
const MISSING_KEY =
    'SpecStream has no key yet, so it lists its tools but cannot run them. ' +
    'Create a key under Agents & API at https://specstream.ai/workspace, then open ' +
    'Settings > Extensions > SpecStream in Claude Desktop and paste it into the "API key" field.'
const SERVER_INFO = { name: 'specstream', title: 'SpecStream', version: VERSION, websiteUrl: 'https://specstream.ai' }

// Claude Desktop leaves "${user_config.api_key}" as written when the field is empty.
function setting(value) {
    const text = (value || '').trim()
    return text.startsWith('${') ? '' : text
}

function authorizationFromEnv(env) {
    const value = setting(env.SPECSTREAM_API_KEY)
    if (!value) {
        return null
    }
    if (!/^[\x20-\x7e]+$/.test(value)) {
        throw new Error('The API key contains invalid characters')
    }
    return value.toLowerCase().startsWith('bearer ') ? value : `Bearer ${value}`
}

function mcpUrl(env) {
    const value = setting(env.SPECSTREAM_MCP_URL) || DEFAULT_MCP_URL
    const problem = new Error(
        'SPECSTREAM_MCP_URL must use HTTPS (or loopback HTTP), without credentials, query or fragment'
    )
    let parsed
    try {
        parsed = new URL(value)
    } catch {
        throw problem
    }
    const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(parsed.hostname)
    const scheme = parsed.protocol
    if (
        !parsed.hostname ||
        !(scheme === 'https:' || (scheme === 'http:' && loopback)) ||
        parsed.username ||
        parsed.password ||
        value.includes('?') ||
        value.includes('#') ||
        /[\x00-\x20\x7f]/.test(value)
    ) {
        throw problem
    }
    return value
}

// Mcp-Name as the 2026-07-28 revision sends it: plain visible ASCII, or the Base64 form.
function headerValue(value) {
    const plain =
        value === value.trim() &&
        /^[\x20-\x7e]*$/.test(value) &&
        !(value.startsWith('=?base64?') && value.endsWith('?='))
    return plain ? value : `=?base64?${Buffer.from(value, 'utf8').toString('base64')}?=`
}

function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function statelessVersion(message) {
    const meta = isObject(message.params) ? message.params._meta : null
    const version = isObject(meta) ? meta[VERSION_KEY] : null
    return typeof version === 'string' && version ? version : null
}

function jsonFromSse(text, requestId) {
    for (const event of text.replace(/\r\n/g, '\n').split('\n\n')) {
        const blob = event
            .split('\n')
            .filter((line) => line.startsWith('data:'))
            .map((line) => line.slice(5).trimStart())
            .join('\n')
        if (!blob) {
            continue
        }
        const payload = JSON.parse(blob)
        if (isObject(payload) && 'id' in payload && payload.id === requestId) {
            return payload
        }
    }
    throw new Error('SpecStream returned no response for the request')
}

function errorBody(raw, requestId) {
    let loaded
    try {
        loaded = raw ? JSON.parse(raw) : null
    } catch {
        return null
    }
    const valid =
        isObject(loaded) &&
        loaded.jsonrpc === '2.0' &&
        'id' in loaded &&
        loaded.id === requestId &&
        isObject(loaded.error)
    return valid ? loaded : null
}

// Returns the reply to write, or null when the message needs none.
async function post(message, state) {
    const headers = {
        Authorization: state.authorization,
        Accept: 'application/json, text/event-stream',
        'Content-Type': 'application/json',
    }
    const stateless = statelessVersion(message)
    if (stateless) {
        const method = String(message.method || '')
        headers['MCP-Protocol-Version'] = stateless
        headers['Mcp-Method'] = method
        const field = NAMED_METHODS[method]
        const name = field && isObject(message.params) ? message.params[field] : null
        if (typeof name === 'string') {
            headers['Mcp-Name'] = headerValue(name)
        }
    } else {
        headers['MCP-Protocol-Version'] = state.sessionVersion
        if (state.sessionId) {
            headers['MCP-Session-Id'] = state.sessionId
        }
    }
    const response = await fetch(state.url, {
        method: 'POST',
        headers,
        body: JSON.stringify(message),
        redirect: 'manual',
        signal: AbortSignal.timeout(TIMEOUT_MS),
    })
    const raw = await response.text()
    const status = response.status
    if (status < 200 || status >= 300) {
        // The 2026-07-28 revision answers version, header and method problems with a JSON-RPC
        // error on a 4xx; the client needs it to pick another version or fall back.
        const error = errorBody(raw, message.id)
        if (error === null) {
            throw new Error(
                status === 401 || status === 403
                    ? `SpecStream refused the API key (HTTP ${status}). Check the key under Agents & API at https://specstream.ai/workspace.`
                    : `SpecStream answered HTTP ${status}`
            )
        }
        return error
    }
    const session = response.headers.get('mcp-session-id')
    if (session && !stateless) {
        state.sessionId = session
    }
    if (!('id' in message)) {
        return null
    }
    if (status === 202) {
        throw new Error('SpecStream returned no response for the request')
    }
    if (!raw) {
        throw new Error('SpecStream returned an empty response')
    }
    const type = response.headers.get('content-type') || ''
    const loaded = type.includes('text/event-stream') ? jsonFromSse(raw, message.id) : JSON.parse(raw)
    if (
        !isObject(loaded) ||
        loaded.jsonrpc !== '2.0' ||
        !('id' in loaded) ||
        loaded.id !== message.id ||
        !('result' in loaded || 'error' in loaded)
    ) {
        throw new Error('SpecStream returned an invalid response')
    }
    if (message.method === 'initialize' && isObject(loaded.result)) {
        const negotiated = loaded.result.protocolVersion
        if (typeof negotiated === 'string' && negotiated) {
            state.sessionVersion = negotiated
        }
    }
    return loaded
}

function keylessReply(message) {
    if (!('id' in message)) {
        return null
    }
    const params = isObject(message.params) ? message.params : {}
    let result
    switch (message.method) {
        case 'initialize':
            result = {
                protocolVersion: KNOWN_VERSIONS.includes(params.protocolVersion)
                    ? params.protocolVersion
                    : PROTOCOL_VERSION,
                capabilities: { tools: { listChanged: false } },
                serverInfo: SERVER_INFO,
                instructions: MISSING_KEY,
            }
            break
        case 'ping':
            result = {}
            break
        case 'tools/list':
            result = { tools: JSON.parse(fs.readFileSync(path.join(__dirname, 'tools.json'), 'utf8')) }
            break
        case 'resources/list':
            result = { resources: [] }
            break
        case 'resources/templates/list':
            result = { resourceTemplates: [] }
            break
        case 'prompts/list':
            result = { prompts: [] }
            break
        case 'tools/call':
            result = { content: [{ type: 'text', text: MISSING_KEY }], isError: true }
            break
        default:
            return { jsonrpc: '2.0', id: message.id, error: { code: -32601, message: MISSING_KEY } }
    }
    return { jsonrpc: '2.0', id: message.id, result }
}

// A request that failed on the way still gets an answer, so the client is not left waiting.
function failureReply(message, error) {
    const text =
        error && error.name === 'TimeoutError'
            ? 'SpecStream did not answer in time'
            : error instanceof SyntaxError
              ? 'SpecStream returned an invalid response'
              : String((error && error.message) || error)
    if (message.method === 'tools/call') {
        return { jsonrpc: '2.0', id: message.id, result: { content: [{ type: 'text', text }], isError: true } }
    }
    return { jsonrpc: '2.0', id: message.id, error: { code: -32603, message: text } }
}

async function handle(line, state, write, log) {
    const text = line.trim()
    if (!text) {
        return
    }
    let message
    try {
        message = JSON.parse(text)
    } catch {
        message = null
    }
    if (!isObject(message)) {
        write({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Parse error' } })
        return
    }
    if (message.method === 'notifications/cancelled' && !('id' in message)) {
        // Each request is one POST that is answered whole, so there is nothing to cancel upstream.
        return
    }
    if (state.authorization === null) {
        const reply = keylessReply(message)
        if (reply !== null) {
            write(reply)
        }
        return
    }
    try {
        const reply = await post(message, state)
        if (reply !== null) {
            write(reply)
        }
    } catch (error) {
        const reply = failureReply(message, error)
        log(`specstream: ${message.method || 'message'} failed: ${reply.error ? reply.error.message : reply.result.content[0].text}`)
        if ('id' in message) {
            write(reply)
        }
    }
}

async function main(env = process.env, input = process.stdin, output = process.stdout, errors = process.stderr) {
    const log = (text) => errors.write(`${text}\n`)
    const write = (reply) => output.write(`${JSON.stringify(reply)}\n`)
    const state = { url: DEFAULT_MCP_URL, authorization: null, sessionId: null, sessionVersion: PROTOCOL_VERSION }
    try {
        state.url = mcpUrl(env)
        state.authorization = authorizationFromEnv(env)
    } catch (error) {
        log(error.message)
        return 2
    }
    if (state.authorization === null) {
        log(MISSING_KEY)
    }
    // One message at a time, in the order received: `initialize` sets the session the next ones use.
    for await (const line of readline.createInterface({ input, crlfDelay: Infinity })) {
        await handle(line, state, write, log)
    }
    return 0
}

if (require.main === module) {
    main().then(
        (code) => {
            process.exitCode = code
        },
        (error) => {
            process.stderr.write(`specstream: ${error.stack || error}\n`)
            process.exitCode = 1
        }
    )
}

module.exports = { main, mcpUrl, authorizationFromEnv, headerValue, keylessReply }
