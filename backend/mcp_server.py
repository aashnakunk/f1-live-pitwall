"""
F1 Dashboard — MCP Server (DEPRECATED)

This file is superseded by the f1_mcp package at f1_mcp/.
Use: python -m f1_mcp

This legacy version proxies to the REST API. The new f1_mcp package
accesses FastF1 directly, has fuzzy driver normalization, and is
installable as a standalone package.
"""

import json
import os
import sys

import httpx
from mcp.server.fastmcp import FastMCP

# Backend URL — defaults to local dev server
BACKEND_URL = os.environ.get("F1_BACKEND_URL", "http://localhost:8000")

mcp = FastMCP(
    "f1-dashboard",
    instructions=(
        "F1 race analysis tools. Use these to answer questions about "
        "Formula 1 sessions — race results, lap times, pit strategies, "
        "telemetry, weather, energy/ERS analysis, and live timing data. "
        "Call get_session_status first to check if a session is loaded."
    ),
)


def _api(path: str, method: str = "GET", **kwargs) -> dict:
    """Call the F1 backend API."""
    url = f"{BACKEND_URL}{path}"
    try:
        if method == "GET":
            resp = httpx.get(url, params=kwargs, timeout=30)
        else:
            resp = httpx.post(url, json=kwargs, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"API returned {e.response.status_code}: {e.response.text}"}
    except httpx.ConnectError:
        return {"error": f"Cannot connect to F1 backend at {BACKEND_URL}. Is it running?"}
    except Exception as e:
        return {"error": str(e)}


# ── Session Tools ────────────────────────────────────────────────────────────


@mcp.tool()
def get_session_status() -> str:
    """Check if an F1 session is currently loaded and get basic info.

    Call this first before using other tools to confirm data is available.
    """
    data = _api("/api/session/status")
    return json.dumps(data, indent=2)


@mcp.tool()
def get_available_events(year: int) -> str:
    """Get the F1 calendar/event list for a given year.

    Args:
        year: The season year (e.g. 2024, 2025, 2026)
    """
    data = _api(f"/api/events/{year}")
    return json.dumps(data, indent=2)


@mcp.tool()
def load_session(year: int, gp: str, session_type: str = "R") -> str:
    """Load an F1 session for analysis. Must be called before querying session data.

    Args:
        year: Season year (e.g. 2024)
        gp: Grand Prix name (e.g. "Bahrain", "Saudi Arabia", "Monaco")
        session_type: "R" for Race, "Q" for Qualifying, "FP1"/"FP2"/"FP3" for practice
    """
    data = _api("/api/session/load", method="POST", year=year, gp=gp, session_type=session_type)
    return json.dumps(data, indent=2)


# ── Race Data Tools ──────────────────────────────────────────────────────────


@mcp.tool()
def get_race_results() -> str:
    """Get race results: top 10 finishers with positions, teams, grid positions,
    status (Finished/DNF/+Nlaps), points, and time gaps.

    Also includes weather summary, tyre strategies, and key metrics
    (total laps, pit stops, SC/VSC count, fastest lap).
    """
    data = _api("/api/session/overview")
    return json.dumps(data, indent=2)


@mcp.tool()
def get_available_drivers() -> str:
    """List all drivers in the current session with their 3-letter codes,
    full names, team names, and team colors.
    """
    data = _api("/api/session/drivers")
    return json.dumps(data, indent=2)


@mcp.tool()
def get_driver_lap_times(drivers: str) -> str:
    """Get detailed lap time data for specific drivers. Includes lap numbers,
    times, tyre compounds, tyre age, fuel-corrected times, and degradation analysis.

    Args:
        drivers: Comma-separated driver codes (e.g. "VER,HAM,LEC")
    """
    data = _api("/api/session/laptimes", drivers=drivers)
    return json.dumps(data, indent=2)


@mcp.tool()
def get_pit_strategy() -> str:
    """Get pit stop strategy data for all drivers: pit stop laps, tyre compounds,
    stint lengths, undercut/overcut detection, and stint timeline.
    """
    data = _api("/api/session/pitstrategy")
    return json.dumps(data, indent=2)


@mcp.tool()
def get_telemetry(drivers: str) -> str:
    """Get speed/throttle/brake telemetry comparison for drivers' fastest laps.
    Returns per-distance data points for overlay comparison.

    Args:
        drivers: Comma-separated driver codes (e.g. "VER,HAM")
    """
    data = _api("/api/session/telemetry/multi", drivers=drivers)
    return json.dumps(data, indent=2)


@mcp.tool()
def get_weather() -> str:
    """Get weather conditions during the session: track temperature,
    air temperature, humidity, and rainfall data over time.
    """
    # Weather is included in session overview
    data = _api("/api/session/overview")
    weather = data.get("weather") if isinstance(data, dict) else None
    if weather:
        return json.dumps(weather, indent=2)
    return json.dumps({"note": "Weather data included in get_race_results overview"})


@mcp.tool()
def get_energy_analysis(driver: str) -> str:
    """Get MGU-K energy harvest/deploy analysis for a driver. Shows estimated
    battery state of charge, clipping zones (power-limited), regen zones,
    and energy management patterns.

    Args:
        driver: Driver 3-letter code (e.g. "VER")
    """
    data = _api("/api/session/energy", driver=driver)
    return json.dumps(data, indent=2)


@mcp.tool()
def get_regulation_info() -> str:
    """Get the regulation era info for the current session: DRS/active aero rules,
    MGU-K power (kW), battery capacity (MJ), fuel effect, and era-specific notes.
    """
    data = _api("/api/session/profile")
    return json.dumps(data, indent=2)


@mcp.tool()
def get_session_insights() -> str:
    """Get high-level session insights: key moments, notable performances,
    strategy highlights, and interesting data patterns.
    """
    data = _api("/api/session/insights")
    return json.dumps(data, indent=2)


@mcp.tool()
def get_overtake_probability() -> str:
    """Get overtake probability scores for each driver, based on position,
    gap, tyre advantage, and track characteristics.
    """
    data = _api("/api/session/overtake-probability")
    return json.dumps(data, indent=2)


@mcp.tool()
def get_track_evolution() -> str:
    """Get track evolution data: how grip, temperature, and lap times
    changed throughout the session.
    """
    data = _api("/api/session/track-evolution")
    return json.dumps(data, indent=2)


@mcp.tool()
def get_circuit_info(driver: str = "VER") -> str:
    """Get circuit layout with DRS zones, sector markers, and corner analysis.

    Args:
        driver: Driver code for telemetry overlay (default: "VER")
    """
    data = _api("/api/session/circuit", driver=driver)
    return json.dumps(data, indent=2)


# ── Live Session Tools ───────────────────────────────────────────────────────


@mcp.tool()
def get_live_timing() -> str:
    """Get live timing data from an active F1 session. Includes current standings,
    gaps, intervals, tyre info, telemetry (speed/throttle/brake), pit stops,
    stint timeline, weather, race control messages, and gap evolution.

    Returns empty data if no live session is being recorded.
    """
    data = _api("/api/live/data")
    return json.dumps(data, indent=2)


@mcp.tool()
def get_live_driver_detail(driver_number: str) -> str:
    """Get detailed live data for a specific driver: position history,
    lap times, telemetry trace, and analysis flags.

    Args:
        driver_number: The driver's car number as a string (e.g. "1" for Verstappen)
    """
    data = _api(f"/api/live/driver/{driver_number}")
    return json.dumps(data, indent=2)


@mcp.tool()
def get_live_driver_zones(driver_number: str) -> str:
    """Get per-track-zone analysis for a live driver: clipping percentage,
    lift-coast count, and estimated ERS usage per corner/straight.

    Args:
        driver_number: The driver's car number as a string (e.g. "1" for Verstappen)
    """
    data = _api(f"/api/live/driver/{driver_number}/zones")
    return json.dumps(data, indent=2)


@mcp.tool()
def get_live_status() -> str:
    """Check if live recording is active and how many data points have been captured."""
    data = _api("/api/live/status")
    return json.dumps(data, indent=2)


# ── Compare Tools ────────────────────────────────────────────────────────────


@mcp.tool()
def compare_sessions(
    yearA: int, gpA: str, driverA: str,
    yearB: int, gpB: str, driverB: str,
    session_type: str = "Q",
) -> str:
    """Compare two F1 sessions head-to-head: corner-by-corner speeds,
    sector analysis, lap time delta, and top speed comparison.

    Args:
        yearA: First session year
        gpA: First session GP name
        driverA: First driver code (e.g. "VER")
        yearB: Second session year
        gpB: Second session GP name
        driverB: Second driver code (e.g. "HAM")
        session_type: Session type for both (default "Q" for qualifying)
    """
    data = _api("/api/compare", method="POST",
                yearA=yearA, gpA=gpA, driverA=driverA,
                yearB=yearB, gpB=gpB, driverB=driverB,
                session_type=session_type)
    return json.dumps(data, indent=2)


# ── Run Server ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
