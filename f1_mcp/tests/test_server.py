"""Tests for the MCP server tool registration and execution.

Unit tests verify tool definitions are correct.
Integration tests call tools through the MCP server interface.
"""

import json

import pytest

from f1_mcp.server import mcp, _mgr, _require_session


# ── Unit Tests ───────────────────────────────────────────────────────────────


class TestServerSetup:
    """Verify the MCP server is configured correctly."""

    def test_server_name(self):
        assert mcp.name == "f1"

    def test_server_has_instructions(self):
        assert mcp.instructions is not None
        assert "Formula 1" in mcp.instructions


class TestRequireSession:
    """The _require_session guard."""

    def test_raises_when_no_session(self):
        # Reset manager state
        _mgr._session = None
        _mgr._session_key = None
        with pytest.raises(ValueError, match="No session loaded"):
            _require_session()


class TestToolDefinitions:
    """Verify all expected tools are registered."""

    def test_expected_tools_exist(self):
        """Check that all core tools are registered on the MCP server."""
        # Get tool names from the server
        # FastMCP stores tools internally — we test by trying to call them
        expected = [
            "season_calendar",
            "load_session",
            "session_status",
            "list_drivers",
            "identify_driver",
            "race_result",
            "qualifying_result",
            "lap_times",
            "fastest_laps",
            "pit_stops",
            "tire_stints",
            "driver_telemetry",
            "head_to_head",
            "weather",
            "session_summary",
            "track_evolution",
            "overtake_analysis",
        ]
        # We can verify tools exist by checking the module has them as functions
        import f1_mcp.server as srv
        for tool_name in expected:
            assert hasattr(srv, tool_name), f"Missing tool function: {tool_name}"
            assert callable(getattr(srv, tool_name)), f"Tool is not callable: {tool_name}"


# ── Integration Tests ────────────────────────────────────────────────────────


@pytest.mark.integration
class TestToolExecution:
    """Call tools through the actual server functions (with a loaded session)."""

    @pytest.fixture(scope="class", autouse=True)
    def load_session(self):
        """Load a session for all tests in this class."""
        _mgr.load(2024, "Bahrain", "R")

    def _parse(self, json_str: str):
        """Parse tool output JSON."""
        return json.loads(json_str)

    def test_session_status(self):
        from f1_mcp.server import session_status
        result = self._parse(session_status())
        assert result["loaded"] is True
        assert result["year"] == 2024

    def test_list_drivers(self):
        from f1_mcp.server import list_drivers
        result = self._parse(list_drivers())
        assert len(result) == 20
        codes = [d["code"] for d in result]
        assert "VER" in codes

    def test_race_result(self):
        from f1_mcp.server import race_result
        result = self._parse(race_result())
        assert result[0]["position"] == 1

    def test_lap_times_fuzzy(self):
        from f1_mcp.server import lap_times
        result = self._parse(lap_times("leclerc"))
        assert result["driver"] == "LEC"
        assert len(result["laps"]) > 0

    def test_fastest_laps(self):
        from f1_mcp.server import fastest_laps
        result = self._parse(fastest_laps(5))
        assert len(result) == 5

    def test_pit_stops_all(self):
        from f1_mcp.server import pit_stops
        result = self._parse(pit_stops("all"))
        assert len(result) > 0

    def test_pit_stops_single(self):
        from f1_mcp.server import pit_stops
        result = self._parse(pit_stops("Verstappen"))
        assert len(result) == 1
        assert result[0]["driver"] == "VER"

    def test_tire_stints(self):
        from f1_mcp.server import tire_stints
        result = self._parse(tire_stints("all"))
        assert len(result) > 0

    def test_driver_telemetry(self):
        from f1_mcp.server import driver_telemetry
        result = self._parse(driver_telemetry("max", -1))
        assert result["driver"] == "VER"
        assert result["speed"]["max"] > 200

    def test_head_to_head(self):
        from f1_mcp.server import head_to_head
        result = self._parse(head_to_head("max", "charles"))
        assert result["driver_a"]["driver"] == "VER"
        assert result["driver_b"]["driver"] == "LEC"

    def test_weather(self):
        from f1_mcp.server import weather
        result = self._parse(weather())
        assert result["available"] is True

    def test_session_summary(self):
        from f1_mcp.server import session_summary
        result = self._parse(session_summary())
        assert result["year"] == 2024
        assert result["winner"]["driver"] is not None

    def test_identify_driver(self):
        from f1_mcp.server import identify_driver
        result = self._parse(identify_driver("checo"))
        assert result["code"] == "PER"

    def test_track_evolution(self):
        from f1_mcp.server import track_evolution
        result = self._parse(track_evolution())
        assert result["available"] is True

    def test_overtake_analysis(self):
        from f1_mcp.server import overtake_analysis
        result = self._parse(overtake_analysis())
        assert len(result) > 0
