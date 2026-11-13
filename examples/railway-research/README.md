# SpecStream deep research for Railway

One small web service that answers a question with a written report from the live web. [SpecStream](https://specstream.ai) searches, reads the pages and writes the report, with the page behind each cited sentence. The service has a page with a question box and JSON routes that your own code can call. It uses the Python standard library only, and it needs one key only: no model key and no search key.

| Route | What it does |
| --- | --- |
| `GET /` | A page with a question box. It shows the report and its sources. |
| `POST /research` | Starts a report: `{"question": "...", "depth": "quick"}` |
| `GET /research/<id>` | The run: its status, its progress and, when it is completed, the report |
| `POST /research/<id>/cancel` | Stops a run that is not finished |
| `GET /health` | `{"status": "ok"}` |

A report costs $0.10 (quick), $0.30 (standard) or $1.00 (deep). SpecStream charges it one time, when the report is delivered. To read a run costs nothing.

## Deploy on Railway

1. Create a service from this folder: in Railway choose **New**, **GitHub Repo**, `specstream/specstream-tools`, and set the root directory to `examples/railway-research`. `railway.json` sets the Dockerfile build and the health check.
2. Set the variables:
   - `SPECSTREAM_API_KEY`: your key from [specstream.ai](https://specstream.ai). It stays on the server.
   - `APP_TOKEN`: the password of your service. Use a long random text; in a Railway template, `${{secret(32)}}` generates one.
   - `MAX_DEPTH` (optional): the deepest report the service starts, `quick`, `standard` or `deep`. The default is `deep`.
3. Under **Networking**, generate a domain.

## Use it

The `/research` routes answer only a request that carries your `APP_TOKEN`, so a stranger who finds the address cannot spend your balance.

```sh
curl https://<your-domain>/research \
  -H "Authorization: Bearer $APP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "How do the prices of the main cloud GPU providers compare this month?", "depth": "quick"}'

curl https://<your-domain>/research/<id> \
  -H "Authorization: Bearer $APP_TOKEN"
```

The first call returns the run with its `id`, `status` and `price_usd`. Read the run until its `status` is `completed`. Then `report` holds the `title`, the `content` in Markdown with numbered citations, the `citations` (the page, the read time and the excerpt behind each cited sentence) and the `sources`.

The same question at the same depth in the same hour returns the run that is already started, so a retry does not buy the report twice.

Each route returns SpecStream's own JSON: see the [Research API](https://specstream.ai/docs/research).

## Run it on your computer

```sh
export SPECSTREAM_API_KEY="..." APP_TOKEN="a-long-random-text"
python app.py
```

Then open http://localhost:8080.
