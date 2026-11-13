"""Run the SpecStream tools as an MCP server: `arcade-specstream` (stdio) or `arcade-specstream http 127.0.0.1 8000`."""

import sys
from typing import cast

from arcade_mcp_server import MCPApp
from arcade_mcp_server.mcp_app import TransportType

import arcade_specstream

app = MCPApp(
    name="SpecStream",
    instructions=(
        "Use this server for data from the live web. For a complete list of things that meet conditions, with the "
        "same facts on each row, call FindList. For one fact or a quick answer, call WebSearch. For the text of "
        "known pages, call ExtractPages."
    ),
)

app.add_tools_from_module(arcade_specstream)


def main() -> None:
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 8000
    app.run(transport=cast(TransportType, transport), host=host, port=port)


if __name__ == "__main__":
    main()
