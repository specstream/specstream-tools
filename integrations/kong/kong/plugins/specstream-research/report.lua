-- What the plugin decides without the network: the body of POST /v1/research, the report ID a
-- reader asks for, and the HTTP status a run answers with. No Kong and no ngx here.

local _M = {}

_M.INPUT_MOST_CHARS = 15000

-- Cheapest first: the rank is what `max_depth` compares.
_M.DEPTHS = { "quick", "standard", "deep" }
local RANK = { quick = 1, standard = 2, deep = 3 }
_M.RANK = RANK

-- After these states nothing changes.
local ENDED = { completed = true, failed = true, cancelled = true, payment_required = true }

local function trim(text)
  return (tostring(text):gsub("^%s+", ""):gsub("%s+$", ""))
end

function _M.ended(run)
  return type(run) == "table" and ENDED[run.status] == true
end

-- The body to send, or nil and the reason the request is refused.
-- A field the caller left out is not sent, so the API's own default holds, except the depth:
-- the depth sets the price, so the route's default and its ceiling come from the plugin.
function _M.body(asked, conf)
  if type(asked) ~= "table" then
    return nil, 'Send a JSON object with the question in "input".'
  end
  local input = asked.input
  if input == nil then
    input = asked.question
  end
  if type(input) ~= "string" or trim(input) == "" then
    return nil, 'Write the question the report answers in "input".'
  end
  input = trim(input)
  if #input > _M.INPUT_MOST_CHARS then
    return nil, "The question holds " .. #input .. " bytes. The most is " .. _M.INPUT_MOST_CHARS .. "."
  end

  local depth = asked.depth
  if depth == nil then
    depth = conf.default_depth
  end
  if type(depth) ~= "string" or not RANK[depth] then
    return nil, "depth must be one of: quick, standard, deep."
  end
  if RANK[depth] > RANK[conf.max_depth] then
    return nil, 'This route allows reports up to depth "' .. conf.max_depth .. '".'
  end

  local body = {}
  for name, value in pairs(asked) do
    body[name] = value
  end
  body.question = nil
  -- A webhook would send the report from SpecStream to an address the caller chose, past the gateway.
  body.webhook = nil
  body.input = input
  body.depth = depth
  return body
end

-- A report ID as the API prints it ("rr_" and hex). Anything else never reaches the address of a call.
function _M.run_id(value)
  if type(value) ~= "string" or #value > 64 then
    return nil
  end
  if not value:match("^rr_%w+$") then
    return nil
  end
  return value
end

-- The report ID at the end of a request path, such as /research/rr_0123abcd.
function _M.path_run_id(path)
  if type(path) ~= "string" then
    return nil
  end
  return _M.run_id(path:match("([^/]+)/*$"))
end

-- The status the gateway answers with for a run it read.
function _M.status(run)
  if type(run) ~= "table" or type(run.status) ~= "string" then
    return 502
  end
  if run.status == "payment_required" then
    return 402
  end
  if ENDED[run.status] then
    return 200
  end
  return 202
end

return _M
