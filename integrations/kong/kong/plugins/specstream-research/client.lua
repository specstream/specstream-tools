-- The calls to the SpecStream Research API. The API key goes only to https://api.specstream.ai.

local http = require "resty.http"
local cjson = require("cjson.safe").new()

-- An empty JSON array stays an array when a request body is decoded and encoded again.
if cjson.decode_array_with_array_mt then
  cjson.decode_array_with_array_mt(true)
end

local _M = {}

_M.API_BASE = "https://api.specstream.ai"
_M.RESEARCH_PATH = "/v1/research"
_M.VERSION = "0.1.0"

_M.decode = cjson.decode
_M.encode = cjson.encode

-- One call. Returns the HTTP status, the body as text and the body as a table (nil when it is not JSON),
-- or nil and the reason no answer came.
function _M.call(conf, method, path, body, headers)
  local client, err = http.new()
  if not client then
    return nil, err
  end
  client:set_timeout(conf.timeout_ms)

  local sent = {
    ["Authorization"] = "Bearer " .. conf.api_key,
    ["Accept"] = "application/json",
    ["User-Agent"] = "kong-plugin-specstream-research/" .. _M.VERSION,
  }
  for name, value in pairs(headers or {}) do
    sent[name] = value
  end
  local text
  if body ~= nil then
    text, err = cjson.encode(body)
    if not text then
      return nil, err
    end
    sent["Content-Type"] = "application/json"
  end

  local res
  res, err = client:request_uri(_M.API_BASE .. path, {
    method = method,
    body = text,
    headers = sent,
    ssl_verify = conf.ssl_verify,
  })
  if not res then
    return nil, err
  end
  local decoded
  if type(res.body) == "string" and res.body ~= "" then
    decoded = cjson.decode(res.body)
  end
  return res.status, res.body, decoded
end

function _M.create(conf, body, idempotency_key)
  local headers
  if idempotency_key then
    headers = { ["Idempotency-Key"] = idempotency_key }
  end
  return _M.call(conf, "POST", _M.RESEARCH_PATH, body, headers)
end

function _M.read(conf, run_id)
  return _M.call(conf, "GET", _M.RESEARCH_PATH .. "/" .. run_id)
end

function _M.cancel(conf, run_id)
  return _M.call(conf, "POST", _M.RESEARCH_PATH .. "/" .. run_id .. "/cancel")
end

return _M
