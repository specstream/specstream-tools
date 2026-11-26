---
name: get-started
description: Shows a new user how to search the live web, read pages, ask for data, watch the results fill in, open their own files and mention a saved list in chat. Use when someone sets up SpecStream, connects it for the first time or asks what it can do.
---

# Get a new user going

Use the SpecStream MCP server at `https://api.specstream.ai/mcp`. Start here when someone chooses Set up, connects SpecStream for the first time, or asks what it can do.

1. **Ask a question or read a page.** `search_web` answers a question from the live web in a few seconds, with the pages behind the answer, and `read_pages` returns the main text of up to 20 pages or documents. Each call takes a small amount from the balance, with no quote. The `search-and-read` skill has the details.
2. **Ask for a list in plain words.** Offer two or three requests they could say as they are, such as companies, places, tenders, datasets or repositories, with the places and conditions they care about. `list_request_templates` has ready-made ones once they're connected. Then follow the compile skill: show how SpecStream read the request, change what is wrong, and get a price before anything runs. Reading a request works before they connect an account. Getting a price or running a list asks them to connect SpecStream first.
3. **Watch it fill in.** Once they approve a run, tell them the Lists app shows it (`open_specstream`): results arrive as they are found, and each opens to the conditions it meets and the quote, with the source URL and read time on every value. `open_specstream_panel` keeps a list beside the conversation; `show_specstream_records` shows a few rows in the conversation. Possible matches are shown apart and are never counted as results. Keep them on the Lists app until the run finishes. A run can take a few minutes, and the rows it shows there are the result.
4. **Open a file they already have.** A .csv, .tsv, .xlsx, .geojson or .kml file opens in the same table and map. The file itself is never changed. If columns are empty, offer to fill in what is missing, and treat their yes as the request to compile. They can also keep the file as a saved list with Import as a saved list.
5. **Bring a list back.** Typing @ in the message box finds their recent lists and records, so "@SpecStream" and the list's name puts that list in front of you. Read it before answering. Without mentions, find it with `list_collections` or `search_workspace`.
6. **Take it with them.** Download as CSV, Excel, JSON or HTML from the Lists app or with `export_find`, or share a fixed copy with `share_find`. Keeping a list up to date, maps, and sending it to Google Sheets, Excel, Notion, Airtable, HubSpot or Salesforce are in the SpecStream workspace at https://specstream.ai/workspace, on the same account.

Opening a list, reading a quote or importing a file never counts as a yes. Never start work for them without a yes to a price, never ask for credentials, and never open a payment page in chat.
