# SpecStream Browser

A real browser in the cloud for your GitHub workflow. Read a page that needs JavaScript, take a screenshot, or connect Playwright or Puppeteer to it. Nothing is installed on the runner, and the browser closes when the job ends.

## Read a page

```yaml
- uses: specstream/browser-action@v1
  id: page
  with:
    api_key: ${{ secrets.SPECSTREAM_API_KEY }}
    url: https://example.com/pricing
    screenshot: true
    keep_open: false
- run: cat "${{ steps.page.outputs.page_path }}"
```

The page's text is written as Markdown to `page_path`, and the screenshot to `screenshot_path`.

## Connect your own code

```yaml
- uses: specstream/browser-action@v1
  id: browser
  with:
    api_key: ${{ secrets.SPECSTREAM_API_KEY }}
- run: node check.js
  env:
    BROWSER_WS: ${{ steps.browser.outputs.connect_url }}
```

```js
// check.js
const { chromium } = require('playwright-core');

(async () => {
  const browser = await chromium.connectOverCDP(process.env.BROWSER_WS);
  const page = await browser.contexts()[0].newPage();
  await page.goto('https://example.com');
  console.log(await page.title());
  await browser.close();
})();
```

`connect_url` speaks the Chrome DevTools Protocol, so Playwright `connectOverCDP`, Puppeteer `connect`, browser-use and Stagehand use it as it is. Its token belongs to this one session and stops working when the session ends. The action hides it in the logs.

## Inputs

| Input | Required | |
| --- | --- | --- |
| `api_key` | yes | A SpecStream API key. Keep it in a repository secret |
| `url` | no | A page to open and read. Leave it empty to only open the browser |
| `format` | no | `markdown` (default) or `text` |
| `screenshot` | no | `true` also saves a PNG of the page. Needs `url` |
| `timeout_s` | no | The most seconds the browser runs, from 60 to 3600. Defaults to 300 |
| `allowed_domains` | no | Hosts the browser may open, separated by commas or new lines. Empty allows every public host |
| `block_media` | no | `true` skips images, video, audio and fonts |
| `headless` | no | `false` runs the browser with a screen |
| `keep_open` | no | `false` closes the browser when this step ends. By default it stays open for the next steps and closes when the job ends |
| `base_url` | no | Defaults to `https://api.specstream.ai` |

## Outputs

`session_id`, `connect_url` and `live_url` describe the open browser. `live_url` is a page that shows the browser's screen as it changes. `page_path`, `page_url`, `page_title` and `screenshot_path` are set when `url` is set.

## Price

Browser time is $0.10 an hour, charged by the second, plus $1 per 1,000 steps. A step is one action the action takes for you, such as opening the page, reading it or taking the screenshot. The log of the closing step shows the seconds, the steps and the charge.

## Notes

- The browser closes when the job ends, whether the job passed or failed. If that call does not get through, the browser ends at `timeout_s`.
- A page outside `allowed_domains` stops the step with `blocked`.
- Get an API key at https://specstream.ai/workspace/agents?tab=keys.

Support: support@specstream.ai. MIT license.
