#!/bin/bash
# F1 Pit Wall — Start/Stop Script
# Usage: ./start.sh        (start both servers)
#        ./start.sh stop   (kill both servers)

DIR="$(cd "$(dirname "$0")" && pwd)"

stop_servers() {
    echo "Stopping all services..."
    # Force-kill anything on these ports
    lsof -ti:8000 2>/dev/null | xargs kill -9 2>/dev/null
    lsof -ti:3000 2>/dev/null | xargs kill -9 2>/dev/null
    # Catch any orphaned processes
    pkill -9 -f "uvicorn backend.main" 2>/dev/null
    pkill -9 -f "vite --port 3000" 2>/dev/null
    pkill -9 -f "vite.*f1_dashboard" 2>/dev/null
    sleep 1
    echo "Stopped."
}

if [ "$1" = "stop" ]; then
    stop_servers
    exit 0
fi

# Stop any existing first
stop_servers

echo ""
echo "  ┌─────────────────────────────────────┐"
echo "  │       F1 PIT WALL — Starting...     │"
echo "  └─────────────────────────────────────┘"
echo ""

# Start backend
cd "$DIR"
./venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
BACK_PID=$!

# Start frontend
cd "$DIR/frontend"
npx vite --port 3000 &
FRONT_PID=$!

# Wait for readiness
echo "Waiting for services..."
for i in {1..20}; do
    BACK_OK=$(curl -s --max-time 1 http://localhost:8000/docs -o /dev/null -w "%{http_code}" 2>/dev/null)
    FRONT_OK=$(curl -s --max-time 1 http://localhost:3000/ -o /dev/null -w "%{http_code}" 2>/dev/null)
    [ "$BACK_OK" = "200" ] && [ "$FRONT_OK" = "200" ] && break
    sleep 1
done

echo ""
echo "  ┌─────────────────────────────────────┐"

if curl -s --max-time 2 http://localhost:8000/docs -o /dev/null 2>/dev/null; then
    echo "  │  ✅ Backend   http://localhost:8000  │"
else
    echo "  │  ❌ Backend failed (check terminal)  │"
fi

if curl -s --max-time 2 http://localhost:3000/ -o /dev/null 2>/dev/null; then
    echo "  │  ✅ Frontend  http://localhost:3000  │"
else
    echo "  │  ❌ Frontend failed (check terminal) │"
fi

echo "  │                                     │"
echo "  │  Stop:  ./start.sh stop             │"
echo "  │  Or:    Ctrl+C                      │"
echo "  └─────────────────────────────────────┘"
echo ""

# Wait for both — Ctrl+C kills everything
trap "stop_servers; exit 0" INT TERM
wait
