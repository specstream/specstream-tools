-- SpecStream Research for Kong Gateway.
--
-- A route with this plugin answers a question with a written report from the live web, with the
-- page behind each cited sentence. The gateway holds the SpecStream API key; the caller never sees it.
--
--   POST   <route>            {"input": "<question>", "depth": "quick"}   starts a report
--   GET    <route>/<id>       reads a report (free)
--   DELETE <route>/<id>       stops a report that is being written (a cancelled report is not charged)
--
-- The plugin answers the request itself, so the route's service is never called.

local client = require "kong.plugins.specstream-research.client"
local report = require "kong.plugins.specstream-research.report"

local JSON = { ["Content-Type"] = "application/json; charset=utf-8" }

local SpecStreamResearch = {
  -- After authentication (1000 and up), ACL (950) and rate limiting (910), so those guard the route.
  PRIORITY = 760,
  VERSION = client.VERSION,
}

local function refuse(status, message, extra)
  local headers = { ["Content-Type"] = JSON["Content-Type"] }
  for name, value in pairs(extra or {}) do
    headers[name] = value
  end
  return kong.response.exit(status, client.encode({ message = message }), headers)
end

-- The answer for a call that brought no usable run: a gateway fault, or the API's own refusal.
local function failed(status, text, err)
  if not status then
    kong.log.err("SpecStream did not answer: ", text or err)
    return refuse(502, "SpecStream did not answer. Try again.")
  end
  if status == 401 or status == 403 then
    kong.log.err("SpecStream refused the API key of this plugin (HTTP ", status, ")")
    return refuse(502, "The gateway's SpecStream API key was refused. Tell the owner of this gateway.")
  end
  if status < 400 or status >= 500 or type(text) ~= "string" or text == "" then
    return refuse(502, "SpecStream answered with an error (HTTP " .. status .. "). Try again.")
  end
  -- 402, 404, 409, 422, 429: the API's own words say what to change.
  return kong.response.exit(status, text, JSON)
end

local function answer(run, text)
  return kong.response.exit(report.status(run), text, JSON)
end

-- Reads the run until it has ended or the route's wait is over.
-- Returns the last run read and its text, or nil, nil and the refusal that stopped the wait.
local function wait(conf, run, text)
  local until_time = ngx.now() + conf.wait_seconds
  while not report.ended(run) and ngx.now() + conf.poll_seconds <= until_time do
    ngx.sleep(conf.poll_seconds)
    local status, new_text, new_run = client.read(conf, run.id)
    if status == 200 and type(new_run) == "table" then
      run, text = new_run, new_text
    elseif not status or status >= 500 or status == 429 then
      kong.log.warn("SpecStream did not show report ", run.id, " (", status or "no answer", "); asking again")
    else
      return nil, nil, status, new_text
    end
  end
  return run, text
end

local function start(conf)
  local raw = kong.request.get_raw_body()
  if raw == nil then
    return refuse(413, "The request body is too large for this gateway to read.")
  end
  local asked = client.decode(raw)
  local body, why = report.body(asked, conf)
  if not body then
    return refuse(400, why)
  end

  local key = kong.request.get_header("Idempotency-Key")
  if type(key) ~= "string" or key == "" then
    key = nil
  end

  local status, text, run = client.create(conf, body, key)
  if not (status and status >= 200 and status < 300 and type(run) == "table" and report.run_id(run.id)) then
    return failed(status, text, run)
  end

  if conf.wait_seconds > 0 then
    -- The first answer carries no report, so the run is read at least once.
    local read_status, read_text, read_run = client.read(conf, run.id)
    if read_status == 200 and type(read_run) == "table" then
      run, text = read_run, read_text
    end
    local err_status, err_text
    run, text, err_status, err_text = wait(conf, run, text)
    if not run then
      return failed(err_status, err_text)
    end
  end
  return answer(run, text)
end

local function read(conf, run_id)
  local status, text, run = client.read(conf, run_id)
  if status ~= 200 or type(run) ~= "table" then
    return failed(status, text, run)
  end
  return answer(run, text)
end

local function cancel(conf, run_id)
  local status, text, run = client.cancel(conf, run_id)
  if status ~= 200 or type(run) ~= "table" then
    return failed(status, text, run)
  end
  return kong.response.exit(200, text, JSON)
end

function SpecStreamResearch:access(conf)
  local method = kong.request.get_method()
  if method == "POST" then
    return start(conf)
  end
  if method == "GET" or method == "DELETE" then
    local run_id = report.path_run_id(kong.request.get_path())
    if not run_id then
      return refuse(400, "Put the report ID at the end of the path, such as /rr_0123abcd.")
    end
    if method == "GET" then
      return read(conf, run_id)
    end
    return cancel(conf, run_id)
  end
  return refuse(405, "Use POST to start a report, GET to read one and DELETE to stop one.", { Allow = "POST, GET, DELETE" })
end

return SpecStreamResearch
