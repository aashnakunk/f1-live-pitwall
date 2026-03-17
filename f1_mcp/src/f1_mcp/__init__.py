"""F1 MCP — Formula 1 race intelligence via Model Context Protocol.

A local-first MCP server that gives Claude (or any MCP client) access to
Formula 1 data through FastF1. Install it, point Claude Desktop at it, done.

Quick start (Claude Desktop config):
    {
        "mcpServers": {
            "f1": {
                "command": "python",
                "args": ["-m", "f1_mcp"]
            }
        }
    }

Programmatic usage:
    from f1_mcp.session import SessionManager
    from f1_mcp.normalize import resolve_driver, resolve_race

    mgr = SessionManager()
    mgr.load(2024, "Bahrain", "R")
    print(mgr.race_result())
"""

__version__ = "0.1.0"

from f1_mcp.normalize import resolve_driver, resolve_race, resolve_session_type
from f1_mcp.session import SessionManager
