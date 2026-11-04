// Registers the hosted SpecStream MCP server with the harness's MCP manager.
// A registration lasts as long as this plugin is enabled; the API key stays in
// the credentials provider and never appears in settings.

export const name = 'specstream'

export const inject = ['mcpManager']

export const SERVER_NAME = 'specstream'
export const SERVER_URL = 'https://api.specstream.ai/mcp'

/** The credential the user stores once; `label` and `url` are what to show next to it. */
export const credential = Object.freeze({
  ref: 'SPECSTREAM_API_KEY',
  label: 'SpecStream API key',
  url: 'https://specstream.ai/?utm_source=deepseek-harness',
})

export function apply(ctx) {
  ctx.mcpManager.register(SERVER_NAME, {
    transport: 'streamable-http',
    url: SERVER_URL,
    headers: { Authorization: `Bearer \${credential:${credential.ref}}` },
  })
}
