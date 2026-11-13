# SpecStream browser runner

A container that gives Puppeteer, Playwright and every other CDP client one address:
`ws://localhost:3000`.
Each connection starts a real Chromium at SpecStream, and the browser ends when the client disconnects.

The browser does not run in the container.
The image holds no Chromium, so it is small, it needs no `--shm-size`, and it uses the same memory with one connection or fifty.

## Start

```bash
docker run -d -p 3000:3000 -e SPECSTREAM_API_KEY=<your key> specstream/browser-runner
```

Get a key at <https://specstream.ai/workspace/agents?tab=keys>.
The key stays in the container: your clients connect without it.

## Connect

Puppeteer:

```js
import puppeteer from "puppeteer-core";

const browser = await puppeteer.connect({ browserWSEndpoint: "ws://localhost:3000" });
const page = await browser.newPage();
await page.goto("https://example.com");
console.log(await page.title());
await browser.close();
```

Playwright (Python):

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("ws://localhost:3000")
    page = browser.new_page()
    page.goto("https://example.com")
    print(page.title())
    browser.close()
```

`http://localhost:3000` works too for clients that read `/json/version` first.

A client that used `browserless/chrome` on port 3000 keeps its code: the address is the same.

## Docker Compose

```yaml
services:
  browser:
    image: specstream/browser-runner
    environment:
      SPECSTREAM_API_KEY: ${SPECSTREAM_API_KEY}
  app:
    build: .
    environment:
      BROWSER_WS_ENDPOINT: ws://browser:3000
```

## Settings

| Variable | Default | What it does |
| --- | --- | --- |
| `SPECSTREAM_API_KEY` | none, required | The key the sessions are charged to. |
| `PORT` | `3000` | The port the runner listens on. |
| `RUNNER_TOKEN` | none | When set, a client must connect with `?token=<value>`. Set it when the port is open to more than your own services. |
| `SESSION_TIMEOUT_S` | `300` | The most seconds one browser runs, from 60 to 3600. |
| `HEADLESS` | `true` | `false` gives the browser a screen, for sites that act differently without one. |
| `BLOCK_MEDIA` | `false` | `true` skips images, video, audio and fonts. |
| `ALLOWED_DOMAINS` | none | Hosts the browser may open, separated by commas, such as `example.com,*.example.org`. |
| `SPECSTREAM_API_URL` | `https://api.specstream.ai` | The API the runner calls. |

A client can also set two values in the address for one connection:
`?timeout=120000` (milliseconds) and `?headless=false`.

## Addresses

| Address | Answer |
| --- | --- |
| `ws://<host>:3000/` | Starts a browser and pipes CDP to it. Every path works. |
| `GET /json/version` | The WebSocket address, as CDP clients expect it. It starts no browser. |
| `GET /health` | `{"status": "ok"}`, for a health check. It starts no browser. |

When SpecStream refuses a session (a wrong key, an empty balance, too many open browsers), the connection is refused with the same HTTP status and message.

## Price

Browser time is $0.10 an hour, charged by the second.
The container itself costs nothing, and `/health` and `/json/version` start no browser.

## Build it yourself

```bash
git clone https://github.com/specstream/specstream-tools
docker build -t specstream/browser-runner specstream-tools/docker/browser-runner
```

The runner is one file, `runner.py`, with one dependency (aiohttp).
