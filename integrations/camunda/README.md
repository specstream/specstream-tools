# SpecStream connector templates for Camunda 8

Two connector templates that give a BPMN process live web data from [SpecStream](https://specstream.ai). Both run on the REST connector that ships with Camunda 8, so there is nothing to deploy: import a template and add your API key.

| Template | What it does | API call | Price |
| --- | --- | --- | --- |
| SpecStream Web Search | Answers a question from the live web. Every value comes with its source URL and read time. | `GET /v1/web-search` | $5 per 1,000 searches of up to 10 results, $1 per 1,000 with Speed set to Fast |
| SpecStream Extract Pages | Reads the main text of 1 to 20 web pages, PDF, Word or Excel files. | `POST /v1/extract` | $0.80 per 1,000 pages; a page with no text is not charged |

## Set up

1. Get an API key at [specstream.ai](https://specstream.ai).
2. Save the key as a Connectors secret named `SPECSTREAM_API_KEY`.
   - Camunda 8 SaaS: Console, your cluster, Connector Secrets, Create new secret.
   - Self-Managed: set the environment variable `SPECSTREAM_API_KEY` on the Connectors runtime (see the Camunda docs for the secret provider you use).
3. Add the templates.
   - Web Modeler: open your project, choose Create new, Connector template, and paste the content of a file from [`element-templates/`](element-templates/). Publish the template.
   - Desktop Modeler: copy the files from `element-templates/` to `resources/element-templates/` in the Modeler's folder, then restart it.

## Use

1. Add a task to your diagram, choose Change element, and pick SpecStream Web Search or SpecStream Extract Pages.
2. Leave API key as `{{secrets.SPECSTREAM_API_KEY}}`.
3. Fill in the fields.

### SpecStream Web Search

| Field | Value |
| --- | --- |
| Search query | The question or search query in everyday words, 1 to 2,000 characters. Text, or a FEEL expression such as `="latest funding round of " + companyName`. |
| Speed | Default or Fast. |
| Include passages | Yes adds the main text passages of the top matching pages. |

The default result expression, `={specstreamSearch: response.body}`, puts the response in the process variable `specstreamSearch`. It holds `answer` (with `value`, `page` and `seen_at`), the matching rows, the ranked sources, `took_ms` and `price_usd`.

### SpecStream Extract Pages

| Field | Value |
| --- | --- |
| URLs | A FEEL list of 1 to 20 http or https URLs, for example `["https://example.com/pricing"]` or a process variable that holds a list. |
| Output format | Markdown or Plain text. |

The default result expression, `={specstreamPages: response.body.results}`, puts one entry per URL in the process variable `specstreamPages`, each with `url`, `status`, `title`, `published`, `read_from` and `text`.

## Errors and retries

A response outside 2xx fails the job, and Camunda retries it as set in the Retries group (3 retries by default). To turn a failure into a BPMN error, set Error expression, for example:

```
=if error.code = "401" then bpmnError("SPECSTREAM_KEY", "The SpecStream API key was refused") else null
```

## Requirements

Camunda 8.3 or later, SaaS or Self-Managed, with the out-of-the-box REST connector (`io.camunda:http-json:1`).

## Docs and support

- API reference: https://specstream.ai/docs/api
- Support: support@specstream.ai

## License

MIT, with the notices for Camunda Marketplace users in [LICENSE.md](LICENSE.md).
