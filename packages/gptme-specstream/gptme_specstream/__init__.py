"""SpecStream for gptme: a plugin with the `specstream` tool (Search API and Extract API).

Installed with pip, gptme finds it through the `gptme.plugins` entry point. A clone of this folder on a
gptme `plugins.paths` entry also loads, as a folder plugin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gptme.plugins.plugin import GptmePlugin

from .client import DEFAULT_BASE_URL, SpecStreamError, __version__, configure

if TYPE_CHECKING:
    from gptme.config import Config

PLUGIN_NAME = "specstream"


def _plugin_settings(config: Any) -> dict[str, Any]:
    """[plugin.specstream] from the user config, overridden by the project config."""
    merged: dict[str, Any] = {}
    for layer in (getattr(config, "user", None), getattr(config, "project", None)):
        table = getattr(layer, "plugin", None) if layer is not None else None
        if isinstance(table, dict) and isinstance(table.get(PLUGIN_NAME), dict):
            merged.update(table[PLUGIN_NAME])
    return merged


def init(config: Config) -> None:
    """Read the key with gptme's own lookup (environment, then [env] in the config files) and the address."""
    settings = _plugin_settings(config)
    base_url = settings.get("base_url") or config.get_env("SPECSTREAM_BASE_URL")
    configure(api_key=config.get_env("SPECSTREAM_API_KEY"), base_url=str(base_url) if base_url else None)


plugin = GptmePlugin(name=PLUGIN_NAME, tool_modules=["gptme_specstream.tools.specstream"], init=init)

__all__ = ["DEFAULT_BASE_URL", "SpecStreamError", "__version__", "configure", "init", "plugin"]
