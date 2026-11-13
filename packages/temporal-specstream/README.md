# temporal-specstream

SpecStream for [Temporal](https://temporal.io): live web search and page reading as durable Activities, in one Plugin.

A Workflow that searches the web or reads a page gets Temporal's guarantees for that call: a timeout, retries with backoff, and a result that is recorded once and replayed, so a Workflow that restarts does not pay for the same search twice.

The Plugin registers two Activities:

1. Search API: `specstream.web_search` calls `GET /v1/web-search`, $5 per 1,000 searches of up to 10 results, or $1 on the fast tier. The most accurate web search API in the world (scores and method: https://specstream.ai/benchmarks).
2. Extract API: `specstream.extract` calls `POST /v1/extract`, up to 20 URLs a call (web pages, PDF, Word, Excel), $0.80 per 1,000 pages. A page with no text is not charged.

Deep Search, structured rows priced per row, is not in this package yet.

## Install

```bash
pip install temporal-specstream
```

It needs Python 3.11 or later and `temporalio` 1.19 or later.
A free account comes with $10 of credit and needs no card: [specstream.ai](https://specstream.ai/signup).
Create a key under Agents & API in the workspace and set it on the Worker as `SPECSTREAM_API_KEY`.

## Use it

Give the Plugin to the Client. A Worker made from that Client has the Activities.

```python
import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import Worker

from temporal_specstream import ExtractInput, SpecStreamActivities, SpecStreamPlugin, WebSearchInput


@workflow.defn
class ResearchWorkflow:
    @workflow.run
    async def run(self, question: str) -> dict:
        found = await workflow.execute_activity(
            SpecStreamActivities.web_search,
            WebSearchInput(q=question),
            start_to_close_timeout=timedelta(seconds=60),
        )
        urls = [source["url"] for source in found.get("sources", [])[:3]]
        pages = await workflow.execute_activity(
            SpecStreamActivities.extract,
            ExtractInput(urls=urls),
            start_to_close_timeout=timedelta(seconds=120),
        )
        return {"answer": found.get("answer"), "pages": pages}


async def main() -> None:
    client = await Client.connect("localhost:7233", plugins=[SpecStreamPlugin()])
    async with Worker(client, task_queue="research", workflows=[ResearchWorkflow]):
        print(await client.execute_workflow(
            ResearchWorkflow.run, "Temporal Python SDK plugins", id="research-1", task_queue="research"
        ))


asyncio.run(main())
```

A Workflow written in another language calls the same Activities by name, `specstream.web_search` and `specstream.extract`, on the task queue of a Python Worker that has the Plugin.

## Activities

| Activity | Input | Returns |
| --- | --- | --- |
| `specstream.web_search` | `WebSearchInput(q, speed="default", passages=False)`. `speed="fast"` answers sooner at the fast price. `passages=True` adds the passages of the top pages. | The Search API's answer: `kind`, `answer`, `rows`, `sources` and, with passages, `passages`. |
| `specstream.extract` | `ExtractInput(urls, format="text")`. 1 to 20 URLs, as `text` or `markdown`. | The Extract API's answer: the main text, title and published date of each page. |

## Failures and retries

- A request that SpecStream refuses (a wrong key, a wrong argument, no credit left) raises an `ApplicationError` of type `SpecStreamError` that is not retried, so the Workflow sees it at once.
- A rate limit (429), a server error (5xx) or a network error raises a retryable `ApplicationError`. The Activity's retry policy decides how many attempts follow.

## The key

`SpecStreamPlugin(api_key=...)` takes the key, or each call reads `SPECSTREAM_API_KEY` from the Worker's environment.
The key stays on the Worker. It is never an Activity input, so it never enters Workflow history.

## Options

`SpecStreamPlugin(api_key=None, base_url="https://api.specstream.ai", timeout=60.0, transport=None)`.
`transport` is an `httpx` transport that replaces the network, for tests.

## License

MIT
