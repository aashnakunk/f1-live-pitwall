"""F1 Dashboard — FastAPI Backend"""

import json
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import anthropic
import fastf1
import httpx
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from scipy import stats

warnings.filterwarnings("ignore")

# ── Driver headshot cache ───────────────────────────────────────────────────
_headshot_cache: dict[str, str] = {}


def _fetch_headshots(year: int):
    """Fetch driver headshot URLs from OpenF1 API.

    Note: F1's media CDN serves current-season photos at all URLs, so
    headshots for historical sessions (e.g. 2024) will show current
    team uniforms. We only fetch headshots for the current year to avoid
    showing misleading photos (e.g. Hamilton in Ferrari kit for a 2024
    Mercedes session).
    """
    global _headshot_cache
    _headshot_cache = {}  # Clear cache when session changes

    from datetime import datetime
    current_year = datetime.now().year

    # Only fetch headshots if session year is current — CDN always shows current photos
    if year < current_year:
        return  # No headshots for historical sessions to avoid wrong uniforms

    try:
        resp = httpx.get(
            f"https://api.openf1.org/v1/drivers?session_key=latest",
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                for d in data:
                    code = d.get("name_acronym", "")
                    url = d.get("headshot_url", "")
                    if code and url:
                        _headshot_cache[code] = url
    except Exception:
        pass  # headshots are nice-to-have, never block on failure


def _get_headshot(driver_code: str) -> Optional[str]:
    return _headshot_cache.get(driver_code)


def _sanitize(obj):
    """Recursively replace NaN/Inf with None so JSON serialization never fails."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if (np.isnan(v) or np.isinf(v)) else v
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj


CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE_DIR))

app = FastAPI(title="F1 Pit Wall API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

COMPOUND_COLORS = {
    "SOFT": "#FF3333", "MEDIUM": "#FFC300", "HARD": "#FFFFFF",
    "INTERMEDIATE": "#39B54A", "WET": "#0067FF", "UNKNOWN": "#888888",
}
TEAM_COLORS = {
    "Red Bull Racing": "#3671C6", "Ferrari": "#E8002D", "Mercedes": "#27F4D2",
    "McLaren": "#FF8000", "Aston Martin": "#229971", "Alpine": "#FF87BC",
    "Williams": "#64C4FF", "AlphaTauri": "#6692FF", "RB": "#6692FF",
    "Alfa Romeo": "#C92D4B", "Haas F1 Team": "#B6BABD",
    "Kick Sauber": "#52E252", "Sauber": "#52E252",
}

# ── Regulation Era Profiles ────────────────────────────────────────────────
SEASON_PROFILES = {
    # Pre-2022: V6 turbo-hybrid, high downforce, DRS
    "v6_hybrid": {
        "label": "V6 Turbo-Hybrid", "years": range(2014, 2022),
        "hasDRS": True, "hasActiveAero": False,
        "mguK_kw": 120, "batteryMJ": 4.0,
        "fuelEffect": 0.035,  # seconds/lap improvement as fuel burns
        "notes": "High-downforce era, DRS on straights, ERS limited to 120kW MGU-K.",
    },
    # 2022-2025: Ground effect + DRS
    "ground_effect": {
        "label": "Ground Effect + DRS", "years": range(2022, 2026),
        "hasDRS": True, "hasActiveAero": False,
        "mguK_kw": 120, "batteryMJ": 4.0,
        "fuelEffect": 0.035,
        "notes": "Ground-effect aero, simplified wings, DRS retained. Less dirty air = better racing.",
    },
    # 2026+: Active aero + no DRS + bigger battery
    "active_aero": {
        "label": "Active Aero Era", "years": range(2026, 2040),
        "hasDRS": False, "hasActiveAero": True,
        "mguK_kw": 350, "batteryMJ": 4.0,
        "fuelEffect": 0.030,  # less fuel effect with lighter PU
        "notes": "No DRS — replaced by X/Z active aero modes. 350kW MGU-K, no MGU-H. Energy management is critical.",
    },
}


def _get_season_profile(year: int) -> dict:
    """Return the regulation profile for a given season year."""
    for key, profile in SEASON_PROFILES.items():
        if year in profile["years"]:
            return {"era": key, **profile}
    # Default fallback for very old seasons
    return {
        "era": "legacy", "label": "Legacy", "years": range(2000, 2014),
        "hasDRS": True if year >= 2011 else False, "hasActiveAero": False,
        "mguK_kw": 60 if year >= 2009 else 0, "batteryMJ": 0.4 if year >= 2009 else 0,
        "fuelEffect": 0.040,
        "notes": f"Pre-hybrid era ({year}). Limited telemetry data available.",
    }


# ── Shared SC/VSC Detection ───────────────────────────────────────────────

def _detect_sc_vsc_laps(laps_df) -> tuple[list[dict], set[int]]:
    """Detect Safety Car and VSC events from laps dataframe.

    Returns:
        sc_events: list of {"type": "SC"|"VSC", "startLap": int, "endLap": int}
        affected_laps: set of lap numbers under SC/VSC (for filtering)
    """
    sc_events = []
    affected_laps = set()
    if laps_df.empty or "TrackStatus" not in laps_df.columns:
        return sc_events, affected_laps

    for lap_num in sorted(laps_df["LapNumber"].unique()):
        lap_data = laps_df[laps_df["LapNumber"] == lap_num]
        statuses = lap_data["TrackStatus"].dropna().unique()
        for st in statuses:
            st_str = str(st)
            if "4" in st_str or "6" in st_str or "7" in st_str:
                flag = "SC" if "4" in st_str else "VSC"
                affected_laps.add(int(lap_num))
                if not sc_events or sc_events[-1]["type"] != flag or int(lap_num) - sc_events[-1]["endLap"] > 1:
                    sc_events.append({"type": flag, "startLap": int(lap_num), "endLap": int(lap_num)})
                else:
                    sc_events[-1]["endLap"] = int(lap_num)

    return sc_events, affected_laps


# ── Fuel-Corrected Lap Times ──────────────────────────────────────────────

def _fuel_correct_laptimes(laps_df, year: int, total_laps: int) -> pd.DataFrame:
    """Add 'FuelCorrectedSec' column: removes fuel effect to reveal true pace/degradation.

    Fuel burns off linearly, making cars ~0.03-0.04s/lap faster.
    We normalize all laps to the fuel load at lap 1 so degradation curves are pure tyre wear.
    """
    profile = _get_season_profile(year)
    fuel_effect = profile["fuelEffect"]  # seconds per lap of fuel burned

    df = laps_df.copy()
    if "LapTime" not in df.columns or df["LapTime"].isna().all():
        df["FuelCorrectedSec"] = None
        return df

    df["LapTimeSec"] = df["LapTime"].dt.total_seconds()
    # Each lap, the car is lighter by fuel_effect * (lap_number - 1).
    # To normalize to lap-1 fuel load, ADD back the fuel benefit.
    df["FuelCorrectedSec"] = df["LapTimeSec"] + df["LapNumber"].apply(
        lambda ln: fuel_effect * (ln - 1)
    )
    return df


# In-memory session store
_session = None
_session_key = None


def _get_session():
    if _session is None:
        raise HTTPException(404, "No session loaded. Call /api/session/load first.")
    return _session


# ── Session Status ──────────────────────────────────────────────────────────

@app.get("/api/session/status")
def session_status():
    if _session is None:
        return {"loaded": False}
    return {
        "loaded": True,
        "event": _session.event["EventName"],
        "year": int(_session.event.year),
        "session": _session.name,
    }


# ── Events ──────────────────────────────────────────────────────────────────

@app.get("/api/events/{year}")
def get_events(year: int):
    schedule = fastf1.get_event_schedule(year)
    events = schedule[schedule["EventFormat"] != "testing"]
    return {"events": events["EventName"].tolist()}


# ── Session Loading ─────────────────────────────────────────────────────────

@app.post("/api/session/load")
def load_session(year: int = Query(...), gp: str = Query(...), session_type: str = Query("R")):
    global _session, _session_key
    key = (year, gp, session_type)
    if _session_key == key and _session is not None:
        # Re-fetch headshots if cache is empty (e.g. after switching from historical session)
        if not _headshot_cache:
            threading.Thread(target=_fetch_headshots, args=(year,), daemon=True).start()
        return {"status": "already_loaded", "event": _session.event["EventName"]}
    sess = fastf1.get_session(year, gp, session_type)
    sess.load()
    _session = sess
    _session_key = key
    # Fetch headshots in background (non-blocking)
    threading.Thread(target=_fetch_headshots, args=(year,), daemon=True).start()
    return {"status": "loaded", "event": sess.event["EventName"], "year": int(sess.event.year)}


# ── Season Profile ─────────────────────────────────────────────────────────

@app.get("/api/session/profile")
def get_session_profile():
    """Return regulation-era profile for the currently loaded session."""
    s = _get_session()
    year = int(s.event.year)
    profile = _get_season_profile(year)
    # Remove range objects (not JSON serializable)
    profile_clean = {k: v for k, v in profile.items() if k != "years"}
    profile_clean["year"] = year
    return profile_clean


# ── Overview ────────────────────────────────────────────────────────────────

@app.get("/api/session/overview")
def get_overview():
    s = _get_session()
    results = s.results
    laps = s.laps

    # Results table
    res_list = []
    for _, r in results.sort_values("Position").iterrows():
        code = r["Abbreviation"]
        res_list.append({
            "position": int(r["Position"]) if pd.notna(r["Position"]) else None,
            "driver": code,
            "fullName": r.get("FullName", code),
            "team": r["TeamName"],
            "teamColor": f"#{r['TeamColor']}" if pd.notna(r.get("TeamColor")) else TEAM_COLORS.get(r["TeamName"], "#FFFFFF"),
            "points": float(r["Points"]) if pd.notna(r["Points"]) else 0,
            "time": str(r["Time"]) if pd.notna(r["Time"]) else "DNF",
            "status": "Finished" if (str(r["Status"]).startswith("+") or r["Status"] == "Finished") else str(r["Status"]),
            "lapped": str(r["Status"]) if str(r["Status"]).startswith("+") else None,
            "grid": int(r["GridPosition"]) if pd.notna(r.get("GridPosition")) else None,
            "headshot": _get_headshot(code),
        })

    # Weather
    weather = {}
    if s.weather_data is not None and not s.weather_data.empty:
        w = s.weather_data
        weather = {
            "trackTemp": round(w["TrackTemp"].mean(), 1),
            "airTemp": round(w["AirTemp"].mean(), 1),
            "humidity": round(w["Humidity"].mean(), 0),
            "rain": bool(w["Rainfall"].any()) if "Rainfall" in w.columns else False,
        }

    # Tyre strategy
    driver_order = results.sort_values("Position")["Abbreviation"].tolist()
    strategies = []
    for drv in driver_order:
        drv_laps = laps[laps["Driver"] == drv].sort_values("LapNumber")
        if drv_laps.empty:
            continue
        stints = []
        groups = drv_laps.groupby((drv_laps["Compound"] != drv_laps["Compound"].shift()).cumsum())
        for _, stint in groups:
            compound = str(stint["Compound"].iloc[0])
            stints.append({
                "compound": compound,
                "startLap": int(stint["LapNumber"].iloc[0]),
                "endLap": int(stint["LapNumber"].iloc[-1]),
                "color": COMPOUND_COLORS.get(compound.upper(), "#888"),
            })
        strategies.append({"driver": drv, "stints": stints})

    # Race metrics
    total_laps = int(laps["LapNumber"].max()) if not laps.empty else 0
    # DNF = statuses that indicate retirement (not lapped finishers like "+1 Lap")
    DNF_KEYWORDS = {"accident", "collision", "spin", "damage", "mechanical", "engine",
                    "gearbox", "hydraulic", "power unit", "electrical", "brakes",
                    "retired", "withdrawal", "dns", "disqualified", "excluded"}
    if "Status" in results.columns:
        def _is_dnf(status):
            s = str(status).lower().strip()
            if s == "finished" or s.startswith("+"):
                return False
            return any(k in s for k in DNF_KEYWORDS) or s not in ("finished",) and not s.startswith("+")
        dnf_count = sum(1 for s in results["Status"] if _is_dnf(s))
        finishers = len(results) - dnf_count
    else:
        dnf_count = 0
        finishers = len(results)
    total_drivers = len(results)

    # SC/VSC events
    sc_events, sc_affected_laps = _detect_sc_vsc_laps(laps)

    # Fastest lap (exclude SC/VSC laps — those are artificially slow)
    fastest_lap_driver = None
    fastest_lap_time = None
    valid_laps = laps[laps["LapTime"].notna() & laps["PitInTime"].isna() & laps["PitOutTime"].isna()]
    valid_laps = valid_laps[~valid_laps["LapNumber"].isin(sc_affected_laps)]
    if not valid_laps.empty:
        fl = valid_laps.loc[valid_laps["LapTime"].idxmin()]
        fastest_lap_driver = fl["Driver"]
        fastest_lap_time = str(fl["LapTime"])

    # Total pit stops
    pit_stops = int(laps["PitInTime"].notna().sum()) if "PitInTime" in laps.columns else 0

    metrics = {
        "totalLaps": total_laps,
        "totalDrivers": total_drivers,
        "finishers": finishers,
        "dnfs": dnf_count,
        "scCount": len([e for e in sc_events if e["type"] == "SC"]),
        "vscCount": len([e for e in sc_events if e["type"] == "VSC"]),
        "scEvents": sc_events,
        "totalPitStops": pit_stops,
        "fastestLapDriver": fastest_lap_driver,
        "fastestLapTime": fastest_lap_time,
    }

    return {"results": res_list, "weather": weather, "strategies": strategies, "metrics": metrics}


# ── Telemetry ───────────────────────────────────────────────────────────────

@app.get("/api/session/telemetry")
def get_telemetry(d1: str = Query(...), d2: str = Query(...)):
    s = _get_session()
    laps = s.laps
    results = s.results

    def get_tel(driver):
        dl = laps.pick_drivers(driver).pick_quicklaps()
        if dl.empty:
            dl = laps.pick_drivers(driver)
        fastest = dl.pick_fastest()
        if fastest is None:
            return None
        tel = fastest.get_telemetry()
        team = results[results["Abbreviation"] == driver]["TeamName"].values
        color = TEAM_COLORS.get(team[0], "#FF4444") if len(team) > 0 else "#FF4444"
        return {
            "driver": driver,
            "color": color,
            "distance": tel["Distance"].tolist(),
            "speed": tel["Speed"].tolist(),
            "throttle": tel["Throttle"].tolist(),
            "brake": tel["Brake"].astype(float).tolist(),
            "time": (tel["Time"].dt.total_seconds() if hasattr(tel["Time"].iloc[0], "total_seconds") else tel["Time"].values / 1e9).tolist() if len(tel) > 0 else [],
        }

    t1 = get_tel(d1)
    t2 = get_tel(d2)
    if not t1 or not t2:
        raise HTTPException(404, "Telemetry not available for selected drivers")

    # Delta
    min_len = min(len(t1["time"]), len(t2["time"]))
    delta = [t1["time"][i] - t2["time"][i] for i in range(min_len)]

    return {"driver1": t1, "driver2": t2, "delta": delta, "deltaDistance": t1["distance"][:min_len]}


@app.get("/api/session/telemetry/multi")
def get_telemetry_multi(drivers: str = Query(..., description="Comma-separated driver codes")):
    """Fetch telemetry for multiple drivers at once."""
    s = _get_session()
    laps = s.laps
    results = s.results
    driver_list = [d.strip() for d in drivers.split(",") if d.strip()]
    if len(driver_list) < 1:
        raise HTTPException(400, "Provide at least one driver code")

    # Track which teams we've seen to differentiate teammates
    team_driver_count = {}

    def get_tel(driver):
        dl = laps.pick_drivers(driver).pick_quicklaps()
        if dl.empty:
            dl = laps.pick_drivers(driver)
        fastest = dl.pick_fastest()
        if fastest is None:
            return None
        tel = fastest.get_telemetry()
        team = results[results["Abbreviation"] == driver]["TeamName"].values
        team_name = team[0] if len(team) > 0 else "Unknown"
        color = TEAM_COLORS.get(team_name, "#FF4444")

        # Track teammate index for differentiation
        team_driver_count[team_name] = team_driver_count.get(team_name, 0) + 1
        teammate_index = team_driver_count[team_name] - 1

        return {
            "driver": driver,
            "color": color,
            "team": team_name,
            "teammateIndex": teammate_index,
            "distance": tel["Distance"].tolist(),
            "speed": tel["Speed"].tolist(),
            "throttle": tel["Throttle"].tolist(),
            "brake": tel["Brake"].astype(float).tolist(),
            "time": (tel["Time"].dt.total_seconds() if hasattr(tel["Time"].iloc[0], "total_seconds") else tel["Time"].values / 1e9).tolist() if len(tel) > 0 else [],
        }

    traces = []
    errors = []
    for drv in driver_list:
        try:
            t = get_tel(drv)
            if t:
                traces.append(t)
            else:
                errors.append(f"{drv}: no fastest lap")
        except Exception as e:
            errors.append(f"{drv}: {str(e)}")

    if not traces:
        raise HTTPException(404, f"Telemetry not available: {'; '.join(errors)}")

    return {"traces": traces}


# ── Lap Times ───────────────────────────────────────────────────────────────

@app.get("/api/session/laptimes")
def get_laptimes():
    s = _get_session()
    laps = s.laps
    results = s.results
    top5 = results.sort_values("Position").head(5)["Abbreviation"].tolist()

    # SC / VSC detection + fuel correction
    sc_events, sc_affected_laps = _detect_sc_vsc_laps(laps)
    year = int(s.event.year)
    total_laps = int(laps["LapNumber"].max()) if not laps.empty else 0

    traces = []
    fuel_traces = []
    pit_laps = set()
    for drv in top5:
        dl = laps[laps["Driver"] == drv].copy()
        dl = dl[dl["PitInTime"].isna() & dl["PitOutTime"].isna()].dropna(subset=["LapTime"])
        # Exclude SC/VSC laps from pace analysis
        dl = dl[~dl["LapNumber"].isin(sc_affected_laps)]
        dl["LapTimeSec"] = dl["LapTime"].dt.total_seconds()
        median = dl["LapTimeSec"].median()
        if pd.notna(median):
            dl = dl[dl["LapTimeSec"] < median * 1.10]
        team = results[results["Abbreviation"] == drv]["TeamName"].values
        color = TEAM_COLORS.get(team[0], "#FFF") if len(team) > 0 else "#FFF"
        traces.append({
            "driver": drv, "color": color,
            "laps": dl["LapNumber"].tolist(),
            "times": dl["LapTimeSec"].round(3).tolist(),
        })
        # Fuel-corrected trace
        dl_fc = _fuel_correct_laptimes(dl, year, total_laps)
        if "FuelCorrectedSec" in dl_fc.columns:
            fuel_traces.append({
                "driver": drv, "color": color,
                "laps": dl_fc["LapNumber"].tolist(),
                "times": dl_fc["FuelCorrectedSec"].round(3).tolist(),
            })
        pits = laps[(laps["Driver"] == drv) & laps["PitInTime"].notna()]["LapNumber"].tolist()
        pit_laps.update(int(p) for p in pits)

    # Degradation (fuel-corrected for accurate tyre wear measurement)
    deg_rows = []
    for drv in top5:
        dl = laps[laps["Driver"] == drv].sort_values("LapNumber").copy().dropna(subset=["LapTime"])
        # Exclude SC/VSC laps
        dl = dl[~dl["LapNumber"].isin(sc_affected_laps)]
        dl = _fuel_correct_laptimes(dl, year, total_laps)
        groups = dl.groupby((dl["Compound"] != dl["Compound"].shift()).cumsum())
        stint_num = 1
        for _, stint in groups:
            clean = stint[stint["PitInTime"].isna() & stint["PitOutTime"].isna()]
            if "FuelCorrectedSec" not in clean.columns or clean["FuelCorrectedSec"].isna().all():
                stint_num += 1
                continue
            med = clean["FuelCorrectedSec"].median()
            if pd.notna(med):
                clean = clean[clean["FuelCorrectedSec"] < med * 1.10]
            if len(clean) >= 3:
                x = np.arange(len(clean))
                y = clean["FuelCorrectedSec"].values
                slope, _, r, _, _ = stats.linregress(x, y)
                deg_rows.append({
                    "driver": drv, "stint": stint_num,
                    "compound": str(clean["Compound"].iloc[0]),
                    "laps": len(clean),
                    "degPerLap": round(slope, 4),
                    "rSquared": round(r ** 2, 3),
                })
            stint_num += 1

    return {
        "traces": traces, "fuelCorrectedTraces": fuel_traces,
        "pitLaps": sorted(pit_laps), "degradation": deg_rows,
        "scEvents": sc_events, "scAffectedLaps": sorted(sc_affected_laps),
        "fuelEffect": _get_season_profile(year)["fuelEffect"],
    }


# ── Predictions ─────────────────────────────────────────────────────────────

@app.get("/api/session/predictions")
def get_predictions(threshold: float = Query(1.5)):
    s = _get_session()
    laps = s.laps
    results = s.results
    drivers = laps["Driver"].unique().tolist()
    year = int(s.event.year)
    total_laps = int(laps["LapNumber"].max()) if not laps.empty else 0

    # Exclude SC/VSC laps from analysis
    _, sc_affected_laps = _detect_sc_vsc_laps(laps)

    # Tyre life predictor (fuel-corrected for accurate degradation)
    tyre_pred = []
    for drv in drivers:
        dl = laps[laps["Driver"] == drv].sort_values("LapNumber").copy().dropna(subset=["LapTime"])
        dl = dl[~dl["LapNumber"].isin(sc_affected_laps)]
        dl = _fuel_correct_laptimes(dl, year, total_laps)
        col = "FuelCorrectedSec" if "FuelCorrectedSec" in dl.columns and not dl["FuelCorrectedSec"].isna().all() else "LapTimeSec"
        if col == "LapTimeSec" and "LapTimeSec" not in dl.columns:
            dl["LapTimeSec"] = dl["LapTime"].dt.total_seconds()
            col = "LapTimeSec"
        groups = dl.groupby((dl["Compound"] != dl["Compound"].shift()).cumsum())
        for _, stint in groups:
            clean = stint[stint["PitInTime"].isna() & stint["PitOutTime"].isna()]
            med = clean[col].median()
            if pd.notna(med):
                clean = clean[clean[col] < med * 1.10]
            if len(clean) < 3:
                continue
            slope, intercept, *_ = stats.linregress(np.arange(len(clean)), clean[col].values)
            life = threshold / slope if slope > 0 else 999
            tyre_pred.append({
                "driver": drv,
                "compound": str(clean["Compound"].iloc[0]),
                "predictedLife": round(life, 1),
                "actualStint": len(stint),
                "degPerLap": round(slope, 4),
            })

    # Pace adjusted (SC-filtered)
    pace = []
    for drv in drivers:
        dl = laps[laps["Driver"] == drv].copy().dropna(subset=["LapTime"])
        dl = dl[~dl["LapNumber"].isin(sc_affected_laps)]
        dl["s"] = dl["LapTime"].dt.total_seconds()
        clean = dl[dl["PitInTime"].isna() & dl["PitOutTime"].isna()]
        med = clean["s"].median()
        if pd.notna(med) and not clean.empty:
            clean = clean[clean["s"] < med * 1.10]
            pace.append({"driver": drv, "medianPace": round(clean["s"].median(), 3)})
    pace.sort(key=lambda x: x["medianPace"])
    for i, p in enumerate(pace):
        p["paceRank"] = i + 1
        actual = results[results["Abbreviation"] == p["driver"]]["Position"].values
        p["actualPos"] = int(actual[0]) if len(actual) > 0 and pd.notna(actual[0]) else None
        p["delta"] = (p["actualPos"] - p["paceRank"]) if p["actualPos"] else None

    # Overtake scorer (final 10 laps)
    max_lap = int(laps["LapNumber"].max()) if not laps.empty else 0
    last = laps[laps["LapNumber"] == max_lap].sort_values("Position")
    overtake = []
    for idx in range(1, len(last)):
        behind = last.iloc[idx]
        ahead = last.iloc[idx - 1]
        gap = 0
        if pd.notna(behind.get("LapTime")) and pd.notna(ahead.get("LapTime")):
            gap = abs(behind["LapTime"].total_seconds() - ahead["LapTime"].total_seconds())
        behind_age = float(behind.get("TyreLife", 0) or 0)
        ahead_age = float(ahead.get("TyreLife", 0) or 0)
        tyre_delta = ahead_age - behind_age
        gap_score = max(0, 3 - gap) / 3 * 40
        tyre_score = min(max(tyre_delta, -10), 10) / 10 * 30
        total = max(0, gap_score + tyre_score)
        overtake.append({
            "driver": behind["Driver"], "attacking": ahead["Driver"],
            "gap": round(gap, 3), "tyreDelta": int(tyre_delta), "score": round(total, 1),
        })
    overtake.sort(key=lambda x: x["score"], reverse=True)

    return {"tyrePredictions": tyre_pred, "paceAdjusted": pace, "overtakeScores": overtake}


# ── Energy / Braking ────────────────────────────────────────────────────────

@app.get("/api/session/energy")
def get_energy(driver: str = Query(...)):
    s = _get_session()
    laps = s.laps
    results = s.results
    dl = laps.pick_drivers(driver).pick_quicklaps()
    if dl.empty:
        dl = laps.pick_drivers(driver)
    fastest = dl.pick_fastest()
    if fastest is None:
        raise HTTPException(404, "No telemetry for this driver")

    tel = fastest.get_telemetry()
    dist = tel["Distance"].values
    speed = tel["Speed"].values
    throttle = tel["Throttle"].values
    brake = tel["Brake"].values.astype(float)
    gear = tel["nGear"].values.tolist() if "nGear" in tel.columns else None
    # DRS: 0/1=off, 2=not detected, 8=eligible, 10/12/14=open
    drs_raw = tel["DRS"].values.astype(int) if "DRS" in tel.columns else None
    drs_map = [1 if int(drs_raw[i]) >= 10 else 0 for i in range(len(speed))] if drs_raw is not None else None

    zones = []
    for i in range(len(tel)):
        thr, brk = throttle[i], brake[i]
        if brk > 0 and thr > 10:
            zones.append("Trail Brake")
        elif brk > 0:
            zones.append("Full Brake")
        elif thr < 5:
            zones.append("Coast/Harvest")
        elif thr < 80:
            zones.append("Partial Throttle")
        else:
            zones.append("Full Throttle")

    # Detected events
    events = []
    prev = zones[0]
    start_d, start_s = dist[0], speed[0]
    for i in range(1, len(zones)):
        if zones[i] != prev:
            length = dist[i] - start_d
            if length > 10:
                events.append({
                    "distance": int(start_d), "zone": prev, "length": int(length),
                    "entrySpeed": int(start_s), "exitSpeed": int(speed[i]),
                    "speedDelta": int(speed[i] - start_s),
                })
            start_d, start_s, prev = dist[i], speed[i], zones[i]

    # Zone summary
    zone_summary = {}
    for e in events:
        z = e["zone"]
        if z not in zone_summary:
            zone_summary[z] = {"zone": z, "count": 0, "totalDist": 0}
        zone_summary[z]["count"] += 1
        zone_summary[z]["totalDist"] += e["length"]
    total = dist[-1] - dist[0]
    for v in zone_summary.values():
        v["pctOfLap"] = round(v["totalDist"] / total * 100, 1)

    team = results[results["Abbreviation"] == driver]["TeamName"].values
    color = TEAM_COLORS.get(team[0], "#FFF") if len(team) > 0 else "#FFF"

    # ── Energy Harvest/Deploy Model ──
    # Model: braking = regen (harvesting), coasting = mild harvest,
    #        full throttle = deployment, partial throttle = neutral
    # 2026 regs: 350kW MGU-K, ~4 MJ battery capacity
    BATTERY_MAX = 4.0  # MJ
    battery = BATTERY_MAX * 0.5  # Start at 50%
    harvest_trace = []
    deploy_trace = []
    battery_trace = []
    clipping_zones = []  # where battery ran out (power clipping)
    regen_zones = []     # where battery is full (regen clipping)

    dt_est = 0.01  # rough time step between samples (~100Hz telemetry)
    for i in range(len(tel)):
        thr, brk, spd = throttle[i], brake[i], speed[i]
        harvest_kw = 0.0
        deploy_kw = 0.0

        if brk > 0:
            # Regen under braking: proportional to brake pressure & speed
            harvest_kw = min(350, brk / 100 * 350 * (spd / 350))
        elif thr < 5 and spd > 50:
            # Coasting: mild regen
            harvest_kw = 80 * (spd / 350)

        if thr > 80:
            # Full deployment
            deploy_kw = 350 * (thr / 100)
        elif 30 < thr <= 80:
            # Partial deployment
            deploy_kw = 150 * (thr / 100)

        # Update battery state (kW * dt => kJ, /1000 => MJ)
        energy_in = harvest_kw * dt_est / 1000
        energy_out = deploy_kw * dt_est / 1000
        battery += energy_in - energy_out
        clipping = False
        regen_clip = False
        if battery <= 0:
            battery = 0
            clipping = True
        elif battery >= BATTERY_MAX:
            battery = BATTERY_MAX
            regen_clip = True

        harvest_trace.append(round(harvest_kw, 1))
        deploy_trace.append(round(-deploy_kw, 1))
        battery_trace.append(round(battery, 3))

        if clipping:
            clipping_zones.append(float(dist[i]))
        if regen_clip:
            regen_zones.append(float(dist[i]))

    # Get X/Y for track overlay
    x_vals = tel["X"].values if "X" in tel.columns else None
    y_vals = tel["Y"].values if "Y" in tel.columns else None

    # Downsample telemetry for frontend (every 3rd point)
    step = 3
    return {
        "driver": driver, "color": color,
        "distance": dist[::step].tolist(),
        "speed": speed[::step].tolist(),
        "throttle": throttle[::step].tolist(),
        "brake": brake[::step].tolist(),
        "gear": gear[::step] if gear else None,
        "zones": [zones[i] for i in range(0, len(zones), step)],
        "events": events,
        "zoneSummary": list(zone_summary.values()),
        "x": x_vals[::step].tolist() if x_vals is not None else None,
        "y": y_vals[::step].tolist() if y_vals is not None else None,
        "harvestKW": harvest_trace[::step],
        "deployKW": deploy_trace[::step],
        "batteryMJ": battery_trace[::step],
        "batteryMax": BATTERY_MAX,
        "clippingZones": clipping_zones[:50],  # limit for frontend
        "regenClipZones": regen_zones[:50],
    }


# ── Race Replay / Predictor ────────────────────────────────────────────────

TYRE_CLIFF = {"SOFT": 18, "MEDIUM": 28, "HARD": 40, "INTERMEDIATE": 30, "WET": 35}


def _compute_win_probability(df: pd.DataFrame, race_progress: float, current_lap: int):
    """Shared prediction model used by both /replay and /sweep.

    Expects df to have columns: driver, _pos, _pace, _gap, _tyreAge, tyre, _lead_laps
    Returns dict with df (augmented with scores/winPct), weights, temperature.
    """
    n_drivers = len(df)

    # ── Feature: Position (higher = better) ──
    max_pos = df["_pos"].max()
    df["pos_s"] = (max_pos - df["_pos"]) / max(max_pos - 1, 1)

    # ── Feature: Pace (lower lap time = better) ──
    valid = df["_pace"].dropna()
    if not valid.empty:
        mn, mx = valid.min(), valid.max()
        sp = mx - mn if mx != mn else 1
        df["pace_s"] = df["_pace"].apply(lambda p: (mx - p) / sp if pd.notna(p) else 0)
    else:
        df["pace_s"] = 0

    # ── Feature: Tyre condition (compound-aware cliff) ──
    def _tyre_score(row):
        cliff = TYRE_CLIFF.get(row["tyre"], 30)
        age = row["_tyreAge"]
        if age <= cliff * 0.5:
            return 1.0
        elif age <= cliff:
            return max(0.2, 1.0 - (age - cliff * 0.5) / (cliff * 0.5) * 0.6)
        else:
            return max(0.0, 0.2 - (age - cliff) / cliff * 0.3)
    df["tyre_s"] = df.apply(_tyre_score, axis=1)

    # ── Feature: Gap to leader (closer = better, clamp negatives) ──
    df["_gap"] = df["_gap"].clip(lower=0)
    max_gap = df["_gap"].max() or 1
    df["gap_s"] = (1 - df["_gap"] / max_gap).clip(0, 1)

    # ── Feature: Leadership consistency (laps spent in P1) ──
    max_lead = max(df["_lead_laps"].max(), 1)
    # Use sqrt scaling so early leads still count but long leads dominate
    df["lead_s"] = (df["_lead_laps"] / max_lead).apply(lambda x: x ** 0.5)

    # ── Dynamic weights: leadership grows with race progress ──
    pw  = 0.20 + 0.25 * race_progress   # position:   0.20 → 0.45
    pcw = 0.30 - 0.10 * race_progress   # pace:       0.30 → 0.20
    tw  = 0.15 - 0.05 * race_progress   # tyre:       0.15 → 0.10
    lw  = 0.15 + 0.10 * race_progress   # leadership: 0.15 → 0.25
    gw  = 1 - pw - pcw - tw - lw        # gap:        0.20 → ~0.00

    df["raw"] = (df["pos_s"] * pw + df["pace_s"] * pcw + df["tyre_s"] * tw
                 + df["gap_s"] * gw + df["lead_s"] * lw)

    # ── Softmax with tighter temperature ──
    # Lower temp = sharper distribution = leader stands out more
    temp = max(0.15, 0.8 - race_progress * 0.6)
    exp_s = np.exp((df["raw"].values - df["raw"].max()) / temp)
    df["winPct"] = (exp_s / exp_s.sum() * 100).round(1)

    return {
        "df": df,
        "weights": {"position": round(pw, 3), "pace": round(pcw, 3),
                     "tyre": round(tw, 3), "gap": round(gw, 3),
                     "leadership": round(lw, 3)},
        "temperature": round(temp, 3),
    }


@app.get("/api/session/replay")
def get_replay(lap: int = Query(...)):
    s = _get_session()
    laps = s.laps
    results = s.results
    max_lap = int(laps["LapNumber"].max()) if not laps.empty else 0
    live_laps = laps[laps["LapNumber"] <= lap]

    if live_laps.empty:
        return {"standings": [], "maxLap": max_lap}

    latest = live_laps[live_laps["LapNumber"] == lap].sort_values("Position")
    if latest.empty:
        latest = live_laps.groupby("Driver").last().sort_values("Position").reset_index()

    rows = []
    leader_time = None
    for _, row in latest.iterrows():
        drv = row["Driver"]
        pos = row.get("Position", 20)
        if pd.isna(pos):
            pos = 20
        recent = live_laps[
            (live_laps["Driver"] == drv) & live_laps["LapTime"].notna()
            & live_laps["PitInTime"].isna() & live_laps["PitOutTime"].isna()
        ].tail(5)
        pace = recent["LapTime"].dt.total_seconds().median() if not recent.empty else None
        tyre_age = float(row.get("TyreLife", 0) or 0)
        compound = str(row.get("Compound", "MEDIUM")).upper()
        cum = live_laps[live_laps["Driver"] == drv]["LapTime"].dropna().dt.total_seconds().sum()
        if leader_time is None:
            leader_time = cum
        gap = cum - leader_time

        team = results[results["Abbreviation"] == drv]["TeamName"].values
        color = TEAM_COLORS.get(team[0], "#FFF") if len(team) > 0 else "#FFF"

        safe_pace = round(pace, 3) if pace is not None and not (isinstance(pace, float) and np.isnan(pace)) else None
        safe_gap = round(gap, 1) if not (isinstance(gap, float) and np.isnan(gap)) else 0.0

        # Pit detection: check if driver pitted on this lap
        pit_in = row.get("PitInTime")
        pit_out = row.get("PitOutTime")
        pitting = bool(pd.notna(pit_in) or pd.notna(pit_out))

        # Lap deficit: how many laps behind the leader
        drv_laps_completed = len(live_laps[(live_laps["Driver"] == drv) & live_laps["LapTime"].notna()])
        leader_laps_completed = len(live_laps[(live_laps["Driver"] == latest.iloc[0]["Driver"]) & live_laps["LapTime"].notna()]) if not latest.empty else drv_laps_completed
        laps_behind = max(0, leader_laps_completed - drv_laps_completed)

        rows.append({
            "driver": drv, "position": int(pos), "pace": safe_pace,
            "tyre": compound, "tyreAge": int(tyre_age), "gap": safe_gap,
            "color": color, "pitting": pitting, "lapsBehind": laps_behind,
            "_pace": pace if pace is not None and not (isinstance(pace, float) and np.isnan(pace)) else None, "_pos": float(pos), "_gap": safe_gap, "_tyreAge": tyre_age,
        })

    # ── Leadership streak: how many laps each driver has been P1 ──
    lead_counts = {}
    if not live_laps.empty:
        for ln in sorted(live_laps["LapNumber"].unique()):
            lap_data = live_laps[live_laps["LapNumber"] == ln]
            if not lap_data.empty:
                leader_row = lap_data.sort_values("Position").iloc[0]
                lead_drv = leader_row["Driver"]
                lead_counts[lead_drv] = lead_counts.get(lead_drv, 0) + 1

    # Win probability
    race_progress = lap / max_lap if max_lap > 0 else 0
    df = pd.DataFrame(rows)

    # Add leadership laps to dataframe
    df["_lead_laps"] = df["driver"].map(lambda d: lead_counts.get(d, 0))

    result = _compute_win_probability(df, race_progress, lap)
    df = result["df"]
    pw, pcw, tw, gw, lw = result["weights"]["position"], result["weights"]["pace"], result["weights"]["tyre"], result["weights"]["gap"], result["weights"]["leadership"]
    temp = result["temperature"]
    df = df.sort_values("winPct", ascending=False)

    standings = []
    for _, r in df.iterrows():
        win_pct = float(r["winPct"]) if pd.notna(r["winPct"]) else 0.0
        standings.append({
            "driver": r["driver"], "position": r["position"],
            "pace": r["pace"] if pd.notna(r.get("pace")) else None,
            "tyre": r["tyre"], "tyreAge": r["tyreAge"],
            "gap": r["gap"] if pd.notna(r["gap"]) else 0.0,
            "color": r["color"], "winPct": win_pct,
            "headshot": _get_headshot(r["driver"]),
            # Diagnostics: feature scores and contributions
            "features": {
                "posScore": round(float(r["pos_s"]), 3),
                "paceScore": round(float(r["pace_s"]), 3),
                "tyreScore": round(float(r["tyre_s"]), 3),
                "gapScore": round(float(r["gap_s"]), 3),
                "leadScore": round(float(r["lead_s"]), 3),
                "rawScore": round(float(r["raw"]), 4),
            },
            "leadLaps": int(r["_lead_laps"]),
        })

    # Position history for top 5
    top5 = [s["driver"] for s in standings[:5]]
    posHistory = {}
    for drv in top5:
        dd = live_laps[live_laps["Driver"] == drv].sort_values("LapNumber").dropna(subset=["Position"])
        posHistory[drv] = {
            "laps": dd["LapNumber"].tolist(),
            "positions": dd["Position"].astype(int).tolist(),
            "color": standings[[s["driver"] for s in standings].index(drv)]["color"] if drv in [s["driver"] for s in standings] else "#FFF",
        }
    # Fix color lookup
    color_map = {s["driver"]: s["color"] for s in standings}
    for drv in posHistory:
        posHistory[drv]["color"] = color_map.get(drv, "#FFF")

    # ── Accuracy vs actual results ──
    actual_order = results.sort_values("Position")["Abbreviation"].tolist()
    predicted_order = [s["driver"] for s in standings]  # sorted by winPct desc

    # Did we predict the winner correctly?
    predicted_winner = predicted_order[0] if predicted_order else None
    actual_winner = actual_order[0] if actual_order else None
    winner_correct = predicted_winner == actual_winner

    # Top 3 overlap
    pred_top3 = set(predicted_order[:3])
    actual_top3 = set(actual_order[:3])
    top3_overlap = len(pred_top3 & actual_top3)

    # Kendall-style correlation: how many pairs are in the right order?
    # Only compare drivers that appear in both lists
    common = [d for d in predicted_order if d in actual_order]
    actual_rank = {d: i for i, d in enumerate(actual_order)}
    concordant = 0
    total_pairs = 0
    for i in range(len(common)):
        for j in range(i + 1, len(common)):
            total_pairs += 1
            if actual_rank.get(common[i], 99) < actual_rank.get(common[j], 99):
                concordant += 1
    order_accuracy = round(concordant / total_pairs * 100, 1) if total_pairs > 0 else 0

    accuracy = {
        "predictedWinner": predicted_winner,
        "actualWinner": actual_winner,
        "winnerCorrect": winner_correct,
        "top3Overlap": top3_overlap,
        "orderAccuracy": order_accuracy,
        "predictedTop3": list(pred_top3),
        "actualTop3": list(actual_top3),
    }

    # Model diagnostics
    model_info = {
        "weights": {"position": round(pw, 3), "pace": round(pcw, 3), "tyre": round(tw, 3), "gap": round(gw, 3), "leadership": round(lw, 3)},
        "temperature": round(temp, 3),
        "raceProgress": round(race_progress, 3),
        "tyreCliffsUsed": TYRE_CLIFF,
    }

    return _sanitize({
        "standings": standings, "maxLap": max_lap, "currentLap": lap,
        "positionHistory": posHistory, "accuracy": accuracy,
        "modelInfo": model_info,
    })


@app.get("/api/session/replay/sweep")
def replay_accuracy_sweep():
    """Run predictions at every 5th lap and track accuracy convergence."""
    s = _get_session()
    laps = s.laps
    results = s.results
    max_lap = int(laps["LapNumber"].max()) if not laps.empty else 0
    actual_order = results.sort_values("Position")["Abbreviation"].tolist()
    actual_winner = actual_order[0] if actual_order else None
    actual_top3 = set(actual_order[:3])

    sweep = []
    sample_laps = list(range(1, max_lap + 1, max(1, max_lap // 20))) + [max_lap]
    sample_laps = sorted(set(sample_laps))

    # Pre-compute leadership counts incrementally
    all_lead_counts = {}  # lap -> {driver: count}
    running_counts = {}
    for ln in sorted(laps["LapNumber"].unique()):
        lap_data = laps[laps["LapNumber"] == ln]
        if not lap_data.empty:
            leader_row = lap_data.sort_values("Position").iloc[0]
            lead_drv = leader_row["Driver"]
            running_counts[lead_drv] = running_counts.get(lead_drv, 0) + 1
        all_lead_counts[ln] = dict(running_counts)

    for check_lap in sample_laps:
        live = laps[laps["LapNumber"] <= check_lap]
        if live.empty:
            continue
        latest = live[live["LapNumber"] == check_lap].sort_values("Position")
        if latest.empty:
            latest = live.groupby("Driver").last().sort_values("Position").reset_index()

        rows = []
        leader_time = None
        for _, row in latest.iterrows():
            drv = row["Driver"]
            pos = row.get("Position", 20)
            if pd.isna(pos):
                pos = 20
            recent = live[
                (live["Driver"] == drv) & live["LapTime"].notna()
                & live["PitInTime"].isna() & live["PitOutTime"].isna()
            ].tail(5)
            pace = recent["LapTime"].dt.total_seconds().median() if not recent.empty else None
            tyre_age = float(row.get("TyreLife", 0) or 0)
            compound = str(row.get("Compound", "MEDIUM")).upper()
            cum = live[live["Driver"] == drv]["LapTime"].dropna().dt.total_seconds().sum()
            if leader_time is None:
                leader_time = cum
            gap = cum - leader_time
            safe_pace = pace if pace is not None and not (isinstance(pace, float) and np.isnan(pace)) else None
            safe_gap = round(gap, 1) if not (isinstance(gap, float) and np.isnan(gap)) else 0.0
            lead_laps = all_lead_counts.get(check_lap, {}).get(drv, 0)
            rows.append({"driver": drv, "_pos": float(pos), "_pace": safe_pace, "_gap": safe_gap, "_tyreAge": tyre_age, "tyre": compound, "_lead_laps": lead_laps})

        if not rows:
            continue

        rp = check_lap / max_lap if max_lap > 0 else 0
        df = pd.DataFrame(rows)
        result = _compute_win_probability(df, rp, check_lap)
        df = result["df"]
        df = df.sort_values("winPct", ascending=False)

        pred_order = df["driver"].tolist()
        pred_winner = pred_order[0]
        pred_top3 = set(pred_order[:3])

        # Kendall concordance
        common = [d for d in pred_order if d in actual_order]
        ar = {d: i for i, d in enumerate(actual_order)}
        conc = sum(1 for i in range(len(common)) for j in range(i+1, len(common)) if ar.get(common[i], 99) < ar.get(common[j], 99))
        tp = len(common) * (len(common) - 1) // 2

        sweep.append({
            "lap": check_lap,
            "raceProgress": round(rp * 100, 1),
            "predictedWinner": pred_winner,
            "winnerCorrect": pred_winner == actual_winner,
            "winnerWinPct": round(float(df[df["driver"] == pred_winner]["winPct"].values[0]), 1),
            "actualWinnerPct": round(float(df[df["driver"] == actual_winner]["winPct"].values[0]), 1) if actual_winner in df["driver"].values else 0,
            "top3Overlap": len(pred_top3 & actual_top3),
            "orderAccuracy": round(conc / tp * 100, 1) if tp > 0 else 0,
            "topPredictions": [{"driver": d, "winPct": round(float(df[df["driver"] == d]["winPct"].values[0]), 1)} for d in pred_order[:5]],
        })

    # Summary: when did we first correctly predict the winner?
    first_correct_lap = None
    for pt in sweep:
        if pt["winnerCorrect"]:
            first_correct_lap = pt["lap"]
            break
    # When did it stay correct permanently?
    locked_lap = None
    for i in range(len(sweep)):
        if all(pt["winnerCorrect"] for pt in sweep[i:]):
            locked_lap = sweep[i]["lap"]
            break

    return _sanitize({
        "sweep": sweep,
        "actualWinner": actual_winner,
        "actualTop3": list(actual_top3),
        "maxLap": max_lap,
        "firstCorrectLap": first_correct_lap,
        "lockedLap": locked_lap,
        "totalCheckpoints": len(sweep),
    })


# ── Track outline cache (shared by replay positions) ──
_track_outline_cache: dict = {}


@app.get("/api/session/replay/positions")
def replay_positions(lap: int = Query(...)):
    """Return synchronized X/Y positions for ALL drivers on a given lap."""
    s = _get_session()
    laps_df = s.laps
    results = s.results
    max_lap = int(laps_df["LapNumber"].max()) if not laps_df.empty else 0

    if lap < 1 or lap > max_lap:
        raise HTTPException(status_code=400, detail=f"Lap must be between 1 and {max_lap}")

    all_drivers = results.sort_values("Position")["Abbreviation"].tolist()

    # Get track outline (cached)
    global _track_outline_cache
    cache_key = id(s)
    if cache_key not in _track_outline_cache:
        # Use the fastest lap from any driver for the outline
        valid = laps_df[laps_df["LapTime"].notna() & laps_df["PitInTime"].isna() & laps_df["PitOutTime"].isna()]
        if not valid.empty:
            fl = valid.loc[valid["LapTime"].idxmin()]
            try:
                tel = fl.get_telemetry()
                if tel is not None and not tel.empty and "X" in tel.columns and "Y" in tel.columns:
                    step = max(1, len(tel) // 400)
                    _track_outline_cache[cache_key] = {
                        "x": tel["X"].values[::step].tolist(),
                        "y": tel["Y"].values[::step].tolist(),
                    }
            except Exception:
                pass
        if cache_key not in _track_outline_cache:
            _track_outline_cache[cache_key] = {"x": [], "y": []}

    track_outline = _track_outline_cache[cache_key]

    # Fetch telemetry for all drivers on this lap in parallel
    def _fetch_tel(drv):
        dl = laps_df[(laps_df["Driver"] == drv) & (laps_df["LapNumber"] == lap)]
        if dl.empty:
            return drv, None
        try:
            tel = dl.iloc[0].get_telemetry()
            if tel is not None and not tel.empty and "X" in tel.columns and "Y" in tel.columns:
                return drv, tel
        except Exception:
            pass
        return drv, None

    driver_data = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_tel, drv): drv for drv in all_drivers}
        for f in as_completed(futures):
            drv, tel = f.result()
            if tel is None:
                continue

            # Resample to ~200 evenly spaced points
            n = len(tel)
            n_out = min(200, n)
            indices = np.linspace(0, n - 1, n_out).astype(int)
            xs = tel["X"].values[indices].tolist()
            ys = tel["Y"].values[indices].tolist()

            # Get driver color
            team = results[results["Abbreviation"] == drv]["TeamName"].values
            color = TEAM_COLORS.get(team[0], "#FFF") if len(team) > 0 else "#FFF"

            driver_data[drv] = {
                "color": color,
                "headshot": _get_headshot(drv),
                "x": xs,
                "y": ys,
            }

    # Start/finish position
    sf = None
    if track_outline["x"]:
        sf = {"x": track_outline["x"][0], "y": track_outline["y"][0]}

    return _sanitize({
        "lap": lap,
        "maxLap": max_lap,
        "trackOutline": track_outline,
        "startFinish": sf,
        "drivers": driver_data,
        "numSamples": 200,
    })


# ── AI Debrief ──────────────────────────────────────────────────────────────

class DebriefRequest(BaseModel):
    apiKey: str


@app.post("/api/session/debrief")
def generate_debrief(req: DebriefRequest):
    s = _get_session()
    results = s.results
    laps = s.laps

    top3 = [
        {"pos": int(r["Position"]), "driver": r["Abbreviation"], "team": r["TeamName"]}
        for _, r in results.sort_values("Position").head(3).iterrows()
    ]
    fl = laps.dropna(subset=["LapTime"])
    fl_data = None
    if not fl.empty:
        fr = fl.loc[fl["LapTime"].idxmin()]
        fl_data = {"driver": fr["Driver"], "time": str(fr["LapTime"]), "lap": int(fr["LapNumber"])}

    pos_changes = []
    for _, r in results.iterrows():
        g, f = r.get("GridPosition"), r.get("Position")
        if pd.notna(g) and pd.notna(f) and abs(int(g) - int(f)) >= 3:
            pos_changes.append({"driver": r["Abbreviation"], "grid": int(g), "finish": int(f), "gained": int(g) - int(f)})

    summary = {
        "event": s.event["EventName"], "year": int(s.event.year),
        "top3": top3, "fastestLap": fl_data, "positionChanges": pos_changes,
    }

    prompt = f"""You are an F1 race engineer writing a post-race debrief.

Session data: {json.dumps(summary)}

Write:
1. A 3-paragraph race engineer debrief: what happened, key strategy moments, standout performances.
2. Then 3 bullet points under "Watch for next race" with predictions.

Keep the tone professional but engaging, like a real race engineer briefing the team."""

    client = anthropic.Anthropic(api_key=req.apiKey)
    msg = client.messages.create(
        model="claude-sonnet-4-20250514", max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return {"debrief": msg.content[0].text}


# ── AI Chat (context-aware) ──────────────────────────────────────────────

class ChatRequest(BaseModel):
    apiKey: str
    question: str
    page: str = "general"
    history: list = []


def _gather_live_chat_context() -> str:
    """Gather rich live session context for the chat agent."""
    # Get latest parsed live data
    try:
        live = get_live_data()
    except Exception:
        return "No live data available. Recording may not be active."

    timing_list = live.get("timing", [])
    if not timing_list:
        return "Live session active but no timing data yet."

    lines = []
    lines.append(f"LIVE SESSION — {live.get('dataPoints', 0)} data points recorded")

    # Weather
    w = live.get("weather")
    if w:
        lines.append(f"Weather: Track {w.get('trackTemp', '?')}°C, Air {w.get('airTemp', '?')}°C, Humidity {w.get('humidity', '?')}%")

    # Race control messages
    rc = live.get("raceControl", [])
    if rc:
        lines.append(f"\nRace Control ({len(rc)} messages):")
        for msg in rc[-10:]:
            lines.append(f"  [{msg.get('flag', '')}] {msg.get('message', '')}")

    # Safety car
    sc = live.get("scStatus")
    if sc:
        lines.append(f"\n⚠ SAFETY CAR: {sc}")

    # Current standings with full detail
    lines.append(f"\nCurrent standings ({len(timing_list)} drivers):")
    pit_drivers = []
    for t in timing_list:
        drv = t.get("name", t.get("driverNumber", "?"))
        pos = t.get("Position", "?")
        team = t.get("team", "?")
        gap = t.get("GapToLeader", "")
        interval = t.get("IntervalToPositionAhead", "")
        best_lap = t.get("bestLapTime", "")
        last_lap = t.get("lastLapTime", "")
        laps = t.get("NumberOfLaps", 0)
        compound = t.get("compound", "?")
        tyre_age = t.get("tyreAge", 0)
        in_pit = t.get("InPit") in (True, "true", "True")
        retired = t.get("Retired") in (True, "true", "True")
        stopped = t.get("Stopped") in (True, "true", "True")

        status = ""
        if retired:
            status = " [RETIRED]"
        elif stopped:
            status = " [STOPPED]"
        elif in_pit:
            status = " [IN PIT]"
            pit_drivers.append(drv)

        tel = t.get("telemetry", {})
        speed = tel.get("speed", 0)
        throttle = tel.get("throttle", 0)
        gear = tel.get("gear", 0)

        lines.append(
            f"  P{pos} {drv} ({team}) — Gap: {gap}, Int: {interval}, "
            f"Best: {best_lap}, Last: {last_lap}, Laps: {laps}, "
            f"Tyre: {compound} (age {tyre_age}), "
            f"Speed: {speed}km/h, Throttle: {throttle}%, Gear: {gear}"
            f"{status}"
        )

    if pit_drivers:
        lines.append(f"\nDrivers currently in pit: {', '.join(pit_drivers)}")

    # Stint timeline (pit stop history)
    stint_tl = live.get("stintTimeline", {})
    if stint_tl:
        lines.append("\nTyre stints:")
        for drv, stints in stint_tl.items():
            stint_strs = []
            for s in stints:
                stint_strs.append(f"{s['compound']}({s['laps']}L)")
            if len(stints) > 1:
                lines.append(f"  {drv}: {' → '.join(stint_strs)} [{len(stints)-1} stop(s)]")

    # Per-driver telemetry analysis (clipping, ERS, speed stats)
    lines.append("\nPer-driver telemetry analysis:")
    for t in timing_list[:22]:
        drv_num = t.get("driverNumber", "")
        drv_name = t.get("name", drv_num)
        history = _live_telemetry_history.get(drv_num, [])
        if len(history) < 5:
            continue

        # Speed stats
        speeds = [s["speed"] for s in history if s["speed"] > 0]
        if speeds:
            peak_speed = max(speeds)
            avg_speed = sum(speeds) / len(speeds)
        else:
            peak_speed = avg_speed = 0

        # Clipping/lift-coast analysis
        patterns = _detect_clipping_patterns(history)
        pattern_strs = []
        for p in patterns:
            pattern_strs.append(f"{p['type']}({p['confidence']*100:.0f}%)")

        # ERS estimate
        ers = _calc_est_ers_usage(history)
        ers_str = f"{ers*100:.0f}%" if ers is not None else "N/A"

        lines.append(
            f"  {drv_name}: peak {peak_speed}km/h, avg {avg_speed:.0f}km/h, "
            f"est.ERS: {ers_str}, "
            f"flags: {', '.join(pattern_strs) if pattern_strs else 'clean'} "
            f"({len(history)} samples)"
        )

        # Per-zone analysis (where on track is clipping/lift-coast happening)
        fused = _fuse_telemetry_with_location(drv_num)
        outline = _circuit_outline_cache.get("outline", [])
        zones = _segment_track_zones(outline)
        if fused and zones:
            zone_analysis = _analyze_per_zone(fused, zones, outline)
            clip_zones = [z for z in zone_analysis if z.get("clippingPct", 0) > 20]
            lift_zones = [z for z in zone_analysis if z.get("liftCoastSamples", 0) > 2]
            if clip_zones:
                clip_strs = [f"{z['label']}({z['clippingPct']:.0f}%)" for z in clip_zones]
                lines.append(f"    Clipping zones: {', '.join(clip_strs)}")
            if lift_zones:
                lift_strs = [f"{z['label']}({z['liftCoastSamples']}x)" for z in lift_zones]
                lines.append(f"    Lift-coast zones: {', '.join(lift_strs)}")

    # Gap evolution
    gap_evo = live.get("gapEvolution", {})
    if gap_evo:
        lines.append("\nGap evolution (recent):")
        for drv, gaps in gap_evo.items():
            if gaps:
                latest = gaps[-1]
                lines.append(f"  {drv}: gap {latest.get('gap', '?')}s at lap {latest.get('lap', '?')}")

    # Pace data
    pace = live.get("paceData", {})
    if pace:
        lines.append("\nLap time history:")
        for drv, laps_data in pace.items():
            if laps_data:
                times = [l.get("time", 0) for l in laps_data if l.get("time")]
                if times:
                    best = min(times)
                    last = times[-1]
                    lines.append(f"  {drv}: best {best:.3f}s, last {last:.3f}s, {len(times)} laps")

    # Alerts
    alerts = live.get("alerts", [])
    if alerts:
        lines.append("\nActive alerts:")
        for a in alerts:
            lines.append(f"  [{a.get('severity', 'info')}] {a.get('message', '')}")

    return "\n".join(lines)


def _gather_chat_context(page: str) -> str:
    """Gather relevant session data as context based on which page the user is on."""
    # Live Pit Wall uses live data, not post-session FastF1
    if page == "live":
        return _gather_live_chat_context()

    # Compare page uses its own data source
    if page == "compare":
        if _last_compare_result is None:
            return "No comparison loaded yet. The user needs to select two sessions and click Compare first."
        cr = _last_compare_result
        sA, sB = cr["sessionA"], cr["sessionB"]
        base = f"GP Comparison: {sA['driver']} ({sA['team']}) at {sA['year']} {sA['event']} vs {sB['driver']} ({sB['team']}) at {sB['year']} {sB['event']}\n\n"
        base += f"Session A: {sA['driver']} — P{sA['position'] or '?'}, fastest lap: {sA['lapTime'] or '?'} (Lap {sA['lapNumber']})\n"
        base += f"Session B: {sB['driver']} — P{sB['position'] or '?'}, fastest lap: {sB['lapTime'] or '?'} (Lap {sB['lapNumber']})\n\n"
        sm = cr["summary"]
        if sm.get("lapTimeDelta") is not None:
            faster = sB["driver"] if sm["lapTimeDelta"] > 0 else sA["driver"]
            base += f"Lap time delta: {abs(sm['lapTimeDelta']):.3f}s ({faster} faster)\n"
        base += f"Top speed: {sA['driver']} {sm.get('maxSpeedA')} km/h vs {sB['driver']} {sm.get('maxSpeedB')} km/h\n"
        base += f"Avg speed: {sA['driver']} {sm.get('avgSpeedA')} km/h vs {sB['driver']} {sm.get('avgSpeedB')} km/h\n"
        base += f"Sectors won: {sA['driver']} {sm.get('sectorsWonA')} vs {sB['driver']} {sm.get('sectorsWonB')} (of {len(cr.get('sectors', []))})\n\n"
        # Corner details
        corners = cr.get("corners", [])
        if corners:
            base += "Corner-by-corner min speeds:\n"
            for c in corners:
                delta = c["speedA"] - c["speedB"]
                adv = sA["driver"] if delta > 2 else sB["driver"] if delta < -2 else "Even"
                base += f"  T{c['number']}: {sA['driver']} {c['speedA']:.0f} km/h vs {sB['driver']} {c['speedB']:.0f} km/h (Δ{delta:+.0f}, {adv})\n"
        # Sector details
        sectors = cr.get("sectors", [])
        if sectors:
            base += "\nSector avg speeds:\n"
            for s in sectors:
                base += f"  S{s['sector']}: {sA['driver']} {s['speedA']} vs {sB['driver']} {s['speedB']} km/h — {sA['driver'] if s['advantage'] == 'A' else sB['driver']} faster\n"
        return base

    try:
        s = _get_session()
    except Exception:
        return "No session loaded."

    results = s.results
    laps = s.laps
    event_name = s.event["EventName"]
    year = int(s.event.year)

    # Always include basic session info
    base = f"Session: {year} {event_name} ({s.name})\n"

    # Top 10 results summary
    top10 = results.sort_values("Position").head(10)
    base += "Results (top 10):\n"
    for _, r in top10.iterrows():
        pos = int(r["Position"]) if pd.notna(r["Position"]) else "?"
        base += f"  P{pos}: {r['Abbreviation']} ({r['TeamName']}) — {r['Status']}\n"

    if page in ("command", "general"):
        # Overview metrics
        total_laps = int(laps["LapNumber"].max()) if not laps.empty else 0
        total_stops = int(laps["PitInTime"].notna().sum()) if "PitInTime" in laps.columns else 0
        base += f"\nTotal laps: {total_laps}, Total pit stops: {total_stops}\n"
        # Weather
        if s.weather_data is not None and not s.weather_data.empty:
            w = s.weather_data
            base += f"Weather: Track {w['TrackTemp'].mean():.0f}°C, Air {w['AirTemp'].mean():.0f}°C, Humidity {w['Humidity'].mean():.0f}%\n"

    if page in ("pitstrategy", "general"):
        # Pit stop details
        base += "\nPit stops by driver:\n"
        for drv in results.sort_values("Position").head(10)["Abbreviation"]:
            dl = laps[(laps["Driver"] == drv) & laps["PitInTime"].notna()]
            if not dl.empty:
                stop_laps = dl["LapNumber"].tolist()
                base += f"  {drv}: stopped on laps {[int(l) for l in stop_laps]}\n"
        # Stints
        base += "\nTyre stints (top 5):\n"
        for drv in results.sort_values("Position").head(5)["Abbreviation"]:
            dl = laps[laps["Driver"] == drv].sort_values("LapNumber")
            if dl.empty:
                continue
            groups = dl.groupby((dl["Compound"] != dl["Compound"].shift()).cumsum())
            stints = []
            for _, stint in groups:
                compound = str(stint["Compound"].iloc[0]).upper()
                sl, el = int(stint["LapNumber"].iloc[0]), int(stint["LapNumber"].iloc[-1])
                stints.append(f"{compound} L{sl}-{el}")
            base += f"  {drv}: {', '.join(stints)}\n"

    if page in ("telemetry", "circuit", "general"):
        # Fastest lap info
        valid = laps[laps["LapTime"].notna() & laps["PitInTime"].isna() & laps["PitOutTime"].isna()]
        if not valid.empty:
            fl = valid.loc[valid["LapTime"].idxmin()]
            base += f"\nFastest lap: {fl['Driver']} — {fl['LapTime']} on lap {int(fl['LapNumber'])}\n"

    if page in ("performance", "general"):
        # Pace analysis for top 5
        base += "\nMedian race pace (top 5, clean laps only):\n"
        for drv in results.sort_values("Position").head(5)["Abbreviation"]:
            dl = laps[laps["Driver"] == drv].copy().dropna(subset=["LapTime"])
            dl["s"] = dl["LapTime"].dt.total_seconds()
            clean = dl[dl["PitInTime"].isna() & dl["PitOutTime"].isna()]
            med = clean["s"].median()
            if pd.notna(med):
                clean = clean[clean["s"] < med * 1.10]
                base += f"  {drv}: {clean['s'].median():.3f}s\n"

    if page in ("replay", "general"):
        # Final standings prediction context
        base += "\nNote: Race Replay shows win probability predictions at each lap. The model uses position, gap, tyre age, and compound.\n"

    if page in ("energy", "general"):
        base += "\nEnergy Map models MGU-K harvest/deploy (2026 regs: 350kW, 4MJ battery). Shows braking zones, regen, and power clipping.\n"

    if page in ("circuit", "general"):
        base += "\nCircuit Lab analysis overlays:\n"
        base += "- Clipping: throttle>=98%, brake==0, speed>250, speed not increasing = engine power-limited\n"
        base += "- ERS Deploy (estimated): full throttle + strong acceleration = battery boost likely active\n"
        base += "- Lift & Coast: off throttle, off brake, high speed = fuel/energy saving strategy\n"
        base += "- DRS: Drag Reduction System — rear wing flap opens on straights when within 1s of car ahead. DRS value >=10 = flap open. Available in 2024/2025 data; 2026+ uses X/Z mode instead.\n"
        base += "These are estimates based on telemetry patterns. Real ERS data is not publicly available.\n"
        base += "Corner cards show per-corner entry/exit speed, clipping %, ERS deploy %, and lift-coast count.\n"

    # Always include regulation era context
    year = int(s.event.year) if hasattr(s, "event") else 2024
    profile = _get_season_profile(year)
    base += f"\nRegulation era: {profile['label']} ({profile['era']})\n"
    base += f"- DRS: {'Yes' if profile['hasDRS'] else 'No (replaced by active aero X/Z modes)'}\n"
    base += f"- MGU-K: {profile['mguK_kw']}kW, Battery: {profile['batteryMJ']}MJ\n"
    base += f"- Fuel effect: ~{profile['fuelEffect']}s/lap improvement as fuel burns off\n"
    base += f"- {profile['notes']}\n"
    base += "- SC/VSC laps are automatically filtered from pace analysis and degradation calculations.\n"
    base += "- Fuel-corrected lap times are available to reveal pure tyre degradation vs fuel-weight improvement.\n"

    return base


@app.post("/api/session/chat")
def chat_with_ai(req: ChatRequest):
    """Context-aware AI chat using MCP-style tool calling.

    Instead of stuffing all data into the system prompt, Claude gets tools
    to fetch specific data on demand. The response includes which tools
    were called so you can see exactly what data Claude used.
    """
    return _chat_with_tools(req)


# ── f1_mcp integration ──────────────────────────────────────────────────────
# Lazy-import to avoid startup failure if f1_mcp isn't installed yet.
# Falls back gracefully to the old backend-only tools.

_f1_mcp_mgr = None


def _get_f1_mcp_manager():
    """Get or create the f1_mcp SessionManager, synced with the backend session."""
    global _f1_mcp_mgr
    try:
        from f1_mcp.session import SessionManager as F1MCPSessionManager
        if _f1_mcp_mgr is None:
            _f1_mcp_mgr = F1MCPSessionManager(cache_dir=CACHE_DIR)
        # Sync: attach the backend's current session
        if _session is not None:
            _f1_mcp_mgr.attach(_session)
        return _f1_mcp_mgr
    except ImportError:
        return None


def _chat_with_tools(req: ChatRequest):
    """Agentic chat using tool calls — Claude decides what data to fetch."""

    page = req.page
    is_live = page == "live"
    mgr = _get_f1_mcp_manager()

    tools = _build_chat_tools(is_live)

    # ── System prompt ────────────────────────────────────────────────────
    live_notes = ""
    if is_live:
        live_notes = """
You have access to LIVE session tools for real-time timing, telemetry, and driver analysis.
ERS estimates are approximate (derived from throttle/acceleration patterns — no actual battery data is public).
When asked "where" something happened, reference track zones (Turn 1, Straight 2, etc.)."""

    system_prompt = f"""You are an expert F1 race engineer assistant embedded in a race analysis dashboard.
You have deep knowledge of Formula 1 strategy, telemetry, tyre management, and race dynamics.

The user is currently viewing the "{page}" page of the dashboard.

IMPORTANT: You have tools to fetch session data. Use them to answer questions with real data.
Call the relevant tool(s) first, then answer based on what the data shows.
Driver names are fuzzy-matched: "Leclerc", "charles", "LEC" all work.

Rules:
- Use tools to fetch data before answering — don't guess.
- Be concise but insightful — like a real race engineer briefing.
- Reference specific drivers, lap numbers, and data points from tool results.
- Use technical F1 terminology where appropriate.
- Keep responses under 200 words unless the question demands more detail.{live_notes}"""

    messages = []
    for msg in req.history[-6:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": req.question})

    # Track which tools Claude calls (returned to frontend for visibility)
    tools_called = []
    total_input_tokens = 0
    total_output_tokens = 0
    api_calls = 0

    try:
        client = anthropic.Anthropic(api_key=req.apiKey)

        # ── Agentic tool-calling loop ─────────────────────────────────────
        max_iterations = 5
        for _ in range(max_iterations):
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=system_prompt,
                messages=messages,
                tools=tools,
            )
            api_calls += 1
            if response.usage:
                total_input_tokens += response.usage.input_tokens
                total_output_tokens += response.usage.output_tokens

            # If Claude is done (no tool calls), extract text and return
            if response.stop_reason == "end_turn":
                text_parts = [b.text for b in response.content if b.type == "text"]
                return {
                    "reply": " ".join(text_parts) if text_parts else "No response generated.",
                    "tools_called": tools_called,
                    "usage": {
                        "input_tokens": total_input_tokens,
                        "output_tokens": total_output_tokens,
                        "api_calls": api_calls,
                    },
                }

            # Process tool calls
            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        # Log the tool call
                        tools_called.append({
                            "tool": block.name,
                            "input": block.input,
                        })
                        result = _execute_chat_tool(block.name, block.input, mgr)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                messages.append({"role": "user", "content": tool_results})
            else:
                text_parts = [b.text for b in response.content if b.type == "text"]
                return {
                    "reply": " ".join(text_parts) if text_parts else "Unexpected response.",
                    "tools_called": tools_called,
                    "usage": {
                        "input_tokens": total_input_tokens,
                        "output_tokens": total_output_tokens,
                        "api_calls": api_calls,
                    },
                }

        return {
            "reply": "I needed too many data lookups. Please try a more specific question.",
            "tools_called": tools_called,
            "usage": {
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "api_calls": api_calls,
            },
        }

    except Exception as e:
        raise HTTPException(500, f"AI chat error: {str(e)}")


def _build_chat_tools(is_live: bool) -> list[dict]:
    """Build tool definitions — domain-specific names, fuzzy driver input."""
    tools = [
        {
            "name": "race_result",
            "description": "Get full race classification — who finished where, with positions, teams, grid positions, status, points, and time gaps.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "qualifying_result",
            "description": "Get qualifying results with Q1/Q2/Q3 times and positions.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "session_summary",
            "description": "Quick overview of the session: winner, DNFs, total laps, pit stops, fastest lap, weather. Good starting point for general questions.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "list_drivers",
            "description": "List all drivers in the session with codes, full names, and teams.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "lap_times",
            "description": "Get lap-by-lap timing data for a specific driver. Includes tyre compound, stint info, and pace statistics. Driver names are fuzzy-matched.",
            "input_schema": {
                "type": "object",
                "properties": {"driver": {"type": "string", "description": "Driver name, code, or number (e.g. 'Leclerc', 'LEC', '16', 'charles')"}},
                "required": ["driver"],
            },
        },
        {
            "name": "fastest_laps",
            "description": "Get the fastest lap set by each driver, ranked. Use for fastest lap comparisons across the field.",
            "input_schema": {
                "type": "object",
                "properties": {"top_n": {"type": "integer", "description": "Number of drivers to return (default 10)"}},
                "required": [],
            },
        },
        {
            "name": "pit_stops",
            "description": "Get pit stop details — when each driver pitted and on which tyre. Omit driver for all drivers.",
            "input_schema": {
                "type": "object",
                "properties": {"driver": {"type": "string", "description": "Driver name/code (optional — omit for all drivers)"}},
                "required": [],
            },
        },
        {
            "name": "tire_stints",
            "description": "Get tyre stint breakdown — compound, start/end lap, stint length per driver. Omit driver for top 10.",
            "input_schema": {
                "type": "object",
                "properties": {"driver": {"type": "string", "description": "Driver name/code (optional — omit for top 10)"}},
                "required": [],
            },
        },
        {
            "name": "driver_telemetry",
            "description": "Get summarized telemetry stats for a driver's lap: top speed, avg speed, throttle %, braking intensity. Defaults to fastest lap.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "driver": {"type": "string", "description": "Driver name, code, or number"},
                    "lap_number": {"type": "integer", "description": "Specific lap number (omit for fastest lap)"},
                },
                "required": ["driver"],
            },
        },
        {
            "name": "head_to_head",
            "description": "Compare two drivers across all key metrics: position, pace, pit stops, fastest lap.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "driver_a": {"type": "string", "description": "First driver — name, code, or number"},
                    "driver_b": {"type": "string", "description": "Second driver — name, code, or number"},
                },
                "required": ["driver_a", "driver_b"],
            },
        },
        {
            "name": "weather",
            "description": "Get weather conditions during the session: track temp, air temp, humidity, rainfall.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "get_regulation_info",
            "description": "Get regulation era info: DRS/active aero rules, MGU-K power (kW), battery capacity (MJ), fuel effect.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "energy_analysis",
            "description": "Get MGU-K energy harvest/deploy model for a driver: braking zones, regen zones, battery state-of-charge, clipping detection (power-limited), and energy management patterns.",
            "input_schema": {
                "type": "object",
                "properties": {"driver": {"type": "string", "description": "Driver name, code, or number (e.g. 'Verstappen', 'VER', '1')"}},
                "required": ["driver"],
            },
        },
        {
            "name": "tyre_predictions",
            "description": "Get tyre life predictions and pace-adjusted standings. Shows estimated remaining tyre life per driver, projected pit windows, and standings adjusted for SC/VSC effects.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "session_insights",
            "description": "Get auto-generated race engineer commentary: gap trends, strategy calls, pace comparisons, key moments, and predicted overtakes.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "overtake_probability",
            "description": "Get overtake likelihood for each consecutive driver pair based on gap, closing speed, tyre delta, DRS/active aero advantage, and energy patterns.",
            "input_schema": {
                "type": "object",
                "properties": {"lap": {"type": "integer", "description": "Specific lap to analyze (omit for final lap)"}},
                "required": [],
            },
        },
        {
            "name": "track_evolution",
            "description": "Get track grip and condition evolution across the session: how lap times, track temp, and grip changed over time. Use when asked about track rubbering in or conditions changing.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "win_probability",
            "description": "Get win probability for each driver at a specific lap. Shows how likely each driver was to win at that point in the race. Use for 'when did X lock in the win?' questions.",
            "input_schema": {
                "type": "object",
                "properties": {"lap": {"type": "integer", "description": "Lap number to check probabilities at"}},
                "required": ["lap"],
            },
        },
    ]

    if is_live:
        tools.extend([
            {
                "name": "get_live_timing",
                "description": "Get live timing: current standings, gaps, intervals, tyre info, telemetry (speed/throttle/brake), pit stops, stints, weather, race control messages.",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
            {
                "name": "get_live_driver_detail",
                "description": "Get detailed live data for a specific driver: position history, lap times, telemetry, analysis flags (clipping, lift-coast, ERS).",
                "input_schema": {
                    "type": "object",
                    "properties": {"driver_number": {"type": "string", "description": "Car number as string, e.g. '1' for Verstappen"}},
                    "required": ["driver_number"],
                },
            },
            {
                "name": "get_live_driver_zones",
                "description": "Get per-track-zone analysis for a live driver: clipping %, lift-coast count, ERS estimate per corner/straight.",
                "input_schema": {
                    "type": "object",
                    "properties": {"driver_number": {"type": "string", "description": "Car number as string, e.g. '1'"}},
                    "required": ["driver_number"],
                },
            },
        ])

    return tools


def _execute_chat_tool(tool_name: str, tool_input: dict, mgr) -> str:
    """Execute a tool call — uses f1_mcp if available, falls back to backend."""
    try:
        # ── f1_mcp-powered tools (with fuzzy driver normalization) ────────
        if mgr is not None and mgr.is_loaded:
            if tool_name == "race_result":
                return json.dumps(mgr.race_result(), default=str)
            elif tool_name == "qualifying_result":
                return json.dumps(mgr.qualifying_result(), default=str)
            elif tool_name == "session_summary":
                return json.dumps(mgr.session_summary(), default=str)
            elif tool_name == "list_drivers":
                return json.dumps(mgr.drivers(), default=str)
            elif tool_name == "lap_times":
                return json.dumps(mgr.lap_times(tool_input.get("driver", "")), default=str)
            elif tool_name == "fastest_laps":
                return json.dumps(mgr.fastest_laps(tool_input.get("top_n", 10)), default=str)
            elif tool_name == "pit_stops":
                drv = tool_input.get("driver", "") or None
                return json.dumps(mgr.pit_stops(drv), default=str)
            elif tool_name == "tire_stints":
                drv = tool_input.get("driver", "") or None
                return json.dumps(mgr.tire_stints(drv), default=str)
            elif tool_name == "driver_telemetry":
                lap = tool_input.get("lap_number", 0)
                return json.dumps(mgr.driver_telemetry(tool_input["driver"], lap if lap > 0 else None), default=str)
            elif tool_name == "head_to_head":
                return json.dumps(mgr.head_to_head(tool_input["driver_a"], tool_input["driver_b"]), default=str)
            elif tool_name == "weather":
                return json.dumps(mgr.weather(), default=str)

        # ── Backend-powered analysis tools (complex logic lives in main.py) ─
        if tool_name == "energy_analysis":
            driver = tool_input.get("driver", "VER")
            # Resolve fuzzy driver name if f1_mcp is available
            if mgr is not None and mgr.is_loaded:
                try:
                    driver = mgr._resolve_driver(driver)
                except ValueError:
                    pass
            data = get_energy(driver=driver)
            return json.dumps(_sanitize(data))
        elif tool_name == "tyre_predictions":
            data = get_predictions()
            return json.dumps(_sanitize(data))
        elif tool_name == "session_insights":
            data = get_insights()
            return json.dumps(_sanitize(data))
        elif tool_name == "overtake_probability":
            lap = tool_input.get("lap") or None
            data = get_overtake_probability(lap=lap)
            return json.dumps(_sanitize(data))
        elif tool_name == "track_evolution":
            data = get_track_evolution()
            return json.dumps(_sanitize(data))
        elif tool_name == "win_probability":
            lap = tool_input.get("lap", 1)
            data = get_replay(lap=lap)
            return json.dumps(_sanitize(data))

        # ── Backend-only tools (live data, regulations) ──────────────────
        elif tool_name == "get_regulation_info":
            data = get_session_profile()
        elif tool_name == "get_live_timing":
            data = get_live_data()
        elif tool_name == "get_live_driver_detail":
            data = get_live_driver_logged(driver_number=tool_input.get("driver_number", "1"))
        elif tool_name == "get_live_driver_zones":
            data = get_driver_zone_analysis(driver_number=tool_input.get("driver_number", "1"))
        # ── Fallbacks when f1_mcp is not available/loaded ────────────────
        elif tool_name == "race_result":
            data = get_overview()
        elif tool_name in ("qualifying_result", "session_summary"):
            s = _get_session()
            data = {"event": s.event["EventName"], "year": int(s.event.year), "session": s.name}
        elif tool_name == "list_drivers":
            data = get_drivers()
        elif tool_name in ("lap_times", "fastest_laps"):
            data = get_laptimes()
        elif tool_name in ("pit_stops", "tire_stints"):
            data = get_pit_strategy()
        elif tool_name == "driver_telemetry":
            drivers = tool_input.get("driver", "VER")
            data = get_telemetry_multi(drivers=drivers)
        elif tool_name == "head_to_head":
            drv_a = tool_input.get("driver_a", "VER")
            drv_b = tool_input.get("driver_b", "HAM")
            data = get_telemetry_multi(drivers=f"{drv_a},{drv_b}")
        elif tool_name == "weather":
            data = get_overview()
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        result = json.dumps(_sanitize(data))
        if len(result) > 15000:
            # Don't break JSON — return a summary note instead of mangled data
            result = json.dumps({
                "_truncated": True,
                "_hint": "Response too large. Ask about a specific driver or use a more targeted tool.",
                "_size": len(result),
            })
        return result
    except HTTPException as e:
        return json.dumps({"error": e.detail})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Track Map ──────────────────────────────────────────────────────────────

@app.get("/api/session/trackmap")
def get_trackmap(driver: str = Query(None)):
    """Return circuit X/Y outline + optional driver telemetry overlay."""
    s = _get_session()
    laps = s.laps
    results = s.results

    # Pick a driver for the circuit outline (or use param)
    drv = driver or results.sort_values("Position").iloc[0]["Abbreviation"]
    dl = laps.pick_drivers(drv).pick_quicklaps()
    if dl.empty:
        dl = laps.pick_drivers(drv)
    fastest = dl.pick_fastest()
    if fastest is None:
        raise HTTPException(404, "No telemetry available for track map")

    tel = fastest.get_telemetry()
    x = tel["X"].values
    y = tel["Y"].values
    dist = tel["Distance"].values
    speed = tel["Speed"].values
    throttle = tel["Throttle"].values
    brake = tel["Brake"].values.astype(float)
    gear = tel["nGear"].values.tolist() if "nGear" in tel.columns else None

    # Classify zones
    zones = []
    for i in range(len(tel)):
        thr, brk = throttle[i], brake[i]
        if brk > 0 and thr > 10:
            zones.append("Trail Brake")
        elif brk > 0:
            zones.append("Full Brake")
        elif thr < 5:
            zones.append("Coast/Harvest")
        elif thr < 80:
            zones.append("Partial Throttle")
        else:
            zones.append("Full Throttle")

    # Detect corners (significant speed minima)
    corners = []
    min_dist_between = 150  # meters
    last_corner_dist = -999
    for i in range(5, len(speed) - 5):
        if speed[i] < speed[i-3] and speed[i] < speed[i+3] and speed[i] < 280:
            if dist[i] - last_corner_dist > min_dist_between:
                corners.append({
                    "x": float(x[i]),
                    "y": float(y[i]),
                    "distance": float(dist[i]),
                    "speed": float(speed[i]),
                    "gear": int(gear[i]) if gear else None,
                })
                last_corner_dist = dist[i]

    team = results[results["Abbreviation"] == drv]["TeamName"].values
    color = TEAM_COLORS.get(team[0], "#FFF") if len(team) > 0 else "#FFF"

    step = 2
    return {
        "driver": drv, "color": color,
        "x": x[::step].tolist(),
        "y": y[::step].tolist(),
        "distance": dist[::step].tolist(),
        "speed": speed[::step].tolist(),
        "throttle": throttle[::step].tolist(),
        "brake": brake[::step].tolist(),
        "gear": gear[::step] if gear else None,
        "zones": [zones[i] for i in range(0, len(zones), step)],
        "corners": corners,
    }


# ── Circuit Analysis (per-lap telemetry) ──────────────────────────────────

@app.get("/api/session/circuit")
def get_circuit(
    driver: str = Query(...),
    lap: Optional[int] = Query(None),
    lap_start: Optional[int] = Query(None, alias="lapStart"),
    lap_end: Optional[int] = Query(None, alias="lapEnd"),
):
    """Return circuit X/Y + telemetry for a specific lap or averaged over a range."""
    s = _get_session()
    laps = s.laps
    results = s.results

    dl = laps[laps["Driver"] == driver]
    if dl.empty:
        raise HTTPException(404, f"No data for driver {driver}")

    available_laps = sorted(dl["LapNumber"].dropna().astype(int).unique().tolist())

    # Determine which laps to use
    if lap is not None:
        target_laps = [lap]
    elif lap_start is not None and lap_end is not None:
        target_laps = [l for l in available_laps if lap_start <= l <= lap_end]
    else:
        # Default: fastest lap
        quick = dl.pick_quicklaps()
        if quick.empty:
            quick = dl
        fastest = quick.pick_fastest()
        if fastest is not None:
            target_laps = [int(fastest["LapNumber"])]
        else:
            target_laps = [available_laps[-1]] if available_laps else []

    if not target_laps:
        raise HTTPException(404, f"No laps found for {driver}")

    # Collect telemetry for target laps
    all_tels = []
    for tl in target_laps:
        lap_row = dl[dl["LapNumber"] == tl]
        if lap_row.empty:
            continue
        try:
            tel = lap_row.iloc[0].get_telemetry()
            if tel is not None and not tel.empty:
                all_tels.append(tel)
        except Exception:
            continue

    if not all_tels:
        raise HTTPException(404, f"No telemetry for {driver} on lap(s) {target_laps}")

    # If single lap, use directly; if range, average by distance
    if len(all_tels) == 1:
        tel = all_tels[0]
    else:
        # Resample all telemetry to common distance grid and average
        ref = all_tels[0]
        dist_grid = ref["Distance"].values
        speed_sum = np.zeros(len(dist_grid))
        throttle_sum = np.zeros(len(dist_grid))
        brake_sum = np.zeros(len(dist_grid))
        count = 0
        for t in all_tels:
            try:
                speed_sum += np.interp(dist_grid, t["Distance"].values, t["Speed"].values)
                throttle_sum += np.interp(dist_grid, t["Distance"].values, t["Throttle"].values)
                brake_sum += np.interp(dist_grid, t["Distance"].values, t["Brake"].values.astype(float))
                count += 1
            except Exception:
                continue
        if count == 0:
            raise HTTPException(404, "Failed to average telemetry")
        tel = ref.copy()
        tel["Speed"] = speed_sum / count
        tel["Throttle"] = throttle_sum / count
        tel["Brake"] = brake_sum / count

    x = tel["X"].values if "X" in tel.columns else None
    y = tel["Y"].values if "Y" in tel.columns else None
    dist = tel["Distance"].values
    speed = tel["Speed"].values
    throttle = tel["Throttle"].values
    brake = tel["Brake"].values.astype(float)
    gear = tel["nGear"].values.tolist() if "nGear" in tel.columns else None

    # DRS extraction (era-aware — only for seasons with DRS)
    # FastF1 DRS: 0/1=off, 2=not detected, 8=eligible, 10/12/14=open
    year = int(s.event.year)
    profile = _get_season_profile(year)
    drs_raw = tel["DRS"].values.astype(int) if "DRS" in tel.columns else None
    if profile["hasDRS"] and drs_raw is not None:
        drs_map = [1 if int(drs_raw[i]) >= 10 else 0 for i in range(len(speed))]
    else:
        drs_map = None

    # Classify zones
    zones = []
    for i in range(len(tel)):
        thr, brk = throttle[i], brake[i]
        if brk > 0 and thr > 10:
            zones.append("Trail Brake")
        elif brk > 0:
            zones.append("Full Brake")
        elif thr < 5:
            zones.append("Coast/Harvest")
        elif thr < 80:
            zones.append("Partial Throttle")
        else:
            zones.append("Full Throttle")

    # Detect corners
    corners = []
    min_dist_between = 150
    last_corner_dist = -999
    for i in range(5, len(speed) - 5):
        if speed[i] < speed[i-3] and speed[i] < speed[i+3] and speed[i] < 280:
            if dist[i] - last_corner_dist > min_dist_between:
                corners.append({
                    "x": float(x[i]) if x is not None else None,
                    "y": float(y[i]) if y is not None else None,
                    "number": len(corners) + 1,
                    "distance": float(dist[i]),
                    "speed": float(speed[i]),
                    "gear": int(gear[i]) if gear else None,
                })
                last_corner_dist = dist[i]

    # Sector-like mini-sector splits (divide track into 20 mini-sectors)
    total_dist = float(dist[-1] - dist[0]) if len(dist) > 1 else 1
    n_sectors = 20
    sector_size = total_dist / n_sectors
    mini_sectors = []
    for s_idx in range(n_sectors):
        s_start = dist[0] + s_idx * sector_size
        s_end = s_start + sector_size
        mask = (dist >= s_start) & (dist < s_end)
        if mask.any():
            mini_sectors.append({
                "sector": s_idx + 1,
                "avgSpeed": round(float(speed[mask].mean()), 1),
                "avgThrottle": round(float(throttle[mask].mean()), 1),
                "avgBrake": round(float(brake[mask].mean()), 1),
                "distance": round(float(s_start), 0),
            })

    # ── Clipping / ERS / Lift-coast analysis per corner zone ──
    clipping_map = []  # per-sample: 0=normal, 1=clipping
    ers_deploy_map = []  # per-sample: 0=not deploying, 1=deploying
    lift_coast_map = []  # per-sample: 0=normal, 1=lift-coast
    for i in range(len(speed)):
        thr, brk, spd = float(throttle[i]), float(brake[i]), float(speed[i])
        # Clipping: full throttle, no brake, high speed, but not accelerating
        is_clipping = 0
        if i > 0 and thr >= 95 and brk == 0 and spd > 200:
            speed_delta = spd - float(speed[i - 1])
            if speed_delta <= 0:
                is_clipping = 1
        clipping_map.append(is_clipping)

        # ERS deploy: full throttle and actually accelerating
        is_deploy = 0
        if i > 0 and thr >= 90 and brk == 0:
            speed_delta = spd - float(speed[i - 1])
            if speed_delta > 1:
                is_deploy = 1
        ers_deploy_map.append(is_deploy)

        # Lift-coast: low throttle, no brake, high speed
        is_lift = 1 if (thr < 40 and brk == 0 and spd > 150) else 0
        lift_coast_map.append(is_lift)

    # Per-corner analysis summary
    corner_analysis = []
    for ci, c in enumerate(corners):
        c_dist = c["distance"]
        # Zone around corner: 100m before to 200m after
        zone_start = c_dist - 100
        zone_end = c_dist + 200
        mask = (dist >= zone_start) & (dist < zone_end)
        n_samples = int(mask.sum())
        if n_samples == 0:
            corner_analysis.append({
                "corner": ci + 1, "clippingPct": 0, "ersDeployPct": 0,
                "liftCoastSamples": 0, "minSpeed": float(c["speed"]),
                "entrySpeed": 0, "exitSpeed": 0,
            })
            continue

        clip_pct = float(np.array(clipping_map)[mask].sum() / n_samples * 100) if n_samples > 0 else 0
        ers_pct = float(np.array(ers_deploy_map)[mask].sum() / n_samples * 100) if n_samples > 0 else 0
        lift_n = int(np.array(lift_coast_map)[mask].sum())
        zone_speeds = speed[mask]
        entry_speed = float(zone_speeds[0]) if len(zone_speeds) > 0 else 0
        exit_speed = float(zone_speeds[-1]) if len(zone_speeds) > 0 else 0
        min_speed = float(zone_speeds.min()) if len(zone_speeds) > 0 else 0

        corner_analysis.append({
            "corner": ci + 1,
            "clippingPct": round(clip_pct, 1),
            "ersDeployPct": round(ers_pct, 1),
            "liftCoastSamples": lift_n,
            "minSpeed": round(min_speed, 1),
            "entrySpeed": round(entry_speed, 1),
            "exitSpeed": round(exit_speed, 1),
        })

    # Overall ERS estimate for the lap
    full_throttle_samples = sum(1 for t in throttle if t >= 95)
    strong_accel_samples = sum(1 for i in range(1, len(speed))
                               if throttle[i] >= 95 and (speed[i] - speed[i-1]) > 2)
    overall_ers = round(strong_accel_samples / full_throttle_samples, 3) if full_throttle_samples > 0 else None

    # Overall clipping percentage
    clip_total = sum(clipping_map)
    high_speed_total = sum(1 for i in range(len(speed)) if speed[i] > 200 and throttle[i] >= 95)
    overall_clipping = round(clip_total / high_speed_total * 100, 1) if high_speed_total > 0 else 0

    team = results[results["Abbreviation"] == driver]["TeamName"].values
    color = TEAM_COLORS.get(team[0], "#FFF") if len(team) > 0 else "#FFF"

    step = 2
    return _sanitize({
        "driver": driver, "color": color,
        "headshot": _get_headshot(driver),
        "lapUsed": target_laps if len(target_laps) > 1 else target_laps[0],
        "availableLaps": available_laps,
        "x": x[::step].tolist() if x is not None else None,
        "y": y[::step].tolist() if y is not None else None,
        "distance": dist[::step].tolist(),
        "speed": speed[::step].tolist(),
        "throttle": throttle[::step].tolist(),
        "brake": brake[::step].tolist(),
        "gear": gear[::step] if gear else None,
        "zones": [zones[i] for i in range(0, len(zones), step)],
        "corners": corners,
        "miniSectors": mini_sectors,
        "clipping": [clipping_map[i] for i in range(0, len(clipping_map), step)],
        "ersDeployment": [ers_deploy_map[i] for i in range(0, len(ers_deploy_map), step)],
        "liftCoast": [lift_coast_map[i] for i in range(0, len(lift_coast_map), step)],
        "drs": [drs_map[i] for i in range(0, len(drs_map), step)] if drs_map else None,
        "drsAvailable": drs_map is not None and any(d == 1 for d in drs_map),
        "cornerAnalysis": corner_analysis,
        "overallErs": overall_ers,
        "overallClipping": overall_clipping,
    })


# ── Pit Strategy & Undercut/Overcut ───────────────────────────────────────

@app.get("/api/session/pitstrategy")
def get_pit_strategy():
    """Full pit strategy: stops, durations, undercut/overcut detection, SC/VSC."""
    s = _get_session()
    laps = s.laps
    results = s.results
    driver_order = results.sort_values("Position")["Abbreviation"].tolist()

    # ── Pit stops for each driver ──
    all_stops = {}
    for drv in driver_order:
        drv_laps = laps[laps["Driver"] == drv].sort_values("LapNumber")
        stops = []
        for _, lap_row in drv_laps.iterrows():
            if pd.notna(lap_row.get("PitInTime")):
                pit_in_lap = int(lap_row["LapNumber"])
                # Get the next lap for pit out
                next_lap = drv_laps[drv_laps["LapNumber"] == pit_in_lap + 1]
                pit_duration = None
                if not next_lap.empty and pd.notna(next_lap.iloc[0].get("PitOutTime")):
                    try:
                        pit_in = lap_row["PitInTime"]
                        pit_out = next_lap.iloc[0]["PitOutTime"]
                        if hasattr(pit_in, "total_seconds"):
                            pit_duration = round((pit_out - pit_in).total_seconds(), 1)
                    except Exception:
                        pass

                # Compound before and after
                compound_before = str(lap_row.get("Compound", "?")).upper()
                after_lap = drv_laps[drv_laps["LapNumber"] > pit_in_lap]
                compound_after = str(after_lap.iloc[0].get("Compound", "?")).upper() if not after_lap.empty else "?"

                stops.append({
                    "lap": pit_in_lap,
                    "duration": pit_duration,
                    "compoundBefore": compound_before,
                    "compoundAfter": compound_after,
                    "colorBefore": COMPOUND_COLORS.get(compound_before, "#888"),
                    "colorAfter": COMPOUND_COLORS.get(compound_after, "#888"),
                })
        team = results[results["Abbreviation"] == drv]["TeamName"].values
        color = TEAM_COLORS.get(team[0], "#FFF") if len(team) > 0 else "#FFF"
        all_stops[drv] = {"driver": drv, "color": color, "stops": stops}

    # ── Stints (for timeline) ──
    stints_data = []
    for drv in driver_order:
        drv_laps = laps[laps["Driver"] == drv].sort_values("LapNumber")
        if drv_laps.empty:
            continue
        groups = drv_laps.groupby((drv_laps["Compound"] != drv_laps["Compound"].shift()).cumsum())
        stints = []
        for _, stint in groups:
            compound = str(stint["Compound"].iloc[0]).upper()
            stints.append({
                "compound": compound,
                "startLap": int(stint["LapNumber"].iloc[0]),
                "endLap": int(stint["LapNumber"].iloc[-1]),
                "laps": len(stint),
                "color": COMPOUND_COLORS.get(compound, "#888"),
            })
        team = results[results["Abbreviation"] == drv]["TeamName"].values
        color = TEAM_COLORS.get(team[0], "#FFF") if len(team) > 0 else "#FFF"
        stints_data.append({"driver": drv, "color": color, "stints": stints})

    # ── Undercut/Overcut Detection ──
    strategies = []
    # Build position-by-lap matrix
    pos_by_lap = {}
    for drv in driver_order:
        drv_laps = laps[laps["Driver"] == drv].sort_values("LapNumber")
        for _, row in drv_laps.iterrows():
            lap_num = int(row["LapNumber"])
            pos = row.get("Position")
            if pd.notna(pos):
                if lap_num not in pos_by_lap:
                    pos_by_lap[lap_num] = {}
                pos_by_lap[lap_num][drv] = int(pos)

    # Find pairs where one pitted before the other and positions swapped
    for drv in driver_order:
        drv_stops = all_stops[drv]["stops"]
        for stop in drv_stops:
            pit_lap = stop["lap"]
            # Look at nearby drivers who pitted within 3 laps
            for rival in driver_order:
                if rival == drv:
                    continue
                rival_stops = all_stops[rival]["stops"]
                for rs in rival_stops:
                    lap_diff = rs["lap"] - pit_lap
                    if 1 <= lap_diff <= 4:
                        # drv pitted first — check if undercut worked
                        pos_before = pos_by_lap.get(pit_lap - 1, {})
                        pos_after = pos_by_lap.get(rs["lap"] + 2, {})
                        if drv in pos_before and rival in pos_before and drv in pos_after and rival in pos_after:
                            was_behind = pos_before[drv] > pos_before[rival]
                            now_ahead = pos_after[drv] < pos_after[rival]
                            if was_behind and now_ahead:
                                strategies.append({
                                    "type": "Undercut",
                                    "driver": drv,
                                    "rival": rival,
                                    "pitLap": pit_lap,
                                    "rivalPitLap": rs["lap"],
                                    "posBefore": pos_before[drv],
                                    "posAfter": pos_after[drv],
                                })
                    elif -4 <= lap_diff <= -1:
                        # drv pitted later — check if overcut worked
                        pos_before = pos_by_lap.get(rs["lap"] - 1, {})
                        pos_after = pos_by_lap.get(pit_lap + 2, {})
                        if drv in pos_before and rival in pos_before and drv in pos_after and rival in pos_after:
                            was_behind = pos_before[drv] > pos_before[rival]
                            now_ahead = pos_after[drv] < pos_after[rival]
                            if was_behind and now_ahead:
                                strategies.append({
                                    "type": "Overcut",
                                    "driver": drv,
                                    "rival": rival,
                                    "pitLap": pit_lap,
                                    "rivalPitLap": rs["lap"],
                                    "posBefore": pos_before[drv],
                                    "posAfter": pos_after[drv],
                                })

    # ── SC / VSC Detection ──
    sc_events, _ = _detect_sc_vsc_laps(laps)

    max_lap = int(laps["LapNumber"].max()) if not laps.empty else 0

    return {
        "pitStops": all_stops,
        "stints": stints_data,
        "strategies": strategies,
        "scEvents": sc_events,
        "maxLap": max_lap,
    }


# ── Lap Insight Narratives (Race Engineer Commentary) ──────────────────────

@app.get("/api/session/insights")
def get_insights():
    """Generate race-engineer-style commentary: gap trends, strategy calls,
    pace comparisons, and predicted overtakes."""
    s = _get_session()
    laps = s.laps
    results = s.results
    year = int(s.event.year)
    total_laps = int(laps["LapNumber"].max()) if not laps.empty else 0
    if total_laps == 0:
        return {"insights": []}

    sc_events, sc_affected = _detect_sc_vsc_laps(laps)
    driver_order = results.sort_values("Position")["Abbreviation"].tolist()
    insights = []

    # ── 1. Gap trends between consecutive positions (top 10) ──
    top10 = driver_order[:10]
    for i in range(len(top10) - 1):
        ahead = top10[i]
        behind = top10[i + 1]
        # Get clean lap times for last 5 laps
        a_laps = laps[(laps["Driver"] == ahead) & laps["LapTime"].notna()
                      & laps["PitInTime"].isna() & ~laps["LapNumber"].isin(sc_affected)].tail(5)
        b_laps = laps[(laps["Driver"] == behind) & laps["LapTime"].notna()
                      & laps["PitInTime"].isna() & ~laps["LapNumber"].isin(sc_affected)].tail(5)
        if len(a_laps) < 3 or len(b_laps) < 3:
            continue
        a_pace = a_laps["LapTime"].dt.total_seconds().values
        b_pace = b_laps["LapTime"].dt.total_seconds().values
        min_len = min(len(a_pace), len(b_pace))
        deltas = b_pace[:min_len] - a_pace[:min_len]
        avg_delta = float(np.mean(deltas))
        trend = "closing" if avg_delta < -0.1 else "pulling away" if avg_delta > 0.1 else "matching pace"

        if abs(avg_delta) > 0.1:
            severity = "high" if abs(avg_delta) > 0.4 else "medium"
            if trend == "closing":
                msg = f"{behind} is {trend} on {ahead} at {abs(avg_delta):.2f}s/lap over the last {min_len} laps."
                # Estimate laps to catch
                final_gap = float(b_laps.iloc[-1].get("LapTime", pd.Timedelta(0)).total_seconds() -
                                  a_laps.iloc[-1].get("LapTime", pd.Timedelta(0)).total_seconds()) if len(a_laps) > 0 and len(b_laps) > 0 else 0
                if avg_delta < -0.15:
                    msg += f" At this rate, could be within DRS range in ~{max(1, int(abs(final_gap) / abs(avg_delta)))} laps."
            else:
                msg = f"{ahead} is {trend} from {behind} at {abs(avg_delta):.2f}s/lap."
            insights.append({"type": "gap_trend", "severity": severity, "message": msg,
                             "drivers": [ahead, behind], "lap": total_laps})

    # ── 2. Tyre cliff warnings ──
    for drv in driver_order[:10]:
        dl = laps[laps["Driver"] == drv].sort_values("LapNumber")
        if dl.empty:
            continue
        last = dl.iloc[-1]
        tyre_age = float(last.get("TyreLife", 0) or 0)
        compound = str(last.get("Compound", "MEDIUM")).upper()
        cliff = TYRE_CLIFF.get(compound, 30)
        if tyre_age >= cliff * 0.85:
            pct = round(tyre_age / cliff * 100)
            insights.append({
                "type": "tyre_warning", "severity": "high" if tyre_age >= cliff else "medium",
                "message": f"{drv} on {compound} tyres at {int(tyre_age)} laps ({pct}% of predicted cliff). "
                           f"{'Box box box!' if tyre_age >= cliff else 'Consider pitting soon.'}",
                "drivers": [drv], "lap": total_laps,
            })

    # ── 3. Undercut/overcut windows ──
    for i in range(len(top10) - 1):
        ahead = top10[i]
        behind = top10[i + 1]
        a_last = laps[laps["Driver"] == ahead].sort_values("LapNumber").iloc[-1] if not laps[laps["Driver"] == ahead].empty else None
        b_last = laps[laps["Driver"] == behind].sort_values("LapNumber").iloc[-1] if not laps[laps["Driver"] == behind].empty else None
        if a_last is None or b_last is None:
            continue
        a_age = float(a_last.get("TyreLife", 0) or 0)
        b_age = float(b_last.get("TyreLife", 0) or 0)
        if b_age > a_age + 5 and b_age > 15:
            insights.append({
                "type": "strategy", "severity": "medium",
                "message": f"Undercut window for {behind} on {ahead}: {behind}'s tyres are {int(b_age - a_age)} laps older. "
                           f"Pitting now could gain track position on fresh rubber.",
                "drivers": [behind, ahead], "lap": total_laps,
            })

    # ── 4. Fastest driver not in top position ──
    clean_laps = laps[laps["PitInTime"].isna() & laps["PitOutTime"].isna()
                      & laps["LapTime"].notna() & ~laps["LapNumber"].isin(sc_affected)]
    if not clean_laps.empty:
        pace_by_driver = clean_laps.groupby("Driver")["LapTime"].apply(
            lambda x: x.dt.total_seconds().median()
        ).sort_values()
        if len(pace_by_driver) >= 2:
            fastest = pace_by_driver.index[0]
            fastest_pos = results[results["Abbreviation"] == fastest]["Position"].values
            if len(fastest_pos) > 0 and pd.notna(fastest_pos[0]) and int(fastest_pos[0]) > 1:
                insights.append({
                    "type": "pace_mismatch", "severity": "medium",
                    "message": f"{fastest} has the best race pace ({pace_by_driver.iloc[0]:.3f}s median) "
                               f"but finished P{int(fastest_pos[0])}. Pace advantage: "
                               f"{pace_by_driver.iloc[1] - pace_by_driver.iloc[0]:.3f}s over {pace_by_driver.index[1]}.",
                    "drivers": [fastest], "lap": total_laps,
                })

    # ── 5. SC/VSC impact narratives ──
    for ev in sc_events:
        # Check who benefited from SC pit stops
        sc_lap_range = range(ev["startLap"], ev["endLap"] + 1)
        pitters = []
        for drv in driver_order:
            pit_laps_drv = laps[(laps["Driver"] == drv) & laps["PitInTime"].notna()]["LapNumber"].tolist()
            if any(int(pl) in sc_lap_range for pl in pit_laps_drv):
                pitters.append(drv)
        if pitters:
            insights.append({
                "type": "sc_impact", "severity": "high",
                "message": f"{ev['type']} on laps {ev['startLap']}-{ev['endLap']}. "
                           f"Cheap stop for: {', '.join(pitters[:5])}.",
                "drivers": pitters[:5], "lap": ev["startLap"],
            })

    # Sort by severity then lap
    severity_order = {"high": 0, "medium": 1, "low": 2}
    insights.sort(key=lambda x: (severity_order.get(x["severity"], 2), -x.get("lap", 0)))

    return {"insights": insights[:25]}  # Cap at 25


# ── Overtake Probability ──────────────────────────────────────────────────

@app.get("/api/session/overtake-probability")
def get_overtake_probability(lap: Optional[int] = Query(None)):
    """Predict overtake likelihood for each consecutive pair based on gap,
    closing speed, tyre delta, DRS availability, and energy patterns."""
    s = _get_session()
    laps_df = s.laps
    results = s.results
    year = int(s.event.year)
    profile = _get_season_profile(year)
    max_lap = int(laps_df["LapNumber"].max()) if not laps_df.empty else 0
    target_lap = lap if lap is not None else max_lap
    _, sc_affected = _detect_sc_vsc_laps(laps_df)

    live_laps = laps_df[laps_df["LapNumber"] <= target_lap]
    if live_laps.empty:
        return {"probabilities": [], "lap": target_lap}

    latest = live_laps[live_laps["LapNumber"] == target_lap].sort_values("Position")
    if latest.empty:
        latest = live_laps.groupby("Driver").last().sort_values("Position").reset_index()

    probabilities = []
    for idx in range(1, len(latest)):
        behind_row = latest.iloc[idx]
        ahead_row = latest.iloc[idx - 1]
        behind = behind_row["Driver"]
        ahead = ahead_row["Driver"]

        # Gap: cumulative time difference
        behind_cum = live_laps[live_laps["Driver"] == behind]["LapTime"].dropna().dt.total_seconds().sum()
        ahead_cum = live_laps[live_laps["Driver"] == ahead]["LapTime"].dropna().dt.total_seconds().sum()
        gap = abs(behind_cum - ahead_cum)

        # Closing speed: pace difference over last 5 clean laps
        def _recent_pace(drv):
            dl = live_laps[(live_laps["Driver"] == drv) & live_laps["LapTime"].notna()
                          & live_laps["PitInTime"].isna() & ~live_laps["LapNumber"].isin(sc_affected)].tail(5)
            return dl["LapTime"].dt.total_seconds().median() if not dl.empty else None

        behind_pace = _recent_pace(behind)
        ahead_pace = _recent_pace(ahead)
        closing_rate = (ahead_pace - behind_pace) if (ahead_pace and behind_pace) else 0

        # Tyre condition
        behind_age = float(behind_row.get("TyreLife", 0) or 0)
        ahead_age = float(ahead_row.get("TyreLife", 0) or 0)
        behind_compound = str(behind_row.get("Compound", "MEDIUM")).upper()
        ahead_compound = str(ahead_row.get("Compound", "MEDIUM")).upper()
        behind_cliff = TYRE_CLIFF.get(behind_compound, 30)
        ahead_cliff = TYRE_CLIFF.get(ahead_compound, 30)
        tyre_advantage = (ahead_age / ahead_cliff) - (behind_age / behind_cliff)  # positive = behind has fresher tyres

        # Score components (0-100 scale)
        # Gap score: closer = higher (within 3s is DRS range)
        gap_score = max(0, (3 - gap) / 3) * 35 if gap < 5 else 0

        # Closing rate score
        closing_score = min(max(closing_rate, 0), 1.0) / 1.0 * 25

        # Tyre advantage score
        tyre_score = min(max(tyre_advantage, -0.5), 0.5) / 0.5 * 20

        # DRS boost (if within 1s and DRS era)
        drs_boost = 10 if (profile["hasDRS"] and gap < 1.0) else 0
        # Active aero boost for 2026+ (less powerful but still helps)
        aero_boost = 5 if (profile["hasActiveAero"] and gap < 1.5) else 0

        # Position factor: harder to overtake for higher positions
        pos_factor = max(0, 10 - int(behind_row.get("Position", 10) or 10)) / 10 * 10

        total = max(0, min(100, gap_score + closing_score + tyre_score + drs_boost + aero_boost + pos_factor))

        # Narrative
        factors = []
        if gap < 1.0:
            factors.append(f"within DRS range ({gap:.1f}s)")
        elif gap < 2.0:
            factors.append(f"gap closing ({gap:.1f}s)")
        if closing_rate > 0.2:
            factors.append(f"gaining {closing_rate:.2f}s/lap")
        if tyre_advantage > 0.15:
            factors.append("fresher tyres")
        elif tyre_advantage < -0.15:
            factors.append("older tyres")
        if drs_boost > 0:
            factors.append("DRS available")

        team_b = results[results["Abbreviation"] == behind]["TeamName"].values
        team_a = results[results["Abbreviation"] == ahead]["TeamName"].values
        color_b = TEAM_COLORS.get(team_b[0], "#FFF") if len(team_b) > 0 else "#FFF"
        color_a = TEAM_COLORS.get(team_a[0], "#FFF") if len(team_a) > 0 else "#FFF"

        probabilities.append({
            "attacker": behind, "attackerColor": color_b,
            "defender": ahead, "defenderColor": color_a,
            "probability": round(total, 1),
            "gap": round(gap, 2),
            "closingRate": round(closing_rate, 3) if closing_rate else 0,
            "tyreDelta": round(tyre_advantage, 2),
            "factors": factors,
            "position": int(behind_row.get("Position", 0) or 0),
        })

    probabilities.sort(key=lambda x: x["probability"], reverse=True)

    return {"probabilities": probabilities, "lap": target_lap, "maxLap": max_lap, "hasDRS": profile["hasDRS"]}


# ── Track Evolution ────────────────────────────────────────────────────────

@app.get("/api/session/track-evolution")
def get_track_evolution():
    """Analyze grip improvement across the session.

    Track rubbers in over a weekend: lap times improve 0.5-1.5s as rubber
    is laid down. This endpoint tracks that evolution and normalizes for it.
    """
    s = _get_session()
    laps = s.laps
    results = s.results
    year = int(s.event.year)
    total_laps = int(laps["LapNumber"].max()) if not laps.empty else 0
    if total_laps == 0:
        return {"evolution": [], "summary": {}}

    _, sc_affected = _detect_sc_vsc_laps(laps)

    # Track best lap time per lap number (across all drivers, clean laps only)
    clean = laps[laps["LapTime"].notna() & laps["PitInTime"].isna()
                 & laps["PitOutTime"].isna() & ~laps["LapNumber"].isin(sc_affected)]
    if clean.empty:
        return {"evolution": [], "summary": {}}

    clean = clean.copy()
    clean["LapTimeSec"] = clean["LapTime"].dt.total_seconds()

    # Per-lap: median of top 5 fastest drivers (avoids outliers)
    evolution = []
    for ln in sorted(clean["LapNumber"].unique()):
        lap_data = clean[clean["LapNumber"] == ln]["LapTimeSec"]
        if len(lap_data) < 3:
            continue
        top5_median = lap_data.nsmallest(5).median()
        evolution.append({"lap": int(ln), "bestMedian": round(top5_median, 3)})

    if len(evolution) < 5:
        return {"evolution": evolution, "summary": {}}

    # Fit linear trend to see overall improvement
    laps_arr = np.array([e["lap"] for e in evolution])
    times_arr = np.array([e["bestMedian"] for e in evolution])
    slope, intercept, r_value, _, _ = stats.linregress(laps_arr, times_arr)

    # Split into thirds for phase analysis
    third = len(evolution) // 3
    early = np.median([e["bestMedian"] for e in evolution[:third]])
    mid = np.median([e["bestMedian"] for e in evolution[third:2*third]])
    late = np.median([e["bestMedian"] for e in evolution[2*third:]])

    # Fuel-correct to isolate track evolution from fuel effect
    profile = _get_season_profile(year)
    fuel_effect = profile["fuelEffect"]
    fc_evolution = []
    for e in evolution:
        fc_time = e["bestMedian"] + fuel_effect * (e["lap"] - 1)
        fc_evolution.append({"lap": e["lap"], "fuelCorrected": round(fc_time, 3)})

    # Re-fit on fuel-corrected data for pure track evolution
    fc_times = np.array([e["fuelCorrected"] for e in fc_evolution])
    fc_slope, fc_intercept, fc_r, _, _ = stats.linregress(laps_arr, fc_times)

    summary = {
        "totalImprovement": round(float(times_arr[0] - times_arr[-1]), 3),
        "fuelCorrectedImprovement": round(float(fc_times[0] - fc_times[-1]), 3),
        "slopePerLap": round(float(slope), 4),
        "fuelCorrectedSlope": round(float(fc_slope), 4),
        "rSquared": round(float(r_value ** 2), 3),
        "earlyPace": round(float(early), 3),
        "midPace": round(float(mid), 3),
        "latePace": round(float(late), 3),
        "trackRubberedIn": fc_slope < -0.005,  # True if track is getting faster (after fuel correction)
        "fuelEffect": fuel_effect,
    }

    return {"evolution": evolution, "fuelCorrectedEvolution": fc_evolution, "summary": summary}


# ── Drivers list ────────────────────────────────────────────────────────────

@app.get("/api/session/drivers")
def get_drivers():
    s = _get_session()
    results = s.results
    drivers = []
    for _, r in results.sort_values("Position").iterrows():
        code = r["Abbreviation"]
        number = int(r["DriverNumber"]) if pd.notna(r.get("DriverNumber")) else None
        # Prefer FastF1's session-specific TeamColor, fall back to static map
        color = TEAM_COLORS.get(r["TeamName"], "#FFFFFF")
        if pd.notna(r.get("TeamColor")):
            color = f"#{r['TeamColor']}"
        drivers.append({
            "code": code,
            "name": r.get("FullName", code),
            "team": r["TeamName"],
            "color": color,
            "number": number,
            "headshot": _get_headshot(code),
        })
    return {"drivers": drivers}


# ── Live Timing ─────────────────────────────────────────────────────────────

# Check both locations: cache dir and project root (CLI recording)
_LIVE_FILE_CACHE = CACHE_DIR / "live_timing.txt"
_LIVE_FILE_ROOT = Path(__file__).parent.parent / "live_data.txt"


def _get_live_file():
    """Return whichever live data file has data, preferring the most recently modified."""
    files = [f for f in [_LIVE_FILE_CACHE, _LIVE_FILE_ROOT] if f.exists() and f.stat().st_size > 0]
    if not files:
        return _LIVE_FILE_ROOT if _LIVE_FILE_ROOT.exists() else _LIVE_FILE_CACHE
    return max(files, key=lambda f: f.stat().st_mtime)


LIVE_DATA_FILE = _LIVE_FILE_CACHE  # default for backward compat
_live_thread = None
_live_running = False
_live_error = None
# Caches updated by get_live_data() and consumed by the per-driver endpoint
_live_telemetry_history: dict[str, list] = {}
_live_positions: dict[str, dict] = {}
_live_driver_info_cache: dict = {}
_live_pos_history: dict[str, list] = {}  # per driver: list of {"x", "y", "ts"} for location fusion

# ── Incremental parsing cache ──
# Instead of re-parsing the entire file on every /api/live/data call,
# we track how many bytes we've already parsed and only read new data.
_live_parse_cache = {
    "file": None,           # which file we parsed
    "offset": 0,            # bytes already consumed
    "mtime": 0,             # last known mtime
    "result": None,         # cached response dict
    "timing": {},           # accumulated timing dict
    "weather": None,
    "race_control": [],
    "car_telemetry": {},
    "telemetry_history": {},
    "positions": {},
    "gap_history": {},
    "stint_history": {},
    "lap_times_history": {},
    "line_count": 0,
}


@app.get("/api/live/status")
def live_status():
    f = _get_live_file()
    has_data = f.exists() and f.stat().st_size > 0
    # Use file size as a fast proxy for data points (avoids reading entire file)
    data_points = _live_parse_cache["line_count"] if _live_parse_cache["line_count"] > 0 else (f.stat().st_size // 200 if has_data else 0)
    return {
        "recording": _live_running,
        "hasData": has_data,
        "dataPoints": data_points,
        "error": _live_error,
        "source": str(f.name) if has_data else None,
    }


@app.post("/api/live/start")
def start_live_recording():
    global _live_thread, _live_running, _live_error
    if _live_running:
        return {"status": "already_recording"}

    _live_running = True
    _live_error = None

    def _record():
        global _live_running, _live_error
        try:
            from fastf1.livetiming.client import SignalRClient
            import logging
            logging.getLogger("fastf1").setLevel(logging.DEBUG)
            logger = logging.getLogger("fastf1.livetiming")
            logger.info("Starting live timing client...")
            client = SignalRClient(filename=str(LIVE_DATA_FILE), filemode="a", timeout=300)
            client.start()
        except Exception as e:
            _live_error = f"{type(e).__name__}: {e}"
            import traceback
            traceback.print_exc()
        finally:
            _live_running = False

    _live_thread = threading.Thread(target=_record, daemon=True)
    _live_thread.start()
    return {"status": "started"}


@app.post("/api/live/stop")
def stop_live_recording():
    global _live_running
    _live_running = False
    return {"status": "stopping"}


@app.post("/api/live/clear")
def clear_live_data():
    for f in [_LIVE_FILE_CACHE, _LIVE_FILE_ROOT]:
        if f.exists():
            f.unlink()
    # Reset incremental parse cache
    _live_parse_cache.update({
        "file": None, "offset": 0, "mtime": 0, "result": None,
        "timing": {}, "weather": None, "race_control": [],
        "car_telemetry": {}, "telemetry_history": {}, "positions": {},
        "gap_history": {}, "stint_history": {}, "lap_times_history": {},
        "line_count": 0,
    })
    return {"status": "cleared"}


@app.get("/api/live/data")
def get_live_data():
    import ast
    import base64
    import zlib

    f = _get_live_file()
    if not f.exists() or f.stat().st_size == 0:
        return {"timing": [], "weather": None, "raceControl": [], "dataPoints": 0}

    # ── Incremental parsing: only read new bytes since last call ──
    cache = _live_parse_cache
    file_size = f.stat().st_size
    file_str = str(f)

    # If same file and no new data, return cached result
    if cache["file"] == file_str and cache["offset"] >= file_size and cache["result"] is not None:
        return cache["result"]

    # If different file, reset cache
    if cache["file"] != file_str:
        cache["file"] = file_str
        cache["offset"] = 0
        cache["timing"] = {}
        cache["weather"] = None
        cache["race_control"] = []
        cache["car_telemetry"] = {}
        cache["telemetry_history"] = {}
        cache["positions"] = {}
        cache["gap_history"] = {}
        cache["stint_history"] = {}
        cache["lap_times_history"] = {}
        cache["line_count"] = 0

    # Read only new bytes
    with open(f, "r") as fh:
        if cache["offset"] == 0:
            # Cold start: only parse last ~3000 lines for speed
            # (current driver state only needs recent messages)
            all_text = fh.read()
            all_lines = all_text.split("\n")
            cache["line_count"] = len(all_lines)
            # Take the last 3000 lines (enough for current state)
            new_lines = all_lines[-3000:] if len(all_lines) > 3000 else all_lines
            new_offset = len(all_text.encode("utf-8", errors="replace"))
        else:
            fh.seek(cache["offset"])
            new_data = fh.read()
            new_offset = fh.tell()
            if not new_data.strip() and cache["result"] is not None:
                return cache["result"]
            new_lines = new_data.strip().split("\n") if new_data.strip() else []
            cache["line_count"] += len(new_lines)

    cache["offset"] = new_offset

    # Use cached accumulators
    timing = cache["timing"]
    weather = cache["weather"]
    race_control = cache["race_control"]
    car_telemetry = cache["car_telemetry"]
    telemetry_history = cache["telemetry_history"]
    positions = cache["positions"]
    gap_history = cache["gap_history"]
    stint_history = cache["stint_history"]
    lap_times_history = cache["lap_times_history"]

    for line in new_lines:
        try:
            if not line.startswith("["):
                continue
            # fastf1 saves as Python repr (single quotes), not JSON
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                entry = ast.literal_eval(line)
            cat = entry[0] if len(entry) > 0 else ""
            # entry[1] might be a JSON string that needs parsing
            raw_data = entry[1] if len(entry) > 1 else {}
            if isinstance(raw_data, str):
                try:
                    data = json.loads(raw_data)
                except (json.JSONDecodeError, ValueError):
                    data = raw_data
            else:
                data = raw_data
            ts = entry[2] if len(entry) > 2 else ""

            if cat == "TimingData" and isinstance(data, dict) and "Lines" in data:
                for drv_num, drv_data in data["Lines"].items():
                    if drv_num not in timing:
                        timing[drv_num] = {"driverNumber": drv_num}
                    for key in ("Position", "GapToLeader", "IntervalToPositionAhead",
                                "NumberOfLaps", "Retired", "InPit", "Stopped"):
                        if key in drv_data:
                            timing[drv_num][key] = drv_data[key]
                    if "LastLapTime" in drv_data:
                        lt = drv_data["LastLapTime"]
                        timing[drv_num]["lastLapTime"] = lt.get("Value", "") if isinstance(lt, dict) else lt
                    if "BestLapTime" in drv_data:
                        bt = drv_data["BestLapTime"]
                        timing[drv_num]["bestLapTime"] = bt.get("Value", "") if isinstance(bt, dict) else bt
                    for sec in ("Sector1", "Sector2", "Sector3"):
                        if f"Sectors" in drv_data and sec[-1] in str(drv_data.get("Sectors", {})):
                            pass  # sectors have complex nested structure
                    timing[drv_num]["_ts"] = ts

                    # Track gap evolution per lap
                    if "NumberOfLaps" in drv_data and "GapToLeader" in drv_data:
                        lap = drv_data["NumberOfLaps"]
                        gap_str = str(drv_data["GapToLeader"]).replace("+", "").strip()
                        try:
                            if "L" in gap_str.upper():
                                gap_val = float(gap_str.upper().replace("L", "").strip() or "0") * 60
                            else:
                                gap_val = float(gap_str) if gap_str else 0.0
                        except ValueError:
                            gap_val = None
                        if gap_val is not None:
                            if drv_num not in gap_history:
                                gap_history[drv_num] = []
                            # Only add if new lap
                            if not gap_history[drv_num] or gap_history[drv_num][-1]["lap"] != lap:
                                gap_history[drv_num].append({"lap": lap, "gap": round(gap_val, 3)})

                    # Track lap times
                    if "NumberOfLaps" in drv_data and "LastLapTime" in drv_data:
                        lap = drv_data["NumberOfLaps"]
                        lt = drv_data["LastLapTime"]
                        lt_val = lt.get("Value", "") if isinstance(lt, dict) else lt
                        if lt_val and ":" in str(lt_val):
                            try:
                                parts = str(lt_val).split(":")
                                secs = float(parts[0]) * 60 + float(parts[1])
                                if drv_num not in lap_times_history:
                                    lap_times_history[drv_num] = []
                                if not lap_times_history[drv_num] or lap_times_history[drv_num][-1]["lap"] != lap:
                                    lap_times_history[drv_num].append({"lap": lap, "time": round(secs, 3), "display": lt_val})
                            except (ValueError, IndexError):
                                pass

            elif cat == "TimingAppData" and isinstance(data, dict) and "Lines" in data:
                for drv_num, drv_data in data["Lines"].items():
                    if drv_num not in timing:
                        timing[drv_num] = {"driverNumber": drv_num}
                    stints = drv_data.get("Stints", {})
                    if stints:
                        # Stints can be a dict or a list depending on the data source
                        try:
                            if isinstance(stints, dict):
                                latest_stint_key = max(stints.keys(), key=lambda k: int(k))
                                stint_data = stints[latest_stint_key]
                            elif isinstance(stints, list):
                                stint_data = stints[-1] if stints else {}
                            else:
                                stint_data = {}
                            if isinstance(stint_data, dict):
                                if "Compound" in stint_data:
                                    timing[drv_num]["compound"] = stint_data["Compound"]
                                if "TotalLaps" in stint_data:
                                    timing[drv_num]["tyreAge"] = stint_data["TotalLaps"]
                        except (ValueError, IndexError, TypeError):
                            pass

                    # Build full stint history for tyre timeline
                    if stints and isinstance(stints, dict):
                        if drv_num not in stint_history:
                            stint_history[drv_num] = {}
                        for stint_key, stint_val in stints.items():
                            if isinstance(stint_val, dict) and "Compound" in stint_val:
                                stint_history[drv_num][stint_key] = {
                                    "compound": stint_val.get("Compound", ""),
                                    "totalLaps": stint_val.get("TotalLaps", 0),
                                    "new": stint_val.get("New", True),
                                    "startLaps": stint_val.get("StartLaps", 0),
                                }

            elif cat == "WeatherData" and isinstance(data, dict):
                weather = {
                    "trackTemp": data.get("TrackTemp"),
                    "airTemp": data.get("AirTemp"),
                    "humidity": data.get("Humidity"),
                    "rain": data.get("Rainfall", "0") not in ("0", "False", False, 0, ""),
                    "windSpeed": data.get("WindSpeed"),
                    "windDir": data.get("WindDirection"),
                }
                cache["weather"] = weather

            elif cat == "RaceControlMessages" and isinstance(data, dict):
                messages = data.get("Messages", {})
                if isinstance(messages, dict):
                    for _, msg in messages.items():
                        if isinstance(msg, dict) and "Message" in msg:
                            race_control.append({
                                "message": msg["Message"],
                                "category": msg.get("Category", ""),
                                "flag": msg.get("Flag", ""),
                            })

            elif cat == "DriverList" and isinstance(data, dict):
                for drv_num, drv_info in data.items():
                    if not isinstance(drv_info, dict):
                        continue
                    if drv_num not in timing:
                        timing[drv_num] = {"driverNumber": drv_num}
                    timing[drv_num]["name"] = drv_info.get("Tla", drv_num)
                    timing[drv_num]["fullName"] = drv_info.get("FullName", "")
                    team = drv_info.get("TeamName", "")
                    timing[drv_num]["team"] = team
                    timing[drv_num]["teamColor"] = f"#{drv_info.get('TeamColour', 'FFFFFF')}"

            elif cat == "CarData.z" and isinstance(data, str) and len(data) > 10:
                try:
                    raw_b64 = data.strip('"')
                    decoded = zlib.decompress(base64.b64decode(raw_b64), -zlib.MAX_WBITS)
                    car_json = json.loads(decoded)
                    for entry_item in car_json.get("Entries", []):
                        entry_ts = entry_item.get("Utc", ts)
                        cars = entry_item.get("Cars", {})
                        for drv_num, car_info in cars.items():
                            ch = car_info.get("Channels", {})
                            snapshot = {
                                "rpm": ch.get("0", 0),
                                "speed": ch.get("2", 0),
                                "gear": ch.get("3", 0),
                                "throttle": min(ch.get("4", 0), 100),
                                "brake": min(ch.get("5", 0), 100),
                                "ts": entry_ts,
                            }
                            car_telemetry[drv_num] = snapshot
                            # Skip junk data: speed=0 + gear=0 with throttle/brake maxed
                            # is garbage from stationary/pit cars, not real telemetry
                            is_junk = (snapshot["speed"] == 0
                                       and snapshot["gear"] == 0
                                       and snapshot["throttle"] >= 90
                                       and snapshot["brake"] >= 90)
                            if not is_junk:
                                if drv_num not in telemetry_history:
                                    telemetry_history[drv_num] = []
                                telemetry_history[drv_num].append(snapshot)
                                if len(telemetry_history[drv_num]) > 200:
                                    telemetry_history[drv_num] = telemetry_history[drv_num][-200:]
                except Exception:
                    pass

            elif cat == "Position.z" and isinstance(data, str) and len(data) > 10:
                try:
                    raw_b64 = data.strip('"')
                    decoded = zlib.decompress(base64.b64decode(raw_b64), -zlib.MAX_WBITS)
                    pos_json = json.loads(decoded)
                    for pos_entry in pos_json.get("Position", []):
                        entries = pos_entry.get("Entries", {})
                        for drv_num, pos_info in entries.items():
                            if isinstance(pos_info, dict):
                                new_x = pos_info.get("X", 0)
                                new_y = pos_info.get("Y", 0)
                                # Filter outlier jumps (noisy GPS)
                                if drv_num in positions:
                                    prev = positions[drv_num]
                                    dx = new_x - prev["x"]
                                    dy = new_y - prev["y"]
                                    dist = (dx * dx + dy * dy) ** 0.5
                                    if dist > 5000:
                                        continue  # skip unrealistic jump
                                positions[drv_num] = {
                                    "x": new_x,
                                    "y": new_y,
                                    "status": pos_info.get("Status", ""),
                                }
                                # Store timestamped position for telemetry-location fusion
                                pos_ts = pos_entry.get("Timestamp", ts)
                                if drv_num not in _live_pos_history:
                                    _live_pos_history[drv_num] = []
                                _live_pos_history[drv_num].append({"x": new_x, "y": new_y, "ts": pos_ts})
                                if len(_live_pos_history[drv_num]) > 2000:
                                    _live_pos_history[drv_num] = _live_pos_history[drv_num][-2000:]
                                # Also store for circuit outline extraction
                                if drv_num not in _position_history:
                                    _position_history[drv_num] = []
                                _position_history[drv_num].append({"x": new_x, "y": new_y})
                                if len(_position_history[drv_num]) > 2000:
                                    _position_history[drv_num] = _position_history[drv_num][-2000:]
                except Exception:
                    pass

        except (json.JSONDecodeError, IndexError, TypeError, KeyError):
            continue

    # Merge car telemetry into timing (smoothed over last 5 samples)
    for drv_num, tel in car_telemetry.items():
        if drv_num in timing:
            # If car is stationary/pit with junk data, zero out throttle+brake
            is_pit_junk = (tel["speed"] == 0 and tel["gear"] == 0
                           and tel["throttle"] >= 90 and tel["brake"] >= 90)
            if is_pit_junk:
                timing[drv_num]["telemetry"] = {
                    "speed": 0, "throttle": 0, "brake": 0, "gear": 0, "rpm": 0,
                }
                continue
            hist = telemetry_history.get(drv_num, [])
            if len(hist) >= 3:
                window = hist[-5:]
                smoothed = {
                    "speed": round(sum(s["speed"] for s in window) / len(window)),
                    "throttle": round(sum(s["throttle"] for s in window) / len(window)),
                    "brake": round(sum(s["brake"] for s in window) / len(window)),
                    "gear": window[-1]["gear"],
                    "rpm": round(sum(s["rpm"] for s in window) / len(window)),
                }
                timing[drv_num]["telemetry"] = smoothed
            else:
                timing[drv_num]["telemetry"] = tel

    # Fallback driver info for 2025/2026 season
    _DRIVER_INFO = {
        "1":  ("NOR", "Lando NORRIS", "McLaren", "#F47600"),
        "3":  ("VER", "Max VERSTAPPEN", "Red Bull Racing", "#4781D7"),
        "5":  ("BOR", "Gabriel BORTOLETO", "Audi", "#F50537"),
        "6":  ("HAD", "Isack HADJAR", "Red Bull Racing", "#4781D7"),
        "10": ("GAS", "Pierre GASLY", "Alpine", "#00A1E8"),
        "11": ("PER", "Sergio PEREZ", "Cadillac", "#909090"),
        "12": ("ANT", "Kimi ANTONELLI", "Mercedes", "#00D7B6"),
        "14": ("ALO", "Fernando ALONSO", "Aston Martin", "#229971"),
        "16": ("LEC", "Charles LECLERC", "Ferrari", "#ED1131"),
        "18": ("STR", "Lance STROLL", "Aston Martin", "#229971"),
        "23": ("ALB", "Alexander ALBON", "Williams", "#1868DB"),
        "27": ("HUL", "Nico HULKENBERG", "Audi", "#F50537"),
        "30": ("LAW", "Liam LAWSON", "Racing Bulls", "#6C98FF"),
        "31": ("OCO", "Esteban OCON", "Haas F1 Team", "#9C9FA2"),
        "41": ("LIN", "Arvid LINDBLAD", "Racing Bulls", "#6C98FF"),
        "43": ("COL", "Franco COLAPINTO", "Alpine", "#00A1E8"),
        "44": ("HAM", "Lewis HAMILTON", "Ferrari", "#ED1131"),
        "55": ("SAI", "Carlos SAINZ", "Williams", "#1868DB"),
        "63": ("RUS", "George RUSSELL", "Mercedes", "#00D7B6"),
        "77": ("BOT", "Valtteri BOTTAS", "Cadillac", "#909090"),
        "81": ("PIA", "Oscar PIASTRI", "McLaren", "#F47600"),
        "87": ("BEA", "Oliver BEARMAN", "Haas F1 Team", "#9C9FA2"),
    }
    for drv_num, t in timing.items():
        if (not t.get("name") or t["name"] == drv_num) and drv_num in _DRIVER_INFO:
            tla, full, team, color = _DRIVER_INFO[drv_num]
            t["name"] = tla
            t["fullName"] = full
            t["team"] = team
            t["teamColor"] = color

    # Sort by position
    timing_list = sorted(
        timing.values(),
        key=lambda x: int(x.get("Position", 99)) if str(x.get("Position", "99")).isdigit() else 99,
    )

    # ── Detect current SC/VSC status from race control messages ──
    sc_active = None  # "SC", "VSC", or None
    sc_history = []   # all SC/VSC events
    for msg in race_control:
        msg_text = msg["message"].upper()
        if "SAFETY CAR" in msg_text and "VIRTUAL" not in msg_text and "IN THIS LAP" not in msg_text:
            if "DEPLOYED" in msg_text or "SAFETY CAR IN" not in msg_text:
                sc_active = "SC"
                sc_history.append({"type": "SC", "message": msg["message"]})
        elif "VIRTUAL SAFETY CAR" in msg_text:
            if "ENDING" not in msg_text:
                sc_active = "VSC"
                sc_history.append({"type": "VSC", "message": msg["message"]})
        elif "GREEN" in msg_text or "SAFETY CAR IN THIS LAP" in msg_text or "VSC ENDING" in msg_text:
            sc_active = None

    # ── Track who pitted during SC/VSC (from InPit flags) ──
    pitted_during_sc = set()
    not_pitted_during_sc = set()
    if sc_active:
        for t in timing_list:
            is_in_pit = t.get("InPit") in (True, "true", "True")
            drv = t.get("name", t.get("driverNumber", ""))
            if is_in_pit:
                pitted_during_sc.add(drv)
            else:
                not_pitted_during_sc.add(drv)

    # ── Enhanced Win Probability Model ──
    # Factors: position, gap, tyre age, compound, SC/VSC status, pit timing
    if len(timing_list) > 1:
        pos_list = []
        gaps = []
        tyre_ages = []
        compounds = []
        in_pits = []

        for t in timing_list:
            pos = int(t.get("Position", 20)) if str(t.get("Position", "20")).isdigit() else 20
            gap_str = str(t.get("GapToLeader", "0"))
            try:
                gap_val = float(gap_str.replace("+", "").replace("LAP", "60").strip() or "0")
            except ValueError:
                gap_val = 30
            tyre_age = int(t.get("tyreAge", 0) or 0)
            compound = (t.get("compound", "") or "").upper()
            is_in_pit = t.get("InPit") in (True, "true", "True")

            pos_list.append(pos)
            gaps.append(gap_val)
            tyre_ages.append(tyre_age)
            compounds.append(compound)
            in_pits.append(is_in_pit)

        max_p = max(pos_list) if pos_list else 20
        max_g = max(gaps) if gaps and max(gaps) > 0 else 1
        max_ta = max(tyre_ages) if tyre_ages and max(tyre_ages) > 0 else 1

        # Compound advantage scoring
        COMPOUND_SCORE = {"SOFT": 0.9, "MEDIUM": 0.7, "HARD": 0.5,
                         "INTERMEDIATE": 0.6, "WET": 0.6}

        scores = []
        for i, (pos, gap, ta, comp, pit) in enumerate(
            zip(pos_list, gaps, tyre_ages, compounds, in_pits)
        ):
            # Position score (higher = better)
            pos_s = (max_p - pos) / max(max_p - 1, 1)

            # Gap score (closer to leader = better)
            gap_s = 1 - gap / max_g

            # Tyre freshness score (fresher = better)
            tyre_s = 1 - ta / max_ta if max_ta > 0 else 0.5

            # Compound score (softer = more pace potential)
            comp_s = COMPOUND_SCORE.get(comp, 0.5)

            if sc_active:
                # During SC/VSC: gaps are compressed, tyre/compound matter MORE
                # Position still matters but gap advantage is almost zero
                s = (pos_s * 0.35 +
                     gap_s * 0.05 +     # gap almost irrelevant under SC
                     tyre_s * 0.30 +     # fresh tyres = huge advantage at restart
                     comp_s * 0.30)      # compound matters at restart

                # Bonus: if you pitted during SC = smart strategy
                drv_name = timing_list[i].get("name", "")
                if drv_name in pitted_during_sc:
                    s += 0.15  # big bonus for free pit stop
            else:
                # Normal racing: weighted factors
                s = (pos_s * 0.35 +
                     gap_s * 0.25 +
                     tyre_s * 0.20 +
                     comp_s * 0.20)

            # Penalty for being in pits right now
            if pit:
                s *= 0.7

            scores.append(s)

        scores = np.array(scores)
        temp = 0.4 if sc_active else 0.5
        exp_s = np.exp((scores - scores.max()) / temp)
        win_pcts = (exp_s / exp_s.sum() * 100).round(1)

        for i, t in enumerate(timing_list):
            t["winPct"] = float(win_pcts[i])

    # ── Strategy Alerts (missed opportunities, smart calls) ──
    alerts = []
    if sc_active:
        # Find drivers who SHOULD pit (old tyres, not pitted yet)
        for t in timing_list:
            drv = t.get("name", t.get("driverNumber", ""))
            tyre_age = int(t.get("tyreAge", 0) or 0)
            is_in_pit = t.get("InPit") in (True, "true", "True")
            pos = int(t.get("Position", 20)) if str(t.get("Position", "20")).isdigit() else 20

            if tyre_age > 15 and not is_in_pit and drv not in pitted_during_sc:
                alerts.append({
                    "type": "MISSED_OPPORTUNITY",
                    "driver": drv,
                    "message": f"{drv} has {tyre_age}-lap old tyres and hasn't pitted under {sc_active} — potential missed free pit stop!",
                    "severity": "high",
                })
            elif drv in pitted_during_sc:
                alerts.append({
                    "type": "SMART_PIT",
                    "driver": drv,
                    "message": f"{drv} pitted under {sc_active} — free pit stop, fresh tyres for restart",
                    "severity": "info",
                })

    # Flag drivers on very old tyres (regardless of SC)
    for t in timing_list:
        tyre_age = int(t.get("tyreAge", 0) or 0)
        compound = (t.get("compound", "") or "").upper()
        drv = t.get("name", t.get("driverNumber", ""))
        # Compound-specific tyre cliff warnings
        cliff_laps = {"SOFT": 20, "MEDIUM": 30, "HARD": 40}.get(compound, 30)
        if tyre_age > cliff_laps:
            alerts.append({
                "type": "TYRE_CLIFF",
                "driver": drv,
                "message": f"{drv} is {tyre_age - cliff_laps} laps past estimated {compound} cliff ({cliff_laps} laps) — expect pace drop",
                "severity": "warning",
            })

    # Store caches for the per-driver endpoint
    global _live_telemetry_history, _live_positions, _live_driver_info_cache
    _live_telemetry_history = telemetry_history
    _live_positions = positions
    _live_driver_info_cache = _DRIVER_INFO

    # Build stint timeline from current timing data
    # Each driver has compound + tyreAge → we can infer current stint
    stint_timeline = {}
    for t in timing_list:
        drv_name = t.get("name", t.get("driverNumber", "?"))
        compound = (t.get("compound", "") or "").upper()
        tyre_age = int(t.get("tyreAge", 0) or 0)
        total_laps = int(t.get("NumberOfLaps", 0) or 0)
        if compound and total_laps > 0:
            # If tyre age < total laps, driver has pitted at least once
            if tyre_age < total_laps and tyre_age > 0:
                # Previous stint(s) = total_laps - tyre_age laps on unknown compound
                stint_timeline[drv_name] = [
                    {"compound": "?", "laps": total_laps - tyre_age},
                    {"compound": compound, "laps": tyre_age},
                ]
            else:
                stint_timeline[drv_name] = [
                    {"compound": compound, "laps": max(tyre_age, total_laps)},
                ]

    # Build gap evolution (top 10 drivers by position)
    top_drivers = [t["driverNumber"] for t in timing_list[:10]]
    gap_evolution = {}
    for drv_num in top_drivers:
        drv_name = timing.get(drv_num, {}).get("name", drv_num)
        if drv_num in gap_history:
            gap_evolution[drv_name] = gap_history[drv_num]

    # Build lap time history for pace analysis
    pace_data = {}
    for drv_num in top_drivers:
        drv_name = timing.get(drv_num, {}).get("name", drv_num)
        if drv_num in lap_times_history:
            pace_data[drv_name] = lap_times_history[drv_num]

    result = {
        "timing": timing_list,
        "weather": weather,
        "raceControl": race_control[-20:],
        "dataPoints": cache["line_count"],
        "scStatus": sc_active,
        "alerts": alerts,
        "positions": positions,
        "gapEvolution": gap_evolution,
        "stintTimeline": stint_timeline,
        "paceData": pace_data,
    }

    # Cache the result for subsequent calls with no new data
    cache["result"] = result
    return result


def _detect_clipping_patterns(history: list[dict]) -> list[dict]:
    """Analyze telemetry history to detect clipping, lift-and-coast, energy saving."""
    patterns = []
    if len(history) < 3:
        return patterns

    # --- Battery clipping ---
    clipping_count = 0
    clipping_samples = 0
    for i in range(1, len(history)):
        prev, cur = history[i - 1], history[i]
        if (cur["throttle"] >= 98 and cur["brake"] == 0 and cur["speed"] > 250):
            clipping_samples += 1
            speed_delta = cur["speed"] - prev["speed"]
            if speed_delta <= 0:
                clipping_count += 1
    if clipping_samples > 0:
        ratio = clipping_count / clipping_samples
        if ratio > 0.3:
            patterns.append({
                "type": "CLIPPING",
                "confidence": round(min(ratio * 1.5, 1.0), 2),
                "description": (
                    f"Battery clipping detected: speed not increasing despite full throttle "
                    f"in {clipping_count}/{clipping_samples} high-speed samples"
                ),
            })

    # --- Lift-and-coast ---
    lift_count = 0
    for i in range(len(history)):
        s = history[i]
        if s["throttle"] < 50 and s["brake"] == 0 and s["speed"] > 200:
            lift_count += 1
    if lift_count >= 2:
        confidence = round(min(lift_count / max(len(history) * 0.3, 1), 1.0), 2)
        patterns.append({
            "type": "LIFT_COAST",
            "confidence": confidence,
            "description": (
                f"Lift-and-coast detected: throttle < 50% with no braking at speed > 200 "
                f"in {lift_count} samples"
            ),
        })

    # --- Energy saving ---
    if len(history) >= 10:
        first_half = history[: len(history) // 2]
        second_half = history[len(history) // 2 :]

        def avg_accel(h):
            accels = []
            for i in range(1, len(h)):
                if h[i]["throttle"] > 80 and h[i]["brake"] == 0:
                    accels.append(h[i]["speed"] - h[i - 1]["speed"])
            return sum(accels) / len(accels) if accels else 0

        a1 = avg_accel(first_half)
        a2 = avg_accel(second_half)
        if a1 > 0 and a2 < a1 * 0.7:
            drop_pct = (a1 - a2) / a1 if a1 != 0 else 0
            patterns.append({
                "type": "ENERGY_SAVING",
                "confidence": round(min(drop_pct, 1.0), 2),
                "description": (
                    f"Energy saving mode: acceleration dropped {drop_pct*100:.0f}% "
                    f"in recent samples vs earlier in stint"
                ),
            })

    return patterns


def _calc_est_ers_usage(history: list[dict]) -> float | None:
    """Estimated ERS usage = time with strong acceleration / time at full throttle.
    Note: this is an estimate from public telemetry, not actual battery/MGU-K data."""
    if len(history) < 3:
        return None
    full_throttle = 0
    strong_accel = 0
    for i in range(1, len(history)):
        if history[i]["throttle"] >= 95:
            full_throttle += 1
            speed_delta = history[i]["speed"] - history[i - 1]["speed"]
            if speed_delta > 2:
                strong_accel += 1
    if full_throttle == 0:
        return None
    return round(strong_accel / full_throttle, 3)


# ── Telemetry-Location Fusion & Zone Analysis ────────────────────────────

def _fuse_telemetry_with_location(drv_num: str) -> list[dict]:
    """Join telemetry samples with nearest GPS position by timestamp.
    Returns list of {speed, throttle, brake, gear, rpm, x, y, ts}."""
    history = _live_telemetry_history.get(drv_num, [])
    pos_hist = _live_pos_history.get(drv_num, [])
    if not history or not pos_hist:
        return []

    # Build position index sorted by timestamp for binary search
    pos_sorted = sorted(pos_hist, key=lambda p: p.get("ts", ""))
    pos_times = [p.get("ts", "") for p in pos_sorted]

    import bisect
    fused = []
    for tel in history:
        tel_ts = tel.get("ts", "")
        if not tel_ts:
            continue
        # Find nearest position by timestamp
        idx = bisect.bisect_left(pos_times, tel_ts)
        # Check closest of idx-1 and idx
        best_pos = None
        if idx < len(pos_sorted):
            best_pos = pos_sorted[idx]
        if idx > 0:
            prev = pos_sorted[idx - 1]
            if best_pos is None:
                best_pos = prev
            else:
                # Pick whichever timestamp is closer
                if abs(ord(prev["ts"][-1]) - ord(tel_ts[-1])) < abs(ord(best_pos["ts"][-1]) - ord(tel_ts[-1])):
                    best_pos = prev
        if best_pos:
            fused.append({
                "speed": tel["speed"],
                "throttle": tel["throttle"],
                "brake": tel["brake"],
                "gear": tel["gear"],
                "rpm": tel["rpm"],
                "x": best_pos["x"],
                "y": best_pos["y"],
                "ts": tel_ts,
            })
    return fused


def _segment_track_zones(circuit_outline: list[dict]) -> list[dict]:
    """Divide circuit into zones (straights vs corners) based on curvature.
    Returns list of {type: 'straight'|'corner', start_idx, end_idx, x, y}."""
    import math
    if len(circuit_outline) < 10:
        return []

    pts = circuit_outline
    zones = []
    # Compute heading change between consecutive segments
    headings = []
    for i in range(1, len(pts)):
        dx = pts[i]["x"] - pts[i-1]["x"]
        dy = pts[i]["y"] - pts[i-1]["y"]
        headings.append(math.atan2(dy, dx))

    # Compute curvature (heading change rate)
    curvatures = []
    for i in range(1, len(headings)):
        delta = headings[i] - headings[i-1]
        # Normalize to [-pi, pi]
        while delta > math.pi: delta -= 2 * math.pi
        while delta < -math.pi: delta += 2 * math.pi
        curvatures.append(abs(delta))

    # Smooth curvatures to avoid micro-zone flickering (rolling avg window=5)
    smooth_window = min(5, len(curvatures))
    smoothed_curv = []
    for i in range(len(curvatures)):
        lo = max(0, i - smooth_window // 2)
        hi = min(len(curvatures), i + smooth_window // 2 + 1)
        smoothed_curv.append(sum(curvatures[lo:hi]) / (hi - lo))

    # Classify: low curvature = straight, high = corner
    threshold = 0.25  # radians — higher = fewer zones
    min_zone_len = max(3, len(pts) // 50)  # minimum points per zone to avoid micro-zones
    zone_start = 0
    is_straight = smoothed_curv[0] < threshold if smoothed_curv else True

    for i in range(1, len(smoothed_curv)):
        cur_straight = smoothed_curv[i] < threshold
        if cur_straight != is_straight and (i - zone_start) >= min_zone_len:
            mid_idx = (zone_start + i) // 2 + 1
            zones.append({
                "type": "straight" if is_straight else "corner",
                "start_idx": zone_start,
                "end_idx": i,
                "x": pts[min(mid_idx, len(pts) - 1)]["x"],
                "y": pts[min(mid_idx, len(pts) - 1)]["y"],
            })
            zone_start = i
            is_straight = cur_straight

    # Final zone
    if zone_start < len(smoothed_curv):
        mid_idx = min((zone_start + len(smoothed_curv)) // 2 + 1, len(pts) - 1)
        zones.append({
            "type": "straight" if is_straight else "corner",
            "start_idx": zone_start,
            "end_idx": len(smoothed_curv),
            "x": pts[mid_idx]["x"],
            "y": pts[mid_idx]["y"],
        })

    # Number the corners and straights
    corner_num = 0
    straight_num = 0
    for z in zones:
        if z["type"] == "corner":
            corner_num += 1
            z["label"] = f"Turn {corner_num}"
        else:
            straight_num += 1
            z["label"] = f"Straight {straight_num}"

    return zones


def _analyze_per_zone(fused_data: list[dict], zones: list[dict], circuit_outline: list[dict]) -> list[dict]:
    """Analyze telemetry per track zone — detect clipping/ERS per zone."""
    import math
    if not fused_data or not zones or not circuit_outline:
        return []

    # For each fused sample, find which zone it's closest to
    zone_samples: dict[int, list] = {i: [] for i in range(len(zones))}

    for sample in fused_data:
        sx, sy = sample["x"], sample["y"]
        # Find nearest circuit point
        min_dist = float("inf")
        nearest_idx = 0
        for j, cp in enumerate(circuit_outline):
            dx = sx - cp["x"]
            dy = sy - cp["y"]
            d = dx * dx + dy * dy
            if d < min_dist:
                min_dist = d
                nearest_idx = j

        # Map circuit point index to zone
        for zi, z in enumerate(zones):
            if z["start_idx"] <= nearest_idx <= z["end_idx"]:
                zone_samples[zi].append(sample)
                break

    # Analyze each zone
    results = []
    for zi, z in enumerate(zones):
        samples = zone_samples.get(zi, [])
        if not samples:
            results.append({**z, "samples": 0})
            continue

        speeds = [s["speed"] for s in samples if s["speed"] > 0]
        throttles = [s["throttle"] for s in samples]

        peak_speed = max(speeds) if speeds else 0
        avg_speed = sum(speeds) / len(speeds) if speeds else 0
        avg_throttle = sum(throttles) / len(throttles) if throttles else 0

        # Clipping in this zone
        clip_count = 0
        clip_total = 0
        for i in range(1, len(samples)):
            cur, prev = samples[i], samples[i-1]
            if cur["throttle"] >= 98 and cur["brake"] == 0 and cur["speed"] > 200:
                clip_total += 1
                if cur["speed"] <= prev["speed"]:
                    clip_count += 1

        clipping_pct = (clip_count / clip_total * 100) if clip_total > 0 else 0

        # Lift-coast in this zone
        lift_count = sum(1 for s in samples if s["throttle"] < 50 and s["brake"] == 0 and s["speed"] > 150)

        results.append({
            **z,
            "samples": len(samples),
            "peakSpeed": peak_speed,
            "avgSpeed": round(avg_speed),
            "avgThrottle": round(avg_throttle),
            "clippingPct": round(clipping_pct, 1),
            "liftCoastSamples": lift_count,
        })

    return results


@app.get("/api/live/driver/{driver_number}/zones")
def get_driver_zone_analysis(driver_number: str):
    """Per-zone telemetry analysis for a driver — fuses telemetry with GPS."""
    fused = _fuse_telemetry_with_location(driver_number)
    outline = _circuit_outline_cache.get("outline", [])
    zones = _segment_track_zones(outline)
    analysis = _analyze_per_zone(fused, zones, outline)

    driver_info = _live_driver_info_cache.get(driver_number)
    drv_name = driver_number
    if driver_info:
        drv_name = driver_info[0]

    return {
        "driver": drv_name,
        "driverNumber": driver_number,
        "zones": analysis,
        "fusedSamples": len(fused),
        "totalZones": len(zones),
    }


# ── Session Analysis Log ──────────────────────────────────────────────────
# Records what our dashboard detected during the session — not raw data,
# but the analysis results: flags, patterns, ERS estimates, key moments.

_SESSION_LOG_FILE = Path(__file__).parent.parent / "session_log.jsonl"
_session_log_seen: set[str] = set()  # dedup key: "driverNum:patternType:timestamp"


def _log_session_event(event: dict):
    """Append an analysis event to the session log (JSONL format)."""
    from datetime import datetime, timezone
    event["logged_at"] = datetime.now(timezone.utc).isoformat()
    with open(_SESSION_LOG_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")


@app.get("/api/live/driver/{driver_number}")
def get_live_driver_logged(driver_number: str):
    """Return detailed telemetry + log any new pattern detections."""
    history = _live_telemetry_history.get(driver_number, [])
    position = _live_positions.get(driver_number)
    patterns = _detect_clipping_patterns(history)
    est_ers_usage = _calc_est_ers_usage(history)

    driver_info = _live_driver_info_cache.get(driver_number)
    driver_meta = None
    driver_name = driver_number
    if driver_info:
        tla, full_name, team, color = driver_info
        driver_name = tla
        driver_meta = {
            "abbreviation": tla,
            "fullName": full_name,
            "team": team,
            "teamColor": color,
        }

    # Log new pattern detections
    for p in patterns:
        dedup_key = f"{driver_number}:{p['type']}"
        if dedup_key not in _session_log_seen:
            _session_log_seen.add(dedup_key)
            _log_session_event({
                "type": "pattern_detected",
                "driver": driver_name,
                "driverNumber": driver_number,
                "team": driver_meta["team"] if driver_meta else "",
                "pattern": p["type"],
                "confidence": p["confidence"],
                "description": p["description"],
            })

    # Log ERS usage snapshots periodically (only when it changes significantly)
    if est_ers_usage is not None:
        ers_key = f"{driver_number}:ers:{round(est_ers_usage, 1)}"
        if ers_key not in _session_log_seen:
            _session_log_seen.add(ers_key)
            _log_session_event({
                "type": "ers_estimate",
                "driver": driver_name,
                "driverNumber": driver_number,
                "estErsUsage": est_ers_usage,
            })

    # Log peak speed
    if history:
        max_speed = max(s["speed"] for s in history)
        speed_key = f"{driver_number}:peak_speed:{max_speed // 10}"
        if speed_key not in _session_log_seen:
            _session_log_seen.add(speed_key)
            if max_speed > 250:
                _log_session_event({
                    "type": "peak_speed",
                    "driver": driver_name,
                    "driverNumber": driver_number,
                    "speed": max_speed,
                })

    return {
        "driverNumber": driver_number,
        "driver": driver_meta,
        "telemetryTrace": history,
        "position": position,
        "patterns": patterns,
        "estErsUsage": est_ers_usage,
    }


@app.get("/api/live/session-log")
def get_session_log():
    """Return the session analysis log — everything our dashboard detected."""
    if not _SESSION_LOG_FILE.exists():
        return {"events": [], "summary": "No session log yet."}

    events = []
    for line in _SESSION_LOG_FILE.read_text().strip().split("\n"):
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    # Build summary
    patterns_by_driver = {}
    peak_speeds = {}
    ers_estimates = {}
    for e in events:
        drv = e.get("driver", "?")
        if e["type"] == "pattern_detected":
            patterns_by_driver.setdefault(drv, []).append(e["pattern"])
        elif e["type"] == "peak_speed":
            peak_speeds[drv] = max(peak_speeds.get(drv, 0), e.get("speed", 0))
        elif e["type"] == "ers_estimate":
            ers_estimates[drv] = e.get("estErsUsage", 0)

    summary_lines = []
    if patterns_by_driver:
        summary_lines.append("=== Pattern Detections ===")
        for drv, pats in sorted(patterns_by_driver.items()):
            summary_lines.append(f"  {drv}: {', '.join(pats)}")
    if peak_speeds:
        summary_lines.append("=== Peak Speeds ===")
        for drv, spd in sorted(peak_speeds.items(), key=lambda x: -x[1]):
            summary_lines.append(f"  {drv}: {spd} km/h")
    if ers_estimates:
        summary_lines.append("=== Est. ERS Usage ===")
        for drv, ers in sorted(ers_estimates.items(), key=lambda x: -x[1]):
            summary_lines.append(f"  {drv}: {ers*100:.0f}%")

    return {
        "events": events,
        "count": len(events),
        "summary": "\n".join(summary_lines) if summary_lines else "No detections yet.",
    }


@app.post("/api/live/session-log/clear")
def clear_session_log():
    """Clear the session log for a fresh session."""
    global _session_log_seen
    _session_log_seen = set()
    if _SESSION_LOG_FILE.exists():
        _SESSION_LOG_FILE.unlink()
    return {"status": "cleared"}


# ── Circuit Outline from OpenF1 ───────────────────────────────────────────

_circuit_outline_cache: dict[str, list] = {}


def _filter_outliers(points: list[dict], max_jump: float = 1500) -> list[dict]:
    """Remove noisy GPS points — drop any point that jumps too far from the previous one.
    Starts from a stable region (finds 3 consecutive close points first)."""
    if len(points) < 5:
        return points
    # Find a stable starting point (3 consecutive points all within max_jump)
    start = 0
    for i in range(len(points) - 2):
        d1 = ((points[i+1]["x"] - points[i]["x"])**2 + (points[i+1]["y"] - points[i]["y"])**2) ** 0.5
        d2 = ((points[i+2]["x"] - points[i+1]["x"])**2 + (points[i+2]["y"] - points[i+1]["y"])**2) ** 0.5
        if d1 < max_jump and d2 < max_jump:
            start = i
            break
    clean = [points[start]]
    for i in range(start + 1, len(points)):
        dx = points[i]["x"] - clean[-1]["x"]
        dy = points[i]["y"] - clean[-1]["y"]
        dist = (dx * dx + dy * dy) ** 0.5
        if dist < max_jump:
            clean.append(points[i])
    return clean


def _smooth_points(points: list[dict], window: int = 3) -> list[dict]:
    """Apply median smoothing to x,y coordinates."""
    if len(points) < window:
        return points
    smoothed = []
    half = window // 2
    for i in range(len(points)):
        lo = max(0, i - half)
        hi = min(len(points), i + half + 1)
        xs = sorted(p["x"] for p in points[lo:hi])
        ys = sorted(p["y"] for p in points[lo:hi])
        smoothed.append({"x": xs[len(xs) // 2], "y": ys[len(ys) // 2]})
    return smoothed


def _extract_circuit_from_positions(position_history: dict[str, list]) -> list[dict]:
    """Extract circuit outline from recorded Position.z data.
    Uses sequential GPS trace from a single driver — preserves driving order."""
    import math

    # Find driver with most data
    best_drv = max(position_history, key=lambda d: len(position_history[d]), default=None)
    if best_drv is None or len(position_history[best_drv]) < 30:
        return []

    points = [{"x": p["x"], "y": p["y"]} for p in position_history[best_drv]]

    # Deduplicate consecutive identical points
    deduped = [points[0]]
    for p in points[1:]:
        if p["x"] != deduped[-1]["x"] or p["y"] != deduped[-1]["y"]:
            deduped.append(p)
    points = deduped
    if len(points) < 30:
        return []

    points = _filter_outliers(points, max_jump=1500)
    if len(points) < 30:
        return []

    # Try crossing detection for a complete lap
    ref_idx = len(points) // 4
    ref_x, ref_y = points[ref_idx]["x"], points[ref_idx]["y"]
    crossings = [ref_idx]
    for i in range(ref_idx + 30, len(points)):
        dx = points[i]["x"] - ref_x
        dy = points[i]["y"] - ref_y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 500 and i - crossings[-1] > 30:
            crossings.append(i)

    if len(crossings) >= 2:
        max_len = 0
        best_start, best_end = crossings[0], crossings[1]
        for j in range(len(crossings) - 1):
            seg_len = crossings[j + 1] - crossings[j]
            if seg_len > max_len:
                max_len = seg_len
                best_start = crossings[j]
                best_end = crossings[j + 1]
        points = points[best_start:best_end + 1]

    points = _filter_outliers(points, max_jump=800)

    # Downsample to ~300 points
    step = max(1, len(points) // 300)
    outline = [{"x": p["x"], "y": p["y"]} for p in points[::step]]

    return outline


# Persistent position history for circuit extraction (separate from live positions)
_position_history: dict[str, list] = {}


@app.get("/api/live/circuit")
def get_circuit_outline():
    """Fetch circuit outline from OpenF1 location data, with fallback to recorded Position.z."""
    if _circuit_outline_cache.get("outline"):
        return {"outline": _circuit_outline_cache["outline"]}

    # First try OpenF1 API
    import logging
    try:
        points = []
        for drv in ["16", "1", "44", "63"]:
            try:
                resp = httpx.get(
                    f"https://api.openf1.org/v1/location?session_key=latest&driver_number={drv}",
                    timeout=5,
                )
                if resp.status_code == 200:
                    pts = resp.json()
                    if isinstance(pts, list) and len(pts) > 300:
                        points = pts
                        print(f"[CIRCUIT] OpenF1: got {len(pts)} points from driver #{drv}", flush=True)
                        break
                    else:
                        print(f"[CIRCUIT] OpenF1: driver #{drv} returned non-list or too few points", flush=True)
            except Exception as e:
                print(f"[CIRCUIT] OpenF1: driver #{drv} request failed: {e}", flush=True)
                break  # don't try more drivers if API is locked

        if len(points) >= 300:
            points = [p for p in points if p.get("x") is not None and p.get("y") is not None]

            deduped = [points[0]]
            for p in points[1:]:
                if p["x"] != deduped[-1]["x"] or p["y"] != deduped[-1]["y"]:
                    deduped.append(p)
            points = deduped
            points = _filter_outliers(points, max_jump=1500)

            if len(points) >= 200:
                ref_idx = len(points) // 3
                ref_x, ref_y = points[ref_idx]["x"], points[ref_idx]["y"]
                close_threshold = 500
                crossings = [ref_idx]
                for i in range(ref_idx + 200, len(points)):
                    dx = points[i]["x"] - ref_x
                    dy = points[i]["y"] - ref_y
                    dist = (dx * dx + dy * dy) ** 0.5
                    if dist < close_threshold and i - crossings[-1] > 150:
                        crossings.append(i)

                best_start, best_end = ref_idx, min(ref_idx + 400, len(points) - 1)
                if len(crossings) >= 2:
                    max_len = 0
                    for j in range(len(crossings) - 1):
                        seg_len = crossings[j + 1] - crossings[j]
                        if seg_len > max_len and seg_len > 200:
                            max_len = seg_len
                            best_start = crossings[j]
                            best_end = crossings[j + 1]

                lap_points = points[best_start:best_end + 1]
                lap_points = _filter_outliers(lap_points, max_jump=800)
                step = max(1, len(lap_points) // 300)
                outline = [{"x": p["x"], "y": p["y"]} for p in lap_points[::step]]
                _circuit_outline_cache["outline"] = outline
                return {"outline": outline}
    except Exception:
        pass

    # Fallback: extract circuit from recorded Position.z in the live data file
    import logging
    print(f"[CIRCUIT] OpenF1 API unavailable, extracting circuit from recorded Position.z data", flush=True)
    try:
        f = _get_live_file()
        if f.exists():
            import base64, zlib
            import ast
            pos_history: dict[str, list] = {}
            for line in f.read_text().strip().split("\n"):
                try:
                    if not line.startswith("["):
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        entry = ast.literal_eval(line)
                    cat = entry[0] if len(entry) > 0 else ""
                    if cat != "Position.z":
                        continue
                    raw_data = entry[1] if len(entry) > 1 else ""
                    if isinstance(raw_data, str) and len(raw_data) > 10:
                        raw_b64 = raw_data.strip('"')
                        decoded = zlib.decompress(base64.b64decode(raw_b64), -zlib.MAX_WBITS)
                        pos_json = json.loads(decoded)
                        for pos_entry in pos_json.get("Position", []):
                            entries = pos_entry.get("Entries", {})
                            for drv_num, pos_info in entries.items():
                                if isinstance(pos_info, dict):
                                    x = pos_info.get("X", 0)
                                    y = pos_info.get("Y", 0)
                                    if drv_num not in pos_history:
                                        pos_history[drv_num] = []
                                    pos_history[drv_num].append({"x": x, "y": y})
                except Exception:
                    continue

            print(f"[CIRCUIT] Extracted position history for {len(pos_history)} drivers", flush=True)
            for drv, pts in sorted(pos_history.items(), key=lambda x: -len(x[1]))[:3]:
                logging.info(f"  Driver #{drv}: {len(pts)} points")

            if pos_history:
                outline = _extract_circuit_from_positions(pos_history)
                logging.info(f"Circuit outline from Position.z: {len(outline)} points")
                if outline:
                    _circuit_outline_cache["outline"] = outline
                    return {"outline": outline}
    except Exception as e:
        print(f"[CIRCUIT] Fallback error: {e}", flush=True)

    return {"outline": []}


# ── GP Comparison ─────────────────────────────────────────────────────────

_compare_cache: dict[tuple, object] = {}
_last_compare_result: dict | None = None  # Store last comparison for chat context


def _load_compare_session(year: int, gp: str, session_type: str = "R"):
    """Load a session for comparison, with caching."""
    key = (year, gp, session_type)
    if key in _compare_cache:
        return _compare_cache[key]
    sess = fastf1.get_session(year, gp, session_type)
    sess.load()
    _compare_cache[key] = sess
    return sess


class CompareRequest(BaseModel):
    yearA: int
    gpA: str
    yearB: int
    gpB: str
    driverA: str
    driverB: str
    sessionType: str = "R"


@app.post("/api/compare")
def compare_gps(req: CompareRequest):
    """Compare two GP sessions — loads in parallel, returns overlaid telemetry."""
    # Load both sessions in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        futA = executor.submit(_load_compare_session, req.yearA, req.gpA, req.sessionType)
        futB = executor.submit(_load_compare_session, req.yearB, req.gpB, req.sessionType)
        try:
            sessA = futA.result(timeout=120)
            sessB = futB.result(timeout=120)
        except Exception as e:
            raise HTTPException(500, f"Failed to load sessions: {str(e)}")

    def _get_driver_telemetry(sess, driver_code):
        """Extract fastest lap telemetry for a driver."""
        laps = sess.laps
        results = sess.results
        dl = laps[laps["Driver"] == driver_code]
        if dl.empty:
            # Try matching by partial name
            for _, r in results.iterrows():
                if driver_code.upper() in str(r.get("Abbreviation", "")).upper():
                    dl = laps[laps["Driver"] == r["Abbreviation"]]
                    driver_code = r["Abbreviation"]
                    break
        if dl.empty:
            return None

        quick = dl.pick_quicklaps()
        if quick.empty:
            quick = dl
        fastest = quick.pick_fastest()
        if fastest is None:
            return None

        tel = fastest.get_telemetry()
        if tel is None or tel.empty:
            return None

        team = results[results["Abbreviation"] == driver_code]["TeamName"].values
        team_name = team[0] if len(team) > 0 else "Unknown"
        color = TEAM_COLORS.get(team_name, "#FFFFFF")

        lap_time = fastest["LapTime"]
        lap_time_str = str(lap_time) if pd.notna(lap_time) else None
        lap_time_s = lap_time.total_seconds() if pd.notna(lap_time) else None

        # Position info
        pos = None
        if not results.empty:
            drv_result = results[results["Abbreviation"] == driver_code]
            if not drv_result.empty and pd.notna(drv_result.iloc[0]["Position"]):
                pos = int(drv_result.iloc[0]["Position"])

        return {
            "driver": driver_code,
            "team": team_name,
            "color": color,
            "headshot": _get_headshot(driver_code),
            "lapNumber": int(fastest["LapNumber"]),
            "lapTime": lap_time_str,
            "lapTimeSeconds": lap_time_s,
            "position": pos,
            "distance": tel["Distance"].values,
            "speed": tel["Speed"].values,
            "throttle": tel["Throttle"].values,
            "brake": tel["Brake"].values.astype(float),
            "gear": tel["nGear"].values if "nGear" in tel.columns else None,
            "x": tel["X"].values if "X" in tel.columns else None,
            "y": tel["Y"].values if "Y" in tel.columns else None,
        }

    telA = _get_driver_telemetry(sessA, req.driverA)
    telB = _get_driver_telemetry(sessB, req.driverB)

    if telA is None:
        raise HTTPException(404, f"No telemetry for {req.driverA} in {req.yearA} {req.gpA}")
    if telB is None:
        raise HTTPException(404, f"No telemetry for {req.driverB} in {req.yearB} {req.gpB}")

    # Resample B to A's distance grid for direct comparison
    dist_a = telA["distance"]
    dist_b = telB["distance"]
    speed_b_resampled = np.interp(dist_a, dist_b, telB["speed"])
    throttle_b_resampled = np.interp(dist_a, dist_b, telB["throttle"])
    brake_b_resampled = np.interp(dist_a, dist_b, telB["brake"])

    # Compute delta time: cumulative time difference based on speed
    # dt = ds / v → sum up small time increments
    ds = np.diff(dist_a, prepend=dist_a[0])
    speed_a = telA["speed"]
    speed_b_on_a = speed_b_resampled

    # Avoid division by zero
    safe_a = np.where(speed_a > 5, speed_a / 3.6, 1e6)  # km/h → m/s
    safe_b = np.where(speed_b_on_a > 5, speed_b_on_a / 3.6, 1e6)

    dt_a = ds / safe_a
    dt_b = ds / safe_b
    delta_time = np.cumsum(dt_b - dt_a)  # positive = A is faster

    # Sector comparison (divide into 20 mini-sectors)
    n_sectors = 20
    total_dist = float(dist_a[-1] - dist_a[0]) if len(dist_a) > 1 else 1
    sector_size = total_dist / n_sectors
    sectors = []
    for s_idx in range(n_sectors):
        s_start = dist_a[0] + s_idx * sector_size
        s_end = s_start + sector_size
        mask = (dist_a >= s_start) & (dist_a < s_end)
        if mask.any():
            sectors.append({
                "sector": s_idx + 1,
                "distance": round(float(s_start), 0),
                "speedA": round(float(speed_a[mask].mean()), 1),
                "speedB": round(float(speed_b_on_a[mask].mean()), 1),
                "maxSpeedA": round(float(speed_a[mask].max()), 1),
                "maxSpeedB": round(float(speed_b_on_a[mask].max()), 1),
                "deltaTime": round(float(delta_time[mask][-1] - (delta_time[mask][0] if mask.any() else 0)), 4),
                "advantage": "A" if speed_a[mask].mean() > speed_b_on_a[mask].mean() else "B",
            })

    # Detect corners (from A's telemetry)
    corners = []
    min_dist_between = 150
    last_corner_dist = -999
    for i in range(5, len(speed_a) - 5):
        if speed_a[i] < speed_a[i-3] and speed_a[i] < speed_a[i+3] and speed_a[i] < 280:
            if dist_a[i] - last_corner_dist > min_dist_between:
                corners.append({
                    "number": len(corners) + 1,
                    "distance": float(dist_a[i]),
                    "speedA": float(speed_a[i]),
                    "speedB": float(speed_b_on_a[i]),
                    "x": float(telA["x"][i]) if telA["x"] is not None else None,
                    "y": float(telA["y"][i]) if telA["y"] is not None else None,
                })
                last_corner_dist = dist_a[i]

    # Summary stats
    summary = {
        "lapTimeDelta": round(telA["lapTimeSeconds"] - telB["lapTimeSeconds"], 3) if telA["lapTimeSeconds"] and telB["lapTimeSeconds"] else None,
        "maxSpeedA": round(float(speed_a.max()), 1),
        "maxSpeedB": round(float(telB["speed"].max()), 1),
        "avgSpeedA": round(float(speed_a.mean()), 1),
        "avgSpeedB": round(float(telB["speed"].mean()), 1),
        "sectorsWonA": sum(1 for s in sectors if s["advantage"] == "A"),
        "sectorsWonB": sum(1 for s in sectors if s["advantage"] == "B"),
    }

    # Save comparison context for chat
    global _last_compare_result
    _last_compare_result = {
        "sessionA": {"year": req.yearA, "gp": req.gpA, "event": sessA.event["EventName"],
                     "driver": telA["driver"], "team": telA["team"], "position": telA["position"],
                     "lapTime": telA["lapTime"], "lapNumber": telA["lapNumber"]},
        "sessionB": {"year": req.yearB, "gp": req.gpB, "event": sessB.event["EventName"],
                     "driver": telB["driver"], "team": telB["team"], "position": telB["position"],
                     "lapTime": telB["lapTime"], "lapNumber": telB["lapNumber"]},
        "summary": summary,
        "sectors": sectors,
        "corners": corners,
    }

    step = 2
    return _sanitize({
        "sessionA": {
            "year": req.yearA, "gp": req.gpA, "event": sessA.event["EventName"],
            "driver": telA["driver"], "team": telA["team"], "color": telA["color"],
            "headshot": telA["headshot"], "position": telA["position"],
            "lapNumber": telA["lapNumber"], "lapTime": telA["lapTime"],
        },
        "sessionB": {
            "year": req.yearB, "gp": req.gpB, "event": sessB.event["EventName"],
            "driver": telB["driver"], "team": telB["team"], "color": telB["color"],
            "headshot": telB["headshot"], "position": telB["position"],
            "lapNumber": telB["lapNumber"], "lapTime": telB["lapTime"],
        },
        "distance": dist_a[::step].tolist(),
        "speedA": speed_a[::step].tolist(),
        "speedB": speed_b_resampled[::step].tolist(),
        "throttleA": telA["throttle"][::step].tolist(),
        "throttleB": throttle_b_resampled[::step].tolist(),
        "brakeA": telA["brake"][::step].tolist(),
        "brakeB": brake_b_resampled[::step].tolist(),
        "gearA": telA["gear"][::step].tolist() if telA["gear"] is not None else None,
        "gearB": np.interp(dist_a, dist_b, telB["gear"]).astype(int)[::step].tolist() if telB["gear"] is not None else None,
        "deltaTime": delta_time[::step].tolist(),
        "trackX": telA["x"][::step].tolist() if telA["x"] is not None else None,
        "trackY": telA["y"][::step].tolist() if telA["y"] is not None else None,
        "sectors": sectors,
        "corners": corners,
        "summary": summary,
    })


@app.get("/api/compare/drivers")
def compare_drivers(year: int = Query(...), gp: str = Query(...), session_type: str = Query("R")):
    """Get list of drivers for a specific GP session (for the compare selector)."""
    try:
        sess = _load_compare_session(year, gp, session_type)
    except Exception as e:
        raise HTTPException(500, f"Failed to load session: {str(e)}")

    results = sess.results
    drivers = []
    for _, r in results.sort_values("Position").iterrows():
        code = r["Abbreviation"]
        drivers.append({
            "code": code,
            "name": r.get("FullName", code),
            "team": r["TeamName"],
            "color": TEAM_COLORS.get(r["TeamName"], "#FFFFFF"),
            "position": int(r["Position"]) if pd.notna(r["Position"]) else None,
            "headshot": _get_headshot(code),
        })
    return {"drivers": drivers}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
