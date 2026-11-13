#
# Copyright (c) 2026, SpecStream SAS
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Voice agent with research reports from the live web via SpecStream.

Ask it "Research how the EU and the US regulate stablecoin reserves"
(specstream_research_price, then specstream_start_research once you accept the price).
The report runs in the background while the bot keeps talking, and
specstream_web_search answers quick questions in the meantime.

Needs SPECSTREAM_API_KEY, DEEPGRAM_API_KEY, CARTESIA_API_KEY and OPENAI_API_KEY.
Run it with: python research.py
"""

import os
from datetime import date

from dotenv import load_dotenv
from loguru import logger
from pipecat.adapters.llm.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.evals.transport import EvalTransportParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.responses.llm import OpenAIResponsesLLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.workers.runner import WorkerRunner

from pipecat_specstream import SpecStreamDeepSearch, SpecStreamResearch

load_dotenv(override=True)

transport_params = {
    "eval": lambda: EvalTransportParams(audio_in_enabled=True, audio_out_enabled=True),
    "daily": lambda: DailyParams(audio_in_enabled=True, audio_out_enabled=True),
    "twilio": lambda: FastAPIWebsocketParams(audio_in_enabled=True, audio_out_enabled=True),
    "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting bot")

    stt = DeepgramSTTService(api_key=os.environ["DEEPGRAM_API_KEY"])
    tts = CartesiaTTSService(
        api_key=os.environ["CARTESIA_API_KEY"],
        settings=CartesiaTTSService.Settings(voice="86e30c1d-714b-4074-a1f2-1cb6b552fb49"),
    )

    system_prompt = f"""\
You are a helpful assistant in a voice conversation with live web access.
Today's date is {date.today():%A, %B %d, %Y}.

Use specstream_web_search for one fact or anything current. Use specstream_read_pages when the user gives a link.
When the user wants a question researched, call specstream_research_price, say the price in dollars and ask whether to go ahead.
Only after a yes, call specstream_start_research with the accepted price. Say the report has started and keep talking; when it arrives, say its main points in a few sentences.

Your output will be spoken aloud, so avoid emojis, URLs, bullet points or other formatting. Use short sentences.
"""

    llm = OpenAIResponsesLLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        settings=OpenAIResponsesLLMService.Settings(system_instruction=system_prompt),
    )

    # The most one list may cost. The model can't raise it.
    specstream = SpecStreamDeepSearch(api_key=os.environ["SPECSTREAM_API_KEY"], max_price_usd=5)

    # Up to $0.30 a report: quick and standard, never deep. The model can't raise it.
    research = SpecStreamResearch(api_key=os.environ["SPECSTREAM_API_KEY"], max_price_usd=0.30)

    tools = ToolsSchema(standard_tools=specstream.function_schemas() + research.function_schemas())
    context = LLMContext(tools=tools)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"Client connected: {client}")
        context.add_message({"role": "developer", "content": "Please introduce yourself to the user."})
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    try:
        await runner.run()
    finally:
        await specstream.close()
        await research.close()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
