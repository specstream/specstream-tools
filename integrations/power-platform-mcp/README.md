# SpecStream

This connector gives AI agents live web research through the Model Context Protocol (MCP). An agent in Microsoft Copilot Studio can search the web, read pages, order a written report with the page behind each cited sentence, and build a complete list from the live web in structured rows.

## Publisher: SpecStream SAS

SpecStream SAS, Narbonne, France. Support: support@specstream.ai. Documentation: https://specstream.ai/docs/integrations

## Prerequisites

- A SpecStream account. It is free to create at https://specstream.ai, and new accounts start with $10 of credit, no card.
- A SpecStream API key.

## Supported Operations

### Invoke SpecStream MCP server

Invokes the SpecStream MCP endpoint (`https://api.specstream.ai/mcp`, Streamable HTTP). The agent reads the tool list from the server, so it always has the current tools. The main ones:

- `search_web`: answers one question from the live web, with the pages behind the answer.
- `read_pages`: returns the text of the pages at the URLs you give.
- `research_price`: returns the price of a written report before it is approved.
- `start_research`: starts a written report that answers a question from the live web, with the page behind each cited sentence, on the price the user approved.
- `get_research`: reads a report's status and, when it is completed, the report.
- `compile`: reads a request for a list or table in everyday words and returns how it was understood.
- `quote_new_list`: prices the list before anything runs.
- `run_new_list`: starts the list from a quote the user approved.
- `get_find`: shows how a run is going and what it has cost so far.
- `list_find_rows`: returns the rows of a run, each value with its source.
- `get_capacity_balance`: reads the account balance.

## Obtaining Credentials

1. Sign in at https://specstream.ai, or create an account.
2. Open **Agents & API** and create an API key. It starts with `ss_live_`.
3. Paste the key when you create the connection. The connector sends it as a Bearer token.

A key carries its own spending ceiling, set in SpecStream. The connector cannot raise it.

## Getting Started

1. In Copilot Studio, open your agent, select **Tools**, then **Add a tool**, and search for SpecStream.
2. Create the connection with your SpecStream API key.
3. Ask the agent a question that needs the live web, for example "Which EU member states changed their public procurement thresholds this year? Give the source for each."

## Pricing

- Web search: $5 per 1,000 searches of up to 10 results, and $1 per 1,000 on the fast tier.
- Page reading: $0.80 per 1,000 pages. A page with no text is not charged.
- Research report: $0.10 quick, $0.30 standard, $1.00 deep.
- Lists: each delivered row is 5¢, 15¢ or $1, plus 5¢ for a person's email and 15¢ for a phone. A run that finds nothing costs nothing.

A report or a list starts only from a price the user approved, and never costs more than that maximum. Current prices are at https://specstream.ai/pricing.

## Regions

The connector is available in all Copilot Studio, Power Automate, Power Apps and Logic Apps regions except the following:

| Service | Not available in |
| --- | --- |
| Copilot Studio | US Government (GCC), US Government (GCC High), China Cloud operated by 21Vianet, US Department of Defense (DoD) |
| Power Automate | US Government (GCC), US Government (GCC High), China Cloud operated by 21Vianet, US Department of Defense (DoD) |
| Power Apps | US Government (GCC), US Government (GCC High), China Cloud operated by 21Vianet, US Department of Defense (DoD) |
| Logic Apps | Azure Government regions, Azure China regions, US Department of Defense (DoD) |

SpecStream is hosted in the commercial cloud. Do not send data that must stay inside a government cloud.

## Known Issues and Limitations

- This is an MCP connector for AI agents in Microsoft Copilot Studio. It has one operation, the MCP endpoint, and no triggers. For a flow with separate actions, call the SpecStream API from the flow.
- A research report and a list take minutes. The agent reads the status with `get_research` or `get_find` until the work is completed.
- Nothing paid starts without a price the user approved. A balance is not permission to spend.

## Support

Documentation: https://specstream.ai/docs/integrations
Email: support@specstream.ai
