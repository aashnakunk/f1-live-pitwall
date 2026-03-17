"""Tests for the MCP protocol layer — verifies the server speaks valid MCP.

These tests simulate what Claude Desktop does: connect via stdio,
send JSON-RPC messages, and verify responses. No Anthropic API key needed.
"""

import json
import select
import subprocess
import sys
import time
from pathlib import Path

import pytest

PYTHON = str(Path(sys.executable))


class MCPProcess:
    """Helper to manage an MCP server subprocess."""

    def __init__(self):
        self.proc = subprocess.Popen(
            [PYTHON, "-m", "f1_mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd="/tmp",  # avoid f1_mcp/ directory shadowing
        )

    def send(self, msg: dict):
        self.proc.stdin.write((json.dumps(msg) + "\n").encode())
        self.proc.stdin.flush()

    def read(self, timeout: float = 3.0) -> str:
        time.sleep(0.5)
        output = b""
        while select.select([self.proc.stdout], [], [], timeout)[0]:
            chunk = self.proc.stdout.read1(4096)
            if not chunk:
                break
            output += chunk
            timeout = 0.3  # short timeout for subsequent reads
        return output.decode()

    def send_and_read(self, msg: dict, timeout: float = 3.0) -> dict:
        self.send(msg)
        raw = self.read(timeout)
        if not raw:
            return {}
        # Handle potential multiple JSON objects in response
        for line in raw.strip().split("\n"):
            line = line.strip()
            if line:
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return {}

    def initialize(self):
        resp = self.send_and_read({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1.0"},
            },
        })
        # Send initialized notification
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        time.sleep(0.3)
        return resp

    def kill(self):
        self.proc.kill()
        self.proc.wait()


@pytest.fixture(scope="module")
def mcp():
    """Start an MCP server process for the test module."""
    server = MCPProcess()
    server.initialize()
    yield server
    server.kill()


# ── Protocol Tests ───────────────────────────────────────────────────────────


class TestMCPHandshake:
    """Test the MCP initialization handshake."""

    def test_initialize_response(self):
        server = MCPProcess()
        resp = server.initialize()
        server.kill()

        assert resp.get("jsonrpc") == "2.0"
        assert resp.get("id") == 1
        result = resp.get("result", {})
        assert result["protocolVersion"] == "2024-11-05"
        assert result["serverInfo"]["name"] == "f1"
        assert "tools" in result["capabilities"]

    def test_server_instructions(self):
        server = MCPProcess()
        resp = server.initialize()
        server.kill()

        instructions = resp["result"].get("instructions", "")
        assert "Formula 1" in instructions
        assert "load_session" in instructions


class TestToolListing:
    """Test that tools/list returns all expected tools."""

    def test_lists_all_tools(self, mcp):
        resp = mcp.send_and_read({
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/list",
            "params": {},
        })

        tools = resp.get("result", {}).get("tools", [])
        tool_names = [t["name"] for t in tools]

        expected = [
            "season_calendar", "load_session", "session_status",
            "list_drivers", "identify_driver",
            "race_result", "qualifying_result",
            "lap_times", "fastest_laps",
            "pit_stops", "tire_stints",
            "driver_telemetry", "head_to_head",
            "weather", "session_summary",
            "track_evolution", "overtake_analysis",
        ]

        for name in expected:
            assert name in tool_names, f"Missing tool: {name}"

    def test_tools_have_descriptions(self, mcp):
        resp = mcp.send_and_read({
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/list",
            "params": {},
        })

        tools = resp.get("result", {}).get("tools", [])
        for tool in tools:
            assert "description" in tool, f"Tool {tool['name']} missing description"
            assert len(tool["description"]) > 20, f"Tool {tool['name']} description too short"
            assert "inputSchema" in tool, f"Tool {tool['name']} missing inputSchema"

    def test_driver_tools_accept_string_input(self, mcp):
        resp = mcp.send_and_read({
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/list",
            "params": {},
        })

        tools = resp.get("result", {}).get("tools", [])
        driver_tools = ["lap_times", "driver_telemetry", "identify_driver"]

        for tool in tools:
            if tool["name"] in driver_tools:
                props = tool["inputSchema"].get("properties", {})
                driver_param = props.get("driver") or props.get("name")
                assert driver_param is not None, f"Tool {tool['name']} missing driver param"
                assert driver_param["type"] == "string", f"Tool {tool['name']} driver param should be string"


class TestToolExecution:
    """Test calling tools via MCP protocol."""

    def test_session_status_no_session(self, mcp):
        resp = mcp.send_and_read({
            "jsonrpc": "2.0",
            "id": 20,
            "method": "tools/call",
            "params": {"name": "session_status", "arguments": {}},
        })

        content = resp.get("result", {}).get("content", [{}])[0]
        assert content.get("type") == "text"
        data = json.loads(content["text"])
        assert data["loaded"] is False

    def test_tool_not_found(self, mcp):
        resp = mcp.send_and_read({
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {"name": "nonexistent_tool_xyz", "arguments": {}},
        })

        # Should return an error
        assert "error" in resp or resp.get("result", {}).get("isError")

    def test_tool_without_session_returns_error(self, mcp):
        resp = mcp.send_and_read({
            "jsonrpc": "2.0",
            "id": 22,
            "method": "tools/call",
            "params": {"name": "race_result", "arguments": {}},
        })

        content = resp.get("result", {}).get("content", [{}])[0]
        text = content.get("text", "")
        # Should mention loading a session
        assert "session" in text.lower() or "load" in text.lower() or resp.get("result", {}).get("isError")


@pytest.mark.integration
class TestToolExecutionWithSession:
    """Test tool calls with a real loaded session."""

    @pytest.fixture(scope="class")
    def loaded_mcp(self):
        server = MCPProcess()
        server.initialize()

        # Load a session
        resp = server.send_and_read({
            "jsonrpc": "2.0",
            "id": 100,
            "method": "tools/call",
            "params": {
                "name": "load_session",
                "arguments": {"year": 2024, "race": "Bahrain", "session": "race"},
            },
        }, timeout=60)

        content = resp.get("result", {}).get("content", [{}])[0]
        data = json.loads(content.get("text", "{}"))
        assert data.get("status") in ("loaded", "already_loaded"), f"Failed to load: {data}"

        yield server
        server.kill()

    def test_race_result(self, loaded_mcp):
        resp = loaded_mcp.send_and_read({
            "jsonrpc": "2.0",
            "id": 101,
            "method": "tools/call",
            "params": {"name": "race_result", "arguments": {}},
        })

        content = resp["result"]["content"][0]
        data = json.loads(content["text"])
        assert isinstance(data, list)
        assert len(data) == 20
        assert data[0]["position"] == 1

    def test_fuzzy_driver_via_protocol(self, loaded_mcp):
        resp = loaded_mcp.send_and_read({
            "jsonrpc": "2.0",
            "id": 102,
            "method": "tools/call",
            "params": {"name": "lap_times", "arguments": {"driver": "charles"}},
        })

        content = resp["result"]["content"][0]
        data = json.loads(content["text"])
        assert data["driver"] == "LEC"
        assert len(data["laps"]) > 0

    def test_head_to_head_fuzzy(self, loaded_mcp):
        resp = loaded_mcp.send_and_read({
            "jsonrpc": "2.0",
            "id": 103,
            "method": "tools/call",
            "params": {
                "name": "head_to_head",
                "arguments": {"driver_a": "max", "driver_b": "checo"},
            },
        })

        content = resp["result"]["content"][0]
        data = json.loads(content["text"])
        assert data["driver_a"]["driver"] == "VER"
        assert data["driver_b"]["driver"] == "PER"

    def test_session_summary(self, loaded_mcp):
        resp = loaded_mcp.send_and_read({
            "jsonrpc": "2.0",
            "id": 104,
            "method": "tools/call",
            "params": {"name": "session_summary", "arguments": {}},
        })

        content = resp["result"]["content"][0]
        data = json.loads(content["text"])
        assert data["year"] == 2024
        assert "Bahrain" in data["event"]
        assert data["winner"]["driver"] is not None
