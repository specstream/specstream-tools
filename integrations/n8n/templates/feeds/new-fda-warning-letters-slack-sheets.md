# Send new FDA warning letters to Slack and Google Sheets with SpecStream

Template page text for n8n.io. Workflow file: [new-fda-warning-letters-slack-sheets.json](new-fda-warning-letters-slack-sheets.json). Written by integrations/feeds/build_templates.py; edit the generator, not this file.

Status: prepared, not published. The rows address answers on production since Nov 10, 2026.

## Submission fields

- **Title:** Send new FDA warning letters to Slack and Google Sheets with SpecStream
- **Categories:** Market Research (Marketing), Personal Productivity (Other). The app icons on the card come from the nodes: Schedule Trigger, HTTP Request, Google Sheets, Slack.
- **Price:** Free.
- **Description:** everything under "Template page" below, pasted as Markdown.

---

## Template page

Every day at 11:00 UTC this workflow reads the new rows of the SpecStream feed of FDA warning letters and sends each one to Slack and to a Google Sheet. The feed is rebuilt from its official source each morning.

## What a row holds

The default feed is **FDA warning letters** (`/data/fda-warning-letters`). Each row has these columns: Company, Issue date, Posted, Issuing office, Subject, Subject group, Response letter posted, Closeout letter posted, Read on, Source.

The Slack message shows Company, Subject, Issuing office, Issue date, linked to the official record. The sheet gets every column.

## How it works

1. **Get new rows** asks SpecStream for the rows of the last 7 days your account has not had, up to 1,000, late rows included. To get older rows not delivered yet (up to 90 days back), remove its `since` parameter.
2. **Only rows not seen before** drops any row this workflow already sent, so each row is sent once.
3. If the new rows cost more than `max_cents`, SpecStream sends the oldest rows it pays for and the next day brings the rest. If it pays for no row, the workflow stops and says how many new rows wait and what they cost. It also stops with SpecStream's message on any other error, such as a wrong key.
4. One Slack message per new row, and one sheet row per new row. A day with nothing new costs nothing and posts nothing.

## What you need

* A SpecStream API key: [specstream.ai](https://specstream.ai)
* Google Sheets and Slack connected in n8n
* Nothing to install: the workflow uses only core nodes, so it runs on n8n Cloud and self-hosted n8n.

## Set up

1. Sign in at specstream.ai. Open **Agents & API** and create a key.
2. In n8n, create a **Bearer Auth** credential. Paste the key as the token, and select it in **Get new rows**.
3. In **Your feed**, keep the page or paste the page path of another feed from [specstream.ai/data/lists](https://specstream.ai/data/lists). Set `max_cents`, the most one day may cost, in cents.
4. Create a Google Sheet with these column names in its first row: Company, Issue date, Posted, Issuing office, Subject, Subject group, Response letter posted, Closeout letter posted, Read on, Source. Select it in **Add to the sheet**.
5. Select a Slack channel in **Post to Slack**.
6. Click **Execute workflow** once, then activate the workflow.

## Customize it

* **A narrower feed:** each feed of FDA warning letters has its own page path, listed at [specstream.ai/data/lists](https://specstream.ai/data/lists). Paste it in **Your feed**.
* **A different time:** change **Every day at 11:00 UTC**. The feeds are rebuilt by about 10:00 UTC.
* **Email instead of Slack:** replace **Post to Slack** with Gmail or Outlook.

## What it costs

5¢ for each row your account has not had from this feed before. A day with nothing new is free. The default maximum is $5.00 a day (100 new rows).
