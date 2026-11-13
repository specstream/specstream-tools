"""The Temporal Plugin that puts the SpecStream Activities on a Worker."""

from __future__ import annotations

import dataclasses

import httpx
from temporalio.plugin import SimplePlugin
from temporalio.worker import WorkflowRunner
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner

from ._api import DEFAULT_BASE_URL, SpecStreamClient
from .activities import SpecStreamActivities

PLUGIN_NAME = "specstream.SpecStreamPlugin"
# Workflow code imports the inputs from this package; the sandbox takes these modules as they
# are instead of loading them again for every Workflow run.
PASSTHROUGH = ("temporal_specstream", "httpx")


def _runner(runner: WorkflowRunner | None) -> WorkflowRunner:
    if runner is None:
        raise ValueError("No WorkflowRunner provided to the SpecStream plugin.")
    if isinstance(runner, SandboxedWorkflowRunner):
        return dataclasses.replace(runner, restrictions=runner.restrictions.with_passthrough_modules(*PASSTHROUGH))
    return runner


class SpecStreamPlugin(SimplePlugin):
    """Registers ``specstream.web_search`` and ``specstream.extract`` on a Worker.

    Give it to the Client (``Client.connect(..., plugins=[SpecStreamPlugin()])``): a Worker
    made from that Client gets the Activities. The key is read from ``api_key`` or, on each
    call, from ``SPECSTREAM_API_KEY``. It stays on the Worker and never enters Workflow history.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        client = SpecStreamClient(api_key, base_url=base_url, timeout=timeout, transport=transport)
        self.specstream = SpecStreamActivities(client)
        super().__init__(
            PLUGIN_NAME,
            activities=[self.specstream.web_search, self.specstream.extract],
            workflow_runner=_runner,
        )
