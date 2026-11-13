# SpecStream Research for Kong Gateway

A [Kong Gateway](https://github.com/Kong/kong) plugin for [SpecStream](https://specstream.ai), the live web data engine for teams and agents. A route with this plugin answers a question with a written report from the live web, with the page behind each cited sentence.

The caller sends the question in plain words to your gateway. SpecStream searches, reads the pages and writes the report. Each cited sentence carries a `[1]` marker, and the report lists the page, the time it was read and the passage behind each marker.

The gateway holds your SpecStream API key, so the callers of the route never see it. Kong's own plugins for authentication, access lists and rate limits run before this one and guard the route.

## Install

The plugin is four Lua files and works with Kong Gateway 3.x.

With LuaRocks, on each Kong node:

```sh
luarocks install https://raw.githubusercontent.com/specstream/specstream-tools/main/integrations/kong/kong-plugin-specstream-research-0.1.0-1.rockspec
```

Or copy the folder `kong/plugins/specstream-research` to a path that Kong reads, and name that path in `KONG_LUA_PACKAGE_PATH`.

Then load the plugin and restart Kong:

```sh
export KONG_PLUGINS=bundled,specstream-research
kong restart
```

## Set up a route

Create an API key under **Agents & API** in your SpecStream workspace. Then add a service, a route and the plugin:

```sh
curl -X POST http://localhost:8001/services \
  --data name=specstream-research --data url=https://api.specstream.ai
curl -X POST http://localhost:8001/services/specstream-research/routes \
  --data name=research --data 'paths[]=/research'
curl -X POST http://localhost:8001/routes/research/plugins \
  --data name=specstream-research --data config.api_key=$SPECSTREAM_API_KEY
```

The plugin answers each request itself, so the address of the service is never called. `kong.example.yml` holds the same route for a DB-less Kong.

## Use

Start a report:

```sh
curl -X POST http://localhost:8000/research \
  -H 'Content-Type: application/json' \
  -d '{"input": "Which EU countries tax sugary drinks, and at what rate?", "depth": "quick"}'
```

The gateway answers `202` with the report's `id` and its price. Read the report until `status` is `completed`:

```sh
curl http://localhost:8000/research/rr_0123456789abcdef01234567
```

| Request | What it does |
| --- | --- |
| `POST <route>` | Starts a report for the question in `input` |
| `GET <route>/<id>` | Reads a report by its ID. Reading is free |
| `DELETE <route>/<id>` | Stops a report that is being written. A cancelled report is not charged |

The body of the `POST` takes the fields of the [SpecStream Research API](https://specstream.ai/docs/api): `input`, `depth`, `length`, `language`, `include_domains`, `exclude_domains`, `after_date`, `output` and `metadata`. The plugin removes `webhook`, so a report leaves only through your gateway.

A finished report carries:

| Field | Meaning |
| --- | --- |
| `report.content` | The text, in Markdown, with `[1]` markers |
| `report.citations` | For each marker: the page, the time it was read and the passage |
| `report.sources` | Every page read |
| `report.structured` | The answer as JSON, when the request set `output` to a JSON Schema |
| `usage.charged_usd` | What the report cost |

The gateway answers `200` for a report that has ended, `202` for a report that is still being written and `402` when the balance does not hold the price.

Send an `Idempotency-Key` header with the `POST` to retry safely: the same key and body return the same report, never a second one.

## Settings

| Setting | Default | What it does |
| --- | --- | --- |
| `api_key` | | Your SpecStream API key. It can be a Kong vault reference |
| `default_depth` | `standard` | The depth of a report when the request names none: `quick`, `standard` or `deep` |
| `max_depth` | `deep` | The deepest report the route allows. A request for more is refused with `400` |
| `wait_seconds` | `0` | How long the gateway holds a `POST` until the report is written, up to 900. With `0` the gateway answers at once with the report ID |
| `poll_seconds` | `3` | The time between two reads of a report while the gateway waits |
| `timeout_ms` | `30000` | The longest one call to SpecStream may take |
| `ssl_verify` | `true` | Check the certificate of `api.specstream.ai` |

With `wait_seconds` set, a report that is not written in that time comes back as `202` with its ID, and the report is not lost. A client that waits must allow a response time as long as `wait_seconds`.

## Pricing

A report costs $0.10 (`quick`), $0.30 (`standard`) or $1.00 (`deep`). The price is taken from your balance once, when the report is delivered. A cancelled report is not charged. A quick report takes about a minute, a standard report about four minutes and a deep report about five.

Every caller of the route spends from the balance of the plugin's API key. Use `max_depth` and Kong's rate limiting plugin to set the most a route can spend.

New accounts start with $10 of credit, no card. See [pricing](https://specstream.ai/pricing).

## Develop

The tests run the plugin's Lua files in LuaJIT with a scripted Kong and a scripted SpecStream API. They call no network.

```sh
uv run --frozen pytest -q
```

## License

MIT
