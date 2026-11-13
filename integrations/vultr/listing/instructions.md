## Open the research page

The page is ready about two minutes after the server starts.

1. Open [https://{{ip}}/](https://{{ip}}/) in a browser.
1. The certificate is made on your server for its own address, so the browser shows a warning the first time. Continue to the page.
1. Sign in with these details:

| Field | Value |
| --- | --- |
| User name | `research` |
| Password | `{{web_pass}}` |

## Save your SpecStream API key

If you did not type a key when you deployed the server, the page asks for one.

1. Create an account at [specstream.ai/workspace](https://specstream.ai/workspace?utm_source=vultr). It starts with $10 of credit.
1. Copy an API key from the workspace.
1. Paste it in the field "SpecStream API key" on the research page and select "Save the key".

## Write a report

1. Type your question.
1. Choose a depth: quick ($0.10, about a minute), standard ($0.30, about four minutes) or deep ($1.00, about five minutes).
1. Select "Write the report". The page shows the progress and then the report, with the page behind each cited sentence.

The price is charged to your SpecStream account when the report is delivered. A stopped or failed report is not charged.

## Use the command line

Connect to the server as root (`ssh root@{{ip}}`, password `{{root_password}}`) and run:

`specstream-research "What changed in the EU AI Act timeline this year?" --depth quick`

The command prints the report as Markdown. It uses the key saved on the page.

## Where things are

| What | Where |
| --- | --- |
| Reports | `/var/lib/specstream-research/reports/` |
| API key | `/var/lib/specstream-research/api-key` |
| Page password | `/etc/specstream-research/web-password` |
| Service | `systemctl status specstream-research` |
| First-boot log | `/var/log/specstream-research-provision.log` |

To use your own domain and certificate, edit `/etc/nginx/sites-available/specstream-research`.

## Help

SpecStream documentation: [specstream.ai/docs](https://specstream.ai/docs)
