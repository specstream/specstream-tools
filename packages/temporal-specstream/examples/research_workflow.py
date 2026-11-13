"""Search the live web, then read the first pages, as one durable Workflow.

    pip install temporal-specstream
    temporal server start-dev
    SPECSTREAM_API_KEY=... python research_workflow.py "who maintains the Temporal Python SDK"
"""

from __future__ import annotations

import asyncio
import sys
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
        urls = [item["url"] for item in found.get("sources", [])[:3] if item.get("url")]
        if not urls:
            return {"search": found, "pages": {}}
        pages = await workflow.execute_activity(
            SpecStreamActivities.extract,
            ExtractInput(urls=urls),
            start_to_close_timeout=timedelta(seconds=120),
        )
        return {"search": found, "pages": pages}


async def main(question: str) -> None:
    client = await Client.connect("localhost:7233", plugins=[SpecStreamPlugin()])
    async with Worker(client, task_queue="specstream-research", workflows=[ResearchWorkflow]):
        result = await client.execute_workflow(
            ResearchWorkflow.run, question, id="specstream-research", task_queue="specstream-research"
        )
    print(result["search"].get("answer"))
    for item in result["search"].get("sources", []):
        print(item.get("url"))


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or "Temporal Python SDK plugins"))
