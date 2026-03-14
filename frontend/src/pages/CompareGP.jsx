import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  GitCompareArrows, Loader2, ArrowRight, Trophy,
  Gauge, Zap, ChevronDown,
} from "lucide-react";
import Plot from "react-plotly.js";
import GlassCard from "../components/GlassCard";
import PageHeader from "../components/PageHeader";
import { useApi } from "../hooks/useApi";

const plotLayout = {
  template: "plotly_dark",
  paper_bgcolor: "transparent",
  plot_bgcolor: "rgba(255,255,255,0.02)",
  font: { color: "#a1a1aa" },
  margin: { l: 50, r: 20, t: 30, b: 40 },
};
const plotConfig = { displayModeBar: false, responsive: true };

const YEARS = [];
for (let y = 2018; y <= 2026; y++) YEARS.push(y);

function DriverAvatar({ driver, size = 10 }) {
  if (driver?.headshot) {
    return (
      <img
        src={driver.headshot}
        alt={driver.code}
        className={`w-${size} h-${size} rounded-full object-cover bg-white/10 flex-shrink-0`}
        onError={(e) => { e.target.style.display = "none"; }}
      />
    );
  }
  return (
    <span
      className={`w-${size} h-${size} rounded-full flex items-center justify-center font-bold flex-shrink-0 text-sm`}
      style={{ backgroundColor: (driver?.color || "#888") + "30", color: driver?.color || "#888" }}
    >
      {driver?.code?.[0] || "?"}
    </span>
  );
}

function SessionSelector({ label, side, year, setYear, gp, setGp, driver, setDriver, events, drivers, loadingEvents, loadingDrivers }) {
  const borderColor = side === "A" ? "border-cyan-500/30" : "border-orange-500/30";
  const accentColor = side === "A" ? "text-cyan-400" : "text-orange-400";
  const bgColor = side === "A" ? "bg-cyan-500/10" : "bg-orange-500/10";

  return (
    <GlassCard className={`p-5 border ${borderColor}`} hover delay={side === "A" ? 0.05 : 0.08}>
      <div className="flex items-center gap-2 mb-4">
        <span className={`w-6 h-6 rounded-lg ${bgColor} flex items-center justify-center text-xs font-bold ${accentColor}`}>
          {side}
        </span>
        <h3 className={`text-sm font-bold ${accentColor}`}>{label}</h3>
      </div>

      <div className="space-y-3">
        {/* Year */}
        <div>
          <label className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1 block">Year</label>
          <div className="relative">
            <select
              value={year}
              onChange={(e) => setYear(parseInt(e.target.value, 10))}
              className="w-full bg-white/5 text-white text-sm rounded-xl px-4 py-2.5 border border-f1-border
                         focus:outline-none focus:border-f1-red/50 appearance-none cursor-pointer"
            >
              {YEARS.map((y) => (
                <option key={y} value={y} className="bg-zinc-900">{y}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
          </div>
        </div>

        {/* GP */}
        <div>
          <label className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1 block">Grand Prix</label>
          <div className="relative">
            <select
              value={gp}
              onChange={(e) => setGp(e.target.value)}
              disabled={loadingEvents || events.length === 0}
              className="w-full bg-white/5 text-white text-sm rounded-xl px-4 py-2.5 border border-f1-border
                         focus:outline-none focus:border-f1-red/50 appearance-none cursor-pointer
                         disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <option value="" className="bg-zinc-900">
                {loadingEvents ? "Loading..." : "Select GP"}
              </option>
              {events.map((e) => (
                <option key={e} value={e} className="bg-zinc-900">{e}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
          </div>
        </div>

        {/* Driver */}
        <div>
          <label className="text-[10px] text-zinc-500 uppercase tracking-widest mb-1 block">Driver</label>
          <div className="relative">
            <select
              value={driver}
              onChange={(e) => setDriver(e.target.value)}
              disabled={loadingDrivers || drivers.length === 0}
              className="w-full bg-white/5 text-white text-sm rounded-xl px-4 py-2.5 border border-f1-border
                         focus:outline-none focus:border-f1-red/50 appearance-none cursor-pointer
                         disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <option value="" className="bg-zinc-900">
                {loadingDrivers ? "Loading drivers..." : "Select driver"}
              </option>
              {drivers.map((d) => (
                <option key={d.code} value={d.code} className="bg-zinc-900">
                  {d.code} — {d.name} ({d.team})
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500 pointer-events-none" />
          </div>
        </div>

        {/* Selected driver card */}
        {driver && drivers.length > 0 && (() => {
          const d = drivers.find((x) => x.code === driver);
          if (!d) return null;
          return (
            <div className="flex items-center gap-3 p-3 rounded-xl bg-white/5 border border-f1-border">
              <DriverAvatar driver={d} />
              <div className="flex-1 min-w-0">
                <p className="text-white font-bold text-sm truncate">{d.name}</p>
                <p className="text-zinc-400 text-xs">{d.team} — P{d.position || "?"}</p>
              </div>
              <span className="w-1.5 h-10 rounded-full flex-shrink-0" style={{ backgroundColor: d.color }} />
            </div>
          );
        })()}
      </div>
    </GlassCard>
  );
}

export default function CompareGP() {
  const api = useApi();

  // Side A state
  const [yearA, setYearA] = useState(2025);
  const [gpA, setGpA] = useState("");
  const [driverA, setDriverA] = useState("");
  const [eventsA, setEventsA] = useState([]);
  const [driversA, setDriversA] = useState([]);
  const [loadingEventsA, setLoadingEventsA] = useState(false);
  const [loadingDriversA, setLoadingDriversA] = useState(false);

  // Side B state
  const [yearB, setYearB] = useState(2026);
  const [gpB, setGpB] = useState("");
  const [driverB, setDriverB] = useState("");
  const [eventsB, setEventsB] = useState([]);
  const [driversB, setDriversB] = useState([]);
  const [loadingEventsB, setLoadingEventsB] = useState(false);
  const [loadingDriversB, setLoadingDriversB] = useState(false);

  // Comparison result
  const [result, setResult] = useState(null);
  const [comparing, setComparing] = useState(false);
  const [error, setError] = useState(null);

  // Fetch events when year changes
  useEffect(() => {
    setLoadingEventsA(true);
    setEventsA([]);
    setGpA("");
    setDriversA([]);
    setDriverA("");
    api.call(`/api/events/${yearA}`).then((d) => {
      setEventsA(d?.events || []);
      setLoadingEventsA(false);
    });
  }, [yearA]);

  useEffect(() => {
    setLoadingEventsB(true);
    setEventsB([]);
    setGpB("");
    setDriversB([]);
    setDriverB("");
    api.call(`/api/events/${yearB}`).then((d) => {
      setEventsB(d?.events || []);
      setLoadingEventsB(false);
    });
  }, [yearB]);

  // Fetch drivers when GP changes
  useEffect(() => {
    if (!gpA) return;
    setLoadingDriversA(true);
    setDriversA([]);
    setDriverA("");
    api.call(`/api/compare/drivers?year=${yearA}&gp=${encodeURIComponent(gpA)}`).then((d) => {
      setDriversA(d?.drivers || []);
      setLoadingDriversA(false);
    });
  }, [yearA, gpA]);

  useEffect(() => {
    if (!gpB) return;
    setLoadingDriversB(true);
    setDriversB([]);
    setDriverB("");
    api.call(`/api/compare/drivers?year=${yearB}&gp=${encodeURIComponent(gpB)}`).then((d) => {
      setDriversB(d?.drivers || []);
      setLoadingDriversB(false);
    });
  }, [yearB, gpB]);

  const canCompare = driverA && driverB && gpA && gpB;

  const runComparison = async () => {
    if (!canCompare) return;
    setComparing(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          yearA, gpA, yearB, gpB, driverA, driverB,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Comparison failed");
      }
      const data = await res.json();
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setComparing(false);
    }
  };

  const sA = result?.sessionA;
  const sB = result?.sessionB;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Compare GPs"
        subtitle="Head-to-head telemetry comparison across sessions"
        icon={GitCompareArrows}
      />

      {/* Selectors */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SessionSelector
          label="Session A"
          side="A"
          year={yearA} setYear={setYearA}
          gp={gpA} setGp={setGpA}
          driver={driverA} setDriver={setDriverA}
          events={eventsA} drivers={driversA}
          loadingEvents={loadingEventsA} loadingDrivers={loadingDriversA}
        />
        <SessionSelector
          label="Session B"
          side="B"
          year={yearB} setYear={setYearB}
          gp={gpB} setGp={setGpB}
          driver={driverB} setDriver={setDriverB}
          events={eventsB} drivers={driversB}
          loadingEvents={loadingEventsB} loadingDrivers={loadingDriversB}
        />
      </div>

      {/* Compare button */}
      <div className="flex justify-center">
        <button
          onClick={runComparison}
          disabled={!canCompare || comparing}
          className="flex items-center gap-3 px-8 py-3 rounded-2xl bg-f1-red text-white font-bold text-sm
                     hover:bg-f1-red/80 transition-all disabled:opacity-30 disabled:cursor-not-allowed
                     shadow-lg shadow-f1-red/20 hover:shadow-f1-red/40"
        >
          {comparing ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Loading sessions (this may take a moment)...
            </>
          ) : (
            <>
              <GitCompareArrows className="w-5 h-5" />
              Compare
            </>
          )}
        </button>
      </div>

      {error && (
        <div className="text-center text-red-400 text-sm py-4 px-6 rounded-xl bg-red-500/10 border border-red-500/20">
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-6"
        >
          {/* Summary cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <GlassCard className="p-4 text-center" hover delay={0.05}>
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest">Lap Time Delta</span>
              <p className={`text-2xl font-bold mt-1 ${
                result.summary.lapTimeDelta > 0 ? "text-orange-400" : result.summary.lapTimeDelta < 0 ? "text-cyan-400" : "text-zinc-400"
              }`}>
                {result.summary.lapTimeDelta != null
                  ? `${result.summary.lapTimeDelta > 0 ? "+" : ""}${result.summary.lapTimeDelta.toFixed(3)}s`
                  : "—"}
              </p>
              <span className="text-[10px] text-zinc-500">
                {result.summary.lapTimeDelta > 0 ? `${sB?.driver} faster` : result.summary.lapTimeDelta < 0 ? `${sA?.driver} faster` : "Equal"}
              </span>
            </GlassCard>

            <GlassCard className="p-4 text-center" hover delay={0.08}>
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest">Top Speed</span>
              <div className="flex items-center justify-center gap-3 mt-1">
                <span className="text-lg font-bold text-cyan-400">{result.summary.maxSpeedA}</span>
                <span className="text-zinc-600 text-xs">vs</span>
                <span className="text-lg font-bold text-orange-400">{result.summary.maxSpeedB}</span>
              </div>
              <span className="text-[10px] text-zinc-500">km/h</span>
            </GlassCard>

            <GlassCard className="p-4 text-center" hover delay={0.11}>
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest">Avg Speed</span>
              <div className="flex items-center justify-center gap-3 mt-1">
                <span className="text-lg font-bold text-cyan-400">{result.summary.avgSpeedA}</span>
                <span className="text-zinc-600 text-xs">vs</span>
                <span className="text-lg font-bold text-orange-400">{result.summary.avgSpeedB}</span>
              </div>
              <span className="text-[10px] text-zinc-500">km/h</span>
            </GlassCard>

            <GlassCard className="p-4 text-center" hover delay={0.14}>
              <span className="text-[10px] text-zinc-500 uppercase tracking-widest">Sectors Won</span>
              <div className="flex items-center justify-center gap-3 mt-1">
                <span className="text-lg font-bold text-cyan-400">{result.summary.sectorsWonA}</span>
                <span className="text-zinc-600 text-xs">vs</span>
                <span className="text-lg font-bold text-orange-400">{result.summary.sectorsWonB}</span>
              </div>
              <span className="text-[10px] text-zinc-500">of {result.sectors?.length || 20}</span>
            </GlassCard>
          </div>

          {/* Session labels */}
          <div className="grid grid-cols-2 gap-4">
            {[
              { s: sA, accent: "cyan", side: "A" },
              { s: sB, accent: "orange", side: "B" },
            ].map(({ s, accent, side }) => (
              <div key={side} className={`flex items-center gap-3 px-4 py-2 rounded-xl bg-${accent}-500/5 border border-${accent}-500/20`}>
                <span className={`w-3 h-3 rounded-full bg-${accent}-400`} />
                <div>
                  <span className={`text-sm font-bold text-${accent}-400`}>{s?.driver}</span>
                  <span className="text-zinc-500 text-xs ml-2">{s?.year} {s?.event}</span>
                  <span className="text-zinc-600 text-xs ml-2">({s?.team})</span>
                </div>
                {s?.lapTime && (
                  <span className="ml-auto font-mono text-xs text-zinc-400">{s.lapTime}</span>
                )}
              </div>
            ))}
          </div>

          {/* Speed overlay */}
          <GlassCard className="p-4" hover delay={0.15}>
            <h3 className="text-sm font-semibold text-white pb-2 uppercase tracking-widest flex items-center gap-2">
              <Gauge className="w-4 h-4 text-zinc-500" /> Speed Comparison
            </h3>
            <Plot
              data={[
                {
                  type: "scatter", mode: "lines",
                  x: result.distance, y: result.speedA,
                  name: `${sA?.driver} (${sA?.year})`,
                  line: { color: "#22d3ee", width: 1.5 },
                  hovertemplate: `${sA?.driver}: %{y:.0f} km/h<extra></extra>`,
                },
                {
                  type: "scatter", mode: "lines",
                  x: result.distance, y: result.speedB,
                  name: `${sB?.driver} (${sB?.year})`,
                  line: { color: "#fb923c", width: 1.5 },
                  hovertemplate: `${sB?.driver}: %{y:.0f} km/h<extra></extra>`,
                },
              ]}
              layout={{
                ...plotLayout,
                height: 300,
                legend: { orientation: "h", y: 1.12, font: { size: 11 } },
                xaxis: {
                  title: { text: "Distance (m)", font: { size: 10, color: "#71717a" } },
                  color: "#71717a", gridcolor: "rgba(255,255,255,0.03)",
                },
                yaxis: {
                  title: { text: "Speed (km/h)", font: { size: 10, color: "#71717a" } },
                  color: "#71717a", gridcolor: "rgba(255,255,255,0.03)",
                },
                margin: { l: 50, r: 20, t: 40, b: 40 },
              }}
              config={plotConfig}
              useResizeHandler
              style={{ width: "100%" }}
            />
          </GlassCard>

          {/* Delta time */}
          <GlassCard className="p-4" hover delay={0.18}>
            <h3 className="text-sm font-semibold text-white pb-2 uppercase tracking-widest flex items-center gap-2">
              <Trophy className="w-4 h-4 text-zinc-500" /> Delta Time
              <span className="text-[10px] text-zinc-500 font-normal normal-case ml-2">
                Above zero = {sA?.driver} faster | Below zero = {sB?.driver} faster
              </span>
            </h3>
            <Plot
              data={[
                {
                  type: "scatter", mode: "lines",
                  x: result.distance, y: result.deltaTime,
                  line: { color: "#E10600", width: 2 },
                  fill: "tozeroy",
                  fillcolor: result.deltaTime?.[result.deltaTime.length - 1] > 0
                    ? "rgba(34,211,238,0.08)"
                    : "rgba(251,146,60,0.08)",
                  hovertemplate: "Delta: %{y:.3f}s<extra></extra>",
                },
              ]}
              layout={{
                ...plotLayout,
                height: 220,
                xaxis: {
                  title: { text: "Distance (m)", font: { size: 10, color: "#71717a" } },
                  color: "#71717a", gridcolor: "rgba(255,255,255,0.03)",
                },
                yaxis: {
                  title: { text: "Delta (s)", font: { size: 10, color: "#71717a" } },
                  color: "#71717a", gridcolor: "rgba(255,255,255,0.03)",
                  zeroline: true, zerolinecolor: "rgba(255,255,255,0.15)", zerolinewidth: 1,
                },
                margin: { l: 50, r: 20, t: 10, b: 40 },
                shapes: [{
                  type: "line", x0: 0, x1: 1, xref: "paper",
                  y0: 0, y1: 0, yref: "y",
                  line: { color: "rgba(255,255,255,0.2)", width: 1, dash: "dash" },
                }],
              }}
              config={plotConfig}
              useResizeHandler
              style={{ width: "100%" }}
            />
          </GlassCard>

          {/* Throttle & Brake */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <GlassCard className="p-4" hover delay={0.2}>
              <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-1 flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5" /> Throttle
              </h3>
              <Plot
                data={[
                  {
                    type: "scatter", mode: "lines",
                    x: result.distance, y: result.throttleA,
                    name: sA?.driver, line: { color: "#22d3ee", width: 1.2 },
                    hovertemplate: `${sA?.driver}: %{y:.0f}%<extra></extra>`,
                  },
                  {
                    type: "scatter", mode: "lines",
                    x: result.distance, y: result.throttleB,
                    name: sB?.driver, line: { color: "#fb923c", width: 1.2 },
                    hovertemplate: `${sB?.driver}: %{y:.0f}%<extra></extra>`,
                  },
                ]}
                layout={{
                  ...plotLayout, height: 200,
                  legend: { orientation: "h", y: 1.15, font: { size: 10 } },
                  xaxis: { color: "#71717a", gridcolor: "rgba(255,255,255,0.03)" },
                  yaxis: { color: "#71717a", gridcolor: "rgba(255,255,255,0.03)", range: [0, 105] },
                  margin: { l: 40, r: 10, t: 30, b: 30 },
                }}
                config={plotConfig} useResizeHandler style={{ width: "100%" }}
              />
            </GlassCard>

            <GlassCard className="p-4" hover delay={0.22}>
              <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-1 flex items-center gap-1.5">
                <span className="w-3.5 h-3.5 rounded-sm bg-red-500/30 flex items-center justify-center text-[8px] text-red-400 font-bold">B</span>
                Brake
              </h3>
              <Plot
                data={[
                  {
                    type: "scatter", mode: "lines",
                    x: result.distance, y: result.brakeA,
                    name: sA?.driver, line: { color: "#22d3ee", width: 1.2 },
                    hovertemplate: `${sA?.driver}: %{y:.0f}%<extra></extra>`,
                  },
                  {
                    type: "scatter", mode: "lines",
                    x: result.distance, y: result.brakeB,
                    name: sB?.driver, line: { color: "#fb923c", width: 1.2 },
                    hovertemplate: `${sB?.driver}: %{y:.0f}%<extra></extra>`,
                  },
                ]}
                layout={{
                  ...plotLayout, height: 200,
                  legend: { orientation: "h", y: 1.15, font: { size: 10 } },
                  xaxis: { color: "#71717a", gridcolor: "rgba(255,255,255,0.03)" },
                  yaxis: { color: "#71717a", gridcolor: "rgba(255,255,255,0.03)", range: [0, 105] },
                  margin: { l: 40, r: 10, t: 30, b: 30 },
                }}
                config={plotConfig} useResizeHandler style={{ width: "100%" }}
              />
            </GlassCard>
          </div>

          {/* Track map with speed advantage */}
          {result.trackX && result.trackY && (
            <GlassCard className="p-4" hover delay={0.24}>
              <h3 className="text-sm font-semibold text-white pb-2 uppercase tracking-widest">
                Track Speed Advantage
              </h3>
              <Plot
                data={[
                  {
                    type: "scatter", mode: "markers",
                    x: result.trackX, y: result.trackY,
                    marker: {
                      color: result.speedA.map((a, i) => a - result.speedB[i]),
                      colorscale: [
                        [0, "#fb923c"],
                        [0.5, "#333"],
                        [1, "#22d3ee"],
                      ],
                      size: 4,
                      colorbar: {
                        title: { text: `← ${sB?.driver} faster | ${sA?.driver} faster →`, font: { color: "#a1a1aa", size: 9 } },
                        tickfont: { color: "#a1a1aa" },
                        ticksuffix: " km/h",
                        thickness: 12, len: 0.6,
                      },
                      cmid: 0,
                    },
                    hovertemplate: result.speedA.map(
                      (a, i) =>
                        `${sA?.driver}: ${a?.toFixed(0)} km/h<br>${sB?.driver}: ${result.speedB[i]?.toFixed(0)} km/h<br>Δ ${(a - result.speedB[i])?.toFixed(0)} km/h<extra></extra>`
                    ),
                    showlegend: false,
                  },
                ]}
                layout={{
                  ...plotLayout, height: 500,
                  xaxis: { scaleanchor: "y", showgrid: false, zeroline: false, showticklabels: false },
                  yaxis: { showgrid: false, zeroline: false, showticklabels: false },
                  margin: { l: 10, r: 10, t: 10, b: 10 },
                  annotations: (result.corners || []).map((c) => ({
                    x: c.x, y: c.y,
                    text: `T${c.number}`,
                    showarrow: false,
                    font: { size: 9, color: "#f1f1f1" },
                    bgcolor: "rgba(0,0,0,0.6)",
                    borderpad: 2,
                  })),
                }}
                config={plotConfig} useResizeHandler style={{ width: "100%" }}
              />
            </GlassCard>
          )}

          {/* Corner analysis table */}
          {result.corners?.length > 0 && (
            <GlassCard className="overflow-hidden" hover delay={0.26}>
              <h3 className="text-sm font-semibold text-white px-5 pt-4 pb-2 uppercase tracking-widest">
                Corner-by-Corner Comparison
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead>
                    <tr className="border-b border-f1-border text-zinc-500 uppercase text-[10px] tracking-wider">
                      <th className="px-5 py-2">Turn</th>
                      <th className="px-5 py-2">
                        <span className="text-cyan-400">{sA?.driver}</span> Speed
                      </th>
                      <th className="px-5 py-2">
                        <span className="text-orange-400">{sB?.driver}</span> Speed
                      </th>
                      <th className="px-5 py-2">Delta</th>
                      <th className="px-5 py-2">Advantage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.corners.map((c) => {
                      const delta = c.speedA - c.speedB;
                      return (
                        <tr key={c.number} className="border-b border-f1-border/40 hover:bg-white/[0.03] transition-colors">
                          <td className="px-5 py-2 font-bold text-white">T{c.number}</td>
                          <td className="px-5 py-2 font-mono text-cyan-400">{Math.round(c.speedA)} km/h</td>
                          <td className="px-5 py-2 font-mono text-orange-400">{Math.round(c.speedB)} km/h</td>
                          <td className="px-5 py-2 font-mono">
                            <span className={delta > 0 ? "text-cyan-400" : delta < 0 ? "text-orange-400" : "text-zinc-500"}>
                              {delta > 0 ? "+" : ""}{Math.round(delta)} km/h
                            </span>
                          </td>
                          <td className="px-5 py-2">
                            <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                              delta > 2 ? "bg-cyan-500/10 text-cyan-400"
                              : delta < -2 ? "bg-orange-500/10 text-orange-400"
                              : "bg-zinc-500/10 text-zinc-400"
                            }`}>
                              {delta > 2 ? sA?.driver : delta < -2 ? sB?.driver : "Even"}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </GlassCard>
          )}

          {/* Sector heatmap comparison */}
          {result.sectors?.length > 0 && (
            <GlassCard className="p-5" hover delay={0.28}>
              <h3 className="text-sm font-semibold text-white pb-3 uppercase tracking-widest">
                Sector Speed Advantage
              </h3>
              <div className="flex gap-1">
                {result.sectors.map((s) => {
                  const diff = s.speedA - s.speedB;
                  const intensity = Math.min(Math.abs(diff) / 15, 1);
                  const bg = diff > 0
                    ? `rgba(34, 211, 238, ${0.1 + intensity * 0.6})`
                    : `rgba(251, 146, 60, ${0.1 + intensity * 0.6})`;
                  return (
                    <div key={s.sector} className="flex-1 group relative">
                      <div
                        className="h-8 rounded-sm transition-all group-hover:h-10"
                        style={{ backgroundColor: bg }}
                      />
                      <span className="text-[8px] text-zinc-500 text-center block mt-1">{s.sector}</span>
                      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 rounded bg-black/80 text-[10px] text-white whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                        {sA?.driver}: {s.speedA} km/h<br />
                        {sB?.driver}: {s.speedB} km/h<br />
                        Max: {s.maxSpeedA} vs {s.maxSpeedB}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="flex justify-between mt-2">
                <span className="text-[10px] text-orange-400">{sB?.driver} faster</span>
                <span className="text-[10px] text-cyan-400">{sA?.driver} faster</span>
              </div>
            </GlassCard>
          )}
        </motion.div>
      )}
    </div>
  );
}
