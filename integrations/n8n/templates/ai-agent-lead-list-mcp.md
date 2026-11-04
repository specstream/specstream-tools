# Ask an AI agent for a lead list in chat, with the SpecStream MCP server and Google Sheets

Template page text for n8n.io. Workflow file: [ai-agent-lead-list-mcp.json](ai-agent-lead-list-mcp.json).

## Submission fields

- **Title:** Ask an AI agent for a lead list in chat, with the SpecStream MCP server and Google Sheets
- **Categories:** Lead Generation (Sales), AI Chatbot (AI). The app icons on the card come from the nodes: Chat Trigger, AI Agent, OpenAI Chat Model, Simple Memory, MCP Client Tool, Google Sheets Tool.
- **Price:** Free.
- **Description:** everything under "Template page" below, pasted as Markdown.

## Real runs behind this page

| Run | Find id | What it returned |
|---|---|---|
| "Web design agencies in Austin, Texas, with their website, phone number and email", 10 results | `fnd_74hsa1m8jftxs9p3jyd7rchek4` | 10 agencies, 7 with a published email or phone |
| "Find 5 more" on the same list | `fnd_gfjd0nc2w3k9bzscrcn5hmha74` | 5 new agencies, none repeated |

Tested in n8n 2.43.5: the workflow imports cleanly, and the **SpecStream** node settings (Streamable HTTP, Bearer Auth) connect to `https://api.specstream.ai/mcp` and call `compile`. The rows above came from the same request through the API the MCP tools call.

---

## Template page

Ask for a lead list the way you'd ask a colleague, and get the list back in the chat: *25 web design agencies in Austin with their email and phone*. The agent sends the request to SpecStream over MCP, tells you what the list will cost, waits for your yes, then shows the rows and saves them to Google Sheets when you ask.

An agent that browses and summarizes will sooner or later invent the email it couldn't find. Here the model never writes a row. SpecStream finds every match on the live web and returns each row with its source URL and read time; the agent only reads it back to you.

## Who it's for

- Agencies building prospect lists for themselves or for clients
- Sales teams that want a list in the time it takes to type a sentence
- Anyone building an agent in n8n who needs company or local business data it can act on

## What you get

Real rows from the request "Web design agencies in Austin, Texas, with their website, phone number and email" (`fnd_74hsa1m8jftxs9p3jyd7rchek4`):

| Agency | Website | Phone | Email |
|---|---|---|---|
| GLIDE | glidedesign.com | 512-215-4236 | hello@glidedesign.com |
| HMG Creative | hmgcreative.com | 888-744-0464 | hello@hmgcreative.com |
| Big Gorilla Design | biggorilladesign.com | 512-550-2358 | info@biggorilladesign.com |
| Webii | webii.net | 512-241-1777 | sales@webii.net |
| CreativePickle | creativepickle.com | 512-796-5405 | info@creativepickle.com |
| Website Design Austin Texas | websitedesignaustintexas.com | 512-295-6816 | |
| Practice Cafe | practicecafe.com | 888-575-2233 | |

Empty cells are details the business didn't publish. The agent leaves them empty instead of guessing. Ask "find 5 more" and you get new agencies only (`fnd_gfjd0nc2w3k9bzscrcn5hmha74` added SaaSify Labs, Fahrenheit Marketing, Kinematic Digital, Austin Web Design and CSTMR).

## How it works

1. **Chat Trigger** takes your message.
2. **Lead list agent** follows a short script: read the request, get a quote, show you the price, and wait for your yes.
3. **SpecStream** connects to `https://api.specstream.ai/mcp` with six tools: `compile` (read the request), `quote_capacity_work` (price it), `authorize_capacity_work` (start it after your yes), `get_find` (progress), `list_find_rows` (the rows with their sources) and `share_find` (a link anyone can open).
4. **add_lead_to_sheet** appends one row per lead to your Google Sheet when you ask to save the list.

The agent never starts paid work on its own. It needs your yes in the chat, it refuses any quote above `max_usd` in **Settings**, and the API key carries its own spending limit that the agent can't raise.

## What you need

- A SpecStream API key. New accounts get $10 of work free, no card: [specstream.ai](https://specstream.ai)
- An OpenAI API key, or any chat model n8n supports
- Google Sheets connected in n8n
- Nothing to install: MCP Client Tool is a core node, so this runs on n8n Cloud and self-hosted n8n.

## Set up

1. Sign in at specstream.ai. Open **Agents & API**, create a key and set a spending limit on it.
2. Open **SpecStream**. Create a **Bearer Auth** credential and paste the key as the token.
3. Open **OpenAI Chat Model** and add your OpenAI credential, or replace the node with another chat model.
4. Create a Google Sheet with the headers Name, Website, Phone, Email, City, Source, Request. Select it in **add_lead_to_sheet**.
5. Set `max_usd` in **Settings**: the most one list may cost.
6. Click **Open chat** and ask for a list. Lists usually take 2 to 10 minutes; ask "is it ready?" and the agent checks.

## Customize it

- **More tools:** add `export_find` to **SpecStream** for a CSV or Excel link, or `create_capacity_schedule` to keep a list up to date and get new matches on a schedule.
- **Other kinds of lists:** the same agent finds companies, local businesses, open grants, job posts and tenders. Ask in plain words.
- **Somewhere other than chat:** swap the Chat Trigger for Slack or Telegram so the team can ask from where they already talk.

## What it costs

5¢, 15¢ or $1 a match depending on the list, plus a little more for a named person's email or phone. The agent shows the exact maximum before anything runs. You pay only for the matches, and a search that finds nothing is free.
