import { useState, useEffect, useMemo } from "react";
import { motion } from "framer-motion";
import { Map, ChevronLeft, ChevronRight, Gauge, Zap as ZapIcon, Timer } from "lucide-react";
import Plot from "react-plotly.js";
import GlassCard from "../components/GlassCard";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import { useApi } from "../hooks/useApi";

const plotLayout = {
  template: "plotly_dark",
  paper_bgcolor: "transparent",
  plot_bgcolor: "rgba(255,255,255,0.02)",
  font: { color: "#a1a1aa" },
  margin: { l: 50, r: 20, t: 30, b: 40 },
};

const plotConfig = { displayModeBar: false, responsive: true };

const COLOR_MODES = [
  { key: "speed", label: "Speed", unit: "km/h", colorscale: "YlOrRd" },
  { key: "throttle", label: "Throttle", unit: "%", colorscale: "Greens" },
  { key: "brake", label: "Brake", unit: "%", colorscale: "Reds" },
  { key: "gear", label: "Gear", unit: "", colorscale: "Viridis" },
  { key: "zones", label: "Zones", unit: "", colorscale: null },
];

const ZONE_COLORS = {
  "Full Throttle": "#22c55e",
  "Partial Throttle": "#86efac",
  "Coast/Harvest": "#fbbf24",
  "Full Brake": "#ef4444",
  "Trail Brake": "#f97316",
};

export default function CircuitLab() {
  const api = useApi();
  const [drivers, setDrivers] = useState([]);
  const [selectedDriver, setSelectedDriver] = useState(null);
  const [circuitData, setCircuitData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [dataLoading, setDataLoading] = useState(false);
  const [colorMode, setColorMode] = useState("speed");
  const [lapMode, setLapMode] = useState("fastest");
  const [singleLap, setSingleLap] = useState(null);
  const [lapRange, setLapRange] = useState([1, 5]);

  useEffect(() => {
    async function init() {
      try {
        const d = await api.call("/api/session/drivers");
        const driverList = d?.drivers || [];
        setDrivers(driverList);
        if (driverList.length > 0) {
          setSelectedDriver(driverList[0].code);
        }
      } catch (e) {
        console.error("Failed to load drivers:", e);
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  useEffect(() => {
    if (!selectedDriver) return;
    async function fetchCircuit() {
      setDataLoading(true);
      try {
        let url = `/api/session/circuit?driver=${selectedDriver}`;
        if (lapMode === "single" && singleLap != null) {
          url += `&lap=${singleLap}`;
        } else if (lapMode === "range") {
          url += `&lapStart=${lapRange[0]}&lapEnd=${lapRange[1]}`;
        }
        const result = await api.call(url);
        setCircuitData(result);
        if (result?.availableLaps?.length > 0 && singleLap == null) {
          setSingleLap(result.availableLaps[Math.floor(result.availableLaps.length / 2)]);
          setLapRange([result.availableLaps[0], result.availableLaps[result.availableLaps.length - 1]]);
        }
      } catch (e) {
        console.error("Failed to load circuit data:", e);
      } finally {
        setDataLoading(false);
      }
    }
    fetchCircuit();
  }, [selectedDriver, lapMode, singleLap, lapRange[0], lapRange[1]]);

  const activeDriver = useMemo(
    () => drivers.find((d) => d.code === selectedDriver),
    [drivers, selectedDriver]
  );

  if (loading) {
    return <LoadingSpinner text="Loading circuit data..." />;
  }

  const buildTrackTrace = () => {
    if (!circuitData?.x || !circuitData?.y) return null;
    const mode = COLOR_MODES.find((m) => m.key === colorMode);

    if (colorMode === "zones") {
      const colors = circuitData.zones.map((z) => ZONE_COLORS[z] || "#888");
      return {
        type: "scatter", mode: "markers",
        x: circuitData.x, y: circuitData.y,
        marker: { color: colors, size: 4.5 },
        hovertemplate: circuitData.zones.map(
          (z, i) => `${z}<br>Speed: ${circuitData.speed[i]?.toFixed(0)} km/h<extra></extra>`
        ),
        showlegend: false,
      };
    }

    const values = colorMode === "gear" ? circuitData.gear : circuitData[colorMode];
    if (!values) return null;

    return {
      type: "scatter", mode: "markers",
      x: circuitData.x, y: circuitData.y,
      marker: {
        color: values, colorscale: mode.colorscale, size: 4.5,
        colorbar: {
          title: { text: mode.label, font: { color: "#a1a1aa", size: 11 } },
          tickfont: { color: "#a1a1aa" },
          thickness: 10, len: 0.5, x: 1.02,
        },
      },
      hovertemplate: circuitData.speed.map(
        (_, i) =>
          `Speed: ${circuitData.speed[i]?.toFixed(0)} km/h<br>Throttle: ${circuitData.throttle[i]?.toFixed(0)}%<br>Brake: ${circuitData.brake[i]?.toFixed(0)}%${circuitData.gear ? `<br>Gear: ${circuitData.gear[i]}` : ""}<extra></extra>`
      ),
      showlegend: false,
    };
  };

  const cornerAnnotations = (circuitData?.corners || []).map((c) => ({
    x: c.x, y: c.y,
    text: `T${c.number}`,
    showarrow: false,
    font: { size: 9, color: "#f1f1f1" },
    bgcolor: "rgba(0,0,0,0.6)",
    borderpad: 2,
  }));

  const trackTrace = buildTrackTrace();
  const availableLaps = circuitData?.availableLaps || [];
  const maxLap = availableLaps.length > 0 ? availableLaps[availableLaps.length - 1] : 60;
  const minLap = availableLaps.length > 0 ? availableLaps[0] : 1;

  // Compute stats for the hero badges
  const topSpeed = circuitData?.speed ? Math.round(Math.max(...circuitData.speed)) : null;
  const avgSpeed = circuitData?.speed ? Math.round(circuitData.speed.reduce((a, b) => a + b, 0) / circuitData.speed.length) : null;
  const nCorners = circuitData?.corners?.length || 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Circuit Lab"
        subtitle="Per-lap track analysis with telemetry overlay"
        icon={Map}
      />

      {/* ── Driver selector: pill-style, compact ── */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 scrollbar-thin">
        {drivers.map((d) => (
          <button
            key={d.code}
            onClick={() => setSelectedDriver(d.code)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold transition-all whitespace-nowrap
              ${selectedDriver === d.code
                ? "text-white shadow-lg scale-105"
                : "text-zinc-500 hover:text-white hover:bg-white/5"
              }`}
            style={selectedDriver === d.code
              ? { backgroundColor: d.color + "25", border: `1px solid ${d.color}60`, boxShadow: `0 0 12px ${d.color}20` }
              : { border: "1px solid transparent" }
            }
          >
            {d.headshot ? (
              <img src={d.headshot} alt={d.code}
                className="w-6 h-6 rounded-full object-cover bg-white/10"
                onError={(e) => { e.target.style.display = "none"; }}
              />
            ) : (
              <span className="w-6 h-6 rounded-full flex items-center justify-center text-[9px] font-bold"
                style={{ backgroundColor: d.color + "30", color: d.color }}
              >{d.code[0]}</span>
            )}
            <span>{d.code}</span>
          </button>
        ))}
      </div>

      {/* ── Hero: Track Map + Sidebar Controls ── */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        {/* Track map — takes 3/4 of the row */}
        <GlassCard className="xl:col-span-3 p-0 relative overflow-hidden" hover delay={0.1}>
          {dataLoading && (
            <div className="absolute inset-0 bg-black/40 backdrop-blur-sm z-10 flex items-center justify-center">
              <div className="flex items-center gap-3 text-zinc-300 text-sm">
                <div className="w-4 h-4 border-2 border-f1-red border-t-transparent rounded-full animate-spin" />
                Loading lap data...
              </div>
            </div>
          )}

          {/* Floating stats badges */}
          {circuitData && (
            <div className="absolute top-4 left-4 z-10 flex flex-col gap-2">
              {topSpeed && (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/60 backdrop-blur-md border border-white/10">
                  <Gauge className="w-3 h-3 text-f1-red" />
                  <span className="text-xs text-zinc-400">Top</span>
                  <span className="text-xs font-bold text-white">{topSpeed} km/h</span>
                </div>
              )}
              {avgSpeed && (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/60 backdrop-blur-md border border-white/10">
                  <Timer className="w-3 h-3 text-cyan-400" />
                  <span className="text-xs text-zinc-400">Avg</span>
                  <span className="text-xs font-bold text-white">{avgSpeed} km/h</span>
                </div>
              )}
              {nCorners > 0 && (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/60 backdrop-blur-md border border-white/10">
                  <Map className="w-3 h-3 text-yellow-400" />
                  <span className="text-xs font-bold text-white">{nCorners} turns</span>
                </div>
              )}
            </div>
          )}

          {/* Floating lap badge */}
          {circuitData?.lapUsed && (
            <div className="absolute top-4 right-4 z-10 px-3 py-1.5 rounded-full bg-black/60 backdrop-blur-md border border-white/10">
              <span className="text-xs text-zinc-400">
                {Array.isArray(circuitData.lapUsed)
                  ? `Laps ${circuitData.lapUsed[0]}–${circuitData.lapUsed[circuitData.lapUsed.length - 1]}`
                  : `Lap ${circuitData.lapUsed}`}
              </span>
              {lapMode === "fastest" && <span className="text-xs text-f1-red font-bold ml-1">FASTEST</span>}
            </div>
          )}

          {trackTrace ? (
            <Plot
              data={[trackTrace]}
              layout={{
                ...plotLayout,
                height: 520,
                xaxis: { scaleanchor: "y", showgrid: false, zeroline: false, showticklabels: false },
                yaxis: { showgrid: false, zeroline: false, showticklabels: false },
                annotations: cornerAnnotations,
                margin: { l: 10, r: 40, t: 10, b: 10 },
                paper_bgcolor: "transparent",
                plot_bgcolor: "transparent",
              }}
              config={plotConfig}
              useResizeHandler
              style={{ width: "100%" }}
            />
          ) : (
            <div className="h-[520px] flex items-center justify-center text-zinc-500">
              No track data available
            </div>
          )}
        </GlassCard>

        {/* Sidebar: Controls + Driver info */}
        <div className="flex flex-col gap-4">
          {/* Driver card */}
          {activeDriver && (
            <motion.div
              key={activeDriver.code}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-2xl p-4 border border-white/10 relative overflow-hidden"
              style={{ background: `linear-gradient(135deg, ${activeDriver.color}15 0%, transparent 60%)` }}
            >
              <div className="absolute top-0 right-0 w-20 h-20 rounded-full blur-3xl opacity-20"
                style={{ backgroundColor: activeDriver.color }} />
              <div className="flex items-center gap-3">
                {activeDriver.headshot ? (
                  <img src={activeDriver.headshot} alt={activeDriver.code}
                    className="w-14 h-14 rounded-2xl object-cover bg-white/10"
                    onError={(e) => { e.target.style.display = "none"; }}
                  />
                ) : (
                  <span className="w-14 h-14 rounded-2xl flex items-center justify-center text-xl font-bold"
                    style={{ backgroundColor: activeDriver.color + "30", color: activeDriver.color }}
                  >{activeDriver.code[0]}</span>
                )}
                <div className="flex-1">
                  <p className="text-white font-bold text-sm">{activeDriver.name || activeDriver.code}</p>
                  <p className="text-zinc-500 text-xs">{activeDriver.team}</p>
                </div>
                <span className="w-1 h-10 rounded-full" style={{ backgroundColor: activeDriver.color }} />
              </div>
            </motion.div>
          )}

          {/* Overlay mode */}
          <GlassCard className="p-4" delay={0.12}>
            <h4 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-widest mb-2">Overlay</h4>
            <div className="grid grid-cols-2 gap-1.5">
              {COLOR_MODES.map((m) => (
                <button
                  key={m.key}
                  onClick={() => setColorMode(m.key)}
                  className={`px-2 py-1.5 rounded-lg text-xs font-medium transition-all
                    ${colorMode === m.key
                      ? "bg-f1-red text-white"
                      : "bg-white/5 text-zinc-400 hover:bg-white/10 hover:text-white"
                    }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
            {colorMode === "zones" && (
              <div className="flex flex-wrap gap-x-3 gap-y-1 mt-3">
                {Object.entries(ZONE_COLORS).map(([zone, color]) => (
                  <div key={zone} className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                    <span className="text-[9px] text-zinc-500">{zone}</span>
                  </div>
                ))}
              </div>
            )}
          </GlassCard>

          {/* Lap selection */}
          <GlassCard className="p-4" delay={0.14}>
            <h4 className="text-[10px] font-semibold text-zinc-500 uppercase tracking-widest mb-2">Lap</h4>
            <div className="flex gap-1 mb-2">
              {[
                { key: "fastest", label: "Best" },
                { key: "single", label: "Pick" },
                { key: "range", label: "Range" },
              ].map((m) => (
                <button
                  key={m.key}
                  onClick={() => setLapMode(m.key)}
                  className={`flex-1 px-2 py-1.5 rounded-lg text-xs font-medium transition-all
                    ${lapMode === m.key
                      ? "bg-f1-red text-white"
                      : "bg-white/5 text-zinc-400 hover:bg-white/10"
                    }`}
                >
                  {m.label}
                </button>
              ))}
            </div>

            {lapMode === "single" && (
              <div className="flex items-center gap-2">
                <button onClick={() => setSingleLap((p) => Math.max(minLap, (p || minLap) - 1))}
                  className="w-7 h-7 rounded-lg bg-white/5 flex items-center justify-center hover:bg-white/10 border border-f1-border">
                  <ChevronLeft className="w-3 h-3 text-zinc-400" />
                </button>
                <input type="range" min={minLap} max={maxLap} value={singleLap || minLap}
                  onChange={(e) => setSingleLap(parseInt(e.target.value, 10))}
                  className="flex-1 h-1.5 rounded-full appearance-none cursor-pointer bg-white/10 accent-f1-red
                    [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5
                    [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-f1-red [&::-webkit-slider-thumb]:cursor-pointer"
                />
                <button onClick={() => setSingleLap((p) => Math.min(maxLap, (p || minLap) + 1))}
                  className="w-7 h-7 rounded-lg bg-white/5 flex items-center justify-center hover:bg-white/10 border border-f1-border">
                  <ChevronRight className="w-3 h-3 text-zinc-400" />
                </button>
                <span className="text-sm font-bold text-gradient min-w-[32px] text-center">{singleLap || "—"}</span>
              </div>
            )}

            {lapMode === "range" && (
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-zinc-500 w-8">From</span>
                  <input type="range" min={minLap} max={maxLap} value={lapRange[0]}
                    onChange={(e) => { const v = parseInt(e.target.value, 10); setLapRange([v, Math.max(v, lapRange[1])]); }}
                    className="flex-1 h-1.5 rounded-full appearance-none cursor-pointer bg-white/10 accent-f1-red
                      [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5
                      [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full
                      [&::-webkit-slider-thumb]:bg-f1-red [&::-webkit-slider-thumb]:cursor-pointer"
                  />
                  <span className="text-xs font-bold text-white w-6 text-center">{lapRange[0]}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-zinc-500 w-8">To</span>
                  <input type="range" min={minLap} max={maxLap} value={lapRange[1]}
                    onChange={(e) => { const v = parseInt(e.target.value, 10); setLapRange([Math.min(v, lapRange[0]), v]); }}
                    className="flex-1 h-1.5 rounded-full appearance-none cursor-pointer bg-white/10 accent-f1-red
                      [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5
                      [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full
                      [&::-webkit-slider-thumb]:bg-f1-red [&::-webkit-slider-thumb]:cursor-pointer"
                  />
                  <span className="text-xs font-bold text-white w-6 text-center">{lapRange[1]}</span>
                </div>
                <p className="text-[10px] text-zinc-500 text-center">{lapRange[1] - lapRange[0] + 1} laps averaged</p>
              </div>
            )}

            {lapMode === "fastest" && circuitData?.lapUsed && (
              <p className="text-[10px] text-zinc-500">
                Best lap: <span className="text-white font-bold">Lap {circuitData.lapUsed}</span>
              </p>
            )}
          </GlassCard>
        </div>
      </div>

      {/* ── Stacked Telemetry Traces ── */}
      {circuitData && (
        <GlassCard className="p-5" hover delay={0.2}>
          <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-3">
            Telemetry — {selectedDriver}
          </h3>
          <div className="space-y-0">
            {/* Speed */}
            <Plot
              data={[{
                type: "scatter", mode: "lines",
                x: circuitData.distance, y: circuitData.speed,
                line: { color: circuitData.color || "#E10600", width: 1.5 },
                fill: "tozeroy",
                fillcolor: `${circuitData.color || "#E10600"}12`,
                hovertemplate: "%{y:.0f} km/h<extra>Speed</extra>",
                name: "Speed",
              }]}
              layout={{
                ...plotLayout, height: 150,
                xaxis: { showticklabels: false, gridcolor: "rgba(255,255,255,0.03)", zeroline: false },
                yaxis: { title: { text: "km/h", font: { size: 9, color: "#71717a" } }, color: "#71717a", gridcolor: "rgba(255,255,255,0.03)" },
                margin: { l: 45, r: 10, t: 5, b: 0 },
                showlegend: false,
              }}
              config={plotConfig} useResizeHandler style={{ width: "100%" }}
            />
            {/* Throttle */}
            <Plot
              data={[{
                type: "scatter", mode: "lines",
                x: circuitData.distance, y: circuitData.throttle,
                line: { color: "#22c55e", width: 1.5 },
                fill: "tozeroy", fillcolor: "rgba(34,197,94,0.06)",
                hovertemplate: "%{y:.0f}%<extra>Throttle</extra>",
                name: "Throttle",
              }]}
              layout={{
                ...plotLayout, height: 100,
                xaxis: { showticklabels: false, gridcolor: "rgba(255,255,255,0.03)", zeroline: false },
                yaxis: { title: { text: "Thr %", font: { size: 9, color: "#71717a" } }, color: "#71717a", gridcolor: "rgba(255,255,255,0.03)", range: [0, 105] },
                margin: { l: 45, r: 10, t: 0, b: 0 },
                showlegend: false,
              }}
              config={plotConfig} useResizeHandler style={{ width: "100%" }}
            />
            {/* Brake */}
            <Plot
              data={[{
                type: "scatter", mode: "lines",
                x: circuitData.distance, y: circuitData.brake,
                line: { color: "#ef4444", width: 1.5 },
                fill: "tozeroy", fillcolor: "rgba(239,68,68,0.06)",
                hovertemplate: "%{y:.0f}%<extra>Brake</extra>",
                name: "Brake",
              }]}
              layout={{
                ...plotLayout, height: 100,
                xaxis: { title: { text: "Distance (m)", font: { size: 9, color: "#71717a" } }, color: "#71717a", gridcolor: "rgba(255,255,255,0.03)" },
                yaxis: { title: { text: "Brk %", font: { size: 9, color: "#71717a" } }, color: "#71717a", gridcolor: "rgba(255,255,255,0.03)", range: [0, 105] },
                margin: { l: 45, r: 10, t: 0, b: 30 },
                showlegend: false,
              }}
              config={plotConfig} useResizeHandler style={{ width: "100%" }}
            />
          </div>
        </GlassCard>
      )}

      {/* ── Corner cards (not a table) ── */}
      {circuitData?.corners?.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-3 px-1">
            Corner Analysis
          </h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-2">
            {circuitData.corners.map((c) => {
              const character = c.speed < 100 ? "Slow" : c.speed < 150 ? "Medium" : c.speed < 200 ? "Fast" : "Flat";
              const charColor = c.speed < 100 ? "#ef4444" : c.speed < 150 ? "#f97316" : c.speed < 200 ? "#fbbf24" : "#22c55e";
              return (
                <motion.div
                  key={c.number}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 0.02 * c.number }}
                  className="rounded-xl bg-white/[0.03] border border-white/[0.06] p-3 hover:bg-white/[0.06] transition-colors group"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-white font-bold text-sm">T{c.number}</span>
                    <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded-full"
                      style={{ color: charColor, backgroundColor: charColor + "18" }}>
                      {character}
                    </span>
                  </div>
                  <p className="text-lg font-bold font-mono" style={{ color: charColor }}>
                    {Math.round(c.speed)}
                    <span className="text-[9px] text-zinc-500 font-normal ml-0.5">km/h</span>
                  </p>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-[9px] text-zinc-500">G{c.gear ?? "?"}</span>
                    <span className="text-[9px] text-zinc-600">{Math.round(c.distance)}m</span>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Mini-sector heatmap ── */}
      {circuitData?.miniSectors?.length > 0 && (
        <GlassCard className="p-5" hover delay={0.28}>
          <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-3">
            Mini-Sector Speed
          </h3>
          <div className="flex gap-0.5 rounded-xl overflow-hidden">
            {circuitData.miniSectors.map((ms) => {
              const pct = ms.avgSpeed / 350;
              const r = Math.round(255 * (1 - pct));
              const g = Math.round(200 * pct);
              const bg = `rgb(${r}, ${g}, 40)`;
              return (
                <div key={ms.sector} className="flex-1 group relative">
                  <div className="h-6 transition-all group-hover:h-9" style={{ backgroundColor: bg, opacity: 0.85 }} />
                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2 py-1 rounded-lg bg-black/80 backdrop-blur text-[10px] text-white whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 border border-white/10">
                    S{ms.sector}: {ms.avgSpeed} km/h<br />
                    Thr: {ms.avgThrottle}% | Brk: {ms.avgBrake}%
                  </div>
                </div>
              );
            })}
          </div>
          <div className="flex justify-between mt-1.5">
            <span className="text-[9px] text-zinc-600">Slow</span>
            <span className="text-[9px] text-zinc-600">Fast</span>
          </div>
        </GlassCard>
      )}
    </div>
  );
}
