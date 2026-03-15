# F1 telemetry dashboard

A full-stack Formula 1 race engineer dashboard built with **FastF1**, **FastAPI**, and **React**. Load any historical F1 session and explore telemetry, strategy, energy modeling, and AI-powered race analysis through a glassmorphism dark UI.

![React](https://img.shields.io/badge/React-19-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green)
![FastF1](https://img.shields.io/badge/FastF1-3.3+-red)
![Claude](https://img.shields.io/badge/AI-Claude%20Sonnet-purple)

---

## Features

### Race Command Center
Session overview with race results, tyre strategy timeline, weather conditions, and race metrics (SC/VSC count, DNFs, pit stops, fastest lap).

### Telemetry Lab
Multi-driver telemetry comparison — select any number of drivers and overlay their speed, throttle, and brake traces. Circuit track map with color-by-speed/throttle/brake/zone modes, auto-detected corner markers, and driver tabs.

### Performance Studio
Lap time evolution with SC/VSC overlay, tyre degradation analysis (slope + R-squared per stint), tyre life predictions, pace-adjusted standings, and overtake scoring.

### Pit Strategy
Stint timeline visualization, pit stop details (duration, compound changes), undercut/overcut detection comparing position swaps around pit windows, and safety car event mapping.

### Energy Map
Braking zone analysis, energy harvest/deploy modeling (350kW MGU-K, 4MJ battery — 2026 regs), battery state-of-charge trace, clipping/regen-clip detection, and circuit energy overlay.

### Race Replay
Lap-by-lap race simulation with a win probability model that only uses data available up to the current lap — no peeking at results. Includes a **prediction accuracy panel** showing winner correctness, podium overlap, and pairwise order accuracy vs actual results. Scrub through the race to watch the model converge.

### Live Pit Wall
Real-time F1 timing via SignalR stream. SC/VSC-aware win probability model with strategy alerts (MISSED_OPPORTUNITY, SMART_PIT, TYRE_CLIFF).

### AI Debrief Agent
Claude-powered post-race analysis. Generates a race engineer-style debrief with key moments, strategy breakdowns, and next-race predictions.

---

## Tech Stack

| Layer | Tech |
|-------|------|
| **Backend** | Python, FastAPI, FastF1, NumPy, SciPy, Pandas |
| **Frontend** | React 19, Vite, Tailwind CSS, Plotly.js, Framer Motion, Lucide Icons |
| **AI** | Anthropic Claude API (Sonnet) |
| **Data** | F1 official timing data via FastF1 (cached locally) |

---

## Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+

### Setup

```bash
# Clone the repo
git clone <your-repo-url>
cd f1_dashboard

# Python backend
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn fastf1 numpy scipy pandas anthropic

# React frontend
cd frontend
npm install
cd ..
```

### Run

```bash
chmod +x start.sh
./start.sh
```

This starts both servers:
- **Frontend:** http://localhost:3000
- **Backend:** http://localhost:8000

To stop:
```bash
./start.sh stop
```

### Usage

1. Open http://localhost:3000
2. Select a year, Grand Prix, and session type (Race, Qualifying, etc.)
3. Click **Load Session** — first load downloads data from F1 servers (~10-30s), subsequent loads are instant from cache
4. Navigate to any dashboard page

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/session/load` | Load an F1 session (year, GP, type) |
| `GET /api/session/overview` | Race results, weather, strategy, metrics |
| `GET /api/session/drivers` | Driver list with team colors |
| `GET /api/session/telemetry?d1=VER&d2=HAM` | Two-driver telemetry comparison |
| `GET /api/session/telemetry/multi?drivers=VER,HAM,NOR` | Multi-driver telemetry |
| `GET /api/session/laptimes` | Lap times, degradation, SC/VSC events |
| `GET /api/session/predictions?threshold=1.5` | Tyre life, pace-adjusted standings, overtake scores |
| `GET /api/session/energy?driver=VER` | Energy harvest/deploy model + braking zones |
| `GET /api/session/trackmap?driver=VER` | Circuit X/Y with speed/throttle/brake overlay |
| `GET /api/session/pitstrategy` | Pit stops, stints, undercut/overcut, SC events |
| `GET /api/session/replay?lap=30` | Replay standings + win probability at given lap |
| `POST /api/session/debrief` | AI-generated race debrief (requires Anthropic API key) |
| `GET /api/live/data` | Live timing data from SignalR stream |

---

## Project Structure

```
f1_dashboard/
  backend/
    main.py          # All FastAPI endpoints
  frontend/
    src/
      pages/
        Home.jsx           # Session loader + navigation
        RaceCommand.jsx    # Results, metrics, weather, strategy
        TelemetryLab.jsx   # Multi-driver telemetry comparison
        PerformanceLab.jsx # Lap times, degradation, predictions
        PitStrategy.jsx    # Pit stops, undercut/overcut
        EnergyMap.jsx      # Energy harvest/deploy modeling
        RaceReplay.jsx     # Lap-by-lap replay + accuracy
        LivePitWall.jsx    # Real-time timing
        AIDebrief.jsx      # Claude-powered analysis
      components/
        Layout.jsx         # Sidebar navigation
        GlassCard.jsx      # Glassmorphism card component
        SessionGate.jsx    # Ensures session is loaded
        PageHeader.jsx     # Page title component
        LoadingSpinner.jsx # Loading state
        SessionLoader.jsx  # Year/GP/session picker
      hooks/
        useApi.js          # Fetch wrapper with error handling
  cache/                   # FastF1 data cache (auto-created)
  start.sh                 # Start/stop both servers
  requirements.txt         # Python dependencies
```

---

## Notes

- **Data caching:** FastF1 caches session data locally in `cache/`. First load of a session hits F1 servers; after that it's instant from disk.
- **AI Debrief:** Requires an Anthropic API key entered in the UI. Uses Claude Sonnet for race analysis.
- **Live timing:** The Live Pit Wall connects to F1's SignalR stream during live sessions. Works best during actual race weekends.
- **Win probability model:** Uses position, gap, tyre age, and compound with softmax temperature scaling. SC/VSC-aware — shifts weights to favor tyre freshness when gaps are neutralized.

---

## License

MIT
