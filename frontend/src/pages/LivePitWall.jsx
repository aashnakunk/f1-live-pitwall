import { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Plot from "react-plotly.js";
import {
  Radio, Wifi, WifiOff, Play, Square, RefreshCw,
  Clock, Trash2, Activity, Zap, TrendingDown, Battery, Gauge, Flag,
  BatteryCharging, BatteryLow, BatteryMedium, BatteryFull, X, Info,
} from "lucide-react";
import GlassCard from "../components/GlassCard";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import { useApi } from "../hooks/useApi";

const miniPlotLayout = {
  template: "plotly_dark",
  paper_bgcolor: "transparent",
  plot_bgcolor: "rgba(255,255,255,0.02)",
  font: { color: "#a1a1aa", size: 9 },
  margin: { l: 30, r: 10, t: 5, b: 20 },
  showlegend: false,
  xaxis: { showticklabels: false, showgrid: false, zeroline: false },
};
const plotConfig = { displayModeBar: false, responsive: true };

const COMPOUND_COLORS = {
  SOFT: "#FF3333", MEDIUM: "#FFC300", HARD: "#FFFFFF",
  INTERMEDIATE: "#39B54A", WET: "#0067FF", "?": "#555",
};

const FLAG_CONFIG = {
  CLIPPING: { icon: Zap, color: "#f97316", bg: "bg-orange-500/10", border: "border-orange-500/20", text: "text-orange-300", label: "Battery Clipping" },
  LIFT_COAST: { icon: TrendingDown, color: "#3b82f6", bg: "bg-blue-500/10", border: "border-blue-500/20", text: "text-blue-300", label: "Lift & Coast" },
  ENERGY_SAVING: { icon: Battery, color: "#eab308", bg: "bg-yellow-500/10", border: "border-yellow-500/20", text: "text-yellow-300", label: "Energy Saving" },
};

const FLAG_DEFINITIONS = {
  CLIPPING: {
    title: "Battery Clipping",
    what: "The car's battery (ERS) has run out of stored energy. The MGU-K can no longer deploy its additional 350kW of electric power.",
    how: "Detected when: full throttle (>98%) + no braking + speed >250 km/h, but speed is NOT increasing. The car should be accelerating but isn't — power is limited.",
    impact: "Driver loses ~3-5 km/h on straights. Lap time cost: 0.3-0.8s depending on track. More clipping = worse energy management earlier in the lap.",
    severity: "high",
  },
  LIFT_COAST: {
    title: "Lift & Coast",
    what: "The driver lifts off the throttle early before a braking zone, coasting at high speed to save energy and brake wear.",
    how: "Detected when: throttle <50% + no braking + speed >200 km/h. The driver is deliberately not accelerating OR braking — just coasting.",
    impact: "Costs ~0.1-0.3s per corner but saves ERS energy for deployment elsewhere. Strategic trade-off managed by the race engineer.",
    severity: "medium",
  },
  ENERGY_SAVING: {
    title: "Energy Saving Mode",
    what: "The car's power unit is deploying less energy than earlier in the stint — acceleration is weaker despite similar throttle inputs.",
    how: "Detected by comparing acceleration in the first half vs second half of the telemetry window. A >30% drop in acceleration rate triggers this flag.",
    impact: "Often seen in the second half of stints or when managing battery for a critical overtake/defense later. Can cost 0.5-1.5s per lap.",
    severity: "low",
  },
  ERS_DEPLOY: {
    title: "Potential ERS Deployment",
    what: "Estimated percentage of time the MGU-K electric motor is actively boosting the car's power. In 2026, the MGU-K adds 350kW (from a 4MJ battery).",
    how: "We measure: when at full throttle (>95%), is speed actually increasing (>2 km/h gain)? The ratio of 'accelerating' vs 'total full throttle' = estimated deployment rate.",
    impact: "Higher % = more electric boost available. Below 40% suggests the driver is conserving energy or the battery is depleted. This is an ESTIMATE — real battery data isn't public.",
    severity: "info",
  },
};

function GlassDefinition({ type, onClose }) {
  const def = FLAG_DEFINITIONS[type];
  if (!def) return null;
  const severityColors = {
    high: "border-orange-500/30 bg-orange-500/5",
    medium: "border-blue-500/30 bg-blue-500/5",
    low: "border-yellow-500/30 bg-yellow-500/5",
    info: "border-emerald-500/30 bg-emerald-500/5",
  };
  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 10, scale: 0.95 }}
      className={`absolute z-50 left-0 right-0 mt-2 rounded-xl border backdrop-blur-xl p-4 shadow-2xl ${severityColors[def.severity]}`}
      style={{ background: "rgba(15, 15, 20, 0.92)" }}
    >
      <div className="flex items-start justify-between mb-3">
        <h4 className="text-white font-bold text-sm">{def.title}</h4>
        <button onClick={onClose} className="text-zinc-500 hover:text-white transition"><X size={14} /></button>
      </div>
      <div className="space-y-2.5 text-[11px] leading-relaxed">
        <div>
          <span className="text-zinc-400 font-semibold uppercase tracking-wider text-[9px]">What is it</span>
          <p className="text-zinc-300 mt-0.5">{def.what}</p>
        </div>
        <div>
          <span className="text-zinc-400 font-semibold uppercase tracking-wider text-[9px]">How we detect it</span>
          <p className="text-zinc-300 mt-0.5">{def.how}</p>
        </div>
        <div>
          <span className="text-zinc-400 font-semibold uppercase tracking-wider text-[9px]">Performance impact</span>
          <p className="text-zinc-300 mt-0.5">{def.impact}</p>
        </div>
      </div>
    </motion.div>
  );
}

function BatteryGauge({ value }) {
  // value: 0-1 (estimated deployment ratio)
  const pct = Math.min(Math.max((value || 0) * 100, 0), 100);
  const segments = 8;
  const filledSegs = Math.round((pct / 100) * segments);
  const color = pct > 70 ? "#4ade80" : pct > 40 ? "#FF8000" : "#ef4444";
  const BatIcon = pct > 70 ? BatteryFull : pct > 40 ? BatteryMedium : pct > 15 ? BatteryLow : BatteryCharging;

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative w-14 h-24 rounded-lg border-2 border-zinc-600 bg-black/40 p-1 flex flex-col-reverse gap-0.5"
        style={{ borderColor: color + "60" }}>
        {/* Battery cap */}
        <div className="absolute -top-2 left-1/2 -translate-x-1/2 w-5 h-2 rounded-t-sm" style={{ background: color + "40", border: `1px solid ${color}40` }} />
        {/* Segments */}
        {Array.from({ length: segments }).map((_, i) => (
          <div
            key={i}
            className="flex-1 rounded-sm transition-all duration-700"
            style={{
              background: i < filledSegs ? color : "rgba(255,255,255,0.03)",
              opacity: i < filledSegs ? 0.7 + (i / segments) * 0.3 : 1,
              boxShadow: i < filledSegs ? `0 0 8px ${color}40` : "none",
            }}
          />
        ))}
      </div>
      <div className="flex items-center gap-1">
        <BatIcon size={11} style={{ color }} />
        <span className="font-mono text-sm font-bold" style={{ color }}>{pct.toFixed(0)}%</span>
      </div>
      <span className="text-[8px] text-zinc-500 uppercase tracking-wider">Potential Deploy</span>
    </div>
  );
}

export default function LivePitWall() {
  const { call, loading } = useApi();
  const [status, setStatus] = useState(null);
  const [liveData, setLiveData] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [selectedDrivers, setSelectedDrivers] = useState(new Set());
  const [driverDetails, setDriverDetails] = useState({});
  const [circuitOutline, setCircuitOutline] = useState([]);
  const [openDefinition, setOpenDefinition] = useState(null); // e.g., "CLIPPING" or "ERS_DEPLOY"
  const [zoneData, setZoneData] = useState({}); // per driver zone analysis
  const intervalRef = useRef(null);

  useEffect(() => { fetchStatus(); fetchData(); fetchCircuit(); }, []);

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(() => { fetchData(); fetchStatus(); }, 1000);
    } else if (intervalRef.current) {
      clearInterval(intervalRef.current);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [autoRefresh]);

  useEffect(() => {
    if (!autoRefresh || selectedDrivers.size === 0) return;
    const id = setInterval(() => {
      selectedDrivers.forEach((num) => fetchDriverDetail(num));
    }, 1000);
    return () => clearInterval(id);
  }, [autoRefresh, selectedDrivers]);

  const fetchStatus = async () => { const d = await call("/api/live/status"); if (d) setStatus(d); };
  const fetchData = async () => { const d = await call("/api/live/data"); if (d) setLiveData(d); };
  const fetchCircuit = async () => {
    const d = await call("/api/live/circuit");
    if (d?.outline?.length > 0) setCircuitOutline(d.outline);
  };
  const startRecording = async () => { await call("/api/live/start", { method: "POST" }); setAutoRefresh(true); fetchStatus(); };
  const stopRecording = async () => { await call("/api/live/stop", { method: "POST" }); setAutoRefresh(false); fetchStatus(); };
  const clearData = async () => { await call("/api/live/clear", { method: "POST" }); setLiveData(null); fetchStatus(); };

  const fetchDriverDetail = async (driverNumber) => {
    const data = await call(`/api/live/driver/${driverNumber}`);
    if (data) setDriverDetails((prev) => ({ ...prev, [driverNumber]: data }));
    // Also fetch zone analysis for heatmap
    const zones = await call(`/api/live/driver/${driverNumber}/zones`);
    if (zones) setZoneData((prev) => ({ ...prev, [driverNumber]: zones }));
  };

  const toggleDriver = (driverNumber) => {
    setSelectedDrivers((prev) => {
      const next = new Set(prev);
      if (next.has(driverNumber)) {
        next.delete(driverNumber);
      } else {
        next.add(driverNumber);
        fetchDriverDetail(driverNumber);
      }
      return next;
    });
  };

  const selectAll = () => {
    if (!liveData?.timing) return;
    const all = new Set(liveData.timing.map((d) => d.driverNumber));
    setSelectedDrivers(all);
    all.forEach((num) => fetchDriverDetail(num));
  };
  const selectNone = () => setSelectedDrivers(new Set());

  const isRecording = status?.recording;
  const hasData = liveData?.timing?.length > 0;

  return (
    <div className="space-y-6">
      <PageHeader title="Live Pit Wall" subtitle="Real-time driver telemetry analysis" icon={Radio} />

      {/* Controls bar */}
      <GlassCard className="p-4" delay={0.1}>
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              {isRecording ? (
                <>
                  <span className="relative flex h-3 w-3">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-500 opacity-75" />
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500" />
                  </span>
                  <span className="text-red-400 text-sm font-semibold uppercase tracking-wide">Recording Live</span>
                </>
              ) : hasData ? (
                <>
                  <div className="w-3 h-3 rounded-full bg-emerald-400" />
                  <span className="text-emerald-400 text-sm font-medium">Data Available</span>
                </>
              ) : (
                <>
                  <div className="w-3 h-3 rounded-full bg-zinc-600" />
                  <span className="text-zinc-500 text-sm font-medium">No Data</span>
                </>
              )}
            </div>
            {status?.dataPoints > 0 && (
              <span className="text-xs text-f1-muted bg-white/5 px-2 py-1 rounded-md">
                {status.dataPoints.toLocaleString()} data points
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {!isRecording ? (
              <button onClick={startRecording} className="flex items-center gap-2 bg-f1-red hover:bg-red-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition">
                <Play size={14} /> Start Recording
              </button>
            ) : (
              <button onClick={stopRecording} className="flex items-center gap-2 bg-zinc-700 hover:bg-zinc-600 text-white text-sm font-medium px-4 py-2 rounded-lg transition">
                <Square size={14} /> Stop
              </button>
            )}
            <button onClick={() => { fetchData(); fetchStatus(); }}
              className="flex items-center gap-2 bg-white/5 hover:bg-white/10 text-zinc-300 text-sm px-3 py-2 rounded-lg transition border border-white/10">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> Refresh
            </button>
            <button onClick={() => setAutoRefresh(!autoRefresh)}
              className={`flex items-center gap-2 text-sm px-3 py-2 rounded-lg transition border ${
                autoRefresh ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" : "bg-white/5 border-white/10 text-zinc-400 hover:bg-white/10"
              }`}>
              <Clock size={14} /> {autoRefresh ? "Auto: ON (1s)" : "Auto-refresh"}
            </button>
            {hasData && (
              <button onClick={clearData} className="flex items-center gap-2 text-zinc-500 hover:text-red-400 text-sm px-2 py-2 rounded-lg transition">
                <Trash2 size={14} />
              </button>
            )}
          </div>
        </div>
        {status?.error && (
          <div className="mt-3 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
            <p className="text-red-400 text-sm">{status.error}</p>
            <p className="text-red-400/60 text-xs mt-1">This usually means no F1 session is currently live.</p>
          </div>
        )}
      </GlassCard>

      {hasData ? (
        <>
          {/* ── Overview row: Track Map + Gap Evolution + Tyre Strategy ── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Track Map */}
            {liveData.positions && Object.keys(liveData.positions).length > 0 && (
              <GlassCard className="p-4" delay={0.12}>
                <h3 className="text-white font-semibold text-sm mb-2">Track Map</h3>
                <div className="relative w-full" style={{ paddingBottom: "75%" }}>
                  {(() => {
                    // Compute viewBox — prefer circuit outline, fall back to positions
                    // Check if positions are spread out or all stale at one point
                    const posPts = Object.values(liveData.positions);
                    const posSpread = posPts.length > 1
                      ? Math.max(...posPts.map(p => p.x)) - Math.min(...posPts.map(p => p.x))
                      : 0;
                    const allPts = circuitOutline.length > 10
                      ? circuitOutline
                      : (posSpread > 100 ? posPts : []);
                    if (!allPts.length && circuitOutline.length <= 10) return null;
                    const usePts = allPts.length > 0 ? allPts : circuitOutline;
                    const xs = usePts.map(p => p.x), ys = usePts.map(p => p.y);
                    const pad = circuitOutline.length > 10 ? 800 : 2000;
                    const vb = `${Math.min(...xs)-pad} ${Math.min(...ys)-pad} ${Math.max(...xs)-Math.min(...xs)+pad*2} ${Math.max(...ys)-Math.min(...ys)+pad*2}`;

                    // Build smooth circuit path using Catmull-Rom → cubic bezier
                    let circuitPath = null;
                    if (circuitOutline.length > 10) {
                      const pts = circuitOutline;
                      const n = pts.length;
                      // Catmull-Rom to cubic bezier conversion
                      let d = `M ${pts[0].x} ${pts[0].y}`;
                      for (let i = 0; i < n - 1; i++) {
                        const p0 = pts[(i - 1 + n) % n];
                        const p1 = pts[i];
                        const p2 = pts[(i + 1) % n];
                        const p3 = pts[(i + 2) % n];
                        // Control points (tension = 0.5 for smooth curves)
                        const cp1x = p1.x + (p2.x - p0.x) / 6;
                        const cp1y = p1.y + (p2.y - p0.y) / 6;
                        const cp2x = p2.x - (p3.x - p1.x) / 6;
                        const cp2y = p2.y - (p3.y - p1.y) / 6;
                        d += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2.x} ${p2.y}`;
                      }
                      circuitPath = d;
                    }

                    return (
                      <svg viewBox={vb} className="absolute inset-0 w-full h-full">
                        {/* Circuit outline */}
                        {circuitPath && (
                          <path d={circuitPath} fill="none" stroke="rgba(255,255,255,0.08)"
                            strokeWidth={200} strokeLinejoin="round" strokeLinecap="round" />
                        )}
                        {circuitPath && (
                          <path d={circuitPath} fill="none" stroke="rgba(255,255,255,0.15)"
                            strokeWidth={60} strokeLinejoin="round" strokeLinecap="round" />
                        )}

                        {/* Zone heatmap overlay — shows clipping/lift-coast for selected driver */}
                        {(() => {
                          const selArr = [...selectedDrivers];
                          if (selArr.length === 0) return null;
                          const zd = zoneData[selArr[0]];
                          if (!zd?.zones?.length) return null;
                          return zd.zones.filter(z => z.samples > 0).map((z, i) => {
                            const clip = z.clippingPct || 0;
                            const lift = z.liftCoastSamples || 0;
                            // Color: green=clean, orange=some clipping, red=heavy clipping, blue=lift-coast
                            let color = "#4ade8040"; // clean
                            let radius = 400;
                            if (clip > 50) { color = "#ef444480"; radius = 600; }
                            else if (clip > 20) { color = "#f9731680"; radius = 500; }
                            else if (lift > 3) { color = "#3b82f680"; radius = 500; }
                            return (
                              <g key={`zone-${i}`}>
                                <circle cx={z.x} cy={z.y} r={radius} fill={color} stroke="none" />
                                {(clip > 10 || lift > 2) && (
                                  <text x={z.x} y={z.y} textAnchor="middle" dominantBaseline="central"
                                    fill="white" fontSize={200} fontWeight="bold" opacity={0.7}>
                                    {clip > 10 ? `${clip.toFixed(0)}%` : `L&C`}
                                  </text>
                                )}
                              </g>
                            );
                          });
                        })()}

                        {/* Driver dots — use transform for smooth CSS transitions */}
                        {Object.entries(liveData.positions).map(([num, pos]) => {
                          const driver = liveData.timing.find(d => d.driverNumber === num);
                          const isInPit = driver?.InPit === true || driver?.InPit === "true";
                          const isRetired = driver?.Retired === true || driver?.Retired === "true";
                          const color = driver?.teamColor || "#888";
                          const isSel = selectedDrivers.has(num);
                          const name = driver?.name || num;
                          const dimmed = isInPit || isRetired;
                          return (
                            <g key={num} onClick={() => toggleDriver(num)}
                              style={{
                                cursor: "pointer",
                                opacity: dimmed ? 0.25 : 1,
                                transform: `translate(${pos.x}px, ${pos.y}px)`,
                                transition: "transform 2.5s ease-in-out",
                              }}>
                              {isSel && !dimmed && (
                                <circle cx={0} cy={0} r={350} fill={`${color}33`} stroke={color} strokeWidth={50}>
                                  <animate attributeName="r" values="300;400;300" dur="1.5s" repeatCount="indefinite" />
                                </circle>
                              )}
                              <circle cx={0} cy={0} r={isSel && !dimmed ? 200 : 130} fill={color}
                                stroke={isSel ? "#fff" : `${color}88`} strokeWidth={isSel ? 50 : 25} />
                              <text x={0} y={-250} textAnchor="middle" fill={isSel ? "#fff" : "#aaa"}
                                fontSize={200} fontWeight={isSel ? "bold" : "normal"} fontFamily="monospace">
                                {name}
                              </text>
                            </g>
                          );
                        })}
                      </svg>
                    );
                  })()}
                </div>
              </GlassCard>
            )}

            {/* Gap Evolution */}
            {liveData.gapEvolution && Object.keys(liveData.gapEvolution).length > 0 && (
              <GlassCard className="p-4" delay={0.14}>
                <h3 className="text-white font-semibold text-sm mb-2">Gap to Leader</h3>
                <Plot
                  data={Object.entries(liveData.gapEvolution).filter(([, pts]) => pts.length > 1).map(([name, pts]) => {
                    const driver = liveData.timing.find(d => (d.name || d.driverNumber) === name);
                    return {
                      type: "scatter", mode: "lines", name,
                      x: pts.map(p => p.lap), y: pts.map(p => p.gap),
                      line: { color: driver?.teamColor || "#888", width: 2 },
                    };
                  })}
                  layout={{
                    ...miniPlotLayout, height: 220, margin: { l: 35, r: 10, t: 5, b: 30 },
                    xaxis: { title: "Lap", showticklabels: true, showgrid: false, zeroline: false, color: "#a1a1aa", titlefont: { size: 9 } },
                    yaxis: { title: "Gap (s)", autorange: "reversed", color: "#a1a1aa", showgrid: true, gridcolor: "rgba(255,255,255,0.04)", titlefont: { size: 9 } },
                    legend: { orientation: "h", y: -0.3, font: { size: 8, color: "#a1a1aa" } },
                    showlegend: true,
                  }}
                  config={plotConfig} style={{ width: "100%" }}
                />
              </GlassCard>
            )}

            {/* Tyre Strategy */}
            {liveData.stintTimeline && Object.keys(liveData.stintTimeline).length > 0 && (
              <GlassCard className="p-4" delay={0.16}>
                <h3 className="text-white font-semibold text-sm mb-2">Tyre Strategy</h3>
                <div className="space-y-1 max-h-[220px] overflow-y-auto pr-1">
                  {liveData.timing.slice(0, 22).map((d) => {
                    const name = d.name || d.driverNumber;
                    const stints = liveData.stintTimeline[name] || [];
                    const totalLaps = stints.reduce((s, st) => s + (st.laps || 0), 0) || 1;
                    return (
                      <div key={d.driverNumber} className="flex items-center gap-2">
                        <span className="text-[9px] font-bold text-white w-7 text-right shrink-0 font-mono">{name}</span>
                        <div className="flex-1 h-4 flex rounded overflow-hidden bg-white/[0.03]">
                          {stints.map((st, i) => {
                            const color = COMPOUND_COLORS[st.compound?.toUpperCase()] || "#555";
                            const pct = (st.laps / totalLaps) * 100;
                            return (
                              <div key={i} className="h-full flex items-center justify-center"
                                style={{ width: `${pct}%`, background: `${color}30`, borderRight: i < stints.length - 1 ? "1px solid rgba(255,255,255,0.1)" : "none" }}>
                                <span className="text-[7px] font-bold font-mono" style={{ color }}>{st.compound?.[0] || "?"}</span>
                                <span className="text-[6px] text-white/50 ml-0.5">{st.laps}</span>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </GlassCard>
            )}
          </div>

          {/* ── Main: Driver selector + Driver cards ── */}
          <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-4">
            {/* Driver selector */}
            <GlassCard className="p-3" delay={0.18}>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-white font-semibold text-sm">Drivers</h3>
                <div className="flex gap-2">
                  <button onClick={selectAll} className="text-[10px] text-cyan-400 hover:text-cyan-300">All</button>
                  <button onClick={selectNone} className="text-[10px] text-zinc-500 hover:text-zinc-300">None</button>
                </div>
              </div>
              <div className="space-y-0.5 max-h-[60vh] overflow-y-auto pr-1">
                {liveData.timing.map((d) => {
                  const checked = selectedDrivers.has(d.driverNumber);
                  const tel = d.telemetry || {};
                  return (
                    <button key={d.driverNumber} onClick={() => toggleDriver(d.driverNumber)}
                      className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left transition ${
                        checked ? "bg-white/[0.06] border border-white/10" : "hover:bg-white/[0.03] border border-transparent"
                      }`}>
                      <div className={`w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0 transition ${
                        checked ? "border-cyan-500 bg-cyan-500/20" : "border-zinc-600"
                      }`}>
                        {checked && <div className="w-1.5 h-1.5 rounded-sm bg-cyan-400" />}
                      </div>
                      <div className="w-1 h-5 rounded-full shrink-0" style={{ background: d.teamColor || "#888" }} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1">
                          <span className="text-[9px] font-mono text-zinc-500 w-4">P{d.Position || "?"}</span>
                          <span className="text-xs font-semibold text-white truncate">{d.name || d.driverNumber}</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        {tel.speed ? <span className="text-[9px] font-mono text-cyan-400">{tel.speed}</span> : null}
                        {tel.gear ? <span className="text-[9px] font-mono text-yellow-400">G{tel.gear}</span> : null}
                      </div>
                    </button>
                  );
                })}
              </div>
            </GlassCard>

            {/* Selected driver cards */}
            <div className="space-y-3">
              {selectedDrivers.size === 0 ? (
                <GlassCard className="p-10" delay={0.2}>
                  <div className="flex flex-col items-center text-center gap-3">
                    <Activity size={32} className="text-zinc-700" />
                    <p className="text-zinc-500 text-sm">Select drivers to see telemetry traces and analysis flags</p>
                  </div>
                </GlassCard>
              ) : (
                [...selectedDrivers].map((driverNum) => {
                  const d = liveData.timing.find((t) => t.driverNumber === driverNum);
                  const detail = driverDetails[driverNum];
                  const tel = d?.telemetry || {};
                  const trace = detail?.telemetryTrace || [];
                  if (!d) return null;

                  return (
                    <motion.div key={driverNum} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                      <GlassCard className="p-4" delay={0}>
                        {/* Header */}
                        <div className="flex items-center gap-3 mb-3">
                          <div className="w-1.5 h-10 rounded-full" style={{ background: d.teamColor || "#888" }} />
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className="text-white font-bold text-lg">{d.name || driverNum}</span>
                              <span className="text-xs text-f1-muted font-mono">#{driverNum}</span>
                              <span className="text-[10px] px-2 py-0.5 rounded-full" style={{
                                background: `${d.teamColor || "#888"}20`, color: d.teamColor || "#888",
                                border: `1px solid ${d.teamColor || "#888"}40`,
                              }}>{d.team || "—"}</span>
                            </div>
                            <div className="flex items-center gap-3 mt-0.5">
                              <span className="text-xs text-zinc-400">P{d.Position || "?"}</span>
                              {d.lastLapTime && <span className="text-xs font-mono text-zinc-400">Last: {d.lastLapTime}</span>}
                              {d.GapToLeader && d.Position !== "1" && (
                                <span className="text-xs font-mono text-zinc-500">Gap: {d.GapToLeader}</span>
                              )}
                            </div>
                          </div>
                          <button onClick={() => toggleDriver(driverNum)}
                            className="text-zinc-600 hover:text-zinc-300 text-xs px-2 py-1 rounded hover:bg-white/5">Hide</button>
                        </div>

                        {/* Live values (compact) */}
                        <div className="grid grid-cols-4 gap-2 mb-3">
                          {[
                            { label: "Speed", value: tel.speed, unit: "km/h", color: "#22d3ee" },
                            { label: "Throttle", value: tel.throttle, unit: "%", color: "#4ade80" },
                            { label: "Brake", value: tel.brake, unit: "%", color: "#ef4444" },
                            { label: "Gear", value: tel.gear, unit: "", color: "#facc15" },
                          ].map(({ label, value, unit, color }) => (
                            <div key={label} className="bg-white/[0.03] rounded-lg px-3 py-2 border border-white/5">
                              <span className="text-[9px] text-f1-muted uppercase tracking-wider">{label}</span>
                              <div className="text-lg font-mono font-bold" style={{ color }}>
                                {value != null ? value : "—"}
                                {value != null && unit && <span className="text-[9px] text-zinc-500 ml-0.5">{unit}</span>}
                              </div>
                            </div>
                          ))}
                        </div>

                        {/* Telemetry traces */}
                        {trace.length > 3 && (
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mb-3">
                            {/* Speed trace */}
                            <div className="bg-white/[0.02] rounded-lg border border-white/5 p-2">
                              <span className="text-[9px] text-f1-muted uppercase tracking-wider">Speed Trace</span>
                              <Plot
                                data={[{
                                  type: "scatter", mode: "lines",
                                  y: trace.map(t => t.speed),
                                  line: { color: d.teamColor || "#22d3ee", width: 1.5 },
                                  fill: "tozeroy", fillcolor: `${d.teamColor || "#22d3ee"}10`,
                                }]}
                                layout={{
                                  ...miniPlotLayout, height: 100,
                                  yaxis: { showticklabels: true, showgrid: false, zeroline: false, color: "#666", range: [0, Math.max(...trace.map(t => t.speed), 100) + 20] },
                                }}
                                config={plotConfig} style={{ width: "100%" }}
                              />
                            </div>
                            {/* Throttle trace */}
                            <div className="bg-white/[0.02] rounded-lg border border-white/5 p-2">
                              <span className="text-[9px] text-f1-muted uppercase tracking-wider">Throttle Trace</span>
                              <Plot
                                data={[{
                                  type: "scatter", mode: "lines",
                                  y: trace.map(t => t.throttle),
                                  line: { color: "#4ade80", width: 1.5 },
                                  fill: "tozeroy", fillcolor: "#4ade8010",
                                }]}
                                layout={{
                                  ...miniPlotLayout, height: 100,
                                  yaxis: { showticklabels: true, showgrid: false, zeroline: false, color: "#666", range: [0, 110] },
                                }}
                                config={plotConfig} style={{ width: "100%" }}
                              />
                            </div>
                            {/* Brake trace */}
                            <div className="bg-white/[0.02] rounded-lg border border-white/5 p-2">
                              <span className="text-[9px] text-f1-muted uppercase tracking-wider">Brake Trace</span>
                              <Plot
                                data={[{
                                  type: "scatter", mode: "lines",
                                  y: trace.map(t => t.brake),
                                  line: { color: "#ef4444", width: 1.5 },
                                  fill: "tozeroy", fillcolor: "#ef444410",
                                }]}
                                layout={{
                                  ...miniPlotLayout, height: 100,
                                  yaxis: { showticklabels: true, showgrid: false, zeroline: false, color: "#666", range: [0, 110] },
                                }}
                                config={plotConfig} style={{ width: "100%" }}
                              />
                            </div>
                          </div>
                        )}

                        {/* Battery + Analysis Flags row */}
                        <div className="flex items-start gap-4">
                          {/* Battery gauge */}
                          {detail?.estErsUsage != null && (
                            <div className="relative cursor-pointer" onClick={() => setOpenDefinition(openDefinition === `ERS_${driverNum}` ? null : `ERS_${driverNum}`)}>
                              <BatteryGauge value={detail.estErsUsage} />
                              <div className="absolute -top-1 -right-1">
                                <Info size={10} className="text-zinc-600 hover:text-zinc-300 transition" />
                              </div>
                              <AnimatePresence>
                                {openDefinition === `ERS_${driverNum}` && (
                                  <GlassDefinition type="ERS_DEPLOY" onClose={() => setOpenDefinition(null)} />
                                )}
                              </AnimatePresence>
                            </div>
                          )}

                          {/* Analysis flags */}
                          <div className="flex-1 relative">
                            <span className="text-[9px] text-f1-muted uppercase tracking-wider">Analysis Flags</span>
                            <div className="flex flex-wrap gap-1.5 mt-1">
                              {detail?.patterns?.length > 0 ? (
                                detail.patterns.map((p, i) => {
                                  const cfg = FLAG_CONFIG[p.type] || FLAG_CONFIG.CLIPPING;
                                  const FlagIcon = cfg.icon;
                                  const defKey = `${p.type}_${driverNum}`;
                                  return (
                                    <div key={i} className="relative">
                                      <div
                                        onClick={() => setOpenDefinition(openDefinition === defKey ? null : defKey)}
                                        className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 cursor-pointer hover:brightness-125 transition ${cfg.bg} ${cfg.border}`}
                                      >
                                        <FlagIcon size={12} style={{ color: cfg.color }} />
                                        <span className={`text-[10px] font-bold ${cfg.text}`}>{cfg.label}</span>
                                        <span className="text-[9px] text-f1-muted">{(p.confidence * 100).toFixed(0)}%</span>
                                        <Info size={9} className="text-zinc-600 ml-0.5" />
                                      </div>
                                      <AnimatePresence>
                                        {openDefinition === defKey && (
                                          <GlassDefinition type={p.type} onClose={() => setOpenDefinition(null)} />
                                        )}
                                      </AnimatePresence>
                                    </div>
                                  );
                                })
                              ) : (
                                <div className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-2.5 py-1.5">
                                  <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                                  <span className="text-[10px] text-emerald-300">Clean running</span>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </GlassCard>
                    </motion.div>
                  );
                })
              )}
            </div>
          </div>
        </>
      ) : (
        <GlassCard className="p-10" delay={0.15}>
          <div className="flex flex-col items-center text-center gap-5">
            <div className="relative">
              <div className="w-16 h-16 rounded-2xl bg-f1-red/10 border border-f1-red/20 flex items-center justify-center">
                {isRecording ? <Wifi className="w-7 h-7 text-f1-red animate-pulse" /> : <WifiOff className="w-7 h-7 text-zinc-600" />}
              </div>
              {isRecording && (
                <span className="absolute -top-1 -right-1 flex h-4 w-4">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-f1-red opacity-40" />
                  <span className="relative inline-flex rounded-full h-4 w-4 bg-f1-red border-2 border-f1-dark" />
                </span>
              )}
            </div>
            <div>
              <h2 className="text-xl font-bold text-white mb-2">
                {isRecording ? "Connecting to F1 Live Timing..." : "No Live Data"}
              </h2>
              <p className="text-zinc-500 text-sm max-w-lg">
                {isRecording
                  ? "Waiting for data from the F1 timing stream. Make sure an F1 session is currently active."
                  : "Click 'Start Recording' during a live F1 session, or record from terminal and refresh."}
              </p>
            </div>
            {!isRecording && (
              <div className="glass rounded-xl p-5 max-w-md w-full text-left mt-2">
                <p className="text-xs text-emerald-400 font-semibold uppercase tracking-widest mb-2">Record from terminal</p>
                <code className="text-sm text-zinc-300 font-mono block bg-white/[0.03] rounded-lg px-4 py-3 border border-f1-border">
                  python -m fastf1.livetiming save live_data.txt
                </code>
              </div>
            )}
            {isRecording && <LoadingSpinner text="Waiting for timing data..." />}
          </div>
        </GlassCard>
      )}
    </div>
  );
}
