"""Fuzzy resolution for drivers, races, and session types.

Users say "Leclerc", "charles", "LEC", or "Charles Leclerc" — this module
resolves all of those to the canonical 3-letter abbreviation. Same idea
for race names ("Monza" → "Italian Grand Prix") and session types
("quali" → "Q").

Design:
    1. Dynamic lookup against the loaded FastF1 session (best source of truth)
    2. Static fallback tables for when no session is loaded
    3. Substring / prefix matching as last resort
    4. Returns None on ambiguity or no match (caller decides how to handle)
"""

from __future__ import annotations

import fastf1
import pandas as pd


# ── Static Driver Aliases ────────────────────────────────────────────────────
# Covers the 2022-2026 grid + common nicknames. Used as fallback when no
# session is loaded, or when the session doesn't contain the driver.

_DRIVER_ALIASES: dict[str, str] = {
    # 2024-2026 grid (lowercase key → 3-letter code)
    "verstappen": "VER", "max verstappen": "VER", "max": "VER",
    "hamilton": "HAM", "lewis hamilton": "HAM", "lewis": "HAM",
    "leclerc": "LEC", "charles leclerc": "LEC", "charles": "LEC",
    "norris": "NOR", "lando norris": "NOR", "lando": "NOR",
    "sainz": "SAI", "carlos sainz": "SAI", "carlos": "SAI",
    "russell": "RUS", "george russell": "RUS", "george": "RUS",
    "piastri": "PIA", "oscar piastri": "PIA", "oscar": "PIA",
    "alonso": "ALO", "fernando alonso": "ALO", "fernando": "ALO",
    "stroll": "STR", "lance stroll": "STR", "lance": "STR",
    "gasly": "GAS", "pierre gasly": "GAS", "pierre": "GAS",
    "ocon": "OCO", "esteban ocon": "OCO", "esteban": "OCO",
    "tsunoda": "TSU", "yuki tsunoda": "TSU", "yuki": "TSU",
    "ricciardo": "RIC", "daniel ricciardo": "RIC", "daniel": "RIC",
    "bottas": "BOT", "valtteri bottas": "BOT", "valtteri": "BOT",
    "zhou": "ZHO", "guanyu zhou": "ZHO", "guanyu": "ZHO",
    "magnussen": "MAG", "kevin magnussen": "MAG", "kevin": "MAG", "kmag": "MAG",
    "hulkenberg": "HUL", "nico hulkenberg": "HUL", "hulk": "HUL",
    "albon": "ALB", "alexander albon": "ALB", "alex albon": "ALB", "alex": "ALB",
    "sargeant": "SAR", "logan sargeant": "SAR", "logan": "SAR",
    "perez": "PER", "sergio perez": "PER", "checo": "PER", "checo perez": "PER",
    "lawson": "LAW", "liam lawson": "LAW", "liam": "LAW",
    "bearman": "BEA", "oliver bearman": "BEA", "ollie bearman": "BEA",
    "colapinto": "COL", "franco colapinto": "COL", "franco": "COL",
    "hadjar": "HAD", "isack hadjar": "HAD", "isack": "HAD",
    "doohan": "DOO", "jack doohan": "DOO", "jack": "DOO",
    "antonelli": "ANT", "kimi antonelli": "ANT", "andrea kimi antonelli": "ANT",
    "bortoleto": "BOR", "gabriel bortoleto": "BOR", "gabriel": "BOR",
    # Historic drivers people commonly ask about
    "schumacher": "MSC", "michael schumacher": "MSC",
    "raikkonen": "RAI", "kimi raikkonen": "RAI", "kimi": "RAI",
    "vettel": "VET", "sebastian vettel": "VET", "seb": "VET",
    "rosberg": "ROS", "nico rosberg": "ROS",
}

# Car number → abbreviation (current + recent grid)
_NUMBER_TO_CODE: dict[str, str] = {
    "1": "VER", "11": "PER", "44": "HAM", "63": "RUS",
    "16": "LEC", "55": "SAI", "4": "NOR", "81": "PIA",
    "14": "ALO", "18": "STR", "10": "GAS", "31": "OCO",
    "22": "TSU", "3": "RIC", "77": "BOT", "24": "ZHO",
    "20": "MAG", "27": "HUL", "23": "ALB", "2": "SAR",
    "30": "LAW", "87": "BEA", "43": "COL",
    "12": "ANT", "5": "DOO", "38": "HAD",
}


# ── Static Race Aliases ──────────────────────────────────────────────────────
# Track / city / nickname → canonical FastF1 event name fragment

_RACE_ALIASES: dict[str, str] = {
    # Circuit name / city → country or GP name substring (matched against schedule)
    "monza": "Italian", "imola": "Emilia Romagna",
    "silverstone": "British", "spa": "Belgian",
    "monaco": "Monaco", "monte carlo": "Monaco",
    "interlagos": "São Paulo", "sao paulo": "São Paulo",
    "suzuka": "Japanese", "japan": "Japanese",
    "singapore": "Singapore", "marina bay": "Singapore",
    "baku": "Azerbaijan", "jeddah": "Saudi Arabian",
    "jedda": "Saudi Arabian", "saudi": "Saudi Arabian",
    "bahrain": "Bahrain", "sakhir": "Bahrain",
    "melbourne": "Australian", "australia": "Australian",
    "barcelona": "Spanish", "spain": "Spanish", "catalunya": "Spanish",
    "zandvoort": "Dutch", "netherlands": "Dutch",
    "hungaroring": "Hungarian", "hungary": "Hungarian",
    "las vegas": "Las Vegas", "vegas": "Las Vegas",
    "miami": "Miami", "austin": "United States", "cota": "United States",
    "usa": "United States", "us": "United States",
    "canada": "Canadian", "montreal": "Canadian",
    "mexico": "Mexico City", "mexico city": "Mexico City",
    "abu dhabi": "Abu Dhabi", "yas marina": "Abu Dhabi",
    "qatar": "Qatar", "losail": "Qatar",
    "china": "Chinese", "shanghai": "Chinese",
    "portimao": "Portuguese", "portugal": "Portuguese",
    "red bull ring": "Austrian", "austria": "Austrian", "spielberg": "Austrian",
}


# ── Session Type Map ─────────────────────────────────────────────────────────

_SESSION_TYPE_MAP: dict[str, str] = {
    "race": "R", "r": "R", "grand prix": "R", "gp": "R",
    "qualifying": "Q", "quali": "Q", "q": "Q", "qualy": "Q",
    "sprint": "S", "sprint race": "S", "s": "S",
    "sprint qualifying": "SQ", "sprint quali": "SQ", "sq": "SQ",
    "sprint shootout": "SS", "shootout": "SS", "ss": "SS",
    "practice 1": "FP1", "fp1": "FP1", "free practice 1": "FP1", "p1": "FP1",
    "practice 2": "FP2", "fp2": "FP2", "free practice 2": "FP2", "p2": "FP2",
    "practice 3": "FP3", "fp3": "FP3", "free practice 3": "FP3", "p3": "FP3",
}


# ── Public API ───────────────────────────────────────────────────────────────


def resolve_driver(query: str, session=None) -> str | None:
    """Resolve a fuzzy driver reference to a 3-letter abbreviation.

    Tries (in order):
        1. Exact abbreviation match (case-insensitive)
        2. Car number lookup
        3. Session-aware match (full name, last name, first name)
        4. Static alias table
        5. Substring match against session drivers
    Returns None if unresolvable.
    """
    if not query or not query.strip():
        return None

    q = query.strip().lower()

    # 1. Exact abbreviation (3-letter codes)
    if len(q) <= 3 and q.upper().isalpha():
        code = q.upper()
        # Validate against session if available
        if session is not None:
            results = session.results
            if code in results["Abbreviation"].values:
                return code
        # Check static aliases (values)
        if code in _DRIVER_ALIASES.values() or code in _NUMBER_TO_CODE.values():
            return code

    # 2. Car number
    if q.isdigit() and q in _NUMBER_TO_CODE:
        code = _NUMBER_TO_CODE[q]
        if session is not None:
            if code in session.results["Abbreviation"].values:
                return code
        return code

    # 3. Session-aware matching (best source of truth)
    if session is not None:
        code = _match_from_session(q, session)
        if code:
            return code

    # 4. Static alias table
    if q in _DRIVER_ALIASES:
        return _DRIVER_ALIASES[q]

    # 5. Substring match against static aliases
    matches = [code for alias, code in _DRIVER_ALIASES.items() if q in alias]
    if len(matches) == 1:
        return matches[0]
    # If multiple matches, try prefix
    prefix_matches = [code for alias, code in _DRIVER_ALIASES.items() if alias.startswith(q)]
    if len(prefix_matches) == 1:
        return prefix_matches[0]

    return None


def _match_from_session(q: str, session) -> str | None:
    """Match against drivers in the loaded FastF1 session."""
    results = session.results
    if results is None or results.empty:
        return None

    for _, row in results.iterrows():
        abbr = str(row.get("Abbreviation", "")).lower()
        full = str(row.get("FullName", "")).lower()
        last = str(row.get("LastName", "")).lower()
        first = str(row.get("FirstName", "")).lower()

        # Exact match on any field
        if q in (abbr, full, last, first):
            return row["Abbreviation"]

    # Prefix / substring match on last name or full name
    candidates = []
    for _, row in results.iterrows():
        full = str(row.get("FullName", "")).lower()
        last = str(row.get("LastName", "")).lower()
        if last.startswith(q) or full.startswith(q) or q in full:
            candidates.append(row["Abbreviation"])

    if len(candidates) == 1:
        return candidates[0]

    return None


def resolve_race(query: str, year: int | None = None) -> str | None:
    """Resolve a fuzzy race name to the canonical FastF1 event name.

    Tries:
        1. Exact match against the year's event schedule
        2. Static alias → event name fragment → schedule match
        3. Substring match against event names, countries, locations

    Returns the EventName string that FastF1 accepts, or None.
    """
    if not query or not query.strip():
        return None

    q = query.strip().lower()

    # 1. Static alias FIRST (handles "spa" → Belgian, "monza" → Italian, etc.)
    alias_fragment = _RACE_ALIASES.get(q)
    if alias_fragment and year is not None:
        match = _match_from_schedule(alias_fragment.lower(), year)
        if match:
            return match

    # 2. Try direct match against the schedule
    if year is not None:
        match = _match_from_schedule(q, year)
        if match:
            return match

    # 3. If no year, return the alias fragment (caller can use it with FastF1)
    if alias_fragment:
        return alias_fragment

    # Last resort: return the query capitalized (FastF1 is somewhat forgiving)
    return query.title()


def _match_from_schedule(q: str, year: int) -> str | None:
    """Match against the FastF1 event schedule for a given year."""
    try:
        schedule = fastf1.get_event_schedule(year)
        events = schedule[schedule["EventFormat"] != "testing"]
    except Exception:
        return None

    for _, row in events.iterrows():
        name = str(row.get("EventName", "")).lower()
        country = str(row.get("Country", "")).lower()
        location = str(row.get("Location", "")).lower()

        # Exact match
        if q in (name, country, location):
            return row["EventName"]

    # Substring match
    candidates = []
    for _, row in events.iterrows():
        name = str(row.get("EventName", "")).lower()
        country = str(row.get("Country", "")).lower()
        location = str(row.get("Location", "")).lower()
        if q in name or q in country or q in location:
            candidates.append(row["EventName"])

    if len(candidates) == 1:
        return candidates[0]

    # Prefix match on event name
    prefix_candidates = []
    for _, row in events.iterrows():
        name = str(row.get("EventName", "")).lower()
        if name.startswith(q):
            prefix_candidates.append(row["EventName"])
    if len(prefix_candidates) == 1:
        return prefix_candidates[0]

    return candidates[0] if candidates else None


def resolve_session_type(query: str) -> str:
    """Resolve a session type string to FastF1's canonical code.

    "qualifying" → "Q", "race" → "R", "practice 1" → "FP1", etc.
    Returns the input unchanged if already a valid code.
    """
    q = query.strip().lower()

    # Already a canonical code?
    if q.upper() in ("R", "Q", "S", "SQ", "SS", "FP1", "FP2", "FP3"):
        return q.upper()

    return _SESSION_TYPE_MAP.get(q, query.upper())


def list_known_drivers() -> list[dict]:
    """Return the static driver alias table as a list (useful for debugging)."""
    # Deduplicate: group aliases by code
    by_code: dict[str, list[str]] = {}
    for alias, code in _DRIVER_ALIASES.items():
        by_code.setdefault(code, []).append(alias)
    return [{"code": code, "aliases": aliases} for code, aliases in sorted(by_code.items())]
