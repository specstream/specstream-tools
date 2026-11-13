# n8n-nodes-specstream-monitor

An [n8n](https://n8n.io) community node for [SpecStream](https://specstream.ai), the live web data engine for teams and agents. It holds one node, the **SpecStream Monitor Trigger**, which starts a workflow when a SpecStream monitor finds new or changed records on the live web.

A monitor is a Deep Search list that SpecStream runs again on a schedule you approved. Each time a run finds records that are new, or records whose facts changed, the trigger passes them to the next node, each with the page it was read from.

The trigger itself never spends money. A monitor runs only within the maximum you approved for it in SpecStream.

## Install

In n8n, go to **Settings > Community nodes**, choose **Install** and enter `n8n-nodes-specstream-monitor`.

Create an API key under **Agents & API** in your SpecStream workspace, then add a **SpecStream Monitor API** credential in n8n with that key.

## Use

1. Set up a monitor in your SpecStream workspace: open a list and choose a schedule for it.
2. Add the **SpecStream Monitor Trigger** node to a workflow and choose the credential.
3. Activate the workflow. The node registers a webhook on your SpecStream account and removes it when you deactivate the workflow.

| Setting | What it does |
| --- | --- |
| Monitor ID | Start the workflow only for this monitor (its `schedule_id`). Leave empty to start it for every monitor of your account |
| Output | **Each Record** gives one item per new or changed record. **Whole Event** gives one item with the event as SpecStream sent it |

With **Each Record**, every item carries:

| Field | Meaning |
| --- | --- |
| `change` | `new` or `changed` |
| `record` | The record: its fields, each with its source |
| `monitor_id` | The monitor that found it |
| `run_id`, `previous_run_id` | The run that found it and the run it was compared with |
| `event_id` | The event, the same for every record of one run |

The node checks the signature of every event with the secret of its own webhook, and refuses an event that is unsigned, wrongly signed or older than five minutes. n8n must keep the raw request body, which it does by default.

## Other SpecStream nodes

To search the web, read pages or build a list from a workflow, install [`n8n-nodes-specstream`](https://www.npmjs.com/package/n8n-nodes-specstream).

## Pricing

New accounts start with $10 of credit, no card. In Deep Search, a delivered result costs 5 cents, 15 cents or $1 depending on how many facts it carries. No result, no charge. See [pricing](https://specstream.ai/pricing).

## Develop

```sh
npm install
npm run build
npm run lint
npm test
```

## License

MIT
