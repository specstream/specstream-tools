# SpecStream for Retool

Research reports from the live web inside a Retool app, workflow or agent. You ask a question in plain words and [SpecStream](https://specstream.ai) writes a report in which each cited sentence links to the page it was read from.

There is nothing to deploy. Retool loads one API specification and shows each action by name.

| Action | What it does | API call | Price |
| --- | --- | --- | --- |
| Start a research report | Starts a report and answers at once with its `id`. | `POST /v1/research` | $0.10 (`quick`), $0.30 (`standard`) or $1.00 (`deep`) a report |
| Read a research report | Reads the report by its `id`: its state, then its text, citations and sources. | `GET /v1/research/{run_id}` | Free |
| List research reports | Lists the account's reports, newest first. | `GET /v1/research` | Free |
| Cancel a research report | Stops a report. A cancelled report is not charged. | `POST /v1/research/{run_id}/cancel` | Free |

The price is taken from the balance once, when the report is delivered. A new account starts with $10 of credit.

## Set up the resource

1. Get an API key: sign in at [specstream.ai/workspace](https://specstream.ai/workspace) and create one under Agents & API.
2. In Retool, open **Resources**, choose **Create new**, then **Resource**, and select **REST API**.
3. Name the resource `SpecStream`.
4. Under **Query mode**, select **Use an API spec**.
5. In **Spec URL**, enter `https://specstream.ai/retool/specstream-openapi.json` and choose **Load spec**. The server URL fills in as `https://api.specstream.ai`.
6. Under **Authentication**, select **Bearer token** and enter your API key.
7. Choose **Test connection**, then **Create resource**.

The same file is in this folder as [`specstream-openapi.json`](specstream-openapi.json) (OpenAPI 3.0.3), for a self-hosted Retool that cannot reach the address above.

## In an app

1. Add a query on the `SpecStream` resource and pick **Start a research report**. Name it `startResearch`.
   - `input`: the question, for example `{{ questionInput.value }}`. It holds up to 15,000 characters.
   - `depth`: `quick`, `standard` or `deep`. Without it the report is `standard`.
2. Add a second query, pick **Read a research report** and name it `getResearch`. Set `run_id` to `{{ startResearch.data.data.id }}`.
3. In the success handler of `startResearch`, trigger `getResearch`. On `getResearch`, turn on **Run this query periodically** with an interval of 5000 ms, and stop it when `{{ getResearch.data.data.status }}` is `completed`, `failed` or `cancelled`.
4. Show `{{ getResearch.data.data.report.content }}` in a Text component (it is Markdown) and `{{ getResearch.data.data.report.sources }}` in a Table.

A quick report takes about a minute, a standard report about four minutes and a deep report about five. `stage` and `progress` show where the report is while you wait.

## In a workflow

A workflow does not need to wait for the report. SpecStream calls a second workflow when the report ends.

1. Create a workflow with a **Webhook** trigger. Copy its URL.
2. In the workflow that asks the question, add a Resource query block on `SpecStream`, pick **Start a research report**, and set `webhook` to `{"url": "<the webhook URL>"}`.
3. When the report ends, SpecStream sends the webhook workflow a `POST` with `event` (`research.completed`, `research.failed` or `research.cancelled`), `run_id`, `status` and `depth`. The call holds no report.
4. In the webhook workflow, add a Resource query block with **Read a research report** and set `run_id` to `{{ startTrigger.data.run_id }}`. The report is in `data.report`.

To start the same report only once when a workflow retries, send the header `Idempotency-Key` with your own ID of at most 128 characters. The same key and body return the same report.

## In an agent

Retool Agents can use the SpecStream MCP server as a tool.

1. In **Resources**, choose **Create new**, then **Resource**, and select **MCP Server**.
2. In **Server URL**, enter `https://api.specstream.ai/mcp`.
3. Under **Authentication**, select **Bearer Token** and enter your API key, or keep **Automatic** to sign in with OAuth.
4. Add the resource as a tool on the agent.

The agent then has `research_price`, `start_research` and `get_research` for reports, `search_web` for one fact and `read_pages` for the text of known pages. `start_research` runs only with the price the person approved, sent as `confirm_max_cents`.

## Results

**Start a research report** returns `data` with the report's `id`, its `status`, its `depth` and `price_usd`.

**Read a research report** returns `data` with:

- `status`: `queued`, `running`, `completed`, `failed`, `cancelled` or `payment_required`.
- `stage` and `progress`: where the report is while it runs.
- `report.title` and `report.content`: the text, in Markdown, with `[1]` markers.
- `report.citations`: for each cited sentence, its page, read time and passage.
- `report.sources`: every page read.

For JSON in place of text, set `output` to `{"type": "json", "schema": {<a JSON Schema>}}`. The filled object is in `report.structured`. `length` is `short`, `standard` or `long`. `include_domains` and `exclude_domains` choose the sites.

## Errors

An error answers with `error.code` and `error.message`.

- `401`: the key is missing or wrong. Check the Bearer token of the resource.
- `402`: the balance does not hold the report's price.
- `404`: no such report on this account.
- `409`: the `Idempotency-Key` was used with another body.
- `422`: a field is wrong. The reply names it.
- `429` with `Retry-After`: the account used its calls for the minute.

## Support

support@specstream.ai
