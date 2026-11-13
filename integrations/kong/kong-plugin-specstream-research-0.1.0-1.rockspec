package = "kong-plugin-specstream-research"
version = "0.1.0-1"

-- The source is the whole public repository, so the module paths below start at its root.
source = {
  url = "git+https://github.com/specstream/specstream-tools.git",
  branch = "main",
}

description = {
  summary = "A Kong Gateway route that answers a question with a research report from the live web, with the page behind each cited sentence.",
  detailed = [[
    SpecStream Research for Kong Gateway. A route with this plugin takes a question in plain words,
    asks the SpecStream Research API for a written report, and returns the report with its sources.
    The gateway holds the SpecStream API key.
  ]],
  homepage = "https://github.com/specstream/specstream-tools/tree/main/integrations/kong",
  license = "MIT",
}

dependencies = {
  "lua >= 5.1",
}

build = {
  type = "builtin",
  modules = {
    ["kong.plugins.specstream-research.handler"] = "integrations/kong/kong/plugins/specstream-research/handler.lua",
    ["kong.plugins.specstream-research.schema"] = "integrations/kong/kong/plugins/specstream-research/schema.lua",
    ["kong.plugins.specstream-research.client"] = "integrations/kong/kong/plugins/specstream-research/client.lua",
    ["kong.plugins.specstream-research.report"] = "integrations/kong/kong/plugins/specstream-research/report.lua",
  },
}
