"""F1 MCP Server — Formula 1 race intelligence tools.

Run standalone:
    python -m f1_mcp

Or connect via Claude Desktop config:
    {
        "mcpServers": {
            "f1": {
                "command": "python",
                "args": ["-m", "f1_mcp"]
            }
        }
    }

Each tool is named for the user's intent (not the data source), with
robust input normalization — "Leclerc", "charles", "LEC" all resolve
to the same driver.
"""

from __future__ import annotations

import json
import logging

from mcp.server.fastmcp import FastMCP

from f1_mcp.session import SessionManager

logger = logging.getLogger("f1_mcp")

# ── Server + shared state ────────────────────────────────────────────────────

mcp = FastMCP(
    "f1",
    instructions=(
        "Formula 1 race intelligence tools powered by FastF1. "
        "Use load_session to load a race/qualifying/practice session, "
        "then query it with the other tools. Driver names are fuzzy-matched: "
        "'Leclerc', 'charles', 'LEC' all work. Race names too: 'Monza', "
        "'Italian GP', 'italy' all resolve correctly."
    ),
)

_mgr = SessionManager()


def _json(data) -> str:
    """Serialize to indented JSON string for LLM readability."""
    return json.dumps(data, indent=2, default=str)


def _require_session() -> None:
    """Raise a clear error if no session is loaded."""
    if not _mgr.is_loaded:
        raise ValueError(
            "No session loaded. Use the load_session tool first — e.g. "
            "load_session(year=2024, race='Bahrain', session='race')"
        )


# ── Session Management ───────────────────────────────────────────────────────


@mcp.tool()
def season_calendar(year: int) -> str:
    """Get the full F1 race calendar for a season.

    Use this when the user asks about the schedule, which races happened,
    or wants to know race names to load a session.

    Args:
        year: Season year (e.g. 2024, 2025, 2026)
    """
    return _json(_mgr.season_calendar(year))


@mcp.tool()
def load_session(year: int, race: str, session: str = "race") -> str:
    """Load an F1 session for analysis. Must be called before other tools.

    Use this when the user mentions a specific race, GP, or session they
    want to analyze. Race and session names are fuzzy-matched:
    - Race: "Bahrain", "Monza", "silverstone", "Monaco GP" all work
    - Session: "race", "qualifying", "quali", "FP1", "sprint" all work

    Args:
        year: Season year (e.g. 2024)
        race: Grand Prix name — fuzzy matched (e.g. "Bahrain", "Monza", "silverstone")
        session: Session type — fuzzy matched (default "race"). Options: race, qualifying, sprint, FP1, FP2, FP3
    """
    result = _mgr.load(year, race, session)
    return _json(result)


@mcp.tool()
def session_status() -> str:
    """Check if a session is currently loaded and get its details.

    Use this when you need to confirm what session is active before
    answering a question.
    """
    return _json(_mgr.status())


# ── Driver Information ───────────────────────────────────────────────────────


@mcp.tool()
def list_drivers() -> str:
    """List all drivers in the current session with codes, names, and teams.

    Use this when the user asks who was in the session, or when you need
    to find a driver's 3-letter code.
    """
    _require_session()
    return _json(_mgr.drivers())


@mcp.tool()
def identify_driver(name: str) -> str:
    """Resolve a driver name, nickname, or number to their full identity.

    Use this when the user refers to a driver ambiguously and you need
    to confirm who they mean. Handles nicknames ("Checo"), first names
    ("Charles"), car numbers ("44"), and partial matches ("lec").

    Args:
        name: Any driver reference — name, nickname, abbreviation, or car number
    """
    _require_session()
    code = _mgr._resolve_driver(name)
    drivers = _mgr.drivers()
    match = next((d for d in drivers if d["code"] == code), None)
    if match:
        return _json(match)
    return _json({"code": code, "resolved_from": name})


# ── Race Results ─────────────────────────────────────────────────────────────


@mcp.tool()
def race_result() -> str:
    """Get the full race classification — who finished where.

    Use this when the user asks about race results, who won, podium
    positions, DNFs, points scored, or finishing order.
    """
    _require_session()
    return _json(_mgr.race_result())


@mcp.tool()
def qualifying_result() -> str:
    """Get qualifying results with Q1/Q2/Q3 times.

    Use this when the user asks about qualifying positions, Q1/Q2/Q3
    times, pole position, or qualifying performance.
    """
    _require_session()
    return _json(_mgr.qualifying_result())


# ── Pace & Lap Times ─────────────────────────────────────────────────────────


@mcp.tool()
def lap_times(driver: str) -> str:
    """Get lap-by-lap timing data for a specific driver.

    Use this when the user asks about a driver's pace, consistency,
    lap time progression, or when they were fast/slow. Includes
    tyre compound and stint info per lap.

    Driver names are fuzzy-matched: "Leclerc", "charles", "LEC" all work.

    Args:
        driver: Driver name, code, or number (e.g. "Leclerc", "LEC", "16")
    """
    _require_session()
    return _json(_mgr.lap_times(driver))


@mcp.tool()
def fastest_laps(top_n: int = 10) -> str:
    """Get the fastest lap set by each driver, ranked.

    Use this when the user asks about fastest laps, who set the quickest
    time, or lap time comparisons across the field.

    Args:
        top_n: Number of drivers to include (default 10)
    """
    _require_session()
    return _json(_mgr.fastest_laps(top_n))


# ── Strategy ─────────────────────────────────────────────────────────────────


@mcp.tool()
def pit_stops(driver: str = "all") -> str:
    """Get pit stop details — when each driver pitted and on which tyre.

    Use this when the user asks about pit strategy, when someone pitted,
    how many stops a driver made, or undercut/overcut timing.

    Args:
        driver: Driver name/code, or "all" for every driver (default: all)
    """
    _require_session()
    return _json(_mgr.pit_stops(None if driver == "all" else driver))


@mcp.tool()
def tire_stints(driver: str = "all") -> str:
    """Get tyre stint breakdown — compound, start/end lap, stint length.

    Use this when the user asks about tyre strategy, which compounds
    were used, how long stints were, or compound choices.

    Args:
        driver: Driver name/code, or "all" for top 10 drivers (default: all)
    """
    _require_session()
    return _json(_mgr.tire_stints(None if driver == "all" else driver))


# ── Telemetry ────────────────────────────────────────────────────────────────


@mcp.tool()
def driver_telemetry(driver: str, lap_number: int = -1) -> str:
    """Get summarized telemetry stats for a driver's lap.

    Returns top speed, average speed, throttle application percentage,
    braking intensity, and other derived metrics. Defaults to the
    driver's fastest lap if no lap number is specified.

    Use this when the user asks about speed, braking, throttle traces,
    or driving style analysis.

    Args:
        driver: Driver name, code, or number (e.g. "Verstappen", "VER", "1")
        lap_number: Specific lap number, or -1 for the driver's fastest lap (default: -1)
    """
    _require_session()
    return _json(_mgr.driver_telemetry(driver, lap_number if lap_number > 0 else None))


# ── Comparisons ──────────────────────────────────────────────────────────────


@mcp.tool()
def head_to_head(driver_a: str, driver_b: str) -> str:
    """Compare two drivers across all key metrics.

    Use this when the user asks to compare drivers, wants a head-to-head
    analysis, or asks who was better between two specific drivers.

    Args:
        driver_a: First driver — name, code, or number
        driver_b: Second driver — name, code, or number
    """
    _require_session()
    return _json(_mgr.head_to_head(driver_a, driver_b))


# ── Conditions ───────────────────────────────────────────────────────────────


@mcp.tool()
def weather() -> str:
    """Get weather conditions during the session.

    Use this when the user asks about weather, track temperature,
    rain, or conditions that may have affected the race.
    """
    _require_session()
    return _json(_mgr.weather())


# ── Overview ─────────────────────────────────────────────────────────────────


@mcp.tool()
def session_summary() -> str:
    """Get a quick overview of the loaded session with key facts.

    Use this as a starting point when the user asks a general question
    about the session, or when you need context before answering.
    Includes: winner, DNFs, pit stops, fastest lap, weather.
    """
    _require_session()
    return _json(_mgr.session_summary())


# ── Track Analysis ───────────────────────────────────────────────────────────


@mcp.tool()
def track_evolution() -> str:
    """Get how track conditions changed during the session.

    Use this when the user asks about track rubbering in, grip changes,
    whether the track got faster, or temperature effects on pace.
    """
    _require_session()
    return _json(_mgr.track_evolution())


@mcp.tool()
def overtake_analysis() -> str:
    """Get position changes and pace comparisons between consecutive drivers.

    Use this when the user asks about overtakes, who was faster than
    the car ahead, position gains/losses, or race dynamics.
    """
    _require_session()
    return _json(_mgr.overtake_analysis())


# ── Entry point ──────────────────────────────────────────────────────────────


def main():
    """Run the MCP server (stdio transport)."""
    mcp.run()


if __name__ == "__main__":
    main()
