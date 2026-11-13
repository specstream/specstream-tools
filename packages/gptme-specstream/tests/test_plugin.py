"""The gptme plugin. Every call goes to an httpx.MockTransport: nothing reaches the live API."""

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from gptme.plugins import discover_plugins
from gptme.plugins.entrypoints import _coerce_to_plugin
from gptme.plugins.plugin import GptmePlugin
from gptme.plugins.registry import clear_registry, discover_all_plugins
from gptme.tools import _discover_tools, get_available_tools
from gptme.tools.base import ToolSpec

import gptme_specstream
from gptme_specstream import SpecStreamError, client, plugin
from gptme_specstream.tools.specstream import read_pages, search_web, tool

SEARCH = {"data": {"kind": "fact", "answer": {"value": "42", "page": "https://a.example"}, "rows": [], "sources": []}}
EXTRACT = {"data": {"results": [{"url": "https://a.example", "status": "ok", "text": "page"}], "price_usd": 0.0008}}
PACKAGE_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def seen(monkeypatch):
    monkeypatch.delenv("SPECSTREAM_API_KEY", raising=False)
    monkeypatch.delenv("SPECSTREAM_BASE_URL", raising=False)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=EXTRACT if request.url.path == "/v1/extract" else SEARCH)

    client.reset()
    client.configure(api_key="ss_test", client=httpx.Client(transport=httpx.MockTransport(handler)))
    yield requests
    client.reset()


def use(handler) -> None:
    client.configure(client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_search_sends_the_question_with_the_key(seen):
    result = json.loads(search_web("  a question  ", passages=True))
    assert result["answer"]["value"] == "42"
    request = seen[0]
    assert request.method == "GET" and str(request.url).startswith("https://api.specstream.ai/v1/web-search")
    assert request.headers["authorization"] == "Bearer ss_test"
    assert request.headers["user-agent"].startswith("gptme-specstream/")
    assert request.url.params["q"] == "a question" and request.url.params["passages"] == "true"


def test_read_pages_posts_at_most_twenty_urls_and_takes_one_url(seen):
    urls = [f"https://a.example/{i}" for i in range(25)]
    result = json.loads(read_pages(urls, format="text"))
    assert result["results"][0]["status"] == "ok"
    body = json.loads(seen[0].content)
    assert seen[0].method == "POST" and seen[0].url.path == "/v1/extract"
    assert body == {"urls": urls[:20], "format": "text"}
    read_pages("https://b.example")
    assert json.loads(seen[1].content) == {"urls": ["https://b.example"], "format": "markdown"}


def test_errors_carry_the_api_message_or_the_status(seen):
    use(lambda r: httpx.Response(402, json={"error": {"message": "Balance is empty."}}))
    with pytest.raises(SpecStreamError, match="Balance is empty."):
        search_web("x")
    use(lambda r: httpx.Response(503, text="busy"))
    with pytest.raises(SpecStreamError, match="HTTP 503") as caught:
        read_pages(["https://a.example"])
    assert caught.value.status_code == 503
    with pytest.raises(SpecStreamError, match="1 to 20"):
        read_pages([" "])
    with pytest.raises(SpecStreamError, match="1 to 2,000"):
        search_web("  ")
    client.reset()
    with pytest.raises(SpecStreamError, match="SPECSTREAM_API_KEY"):
        search_web("x")


def test_entry_point_object_is_a_plugin_that_loads_the_tool():
    assert isinstance(plugin, GptmePlugin) and plugin.name == "specstream"
    assert _coerce_to_plugin("specstream", plugin) is plugin
    tools = _discover_tools(plugin.tool_modules)
    assert [t.name for t in tools] == ["specstream"]
    assert {f.name for f in tools[0].functions} == {"search_web", "read_pages"}


def test_installed_package_reaches_gptme_available_tools():
    # The path gptme takes at startup: discover every plugin, then list the tools.
    clear_registry()
    try:
        found = {p.name: p for p in discover_all_plugins()}
        assert found["specstream"] is plugin
        assert "specstream" in {t.name for t in get_available_tools(include_mcp=False)}
    finally:
        clear_registry()


def test_folder_plugin_discovery_finds_the_tool():
    found = {p.name: p for p in discover_plugins([PACKAGE_DIR])}
    assert "gptme_specstream" in found
    assert "gptme_specstream.tools.specstream" in found["gptme_specstream"].tool_modules


def test_tool_calls_run_without_ipython(seen):
    subtools = {sub.name: sub for sub in tool.as_function_subtoolspecs()}
    assert set(subtools) == {"specstream.search_web", "specstream.read_pages"}
    assert isinstance(subtools["specstream.search_web"], ToolSpec)
    assert {p.name for p in subtools["specstream.search_web"].parameters} == {"query", "passages"}
    assert "search_web" in tool.get_functions_description()


def test_init_reads_the_key_and_address_from_gptme_config(seen, monkeypatch):
    client.reset()
    env = {"SPECSTREAM_API_KEY": "ss_from_config"}
    config = SimpleNamespace(
        user=SimpleNamespace(plugin={"specstream": {"base_url": "https://user.example"}}),
        project=SimpleNamespace(plugin={"specstream": {"base_url": "https://project.example/"}}),
        get_env=lambda key, default=None: env.get(key, default),
    )
    gptme_specstream.init(config)
    requests: list[httpx.Request] = []
    use(lambda r: requests.append(r) or httpx.Response(200, json=SEARCH))
    search_web("x")
    assert requests[0].headers["authorization"] == "Bearer ss_from_config"
    assert str(requests[0].url).startswith("https://project.example/v1/web-search")


def test_init_without_project_config_keeps_the_default_address(seen):
    client.reset()
    config = SimpleNamespace(user=SimpleNamespace(plugin={}), project=None, get_env=lambda key, default=None: None)
    gptme_specstream.init(config)
    assert client._base_url() == client.DEFAULT_BASE_URL
