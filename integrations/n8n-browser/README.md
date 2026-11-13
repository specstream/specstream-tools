# n8n-nodes-specstream-browser

An [n8n](https://n8n.io) community node for [SpecStream](https://specstream.ai), the live web data engine for teams and agents. It holds one node, **SpecStream Browser**, which opens a real browser in the cloud and drives it from a workflow: go to a page, read it, click, type, take a screenshot.

Use it for pages that a plain request cannot read: pages built by scripts, pages behind a button or a form, and pages you need as a picture. The browser runs on SpecStream, so n8n needs no Chrome, no Puppeteer and no extra container.

## Install

In n8n, go to **Settings > Community nodes**, choose **Install** and enter `n8n-nodes-specstream-browser`.

Create an API key under **Agents & API** in your SpecStream workspace, then add a **SpecStream Browser API** credential in n8n with that key.

## Use

Add the **SpecStream Browser** node to a workflow, choose the credential, then choose a resource and an operation.

For one page, **Read a Web Page** is the whole job in one step: it opens a browser, goes to the address, returns the text of the page and closes the browser.

For more than one step on the same page, open a session, pass its `id` to each step as **Session ID**, and close the session at the end.

Operations of **Page**:

| Operation | What it does |
| --- | --- |
| Read a Web Page | Opens a browser, goes to an address, reads the text of the page and closes the browser, in one step |
| Go to a Page | Opens an address in the session |
| Read the Page | Returns the text of the page that the session shows, as Markdown or plain text |
| Get Page Snapshot | Returns the elements of the page with the `ref` of each, for **Click** and **Type** |
| Click | Clicks an element, by its `ref` |
| Type | Types text into a field, by its `ref`, and can press Enter after |
| Take a Screenshot | Returns a picture of the page as a PNG file, the part in view or the full page |
| Run a Tool | Runs any other Playwright MCP tool in the session, such as `browser_press_key`, with its arguments as JSON |

Operations of **Session**:

| Operation | What it does |
| --- | --- |
| Open | Starts a browser and returns its `id` |
| Get | Reads the state of a session: its time, its steps and what it has cost |
| Get Many | Lists the sessions of your account |
| Close | Ends the session and stops its charge |

Options of **Open** and **Read a Web Page**:

| Option | What it does |
| --- | --- |
| Allowed Domains | The only hosts the browser may open. Empty allows every public host |
| Block Media | Skips images, video, audio and fonts, so pages load faster |
| Headless | Off runs the browser with a screen, for sites that act differently without one |
| Idle Timeout (Seconds) | The session ends after this many seconds with no step |
| Keep Alive | The session stays open when a client that drives it over its `connect_url` disconnects |
| Timeout (Seconds) | The most seconds the session runs |

Each step on a page returns:

| Field | Meaning |
| --- | --- |
| `text` | What the step returned: the text of the page, the snapshot, or the result of the action |
| `url`, `title` | The page the session shows after the step |
| `price_usd` | What the step cost |
| `data` (binary) | The picture, for **Take a Screenshot** |

**Read a Web Page** also returns `seconds`, `actions` and `charged_usd`: what the whole session cost.

The node can also be used as a tool by an n8n AI agent.

## Pricing

A session costs $0.10 an hour, charged by the second. Each step costs $0.001 ($1 per 1,000 steps).

A session that a workflow does not close ends by its own timeout. **Read a Web Page** closes its browser in every case, also when a step fails.

New accounts start with $10 of credit, no card. See [pricing](https://specstream.ai/pricing).

## Other SpecStream nodes

To search the web, read pages or build a list from a workflow, install [`n8n-nodes-specstream`](https://www.npmjs.com/package/n8n-nodes-specstream). To write a research report with the page behind each cited sentence, install [`n8n-nodes-specstream-research`](https://www.npmjs.com/package/n8n-nodes-specstream-research). To start a workflow when a monitor finds new or changed records, install [`n8n-nodes-specstream-monitor`](https://www.npmjs.com/package/n8n-nodes-specstream-monitor).

## Develop

```sh
npm install
npm run build
npm run lint
npm test
```

## License

MIT
