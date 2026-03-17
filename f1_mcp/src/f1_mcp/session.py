"""FastF1 session management and structured data extraction.

Handles session loading, caching, and provides clean data-extraction methods
that return JSON-friendly dicts/lists. The MCP tools call these methods —
they never touch FastF1 directly.

Usage:
    mgr = SessionManager()
    mgr.load(2024, "Bahrain", "R")
    mgr.race_result()     # → list[dict]
    mgr.lap_times("VER")  # → list[dict]
"""

from __future__ import annotations

import warnings
from pathlib import Path

import fastf1
import numpy as np
import pandas as pd

from f1_mcp.normalize import resolve_driver, resolve_race, resolve_session_type

warnings.filterwarnings("ignore")


class SessionManager:
    """Manages a single loaded FastF1 session with structured data access."""

    def __init__(self, cache_dir: str | Path | None = None):
        self._session = None
        self._session_key: tuple | None = None
        cache = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "f1_mcp"
        cache.mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(str(cache))

    # ── Session lifecycle ────────────────────────────────────────────────

    @property
    def is_loaded(self) -> bool:
        return self._session is not None

    @property
    def session(self):
        if self._session is None:
            raise RuntimeError("No session loaded. Call load_session first.")
        return self._session

    def attach(self, session) -> None:
        """Attach a pre-loaded FastF1 session (avoids re-loading).

        Use this when integrating into an app that already manages sessions,
        e.g. the F1 dashboard backend.
        """
        self._session = session
        self._session_key = ("attached",)

    def status(self) -> dict:
        if not self.is_loaded:
            return {"loaded": False}
        s = self.session
        return {
            "loaded": True,
            "year": int(s.event.year),
            "event": s.event["EventName"],
            "session_type": s.name,
        }

    def load(self, year: int, race: str, session_type: str = "R") -> dict:
        """Load a session. Race and session_type are normalized automatically."""
        if year < 2018:
            raise ValueError(
                f"FastF1 supports 2018 onwards (got {year}). "
                "Try a more recent season."
            )

        resolved_race = resolve_race(race, year) or race
        resolved_type = resolve_session_type(session_type)

        key = (year, resolved_race, resolved_type)
        if self._session_key == key and self._session is not None:
            return {
                "status": "already_loaded",
                **self.status(),
            }

        try:
            sess = fastf1.get_session(year, resolved_race, resolved_type)
            sess.load()
        except Exception as e:
            raise ValueError(
                f"Failed to load {year} {resolved_race} ({resolved_type}): {e}. "
                f"Check the race name and year are correct."
            ) from e

        self._session = sess
        self._session_key = key

        return {
            "status": "loaded",
            "year": int(sess.event.year),
            "event": sess.event["EventName"],
            "session_type": sess.name,
        }

    # ── Helpers ──────────────────────────────────────────────────────────

    def _resolve_driver(self, query: str) -> str:
        """Resolve a fuzzy driver query to a 3-letter code, or raise."""
        code = resolve_driver(query, session=self._session)
        if code is None:
            available = self._driver_codes()
            raise ValueError(
                f"Could not resolve driver '{query}'. "
                f"Available: {', '.join(available)}"
            )
        return code

    def _driver_codes(self) -> list[str]:
        return self.session.results["Abbreviation"].tolist()

    def _clean(self, val):
        """Make a value JSON-safe."""
        if val is None or val is pd.NaT:
            return None
        if isinstance(val, pd.Timedelta):
            if pd.isna(val):
                return None
            return round(val.total_seconds(), 3)
        if isinstance(val, (np.floating,)):
            v = float(val)
            return None if (np.isnan(v) or np.isinf(v)) else round(v, 3)
        if isinstance(val, (np.integer,)):
            return int(val)
        if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
            return None
        return val

    def _row_dict(self, row, keys: list[str]) -> dict:
        """Extract named fields from a pandas row, cleaning each value."""
        return {k: self._clean(row.get(k)) for k in keys if k in row.index}

    # ── Data extraction methods ──────────────────────────────────────────

    def season_calendar(self, year: int) -> list[dict]:
        """Get the F1 calendar for a year."""
        if year < 2018:
            raise ValueError(f"FastF1 supports 2018 onwards (got {year}).")
        try:
            schedule = fastf1.get_event_schedule(year)
        except Exception as e:
            raise ValueError(f"Could not fetch {year} calendar: {e}") from e
        events = schedule[schedule["EventFormat"] != "testing"]
        out = []
        for _, row in events.iterrows():
            out.append({
                "round": int(row.get("RoundNumber", 0)),
                "name": row.get("EventName", ""),
                "country": row.get("Country", ""),
                "location": row.get("Location", ""),
                "date": str(row.get("EventDate", "")),
                "format": row.get("EventFormat", ""),
            })
        return out

    def drivers(self) -> list[dict]:
        """List drivers in the session with codes, names, teams."""
        results = self.session.results
        out = []
        for _, r in results.sort_values("Position").iterrows():
            out.append({
                "code": r["Abbreviation"],
                "number": self._clean(r.get("DriverNumber")),
                "full_name": r.get("FullName", r["Abbreviation"]),
                "first_name": r.get("FirstName", ""),
                "last_name": r.get("LastName", ""),
                "team": r.get("TeamName", ""),
                "position": self._clean(r.get("Position")),
            })
        return out

    def race_result(self) -> list[dict]:
        """Full race classification."""
        s = self.session
        results = s.results.sort_values("Position")
        out = []
        for _, r in results.iterrows():
            out.append({
                "position": self._clean(r.get("Position")),
                "code": r["Abbreviation"],
                "full_name": r.get("FullName", r["Abbreviation"]),
                "team": r.get("TeamName", ""),
                "grid_position": self._clean(r.get("GridPosition")),
                "status": r.get("Status", ""),
                "points": self._clean(r.get("Points")),
                "time": self._clean(r.get("Time")),
            })
        return out

    def qualifying_result(self) -> list[dict]:
        """Qualifying results with Q1/Q2/Q3 times."""
        s = self.session
        results = s.results.sort_values("Position")
        out = []
        for _, r in results.iterrows():
            entry = {
                "position": self._clean(r.get("Position")),
                "code": r["Abbreviation"],
                "full_name": r.get("FullName", r["Abbreviation"]),
                "team": r.get("TeamName", ""),
            }
            for q in ("Q1", "Q2", "Q3"):
                if q in r.index:
                    entry[q.lower()] = self._clean(r.get(q))
            out.append(entry)
        return out

    def lap_times(self, driver: str) -> dict:
        """Lap-by-lap data for a driver."""
        code = self._resolve_driver(driver)
        laps = self.session.laps
        dl = laps[laps["Driver"] == code].sort_values("LapNumber")

        lap_list = []
        for _, lap in dl.iterrows():
            lt = lap.get("LapTime")
            lap_list.append({
                "lap": int(lap["LapNumber"]),
                "time_seconds": round(lt.total_seconds(), 3) if pd.notna(lt) else None,
                "compound": str(lap.get("Compound", "")).upper() if pd.notna(lap.get("Compound")) else None,
                "tyre_life": self._clean(lap.get("TyreLife")),
                "is_pit_in": pd.notna(lap.get("PitInTime")),
                "is_pit_out": pd.notna(lap.get("PitOutTime")),
            })

        # Summary stats (clean laps only)
        clean = dl[dl["LapTime"].notna() & dl["PitInTime"].isna() & dl["PitOutTime"].isna()]
        times = clean["LapTime"].dt.total_seconds()
        stats = {}
        if not times.empty:
            stats = {
                "fastest": round(float(times.min()), 3),
                "median": round(float(times.median()), 3),
                "slowest": round(float(times.max()), 3),
                "std_dev": round(float(times.std()), 3) if len(times) > 1 else 0,
                "clean_laps": len(times),
            }

        return {"driver": code, "laps": lap_list, "stats": stats}

    def pit_stops(self, driver: str | None = None) -> list[dict]:
        """Pit stop details. If driver is None, returns all drivers."""
        laps = self.session.laps
        results = self.session.results

        if driver:
            code = self._resolve_driver(driver)
            codes = [code]
        else:
            codes = results.sort_values("Position")["Abbreviation"].tolist()

        out = []
        for code in codes:
            dl = laps[laps["Driver"] == code].sort_values("LapNumber")
            pit_laps = dl[dl["PitInTime"].notna()]
            stops = []
            for _, p in pit_laps.iterrows():
                stops.append({
                    "lap": int(p["LapNumber"]),
                    "compound_before": str(p.get("Compound", "?")).upper(),
                })
            if stops:
                out.append({"driver": code, "stops": stops, "total_stops": len(stops)})

        return out

    def tire_stints(self, driver: str | None = None) -> list[dict]:
        """Tyre stint breakdown: compound, start/end lap, length."""
        laps = self.session.laps
        results = self.session.results

        if driver:
            code = self._resolve_driver(driver)
            codes = [code]
        else:
            codes = results.sort_values("Position").head(10)["Abbreviation"].tolist()

        out = []
        for code in codes:
            dl = laps[laps["Driver"] == code].sort_values("LapNumber")
            if dl.empty:
                continue
            stints = []
            groups = dl.groupby((dl["Compound"] != dl["Compound"].shift()).cumsum())
            for _, stint in groups:
                compound = str(stint["Compound"].iloc[0]).upper() if pd.notna(stint["Compound"].iloc[0]) else "?"
                start = int(stint["LapNumber"].iloc[0])
                end = int(stint["LapNumber"].iloc[-1])
                stints.append({
                    "compound": compound,
                    "start_lap": start,
                    "end_lap": end,
                    "length": end - start + 1,
                })
            out.append({"driver": code, "stints": stints})

        return out

    def fastest_laps(self, top_n: int = 10) -> list[dict]:
        """Fastest lap for each driver, ranked."""
        laps = self.session.laps
        valid = laps[laps["LapTime"].notna() & laps["PitInTime"].isna() & laps["PitOutTime"].isna()]

        by_driver = []
        for drv in valid["Driver"].unique():
            dl = valid[valid["Driver"] == drv]
            fastest = dl.loc[dl["LapTime"].idxmin()]
            lt = fastest["LapTime"]
            by_driver.append({
                "driver": drv,
                "lap": int(fastest["LapNumber"]),
                "time_seconds": round(lt.total_seconds(), 3) if pd.notna(lt) else None,
                "compound": str(fastest.get("Compound", "?")).upper(),
            })

        by_driver.sort(key=lambda x: x["time_seconds"] or 999)
        return by_driver[:top_n]

    def driver_telemetry(self, driver: str, lap_number: int | None = None) -> dict:
        """Summarized telemetry for a driver's lap (default: fastest).

        Returns stats, not raw trace data (which would be 300+ points).
        """
        code = self._resolve_driver(driver)
        laps = self.session.laps
        dl = laps[laps["Driver"] == code]

        if lap_number is not None:
            target = dl[dl["LapNumber"] == lap_number]
            if target.empty:
                raise ValueError(f"No data for {code} on lap {lap_number}")
            lap = target.iloc[0]
        else:
            quick = dl.pick_quicklaps()
            if quick.empty:
                quick = dl[dl["LapTime"].notna()]
            if quick.empty:
                raise ValueError(f"No telemetry available for {code}")
            lap = quick.pick_fastest()

        try:
            tel = lap.get_telemetry()
        except Exception:
            return {"driver": code, "error": "No telemetry data for this lap"}
        if tel.empty:
            return {"driver": code, "error": "No telemetry data for this lap"}

        result = {
            "driver": code,
            "lap": int(lap["LapNumber"]),
            "lap_time": self._clean(lap["LapTime"]),
            "compound": str(lap["Compound"]).upper() if pd.notna(lap.get("Compound")) else None,
            "data_points": len(tel),
        }

        if "Speed" in tel.columns:
            speed = tel["Speed"].values
            result["speed"] = {
                "max": round(float(speed.max()), 1),
                "avg": round(float(speed.mean()), 1),
                "min": round(float(speed.min()), 1),
            }
        if "Throttle" in tel.columns:
            throttle = tel["Throttle"].values
            result["throttle"] = {
                "full_pct": round(float((throttle >= 98).mean() * 100), 1),
                "avg": round(float(throttle.mean()), 1),
            }
        if "Brake" in tel.columns:
            brake = tel["Brake"].values.astype(float)
            result["braking"] = {
                "brake_pct": round(float((brake > 0).mean() * 100), 1),
                "heavy_brake_pct": round(float((brake > 50).mean() * 100), 1),
            }

        return result

    def head_to_head(self, driver_a: str, driver_b: str) -> dict:
        """Compare two drivers across key metrics."""
        code_a = self._resolve_driver(driver_a)
        code_b = self._resolve_driver(driver_b)
        results = self.session.results
        laps = self.session.laps

        def driver_stats(code):
            r_df = results[results["Abbreviation"] == code]
            if r_df.empty:
                return {"driver": code, "error": f"Driver {code} not found in results"}
            r = r_df.iloc[0]
            dl = laps[laps["Driver"] == code]
            clean = dl[dl["LapTime"].notna() & dl["PitInTime"].isna() & dl["PitOutTime"].isna()]
            times = clean["LapTime"].dt.total_seconds()
            fl_time = None
            if not dl.empty:
                quick = dl.pick_quicklaps()
                if not quick.empty:
                    fl = quick.pick_fastest()
                    fl_time = round(fl["LapTime"].total_seconds(), 3) if pd.notna(fl["LapTime"]) else None
            return {
                "driver": code,
                "position": self._clean(r.get("Position")),
                "grid": self._clean(r.get("GridPosition")),
                "status": r.get("Status", ""),
                "points": self._clean(r.get("Points")),
                "fastest_lap": fl_time,
                "median_pace": round(float(times.median()), 3) if not times.empty else None,
                "total_laps": len(dl),
                "pit_stops": int(dl["PitInTime"].notna().sum()),
            }

        return {
            "driver_a": driver_stats(code_a),
            "driver_b": driver_stats(code_b),
        }

    def weather(self) -> dict:
        """Session weather conditions."""
        s = self.session
        w = s.weather_data
        if w is None or w.empty:
            return {"available": False}
        out = {"available": True}
        if "TrackTemp" in w.columns:
            out["track_temp_avg"] = round(float(w["TrackTemp"].mean()), 1)
            out["track_temp_max"] = round(float(w["TrackTemp"].max()), 1)
        if "AirTemp" in w.columns:
            out["air_temp_avg"] = round(float(w["AirTemp"].mean()), 1)
        if "Humidity" in w.columns:
            out["humidity_avg"] = round(float(w["Humidity"].mean()), 1)
        if "Rainfall" in w.columns:
            out["rainfall"] = bool(w["Rainfall"].any())
        return out

    def session_summary(self) -> dict:
        """Quick overview of the loaded session."""
        s = self.session
        results = s.results.sort_values("Position")
        laps = s.laps

        total_laps = int(laps["LapNumber"].max()) if not laps.empty else 0
        dnfs = results[results["Status"].str.contains("Retired|DNF|Accident|Collision|Mechanical|Engine|Gearbox|Hydraulic|Spin", case=False, na=False)]
        total_stops = int(laps["PitInTime"].notna().sum())

        # Fastest lap
        valid = laps[laps["LapTime"].notna() & laps["PitInTime"].isna() & laps["PitOutTime"].isna()]
        fl = None
        if not valid.empty:
            f = valid.loc[valid["LapTime"].idxmin()]
            fl = {
                "driver": f["Driver"],
                "lap": int(f["LapNumber"]),
                "time": round(f["LapTime"].total_seconds(), 3),
            }

        # Winner
        winner = results.iloc[0] if not results.empty else None

        return {
            "year": int(s.event.year),
            "event": s.event["EventName"],
            "session_type": s.name,
            "total_laps": total_laps,
            "total_drivers": len(results),
            "finishers": len(results) - len(dnfs),
            "dnfs": len(dnfs),
            "total_pit_stops": total_stops,
            "fastest_lap": fl,
            "winner": {
                "driver": winner["Abbreviation"],
                "team": winner.get("TeamName", ""),
            } if winner is not None else None,
            "weather": self.weather(),
        }

    def track_evolution(self) -> dict:
        """How track conditions changed across the session."""
        s = self.session
        laps = s.laps
        weather = s.weather_data

        # Lap time evolution by stint thirds (early/mid/late)
        valid = laps[laps["LapTime"].notna() & laps["PitInTime"].isna() & laps["PitOutTime"].isna()]
        if valid.empty:
            return {"available": False}

        total_laps = int(valid["LapNumber"].max())
        third = max(total_laps // 3, 1)

        def avg_pace(start, end):
            chunk = valid[(valid["LapNumber"] >= start) & (valid["LapNumber"] <= end)]
            times = chunk["LapTime"].dt.total_seconds()
            # Use top 5 drivers' median to avoid outliers
            top5 = self.session.results.sort_values("Position").head(5)["Abbreviation"].tolist()
            top_times = chunk[chunk["Driver"].isin(top5)]["LapTime"].dt.total_seconds()
            return round(float(top_times.median()), 3) if not top_times.empty else None

        result = {
            "available": True,
            "total_laps": total_laps,
            "pace_early": avg_pace(1, third),
            "pace_mid": avg_pace(third + 1, third * 2),
            "pace_late": avg_pace(third * 2 + 1, total_laps),
        }

        if weather is not None and not weather.empty:
            if "TrackTemp" in weather.columns:
                result["track_temp_start"] = round(float(weather["TrackTemp"].iloc[0]), 1)
                result["track_temp_end"] = round(float(weather["TrackTemp"].iloc[-1]), 1)

        return result

    def overtake_analysis(self) -> list[dict]:
        """Position changes and overtake opportunities."""
        s = self.session
        results = s.results.sort_values("Position")
        laps = s.laps

        analysis = []
        drivers = results.head(15)["Abbreviation"].tolist()
        for i in range(len(drivers) - 1):
            ahead = drivers[i]
            behind = drivers[i + 1]

            # Get final gap
            ahead_laps = laps[laps["Driver"] == ahead]
            behind_laps = laps[laps["Driver"] == behind]

            if ahead_laps.empty or behind_laps.empty:
                continue

            # Pace comparison (clean laps)
            def median_pace(dl):
                clean = dl[dl["LapTime"].notna() & dl["PitInTime"].isna() & dl["PitOutTime"].isna()]
                times = clean["LapTime"].dt.total_seconds()
                clean_times = times[times < times.median() * 1.10] if not times.empty else times
                return round(float(clean_times.median()), 3) if not clean_times.empty else None

            ahead_pace = median_pace(ahead_laps)
            behind_pace = median_pace(behind_laps)

            # Grid vs finish position change
            ahead_result = results[results["Abbreviation"] == ahead].iloc[0]
            behind_result = results[results["Abbreviation"] == behind].iloc[0]
            ahead_grid = self._clean(ahead_result.get("GridPosition"))
            behind_grid = self._clean(behind_result.get("GridPosition"))

            entry = {
                "position": i + 1,
                "driver_ahead": ahead,
                "driver_behind": behind,
                "ahead_pace": ahead_pace,
                "behind_pace": behind_pace,
                "pace_delta": round(ahead_pace - behind_pace, 3) if ahead_pace and behind_pace else None,
            }
            if ahead_grid and behind_grid:
                entry["ahead_gained"] = int(behind_grid) - (i + 1) if behind_grid else None
                entry["behind_gained"] = int(behind_grid) - (i + 2) if behind_grid else None

            analysis.append(entry)

        return analysis
