# F1 Telemetry Lab

A full-stack Formula 1 race engineer dashboard built with **FastF1**, **FastAPI**, and **React**. Load any historical session or connect to live timing — explore telemetry, strategy, energy modeling, race replay, and AI-powered analysis through a dark glassmorphism UI.

![React](https://img.shields.io/badge/React-19-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green)
![FastF1](https://img.shields.io/badge/FastF1-3.3+-red)
![Claude](https://img.shields.io/badge/AI-Claude%20Sonnet-purple)

---

## Features

### Race Command Center
Session overview with race results, tyre strategy timeline, weather conditions, and key race metrics (SC/VSC count, DNFs, pit stops, fastest lap).

### Telemetry Lab
Multi-driver telemetry comparison — overlay speed, throttle, and brake traces for any combination of drivers. Circuit map with color-by-speed/throttle/brake/zone modes, auto-detected corner markers, and animated driver trail overlays.

### Performance Studio
Lap time evolution with SC/VSC shading, tyre degradation analysis (slope + R² per stint), tyre life predictions, fuel-corrected lap times, pace-adjusted standings, and overtake probability scoring.

### Pit Strategy
Stint timeline visualization, pit stop details (duration, compound changes), undercut/overcut detection comparing position swaps around pit windows, and safety car event mapping.

### Energy Map
Braking zone analysis, energy harvest/deploy modeling (350kW MGU-K, 4MJ battery — 2026 regulation profiles), battery state-of-charge trace, clipping/regen-clip detection, circuit energy overlay, and ERS status gauges.

### Circuit Lab
Interactive circuit visualization with track outlines, DRS zones, sector markers, and speed/throttle/brake heatmap overlays. Supports all circuits in the F1 calendar.

### Race Replay
Lap-by-lap race simulation with animated circuit map — drivers move around the track with broadcast-style markers (dot + stick + name badge). Gap-based position offsets, pit and lapped-car indicators. Win probability model uses only data available up to the current lap. Prediction accuracy panel with winner correctness, podium overlap, and pairwise order accuracy. Full-race accuracy sweep to see when the model locks onto the correct winner.

### Compare GP
Multi-session and cross-Grand-Prix comparison. Compare driver performance, lap times, and strategies across different race weekends.

### Live Pit Wall
Real-time F1 timing via SignalR stream with incremental data parsing for fast updates. Driver cards with sector times, tyre info, gap tracking, and zone-level telemetry. SC/VSC-aware strategy alerts (MISSED_OPPORTUNITY, SMART_PIT, TYRE_CLIFF).

### AI Debrief
Claude-powered post-race analysis. Generates a race engineer-style debrief with key moments, strategy breakdowns, and next-race predictions.

---

## Tech Stack

| Layer | Tech |
|-------|------|
| **Backend** | Python, FastAPI, FastF1, NumPy, SciPy, Pandas |
| **Frontend** | React 19, Vite, Tailwind CSS, Plotly.js, Framer Motion, Lucide Icons |
| **AI** | Anthropic Claude API |
| **Data** | F1 official timing via FastF1 (cached locally) |

---

## Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+

### Setup

```bash
git clone <your-repo-url>
cd f1_dashboard

# Backend
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn fastf1 numpy scipy pandas anthropic

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

- **Frontend:** http://localhost:3000
- **Backend:** http://localhost:8000

```bash
./start.sh stop
```

### Usage

1. Open http://localhost:3000
2. Select a year, Grand Prix, and session type
3. Click **Load Session** — first load downloads from F1 servers (~10-30s), subsequent loads are cached
4. Navigate to any page from the sidebar

---

## API

| Endpoint | Description |
|----------|-------------|
| `POST /api/session/load` | Load an F1 session |
| `GET /api/session/overview` | Results, weather, strategy, metrics |
| `GET /api/session/drivers` | Driver list with team colors |
| `GET /api/session/telemetry/multi` | Multi-driver telemetry |
| `GET /api/session/laptimes` | Lap times, degradation, SC/VSC |
| `GET /api/session/predictions` | Tyre life, pace-adjusted standings |
| `GET /api/session/energy` | Energy harvest/deploy model |
| `GET /api/session/trackmap` | Circuit with speed/throttle/brake overlay |
| `GET /api/session/pitstrategy` | Pit stops, stints, undercut/overcut |
| `GET /api/session/replay` | Replay standings + win probability |
| `GET /api/session/replay/positions` | Track positions for circuit animation |
| `GET /api/session/replay/sweep` | Full-race accuracy sweep |
| `GET /api/session/circuit` | Circuit data |
| `GET /api/session/overtake-probability` | Overtake scoring |
| `POST /api/session/debrief` | AI race debrief |
| `POST /api/session/chat` | Chat with AI about the session |
| `GET /api/live/data` | Live timing data |
| `GET /api/live/status` | Live stream status |
| `POST /api/live/start` | Start live recording |
| `POST /api/live/stop` | Stop live recording |
| `GET /api/live/driver/{n}` | Live driver detail |
| `GET /api/live/driver/{n}/zones` | Live driver braking zones |
| `GET /api/compare` | Multi-session comparison |
| `GET /api/events/{year}` | F1 calendar events |

---

## Project Structure

```
f1_dashboard/
  backend/
    main.py              # FastAPI endpoints
  frontend/src/
    pages/
      Home.jsx           # Session loader + grouped navigation
      RaceCommand.jsx    # Results, metrics, weather
      TelemetryLab.jsx   # Multi-driver telemetry
      PerformanceLab.jsx # Lap times, degradation
      PitStrategy.jsx    # Pit stops, undercut/overcut
      EnergyMap.jsx      # Energy modeling (2026 regs)
      CircuitLab.jsx     # Circuit visualization
      RaceReplay.jsx     # Lap-by-lap replay
      CompareGP.jsx      # Cross-session comparison
      LivePitWall.jsx    # Real-time timing
      AIDebrief.jsx      # Claude analysis
    components/
      Layout.jsx         # Sidebar navigation
      CircuitSVG.jsx     # SVG circuit renderer
      GlassCard.jsx      # Glassmorphism card
      SessionGate.jsx    # Session guard
      PageHeader.jsx     # Page header
      LoadingSpinner.jsx # F1 car loading animation
      SessionLoader.jsx  # Year/GP/session picker
    hooks/
      useApi.js          # Fetch wrapper
  cache/                 # FastF1 data cache
  start.sh               # Start/stop script
```

---

## Notes

- **Caching:** FastF1 caches session data in `cache/`. First load hits F1 servers; subsequent loads are instant.
- **AI Debrief:** Requires an Anthropic API key entered in the UI.
- **Live timing:** Connects to F1's SignalR stream during live sessions. Uses incremental parsing for sub-second updates even with large data files.
- **Win probability:** Position, gap, tyre age, and compound with softmax temperature. SC/VSC-aware — shifts weights toward tyre freshness when gaps are neutralized.
- **Circuit rendering:** Broadcast-style thick track with Catmull-Rom splines, kerb markings, DRS zones, and driver markers with stick-and-badge labels.

---

## License

MIT
