# SpecStream for Open WebUI

Live web data for your model. Ask in plain words and get every match: every roofer in Columbus rated 4.5 or better, every food bank in Texas with its revenue, every company that filed to raise $5M or more this week. SpecStream reads the live web where those things are kept and hands back every match, each value with the page it came from.

You see the price before anything runs, and you pay for each result delivered: 10¢, 30¢ or $1 a row, and 5¢ for a company left out for a detail you marked as needed. New accounts start with $10 of work, no card.

Two ways to connect it. Pick one.

| | Tool (this file) | Native MCP |
|---|---|---|
| Setup | Import `specstream_tool.py`, paste a key | Add the server URL in Admin settings |
| Price check | Dialog in the chat, plus a spending cap you set | Your model asks you before it approves |
| Rows in the chat | Source chips under each answer | Plain tool results |
| What the model sees | 4 small tools | 97 tools, or the few you allow |
| Best for | Teams who want a hard cap and one-click approval | Anyone already running MCP servers |

## Option 1: the tool

1. In SpecStream, open **Agents & API** and create an API key (it starts with `ss_live_`). [Sign up](https://specstream.ai) if you don't have an account.
2. In Open WebUI, go to **Workspace > Tools > +**, paste the contents of [`specstream_tool.py`](specstream_tool.py), and save. Or import it from the openwebui.com post with **Get**.
3. Open the tool's **Valves** (the gear icon), paste the key, and set the spending cap.
4. In a chat, turn the tool on under **+ > Integrations > Tools**. Use a model with **Function Calling: native** (Model settings > Advanced Params).

Then ask:

> Find every roofing company in Columbus, Ohio rated 4.5 or better with fewer than 20 Google reviews, with their phone number. Give me 50.

The model reads your request back to you with the price, and a dialog asks you to approve it. Rows come back with the page each value was read from, shown as sources under the answer.

### What the model can do

| Tool | What it does | Cost |
|---|---|---|
| `quote_list` | Reads the request and returns what it will find and the most it can cost | Free |
| `approve_list` | Starts the list from a quote you approved and returns the rows | Up to the quoted maximum, matches only |
| `get_list_rows` | Reads the rows of a list already started, a page at a time | Free |
| `get_balance` | Shows what's left on the account | Free |

### Valves

Set by the admin:

| Valve | Default | What it does |
|---|---|---|
| `api_key` | empty | SpecStream API key |
| `max_price_usd` | 5.00 | The most one list may cost. A quote above it is refused before anything runs |
| `confirm_with_dialog` | on | Asks the person to approve each price in a dialog. The model can't click it |
| `auto_approve_within_cap` | off | Starts any list at or under the cap without asking |
| `wait_seconds` | 90 | How long to wait for rows after a list starts. The list keeps running after that |
| `max_rows_shown` | 25 | Most rows handed to the model per read |

Set by each user (**UserValves**): their own `api_key`, so lists go on their own balance, and their own `max_price_usd`, which can only lower the admin's cap.

### How the price check works

- `quote_list` spends nothing. It returns the price and a `quote_id`.
- `approve_list` looks the quote up again on SpecStream instead of trusting the model's numbers, checks it against your cap, and asks you in a dialog. A timeout, a closed tab or a "no" starts nothing.
- If the dialog can't run, the model has to ask you in the chat and pass `user_said_yes=true`.
- Each quote starts at most one list. A retry returns the list it already started instead of buying it twice.
- An API key also carries its own spending ceiling, set in SpecStream. The tool can't raise it.

## Option 2: native MCP, no code

Open WebUI 0.6.31 or later connects to remote MCP servers directly. SpecStream's server is `https://api.specstream.ai/mcp` (Streamable HTTP).

1. Set `WEBUI_SECRET_KEY` in your Open WebUI environment. Without it, sign-in tokens can fail to decrypt after a restart.
2. Go to **Settings > Admin > Integrations**, and under **External Tool Servers** click **+ Add Connection**.
3. Set **Type** to **MCP (Streamable HTTP)**. Don't pick OpenAPI.
4. Enter the **Server URL**: `https://api.specstream.ai/mcp`
5. Choose how to sign in:
   - **Bearer** with your `ss_live_...` key in **Key**, or
   - **OAuth 2.1** and click **Register Client**. SpecStream supports dynamic client registration, so each person signs in to their own account on first use.
6. In **Function Name Filter List**, allow only the tools a chat needs. The server has 97, and most models do better with a few:

   ```
   compile,quote_capacity_work,authorize_capacity_work,list_find_rows,get_find,get_capacity_balance
   ```

7. Save, then turn the server on in a chat under **+ > Integrations > Tools**. Only admins can add MCP servers; use **Access Control** to choose who can use it.

The server tells the model to show you the price and wait for your yes before anything runs. Reading, exporting and sharing a list you own costs nothing.

## Pricing

A match costs 10¢, 30¢ or $1 depending on how many facts it carries. No match, no charge. A recheck costs half. The same rates apply on every plan, Free included. See [specstream.ai/pricing](https://specstream.ai/pricing).

## Troubleshooting

- **"SpecStream did not accept this API key."** Paste the key again in Valves. Keys start with `ss_live_`.
- **The model answers without calling the tool.** Turn the tool on for the chat and set the model's Function Calling to native.
- **"Needs a clearer request."** Add the place, the kind of thing, or what every row must meet.
- **A list is still running.** It keeps going. Ask the model to read the list again later with its `list_id`.

## Links

- [SpecStream](https://specstream.ai) · [Agents and API docs](https://specstream.ai/docs/mcp) · [Pricing](https://specstream.ai/pricing)
- [Source and issues](https://github.com/specstream/specstream-tools/tree/main/integrations/open-webui)
- Support: support@specstream.ai

MIT license.
