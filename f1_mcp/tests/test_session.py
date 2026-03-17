"""Tests for SessionManager.

Split into:
- Unit tests: no network, test error handling and helpers
- Integration tests: require FastF1 (marked with @pytest.mark.integration)
  These download/cache real data on first run (~30s), instant after.
"""

import pytest

from f1_mcp.session import SessionManager


# ── Unit Tests (no network) ──────────────────────────────────────────────────


class TestSessionManagerLifecycle:
    """Manager state before any session is loaded."""

    def test_not_loaded_initially(self):
        mgr = SessionManager()
        assert mgr.is_loaded is False

    def test_status_when_unloaded(self):
        mgr = SessionManager()
        assert mgr.status() == {"loaded": False}

    def test_accessing_session_raises(self):
        mgr = SessionManager()
        with pytest.raises(RuntimeError, match="No session loaded"):
            mgr.session

    def test_race_result_raises_when_unloaded(self):
        mgr = SessionManager()
        with pytest.raises(RuntimeError):
            mgr.race_result()

    def test_year_validation_too_old(self):
        mgr = SessionManager()
        with pytest.raises(ValueError, match="2018 onwards"):
            mgr.load(2010, "Bahrain", "R")

    def test_year_validation_boundary(self):
        mgr = SessionManager()
        with pytest.raises(ValueError, match="2018 onwards"):
            mgr.load(2017, "Bahrain", "R")


class TestCleanMethod:
    """The _clean helper for JSON-safe values."""

    def test_none(self):
        mgr = SessionManager()
        assert mgr._clean(None) is None

    def test_int(self):
        mgr = SessionManager()
        assert mgr._clean(42) == 42

    def test_float(self):
        mgr = SessionManager()
        assert mgr._clean(3.14159) == 3.14159

    def test_float_nan(self):
        import math
        mgr = SessionManager()
        assert mgr._clean(float("nan")) is None

    def test_float_inf(self):
        mgr = SessionManager()
        assert mgr._clean(float("inf")) is None

    def test_numpy_int(self):
        import numpy as np
        mgr = SessionManager()
        assert mgr._clean(np.int64(42)) == 42
        assert isinstance(mgr._clean(np.int64(42)), int)

    def test_numpy_float(self):
        import numpy as np
        mgr = SessionManager()
        result = mgr._clean(np.float64(3.14))
        assert isinstance(result, float)

    def test_numpy_nan(self):
        import numpy as np
        mgr = SessionManager()
        assert mgr._clean(np.float64("nan")) is None

    def test_timedelta(self):
        import pandas as pd
        mgr = SessionManager()
        td = pd.Timedelta(seconds=83.456)
        assert mgr._clean(td) == 83.456

    def test_nat(self):
        import pandas as pd
        mgr = SessionManager()
        assert mgr._clean(pd.NaT) is None


class TestResolveDriver:
    """Driver resolution through the manager (delegates to normalize.py)."""

    def test_resolve_known_driver(self):
        mgr = SessionManager()
        # Without a session, falls back to static aliases
        assert mgr._resolve_driver("Leclerc") == "LEC"

    def test_resolve_unknown_raises(self):
        mgr = SessionManager()
        # Without a session loaded, can't list available drivers
        with pytest.raises((ValueError, RuntimeError)):
            mgr._resolve_driver("xyznonexistent")


# ── Integration Tests (require network on first run) ─────────────────────────


@pytest.mark.integration
class TestSessionLoading:
    """Tests that load real F1 sessions. Slow on first run, cached after."""

    @pytest.fixture(scope="class")
    def loaded_mgr(self):
        """Load 2024 Bahrain GP race once for the whole class."""
        mgr = SessionManager()
        mgr.load(2024, "Bahrain", "R")
        return mgr

    def test_load_returns_status(self, loaded_mgr):
        status = loaded_mgr.status()
        assert status["loaded"] is True
        assert status["year"] == 2024
        assert "Bahrain" in status["event"]
        assert status["session_type"] == "Race"

    def test_reload_same_session(self, loaded_mgr):
        result = loaded_mgr.load(2024, "Bahrain", "R")
        assert result["status"] == "already_loaded"

    def test_drivers_list(self, loaded_mgr):
        drivers = loaded_mgr.drivers()
        assert len(drivers) == 20
        codes = [d["code"] for d in drivers]
        assert "VER" in codes
        assert "HAM" in codes
        assert "LEC" in codes

    def test_race_result(self, loaded_mgr):
        result = loaded_mgr.race_result()
        assert len(result) > 0
        winner = result[0]
        assert winner["position"] == 1
        assert winner["code"] is not None
        assert winner["team"] is not None

    def test_qualifying_result(self, loaded_mgr):
        # This is a race session, so Q times may be empty but shouldn't crash
        result = loaded_mgr.qualifying_result()
        assert isinstance(result, list)

    def test_lap_times_by_code(self, loaded_mgr):
        result = loaded_mgr.lap_times("VER")
        assert result["driver"] == "VER"
        assert len(result["laps"]) > 0
        assert result["stats"]["fastest"] > 0

    def test_lap_times_by_name(self, loaded_mgr):
        result = loaded_mgr.lap_times("Verstappen")
        assert result["driver"] == "VER"

    def test_lap_times_by_first_name(self, loaded_mgr):
        result = loaded_mgr.lap_times("max")
        assert result["driver"] == "VER"

    def test_lap_times_by_number(self, loaded_mgr):
        result = loaded_mgr.lap_times("1")
        assert result["driver"] == "VER"

    def test_lap_times_invalid_driver(self, loaded_mgr):
        with pytest.raises(ValueError, match="Could not resolve"):
            loaded_mgr.lap_times("nonexistent_driver_xyz")

    def test_pit_stops_all(self, loaded_mgr):
        result = loaded_mgr.pit_stops()
        assert isinstance(result, list)
        assert len(result) > 0
        assert "driver" in result[0]
        assert "stops" in result[0]

    def test_pit_stops_single_driver(self, loaded_mgr):
        result = loaded_mgr.pit_stops("VER")
        assert len(result) == 1
        assert result[0]["driver"] == "VER"

    def test_tire_stints(self, loaded_mgr):
        result = loaded_mgr.tire_stints()
        assert isinstance(result, list)
        assert len(result) > 0
        first = result[0]
        assert "stints" in first
        assert first["stints"][0]["compound"] in ("SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET")

    def test_fastest_laps(self, loaded_mgr):
        result = loaded_mgr.fastest_laps(5)
        assert len(result) == 5
        assert result[0]["time_seconds"] <= result[1]["time_seconds"]

    def test_driver_telemetry(self, loaded_mgr):
        result = loaded_mgr.driver_telemetry("VER")
        assert result["driver"] == "VER"
        assert "speed" in result
        assert result["speed"]["max"] > 200
        assert "throttle" in result
        assert "braking" in result

    def test_driver_telemetry_fuzzy(self, loaded_mgr):
        result = loaded_mgr.driver_telemetry("leclerc")
        assert result["driver"] == "LEC"

    def test_head_to_head(self, loaded_mgr):
        result = loaded_mgr.head_to_head("VER", "LEC")
        assert result["driver_a"]["driver"] == "VER"
        assert result["driver_b"]["driver"] == "LEC"
        assert result["driver_a"]["position"] is not None
        assert result["driver_b"]["fastest_lap"] is not None

    def test_head_to_head_fuzzy_names(self, loaded_mgr):
        result = loaded_mgr.head_to_head("max", "charles")
        assert result["driver_a"]["driver"] == "VER"
        assert result["driver_b"]["driver"] == "LEC"

    def test_weather(self, loaded_mgr):
        result = loaded_mgr.weather()
        assert result["available"] is True
        assert result["track_temp_avg"] > 0

    def test_session_summary(self, loaded_mgr):
        result = loaded_mgr.session_summary()
        assert result["year"] == 2024
        assert "Bahrain" in result["event"]
        assert result["total_laps"] > 0
        assert result["winner"]["driver"] is not None

    def test_track_evolution(self, loaded_mgr):
        result = loaded_mgr.track_evolution()
        assert result["available"] is True
        assert result["total_laps"] > 0
        assert result["pace_early"] is not None

    def test_overtake_analysis(self, loaded_mgr):
        result = loaded_mgr.overtake_analysis()
        assert isinstance(result, list)
        assert len(result) > 0
        assert "driver_ahead" in result[0]
        assert "pace_delta" in result[0]


@pytest.mark.integration
class TestSessionLoadingFuzzyRace:
    """Test that fuzzy race names resolve correctly when loading."""

    def test_load_by_circuit_name(self):
        mgr = SessionManager()
        result = mgr.load(2024, "monza", "race")
        assert "Italian" in result["event"]

    def test_load_by_alias(self):
        mgr = SessionManager()
        result = mgr.load(2024, "silverstone", "qualifying")
        assert "British" in result["event"]
        assert result["session_type"] == "Qualifying"


@pytest.mark.integration
class TestAttach:
    """Test attach() for dashboard integration."""

    def test_attach_shares_session(self):
        # Load a session normally
        mgr1 = SessionManager()
        mgr1.load(2024, "Bahrain", "R")

        # Attach to a second manager
        mgr2 = SessionManager()
        assert mgr2.is_loaded is False
        mgr2.attach(mgr1.session)
        assert mgr2.is_loaded is True

        # Both should return the same data
        r1 = mgr1.race_result()
        r2 = mgr2.race_result()
        assert r1[0]["code"] == r2[0]["code"]
