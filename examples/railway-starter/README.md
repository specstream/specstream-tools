# SpecStream starter for Railway

One small web service that searches the live web and reads pages with [SpecStream](https://specstream.ai). It has a page with a search box and two JSON routes that your own code can call. It uses the Python standard library only.

| Route | What it does | SpecStream price |
| --- | --- | --- |
| `GET /` | A page with a search box | |
| `GET /search?q=` | Answers a question from the live web, with its sources | $5 per 1,000 searches of up to 10 results; $1 per 1,000 with `speed=fast` |
| `POST /read` | The main text of up to 20 pages: `{"urls": ["https://example.com"]}` | $0.80 per 1,000 pages. A page with no text is not charged. |
| `GET /health` | `{"status": "ok"}` | |

## Deploy on Railway

1. Create a service from this folder: in Railway choose **New**, **GitHub Repo**, `specstream/specstream-tools`, and set the root directory to `examples/railway-starter`. `railway.json` sets the Dockerfile build and the health check.
2. Set two variables:
   - `SPECSTREAM_API_KEY`: your key from [specstream.ai](https://specstream.ai). It stays on the server.
   - `APP_TOKEN`: the password of your service. Use a long random text; in a Railway template, `${{secret(32)}}` generates one.
3. Under **Networking**, generate a domain.

## Use it

`/search` and `/read` answer only a request that carries your `APP_TOKEN`, so a stranger who finds the address cannot spend your balance.

```sh
curl -G https://<your-domain>/search \
  -H "Authorization: Bearer $APP_TOKEN" \
  --data-urlencode "q=What is the population of Japan?"

curl https://<your-domain>/read \
  -H "Authorization: Bearer $APP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"]}'
```

Each route returns SpecStream's own JSON: see the [Search API](https://specstream.ai/docs/search-api) and the [Extract API](https://specstream.ai/extract-api).

## Run it on your computer

```sh
export SPECSTREAM_API_KEY="..." APP_TOKEN="a-long-random-text"
python app.py
```

Then open http://localhost:8080.
