import { useState, useEffect } from "react";
import { useApi } from "../hooks/useApi";
import LoadingSpinner from "./LoadingSpinner";

export default function SessionLoader({ onLoaded }) {
  const { call, loading, error } = useApi();
  const [year, setYear] = useState(2024);
  const [events, setEvents] = useState([]);
  const [gp, setGp] = useState("");
  const [sessionType, setSessionType] = useState("R");

  useEffect(() => {
    call(`/api/events/${year}`).then((data) => {
      if (data) {
        setEvents(data.events);
        setGp(data.events[0] || "");
      }
    });
  }, [year]);

  const handleLoad = async () => {
    const data = await call(
      `/api/session/load?year=${year}&gp=${encodeURIComponent(gp)}&session_type=${sessionType}`,
      { method: "POST" }
    );
    if (data) onLoaded(data);
  };

  return (
    <div className="glass p-6 rounded-2xl max-w-md w-full">
      <h3 className="text-lg font-semibold mb-4 text-white">Load Session</h3>

      <div className="space-y-3">
        <div>
          <label className="text-xs text-f1-muted uppercase tracking-wider">Year</label>
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm focus:border-f1-red/50 focus:outline-none transition"
          >
            {[2026, 2025, 2024, 2023, 2022].map((y) => (
              <option key={y} value={y} className="bg-[#1a1a2e]">{y}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs text-f1-muted uppercase tracking-wider">Grand Prix</label>
          <select
            value={gp}
            onChange={(e) => setGp(e.target.value)}
            className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm focus:border-f1-red/50 focus:outline-none transition"
          >
            {events.map((e) => (
              <option key={e} value={e} className="bg-[#1a1a2e]">{e}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs text-f1-muted uppercase tracking-wider">Session</label>
          <select
            value={sessionType}
            onChange={(e) => setSessionType(e.target.value)}
            className="w-full mt-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-sm focus:border-f1-red/50 focus:outline-none transition"
          >
            <option value="R" className="bg-[#1a1a2e]">Race</option>
            <option value="Q" className="bg-[#1a1a2e]">Qualifying</option>
            <option value="S" className="bg-[#1a1a2e]">Sprint</option>
          </select>
        </div>
      </div>

      {error && <p className="text-red-400 text-xs mt-2">{error}</p>}

      <button
        onClick={handleLoad}
        disabled={loading || !gp}
        className="w-full mt-4 bg-f1-red hover:bg-red-700 disabled:opacity-50 text-white font-semibold py-2.5 rounded-lg transition-all duration-200 text-sm"
      >
        {loading ? "Loading session..." : "Load Session"}
      </button>

      {loading && (
        <p className="text-f1-muted text-xs mt-2 text-center">
          First load downloads from F1 API (~30-60s). Cached after that.
        </p>
      )}
    </div>
  );
}
