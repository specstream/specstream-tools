"""A Griptape agent that searches and reads the live web with SpecStream.

Needs SPECSTREAM_API_KEY and a prompt driver's key (Griptape's default reads OPENAI_API_KEY).
"""

from griptape.loaders import WebLoader
from griptape.structures import Agent
from griptape.tools import WebScraperTool, WebSearchTool

from griptape.specstream import SpecStreamWebScraperDriver, SpecStreamWebSearchDriver

agent = Agent(
    tools=[
        WebSearchTool(web_search_driver=SpecStreamWebSearchDriver(results_count=5)),
        WebScraperTool(web_loader=WebLoader(web_scraper_driver=SpecStreamWebScraperDriver())),
    ]
)

if __name__ == "__main__":
    agent.run("Who won the 2025 Nobel Prize in Physics? Read the announcement page and quote one line.")
