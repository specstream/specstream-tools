# crewai-specstream

Most web tools for CrewAI hand your agent pages to read, and the agent builds the list itself, one search and one scrape at a time. This one hands it the finished list. The agent asks in plain words – "dental clinics in Lisbon with online booking", "US startups that filed a $5M+ Form D after October 8, 2026" – and gets back every matching row, each with the page it was read from. The list starts only within a price you set in code, and the model can't raise it.

```bash
pip install -U crewai-specstream
export SPECSTREAM_API_KEY=ss_live_...   # Agents & API in your SpecStream workspace
```

A free account comes with $10 of credit to use within 30 days and needs no card: [specstream.ai](https://specstream.ai/signup). Works with CrewAI 1.x on Python 3.10 – 3.13.

## A crew that can find lists

```python
from crewai import Agent, Crew, Task
from crewai_specstream import specstream_tools

analyst = Agent(
    role="Funding analyst",
    goal="Answer questions about who is raising money, with a source for every claim",
    backstory="You work from lists, not from memory. You cite the page each row came from.",
    tools=specstream_tools(max_price_usd=5),
)

task = Task(
    description=(
        "Find US startups that raised $5M or more in a Form D filed after October 8, 2026. "
        "Which industries lead? Link the filing for each company you name."
    ),
    expected_output="The three leading industries, with the companies and their filing links.",
    agent=analyst,
)

print(Crew(agents=[analyst], tasks=[task]).kickoff().raw)
```

The agent writes the request and picks how many rows. You decide what one list may cost. The agent uses your default model; pass `llm="..."` to `Agent` to choose another.

## What comes back

One flat row per match: the list's own columns, then where the row was read. This is a real row from the request above.

```json
{
  "list_id": "fnd_gk5y3d0r97bvyz0t08zzh75kr6",
  "position": 26,
  "Organization": "RapidCanvas Inc",
  "Published address": "801 BARTON SPRINGS RD, AUSTIN, TEXAS, 78704",
  "Source industry classification": "Other Technology",
  "Amount sold (USD)": "28999988",
  "Funding filing date": "2026-10-14",
  "source_url": "https://www.sec.gov/Archives/edgar/data/2052031/000205203126000006/primary_doc.xml",
  "checked_at": "2026-10-14T19:56:02.016693Z",
  "list_link": "https://specstream.ai/workspace/collections/fnd_gk5y3d0r97bvyz0t08zzh75kr6"
}
```

Columns follow the request. Ask for "breweries in Portland, Oregon that host events, with their website" and the rows carry the brewery and its website instead. A fact a source doesn't publish comes back empty, never guessed.

## The two tools

| Tool | The model gives | What happens | Cost |
| --- | --- | --- | --- |
| `specstream_find_list` | `request`, `max_results` (1 – 1000, default 25) | Reads the request, prices it, starts it only within `max_price_usd`, waits up to `wait_seconds` (7 minutes by default) and returns every row | Only the rows that match |
| `specstream_get_list_results` | `list_id` | Every row found so far, for a list that was still running | Free |

When the price is above your maximum, nothing runs: the tool returns the price, so the agent can ask for fewer rows or tell the user. When a request is too vague to price ("clinics"), it returns how SpecStream read it, so the agent can add the place or the conditions.

Use the classes directly when you want different settings per tool:

```python
from crewai_specstream import SpecStreamFindListTool, SpecStreamGetListResultsTool

find = SpecStreamFindListTool(max_price_usd=20, wait_seconds=600)
results = SpecStreamGetListResultsTool()
```

Both read `SPECSTREAM_API_KEY`; pass `api_key="..."` to use another. The key is stored as a secret, so it stays out of reprs and dumps, and it is sent only in the `Authorization` header.

## In a crew project

Give the tools to an agent in your `@CrewBase` class the way you would any other:

```python
from crewai import Agent
from crewai.project import CrewBase, agent
from crewai_specstream import specstream_tools

@CrewBase
class LeadCrew:
    @agent
    def researcher(self) -> Agent:
        return Agent(config=self.agents_config["researcher"], tools=specstream_tools(max_price_usd=5))
```

The tools also implement CrewAI's async hook (`_arun`) and run their requests in a worker thread, so an async crew's event loop isn't blocked while a list runs.

## Money, plainly

- `max_price_usd` lives on the tool, in your code. The model never sees it and can't change it.
- You pay for rows that match. Candidates SpecStream couldn't confirm are left out and aren't billed.
- A retried step asking for the same list within the hour gets the list it already started, not a second bill. That covers CrewAI retrying a failed tool call.
- CrewAI caches tool calls by their arguments. These tools cache a list only once it has finished, so a list that was still running is read again instead of replayed.
- Rates and plans: [specstream.ai/pricing](https://specstream.ai/pricing).

## When to reach for it

When the answer is many things that meet conditions: companies in a city, clinics with a service, funding filings, open grants, tenders, repositories, people in a role. For a single fact or a summary of one page, a search tool fits better.

## More

- [SpecStream docs](https://specstream.ai/docs) and the [CrewAI page](https://specstream.ai/docs/crewai)
- Agents outside CrewAI: the [MCP server](https://specstream.ai/docs/mcp) at `https://api.specstream.ai/mcp`
- The [Python SDK](https://pypi.org/project/specstream-client/) for everything else in the API
- Questions: support@specstream.ai

MIT licensed. Made by [SpecStream](https://specstream.ai), the live web data engine for teams and agents.
