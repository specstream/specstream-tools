# Send new federal grants for your field to Slack and Google Sheets every morning with SpecStream

Template page text for n8n.io. Workflow file: [new-grants-every-morning-slack-sheets.json](new-grants-every-morning-slack-sheets.json).

## Submission fields

- **Title:** Send new federal grants for your field to Slack and Google Sheets every morning with SpecStream
- **Categories:** Market Research (Marketing), Personal Productivity (Other). The app icons on the card come from the nodes: Schedule Trigger, Google Sheets, Slack, HTTP Request, Code.
- **Price:** Free.
- **Description:** everything under "Template page" below, pasted as Markdown.

## Real runs behind this page

| Run | Find id | What it returned |
|---|---|---|
| First run: "Open federal grants for cancer research", 15 results | `fnd_xsy4p9k1tzp4s10zm2jmdg4sr6` | 15 grants from Grants.gov (NIH, Defense Health Agency) |
| Next morning, run through this workflow in n8n 2.43.5 (continue the list, 3 new) | `fnd_0198y3a1dhsatne0skqzkev9w2` | 3 grants the first run didn't hold |
| The morning after, same workflow | `fnd_r0q8h1dpvyny2c3xcz38w62je5` | 3 more, none repeated from the two runs before |

Two earlier attempts with "with the award ceiling and the close date" added to the request ended with no rows (`fnd_mk56cnwfzqgdpzzfjmf6bh3sx6`, `fnd_fvkccvw8spj7zfmwqjgmqv8r37`), so the default request in the workflow is the plain sentence. The funder, the deadline and the official link come back with every Grants.gov row anyway.

---

## Template page

Every grant office has the same morning ritual: open Grants.gov, type the same keywords, scroll past what you saw yesterday, and hope nothing new slipped by on page three. This workflow does the scrolling. Each morning at 7 it asks SpecStream for open federal grants in your field and posts only the new ones to Slack, linked to the official listing. Every grant also lands in a Google Sheet, so the team has one log of what's open.

## Who it's for

- Grant writers and development teams at nonprofits
- University research offices and lab managers
- Consultants who track funding for several clients (one copy of the workflow per client)

## What a morning looks like

A real message from this workflow, from the run `fnd_0198y3a1dhsatne0skqzkev9w2`:

> **3 new grants** for "Open federal grants for cancer research"
> • [Cancer Center Support Grants (CCSGs) for NCI-designated Cancer Centers (P30 Clinical Trial Optional)](https://www.grants.gov/search-results-detail/360918) · National Institutes of Health · closes 2028-09-25
> • [DoW Rare Cancers Idea Development Award](https://www.grants.gov/search-results-detail/362849) · Defense Health Agency Contracting Activity - DHACA · closes 2026-11-18
> • [DoW Rare Cancers Resource and Community Development Award](https://www.grants.gov/search-results-detail/362850) · Defense Health Agency Contracting Activity - DHACA · closes 2026-11-18

And part of the first run, which fills the log (`fnd_xsy4p9k1tzp4s10zm2jmdg4sr6`, 15 grants):

| Grant | Funder | Number | Deadline |
|---|---|---|---|
| Early-Stage Innovative Technology Development for Basic and Clinical Cancer Research (R61) | National Institutes of Health | RFA-CA-27-001 | 2026-11-10 |
| Advanced Development and Validation of Emerging Technologies for Basic and Clinical Cancer Research (R33) | National Institutes of Health | RFA-CA-27-002 | 2026-11-10 |
| DoW Breast Cancer, Clinical Research Extension Award | Defense Health Agency Contracting Activity | HT942526BCRPCREA2 | 2026-11-18 |
| Basic Research in Cancer Health Disparities (R21) | National Institutes of Health | PAR-25-244 | 2027-11-16 |
| Exploratory Grants in Cancer Control (R21) | National Institutes of Health | PA-25-253 | 2028-09-07 |
| The Metastasis Research Network (MetNet): MetNet Research Projects (U01) | National Institutes of Health | PAR-26-134 | 2028-11-22 |
| Pancreatic Cancer Detection Consortium: Research Units (U01) | National Institutes of Health | PAR-28-056 | 2029-11-05 |

Each row in the sheet also has the opportunity number, the posted date, the assistance listings, the link to the official listing, and the date the workflow found it.

## How it works

1. **First run:** SpecStream reads your request, finds every open grant that fits, and writes them all to the sheet.
2. **Every morning after that:** the workflow opens the last list in the sheet and asks only for grants it doesn't hold yet. You never get the same grant twice.
3. **Price first:** every run gets a quote before it starts. If the quote is above your maximum, the workflow stops and tells you the price.
4. **Slack and the sheet:** one Slack message with the new grants, one sheet row per grant. A morning with nothing new costs nothing and posts nothing.

## What you need

- A SpecStream API key. New accounts get $10 of work free, no card: [specstream.ai](https://specstream.ai)
- Google Sheets and Slack connected in n8n
- Nothing to install: the workflow uses only core nodes (HTTP Request, Code, Google Sheets, Slack), so it runs on n8n Cloud and self-hosted n8n.

## Set up

1. Sign in at specstream.ai. Open **Agents & API** and create a key. Give the key a spending limit if you like.
2. In n8n, create a **Bearer Auth** credential. Paste the key as the token.
3. Select that credential in the six HTTP Request nodes: **Read the request**, **Open the last list**, **Get the price**, **Approve and start**, **Check progress** and **Get every row**.
4. In **Your grant search**, write your field after "Open federal grants for". Set `count` (the most new grants per morning) and `max_cents` (the most one morning can cost, in cents).
5. Create an empty Google Sheet. Select it in **Read the grant log** and in **Add to the grant log**.
6. Select a Slack channel in **Post to Slack**.
7. Click **Execute workflow** once. The first run fills the sheet. Then activate the workflow.

## Customize it

- **A different field:** "Open federal grants for rural broadband", "Open federal grants for early childhood education", "Open federal grants that tribes can apply for". Use a new empty sheet for each field.
- **A different time:** change **Every morning at 7** to weekly on Monday.
- **Email instead of Slack:** replace **Post to Slack** with Gmail or Outlook and send `text` as the body.
- **More than federal:** ask for foundation or state grants in the same sentence. SpecStream reads wherever that kind of grant is published.

## What it costs

10¢ a grant, shown before anything runs. The default maximum is $2.50 a morning (25 new grants). You pay only for new grants, and a morning with nothing new is free.
