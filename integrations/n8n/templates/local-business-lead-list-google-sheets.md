# Build a lead list of local businesses in any city into Google Sheets with SpecStream

Template page text for n8n.io. Workflow file: [local-business-lead-list-google-sheets.json](local-business-lead-list-google-sheets.json).

## Submission fields

- **Title:** Build a lead list of local businesses in any city into Google Sheets with SpecStream
- **Categories:** Lead Generation (Sales), Market Research (Marketing). The app icons on the card come from the nodes: n8n Form, HTTP Request, Code, Google Sheets.
- **Price:** Free.
- **Description:** everything under "Template page" below, pasted as Markdown.

## Real runs behind this page

| Run | Find id | What it returned |
|---|---|---|
| "HVAC companies in Columbus, Ohio, with their phone number and website", 25 results | `fnd_qjm2jjsn8k09z1hckb2gdhpav2` | 25 companies, 21 with a phone number |
| This workflow end to end in n8n 2.43.5 ("Plumbers in Dayton, Ohio", 5 results, Google Sheets swapped for a no-op) | `fnd_ptg5cbswwgzp75rzz2hf5s4wd4`, `fnd_7x3jjn0wt5tr7e0ra9e2fjaad7` | 5 plumbers each, written as 5 flat rows with Business, Where, Reviews, Phone, Website, Source |

Rows left out of the samples below: Trane and Airtron (national brands), a directory page (ThreeBestRated) and one row with no name, all from the HVAC run. They are engine issues, logged for the engine session, not template issues.

---

## Template page

Type a trade and a city into a form, such as *HVAC companies in Columbus, Ohio*. Get every match in a Google Sheet with its name, phone and website. Source URL and read time on every value. No Google Cloud project, no scraper to babysit, no list of search queries to feed it.

A Maps search shows about 120 places and ranks them its own way, so the newer shop with seven reviews sits at the bottom or doesn't show at all. Those are often the clients worth calling first. This workflow asks SpecStream, which keeps searching until it has the number you asked for, up to 10,000.

## Who it's for

- Agencies selling websites, SEO or ads to local businesses
- Field sales and lead-gen teams working one city at a time
- Anyone who has copied businesses out of Google Maps by hand

## What you get

Ten of the 25 rows from "HVAC companies in Columbus, Ohio, with their phone number and website" (`fnd_qjm2jjsn8k09z1hckb2gdhpav2`):

| Company | Phone | Website |
|---|---|---|
| Columbus Worthington Air | 614-405-7819 | cwaohio.com |
| Hetter Heating & Cooling | 614-784-9200 | hetterheating.com |
| Buckeye Heating, Cooling, Plumbing & Electrical | 614-647-5306 | buckeyeheat.com |
| Ohio Heating | 614-863-6666 | ohheating.com |
| Custom Air | 614-552-4822 | customairco.com |
| Arrow Heating And Cooling | 614-229-4328 | arrowhvac.com |
| Five Star Heating & Cooling Group | 614-490-7550 | fivestarheatingandcoolinggroup.com |
| Mid Ohio Air Conditioning | 614-291-4664 | midohioac.com |
| Sears Heating and Cooling | 614-475-1800 | searsheatingcooling.com |
| Ketchum & Walton Co. | 614-486-5961 | ketchumandwalton.com |

Add a condition in the form, such as a minimum rating, and the list narrows to the businesses that meet it.

Every row in the sheet also has **Source** (the source URL), **Read at** (when) and **List** (the full list in SpecStream).

## How it works

1. **Describe the list:** an n8n form asks for the business type, the city, an optional condition, how many, and your maximum price.
2. **Read the request** and **Get the price:** SpecStream reads the sentence and quotes the most it can cost. Both steps are free.
3. **Within your maximum?:** if the quote is above your maximum, the workflow stops and tells you the price. Nothing is spent.
4. **Approve and start:** the only step that spends. It carries one fixed key per execution, so a retry never buys the list twice.
5. **Wait and check progress:** every 30 seconds until the run ends. Most lists take 2 to 10 minutes.
6. **Get every row** and **Add rows to your sheet:** all pages of results, one row per business.

## What you need

- A SpecStream API key. New accounts get $10 of credit, no card: [specstream.ai](https://specstream.ai)
- Google Sheets connected in n8n
- Nothing to install: the workflow uses only core nodes, so it runs on n8n Cloud and self-hosted n8n.

## Set up

1. Sign in at specstream.ai. Open **Agents & API** and create a key.
2. In n8n, create a **Bearer Auth** credential. Paste the key as the token.
3. Select that credential in the five HTTP Request nodes: **Read the request**, **Get the price**, **Approve and start**, **Check progress** and **Get every row**.
4. Create an empty Google Sheet. Select it in **Add rows to your sheet**. The first run writes the column headers.
5. Activate the workflow, open the form URL from **Describe the list**, and submit your first list.

## Customize it

- **More facts per business:** change the sentence in **Write the request**, for example "with their phone number, website, email and the owner's name".
- **A CRM instead of a sheet:** replace **Add rows to your sheet** with HubSpot, Pipedrive or Airtable.
- **Many cities at once:** replace the form with a Google Sheets trigger that reads one trade and city per row.
- **Keep the list up to date:** open the list from the **List** link and turn on a schedule. New businesses come to you; you pay only for the new ones.

## What it costs

5¢ a business for a plain list with phone and website, 15¢ when every business has to meet a condition such as a rating. The quote shows the exact maximum before anything runs: $2.50 for the 25 HVAC companies above. You pay for the rows delivered, and a run that finds nothing is free.

## Screenshots (if the Creator Portal asks)

n8n renders the canvas from the JSON. If an image is requested:

1. The canvas, zoomed to fit, with the five sticky notes visible.
2. The form from **Describe the list**, filled in with "HVAC companies", "Columbus, Ohio", no condition, 25, 10.
3. The Google Sheet after a run (use the HVAC rows above; crop out the List link).
