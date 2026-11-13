local typedefs = require "kong.db.schema.typedefs"

local DEPTHS = { "quick", "standard", "deep" }
local RANK = { quick = 1, standard = 2, deep = 3 }

return {
  name = "specstream-research",
  fields = {
    { protocols = typedefs.protocols_http },
    {
      config = {
        type = "record",
        fields = {
          {
            api_key = {
              description = "Your SpecStream API key. Create it under Agents & API in your SpecStream workspace.",
              type = "string",
              required = true,
              encrypted = true,
              referenceable = true,
            },
          },
          {
            default_depth = {
              description = "The depth of a report when the request names none. The depth sets the price.",
              type = "string",
              default = "standard",
              one_of = DEPTHS,
            },
          },
          {
            max_depth = {
              description = "The deepest report this route allows. A request for more is refused.",
              type = "string",
              default = "deep",
              one_of = DEPTHS,
            },
          },
          {
            wait_seconds = {
              description = "How long the gateway holds a POST until the report is written. 0 answers at once with the report ID.",
              type = "integer",
              default = 0,
              between = { 0, 900 },
            },
          },
          {
            poll_seconds = {
              description = "The time between two reads of a report while the gateway waits.",
              type = "integer",
              default = 3,
              between = { 1, 60 },
            },
          },
          {
            timeout_ms = {
              description = "The longest one call to SpecStream may take, in milliseconds.",
              type = "integer",
              default = 30000,
              between = { 1000, 120000 },
            },
          },
          {
            ssl_verify = {
              description = "Check the certificate of api.specstream.ai.",
              type = "boolean",
              default = true,
            },
          },
        },
        custom_validator = function(config)
          if RANK[config.default_depth] and RANK[config.max_depth]
            and RANK[config.default_depth] > RANK[config.max_depth] then
            return nil, "default_depth must not be deeper than max_depth"
          end
          return true
        end,
      },
    },
  },
}
