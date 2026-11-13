# SpecStream for SAP Build and Joule Studio

Two actions that give an SAP Build process, an SAP Build app or a Joule Studio agent live web data from [SpecStream](https://specstream.ai). They run on SAP Build Actions and an SAP BTP destination, so there is nothing to deploy: import the files and add your API key.

| Action | What it does | API call | Price |
| --- | --- | --- | --- |
| Search the web | Answers a question from the live web. Every value comes with the page it was read from. | `GET /v1/web-search` | $5 per 1,000 searches of up to 10 results, $1 per 1,000 with speed set to fast |
| Extract pages | Reads the main text of 1 to 20 web pages, PDF, Word or Excel files. | `POST /v1/extract` | $0.80 per 1,000 pages; a page with no text is not charged |

## Files

| File | What it is |
| --- | --- |
| [`actions/specstream-openapi.json`](actions/specstream-openapi.json) | The API specification (OpenAPI 3.0.3) to upload to SAP Build Actions. |
| [`btp/SpecStream`](btp/SpecStream) | The destination to import in the SAP BTP cockpit. |

## Set up

1. Get an API key at [specstream.ai](https://specstream.ai).
2. Create the destination in your SAP BTP subaccount.
   - In the BTP cockpit, open Connectivity, Destinations, and choose Import Destination. Select the file `btp/SpecStream`.
   - In the property `URL.headers.Authorization`, replace `<your SpecStream API key>` with your key. Keep the word `Bearer` and the space before the key.
   - Keep the URL as `https://api.specstream.ai`, without a path. Save.
3. Add the destination to SAP Build: in the SAP Build lobby, open Control Tower, Destinations, choose New Destination, and select `SpecStream`.
4. Create the actions project: in the SAP Build lobby, open Connectors, Actions, choose Create, then Upload API Specification, and select `actions/specstream-openapi.json`. Name the project `SpecStream`.
5. In the project, add the actions `Search the web` (GET /v1/web-search) and `Extract pages` (POST /v1/extract). Test them with the destination `SpecStream`, then release and publish the project.

## Use

- **In a process:** add an action, choose `SpecStream`, and pick `Search the web` or `Extract pages`. In the process settings, add a destination variable and select `SpecStream` for it on deploy. Map `q` or `urls` from earlier steps; the answer is in `data.answer.value`, with its page in `data.answer.page`.
- **In a Joule Studio agent:** add the published `SpecStream` actions project as a tool of the agent. The agent calls `Search the web` for a fact from the web and `Extract pages` to read pages it already has.
- **In SAP Build Apps:** use the same destination through an SAP BTP Destination REST data resource.

## Results

`Search the web` returns `data` with `kind` (`fact` or `list`), `answer` (`value`, `page`, `seen_at`), `rows` for a list, the `sources` read, `took_ms` and `price_usd`. With `passages` set to true it also returns the text of the top pages.

`Extract pages` returns `data.results`, one item for each URL in the order sent, each with `status`, `title`, `text` and `published`.

An error answers with `error.code` and `error.message`. When a call is refused, check the key in the destination property `URL.headers.Authorization` and the balance of your SpecStream account.

## Support

support@specstream.ai
