# F1 Pit Wall

A full-stack Formula 1 race engineer dashboard with AI-powered analysis. Load any historical session or connect to live timing — explore telemetry, strategy, energy modeling, race replay, and chat with an AI race engineer that fetches real data via MCP tools.

![React](https://img.shields.io/badge/React-19-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green)
![FastF1](https://img.shields.io/badge/FastF1-3.3+-red)
![Claude](https://img.shields.io/badge/AI-Claude%20Sonnet-purple)
![MCP](https://img.shields.io/badge/MCP-Tools-orange)
![Tests](https://img.shields.io/badge/Tests-121%20passing-brightgreen)

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- An [Anthropic API key](https://console.anthropic.com/) (for AI chat features)

### Setup

```bash
git clone <your-repo-url>
cd f1_dashboard

# Backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e f1_mcp/

# Frontend
cd frontend
npm install
cd ..
```

### Run

```bash
chmod +x start.sh
./start.sh
```

Open http://localhost:3000 and you're in.

- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8000
- **Stop:** `./start.sh stop`

### First Steps

1. Select a year, Grand Prix, and session type on the home page
2. Click **Load Session** (first load downloads from F1 servers ~10-30s, cached after)
3. Explore any page from the sidebar
4. Open the **AI chat** (red bubble, bottom-right) — enter your Anthropic API key once, then ask anything

---

## Features

| Page | What It Does |
|------|-------------|
| **Race Command** | Results, tyre strategy timeline, weather, SC/VSC count, DNFs, fastest lap |
| **Telemetry Lab** | Multi-driver speed/throttle/brake overlays, circuit map with heatmaps |
| **Performance Studio** | Lap time evolution, tyre degradation, fuel-corrected times, pace-adjusted standings |
| **Pit Strategy** | Stint timeline, undercut/overcut detection, pit stop details, SC event mapping |
| **Energy Map** | MGU-K harvest/deploy model (2026 regs: 350kW), battery SoC, clipping detection |
| **Circuit Lab** | Interactive circuit with DRS zones, sector markers, corner-by-corner analysis |
| **Race Replay** | Animated circuit map with drivers, win probability model, accuracy sweep |
| **Compare GP** | Cross-session head-to-head: corner speeds, sector deltas, lap time comparison |
| **Live Pit Wall** | Real-time SignalR stream, driver cards, gap tracking, strategy alerts |
| **AI Debrief** | Claude-powered race analysis with next-race predictions |

### AI Race Engineer Chat

The chat widget uses **tool calling** instead of dumping all data into the prompt. Claude picks which data to fetch per question — 21 tools covering results, lap times, pit stops, telemetry, energy, predictions, overtakes, and more.

Driver names are fuzzy-matched: "Leclerc", "charles", "LEC", "16" all work. Tool calls are shown as green tags below each message so you can see exactly what data Claude used.

---

## Tech Stack

| Layer | Tech |
|-------|------|
| **Backend** | Python, FastAPI, FastF1, NumPy, SciPy, Pandas |
| **Frontend** | React 19, Vite, Tailwind CSS, Plotly.js, Framer Motion |
| **AI** | Anthropic Claude API (tool calling) |
| **MCP** | f1_mcp package (local MCP server for Claude Desktop) |
| **Data** | F1 official timing via FastF1 (cached locally) |
| **Tests** | pytest (121 tests — unit + integration) |

---

## F1 MCP Server

The `f1_mcp/` directory is a standalone, installable Python package that exposes F1 race data as MCP tools. It powers the dashboard's AI chat **and** works as a standalone server for Claude Desktop, Cursor, or any MCP-compatible client.

### How It Works

```
Claude Desktop / Dashboard Chat
       |
       | "Who won the 2024 Bahrain race?"
       v
  Claude picks tools:  race_result()
       |
       v
  f1_mcp server executes tool
       |
       v
  FastF1 loads data (cached locally)
       |
       v
  Returns structured JSON -> Claude answers
```

No hosted API. No credentials needed for data. Everything runs locally on your machine.

### Use with Claude Desktop

1. Install the package:
```bash
source venv/bin/activate
pip install -e f1_mcp/
```

2. Add to Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "f1": {
      "command": "/path/to/f1_dashboard/venv/bin/python",
      "args": ["-m", "f1_mcp"]
    }
  }
}
```
Use the full path to your venv Python (run `which python` with venv activated to find it).

3. Restart Claude Desktop (Cmd+Q, reopen). You'll see a tools icon in the chat input.

4. Ask Claude: *"Load the 2024 Monaco qualifying and tell me who got pole"*

### MCP Tools

| Tool | Description |
|------|-------------|
| `load_session` | Load a race/quali/practice — fuzzy race names ("monza", "spa", "silverstone") |
| `season_calendar` | F1 calendar for a year |
| `race_result` | Full race classification |
| `qualifying_result` | Q1/Q2/Q3 times |
| `lap_times` | Lap-by-lap data for a driver |
| `fastest_laps` | Fastest laps ranked |
| `pit_stops` | Pit stop details |
| `tire_stints` | Tyre compound and stint breakdown |
| `driver_telemetry` | Speed/throttle/brake summary for a lap |
| `head_to_head` | Two-driver comparison across all metrics |
| `weather` | Session weather conditions |
| `session_summary` | Quick overview (winner, DNFs, laps, fastest lap) |
| `track_evolution` | How grip and pace changed over the session |
| `overtake_analysis` | Position changes and pace deltas between drivers |
| `identify_driver` | Resolve a fuzzy name to full driver info |
| `list_drivers` | All drivers in the session |
| `session_status` | Check what session is loaded |

The dashboard chat has 4 additional tools that use backend-specific analysis: `energy_analysis`, `tyre_predictions`, `session_insights`, `overtake_probability`, `win_probability`.

### Fuzzy Input Normalization

No need to know exact codes. The package resolves:

| You say | Resolves to |
|---------|-------------|
| "Leclerc", "charles", "LEC", "16" | Charles Leclerc (LEC) |
| "checo", "Perez", "11" | Sergio Perez (PER) |
| "spa" | Belgian Grand Prix |
| "monza" | Italian Grand Prix |
| "silverstone" | British Grand Prix |
| "qualifying", "quali", "Q" | Qualifying session |

---

## Testing

The f1_mcp package has a full test suite:

```bash
cd f1_mcp

# Unit tests only (no network, instant)
pytest tests/ -m "not integration" -v

# Full test suite (downloads F1 data on first run, cached after)
pytest tests/ -v
```

**121 tests** covering:
- 60 normalization tests (driver codes, names, nicknames, numbers, races, sessions)
- 40 session manager tests (lifecycle, data extraction, fuzzy loading, error handling)
- 21 MCP server tests (tool registration, execution, output format)

---

## Project Structure

```
f1_dashboard/
  backend/
    main.py                # FastAPI backend (all endpoints + AI chat)
  frontend/src/
    pages/                 # 11 page components
    components/
      ChatWidget.jsx       # AI chat with tool-call display
      Layout.jsx           # Sidebar navigation
      CircuitSVG.jsx       # SVG circuit renderer
    hooks/
      useApi.js            # Fetch wrapper
  f1_mcp/                  # Standalone MCP server package
    src/f1_mcp/
      normalize.py         # Fuzzy driver/race/session resolution
      session.py           # FastF1 session manager + data extraction
      server.py            # MCP server + tool definitions
    tests/                 # 121 tests (pytest)
    pyproject.toml         # Package config
  cache/                   # FastF1 data cache (auto-created)
  start.sh                 # Start/stop script
  requirements.txt         # Python dependencies
```

---

## Developer Commands

```bash
# Start everything
./start.sh

# Stop everything
./start.sh stop

# Quick restart
./start.sh stop && ./start.sh

# Rebuild frontend + restart
./start.sh stop
cd frontend && npm install && npm run build && cd ..
./start.sh

# Install/update all dependencies
source venv/bin/activate
pip install -r requirements.txt
pip install -e f1_mcp/

# Kill stale processes (if ports are stuck)
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:3000 | xargs kill -9 2>/dev/null

# Run tests
cd f1_mcp && pytest tests/ -v
```

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/session/load` | Load an F1 session |
| `GET /api/session/overview` | Results, weather, strategy, metrics |
| `GET /api/session/drivers` | Driver list with team colors |
| `GET /api/session/telemetry/multi` | Multi-driver telemetry |
| `GET /api/session/laptimes` | Lap times, degradation, SC/VSC |
| `GET /api/session/predictions` | Tyre life, pace-adjusted standings |
| `GET /api/session/energy` | Energy harvest/deploy model |
| `GET /api/session/pitstrategy` | Pit stops, stints, undercut/overcut |
| `GET /api/session/replay` | Win probability per lap |
| `GET /api/session/insights` | Auto-generated race commentary |
| `GET /api/session/overtake-probability` | Overtake scoring |
| `GET /api/session/track-evolution` | Grip/temperature changes |
| `GET /api/session/circuit` | Circuit layout with DRS zones |
| `GET /api/session/trackmap` | Circuit with telemetry overlay |
| `POST /api/session/chat` | AI chat (tool calling) |
| `POST /api/session/debrief` | AI race debrief |
| `GET /api/live/data` | Live timing data |
| `POST /api/live/start` | Start live recording |
| `POST /api/live/stop` | Stop live recording |
| `GET /api/live/driver/{n}` | Live driver detail |
| `GET /api/live/driver/{n}/zones` | Per-zone telemetry analysis |
| `POST /api/compare` | Cross-session comparison |
| `GET /api/events/{year}` | F1 calendar |

---

## Notes

- **Caching:** FastF1 caches session data in `cache/`. First load hits F1 servers; subsequent loads are instant.
- **AI Chat:** Uses tool calling (not context stuffing). Claude picks which data to fetch per question. 21 tools available. Tool calls shown as green tags in the UI.
- **AI Debrief:** Requires an Anthropic API key entered in the UI.
- **Live Timing:** Connects to F1's SignalR stream during live sessions. Incremental parsing for sub-second updates.
- **MCP Server:** The f1_mcp package is a standalone installable that works with Claude Desktop independently of the dashboard.
- **Data:** All F1 data comes from public timing servers via FastF1. No API keys or accounts needed for data access.

---

## License

MIT
