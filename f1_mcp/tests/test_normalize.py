"""Tests for driver, race, and session type normalization.

These tests run without any network calls or FastF1 sessions —
they only test the static alias tables and matching logic.
"""

import pytest

from f1_mcp.normalize import resolve_driver, resolve_race, resolve_session_type


# ── Driver Resolution (static, no session) ──────────────────────────────────


class TestResolveDriverByCode:
    """Exact 3-letter abbreviation matches."""

    def test_uppercase(self):
        assert resolve_driver("VER") == "VER"

    def test_lowercase(self):
        assert resolve_driver("ver") == "VER"

    def test_mixed_case(self):
        assert resolve_driver("Lec") == "LEC"


class TestResolveDriverByFullName:
    """Full name matches from static alias table."""

    def test_full_name(self):
        assert resolve_driver("Charles Leclerc") == "LEC"

    def test_full_name_lowercase(self):
        assert resolve_driver("charles leclerc") == "LEC"

    def test_full_name_max(self):
        assert resolve_driver("Max Verstappen") == "VER"

    def test_full_name_lewis(self):
        assert resolve_driver("Lewis Hamilton") == "HAM"


class TestResolveDriverByLastName:
    """Last name only."""

    def test_leclerc(self):
        assert resolve_driver("Leclerc") == "LEC"

    def test_verstappen(self):
        assert resolve_driver("Verstappen") == "VER"

    def test_hamilton(self):
        assert resolve_driver("Hamilton") == "HAM"

    def test_norris(self):
        assert resolve_driver("Norris") == "NOR"

    def test_piastri(self):
        assert resolve_driver("Piastri") == "PIA"

    def test_alonso(self):
        assert resolve_driver("Alonso") == "ALO"


class TestResolveDriverByFirstName:
    """First name only (must be unambiguous in alias table)."""

    def test_charles(self):
        assert resolve_driver("charles") == "LEC"

    def test_max(self):
        assert resolve_driver("max") == "VER"

    def test_lewis(self):
        assert resolve_driver("lewis") == "HAM"

    def test_lando(self):
        assert resolve_driver("lando") == "NOR"


class TestResolveDriverByNumber:
    """Car number lookup."""

    def test_1_verstappen(self):
        assert resolve_driver("1") == "VER"

    def test_44_hamilton(self):
        assert resolve_driver("44") == "HAM"

    def test_16_leclerc(self):
        assert resolve_driver("16") == "LEC"

    def test_4_norris(self):
        assert resolve_driver("4") == "NOR"

    def test_55_sainz(self):
        assert resolve_driver("55") == "SAI"

    def test_14_alonso(self):
        assert resolve_driver("14") == "ALO"


class TestResolveDriverByNickname:
    """Nicknames and common aliases."""

    def test_checo(self):
        assert resolve_driver("checo") == "PER"

    def test_kmag(self):
        assert resolve_driver("kmag") == "MAG"

    def test_hulk(self):
        assert resolve_driver("hulk") == "HUL"

    def test_seb(self):
        assert resolve_driver("seb") == "VET"


class TestResolveDriverEdgeCases:
    """Edge cases and error handling."""

    def test_empty_string(self):
        assert resolve_driver("") is None

    def test_none_input(self):
        assert resolve_driver("") is None

    def test_whitespace(self):
        assert resolve_driver("   ") is None

    def test_gibberish(self):
        assert resolve_driver("xyzabc123") is None

    def test_padded_whitespace(self):
        assert resolve_driver("  Leclerc  ") == "LEC"


# ── Session Type Resolution ──────────────────────────────────────────────────


class TestResolveSessionType:
    """Session type normalization."""

    def test_race_word(self):
        assert resolve_session_type("race") == "R"

    def test_race_code(self):
        assert resolve_session_type("R") == "R"

    def test_qualifying_word(self):
        assert resolve_session_type("qualifying") == "Q"

    def test_quali_shorthand(self):
        assert resolve_session_type("quali") == "Q"

    def test_q_code(self):
        assert resolve_session_type("Q") == "Q"

    def test_sprint(self):
        assert resolve_session_type("sprint") == "S"

    def test_fp1(self):
        assert resolve_session_type("FP1") == "FP1"

    def test_practice_1(self):
        assert resolve_session_type("practice 1") == "FP1"

    def test_fp2(self):
        assert resolve_session_type("FP2") == "FP2"

    def test_fp3(self):
        assert resolve_session_type("FP3") == "FP3"

    def test_practice_3(self):
        assert resolve_session_type("practice 3") == "FP3"

    def test_shootout(self):
        assert resolve_session_type("shootout") == "SS"

    def test_gp(self):
        assert resolve_session_type("gp") == "R"

    def test_grand_prix(self):
        assert resolve_session_type("grand prix") == "R"

    def test_case_insensitive(self):
        assert resolve_session_type("QUALIFYING") == "Q"


# ── Race Resolution (static aliases only, no network) ────────────────────────


class TestResolveRaceStaticAliases:
    """Race aliases without year (no FastF1 schedule call)."""

    def test_monza(self):
        result = resolve_race("monza")
        assert result == "Italian"

    def test_silverstone(self):
        result = resolve_race("silverstone")
        assert result == "British"

    def test_spa(self):
        result = resolve_race("spa")
        assert result == "Belgian"

    def test_monaco(self):
        result = resolve_race("monaco")
        assert result == "Monaco"

    def test_suzuka(self):
        result = resolve_race("suzuka")
        assert result == "Japanese"

    def test_baku(self):
        result = resolve_race("baku")
        assert result == "Azerbaijan"

    def test_jeddah(self):
        result = resolve_race("jeddah")
        assert result == "Saudi Arabian"

    def test_sakhir(self):
        result = resolve_race("sakhir")
        assert result == "Bahrain"

    def test_cota(self):
        result = resolve_race("cota")
        assert result == "United States"

    def test_vegas(self):
        result = resolve_race("vegas")
        assert result == "Las Vegas"

    def test_interlagos(self):
        result = resolve_race("interlagos")
        assert result == "São Paulo"

    def test_unknown_returns_title_case(self):
        result = resolve_race("mars grand prix")
        assert result == "Mars Grand Prix"
