import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { motion } from "framer-motion";
import { Map, ChevronLeft, ChevronRight, Gauge, Zap as ZapIcon, Timer, AlertTriangle, Battery, Wind, Play, Pause, RotateCcw, FastForward } from "lucide-react";
import Plot from "react-plotly.js";
import GlassCard from "../components/GlassCard";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import CircuitSVG from "../components/CircuitSVG";
import SpeedometerGauge, { ERSStatusIndicator } from "../components/SpeedometerGauge";
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
  { key: "clipping", label: "Clipping", unit: "", colorscale: null },
  { key: "ersDeployment", label: "ERS Deploy", unit: "", colorscale: null },
  { key: "liftCoast", label: "Lift & Coast", unit: "", colorscale: null },
  { key: "drs", label: "DRS", unit: "", colorscale: null },
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

  // Replay state
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState(1);
  const [replayIndex, setReplayIndex] = useState(0);
  const animRef = useRef(null);
  const lastFrameRef = useRef(0);
  const indexRef = useRef(0);

  // Replay animation loop
  useEffect(() => {
    if (colorMode !== "replay" || !replayPlaying || !circuitData?.x?.length) {
      if (animRef.current) cancelAnimationFrame(animRef.current);
      return;
    }
    const totalSamples = circuitData.x.length;
    // ~90s for a full lap at 1x speed
    const msPerSample = (90 * 1000) / totalSamples;

    const animate = (timestamp) => {
      if (!lastFrameRef.current) lastFrameRef.current = timestamp;
      const elapsed = timestamp - lastFrameRef.current;
      lastFrameRef.current = timestamp;

      const advance = (elapsed / msPerSample) * replaySpeed;
      indexRef.current = Math.min(indexRef.current + advance, totalSamples - 1);

      const idx = Math.round(indexRef.current);
      setReplayIndex(idx);

      if (indexRef.current >= totalSamples - 1) {
        setReplayPlaying(false);
        return;
      }
      animRef.current = requestAnimationFrame(animate);
    };

    lastFrameRef.current = 0;
    animRef.current = requestAnimationFrame(animate);
    return () => { if (animRef.current) cancelAnimationFrame(animRef.current); };
  }, [colorMode, replayPlaying, replaySpeed, circuitData]);

  // Reset replay when driver/lap changes
  useEffect(() => {
    setReplayPlaying(false);
    setReplayIndex(0);
    indexRef.current = 0;
  }, [selectedDriver, lapMode, singleLap, lapRange[0], lapRange[1]]);

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

    if (colorMode === "clipping" && circuitData.clipping) {
      const colors = circuitData.clipping.map((c) => c ? "#ef4444" : "#22c55e40");
      return {
        type: "scatter", mode: "markers",
        x: circuitData.x, y: circuitData.y,
        marker: { color: colors, size: circuitData.clipping.map(c => c ? 7 : 4), opacity: circuitData.clipping.map(c => c ? 1 : 0.4) },
        hovertemplate: circuitData.clipping.map(
          (c, i) => `${c ? "CLIPPING" : "Normal"}<br>Speed: ${circuitData.speed[i]?.toFixed(0)} km/h<br>Throttle: ${circuitData.throttle[i]?.toFixed(0)}%<extra></extra>`
        ),
        showlegend: false,
      };
    }

    if (colorMode === "ersDeployment" && circuitData.ersDeployment) {
      const colors = circuitData.ersDeployment.map((e) => e ? "#4ade80" : "#ffffff10");
      return {
        type: "scatter", mode: "markers",
        x: circuitData.x, y: circuitData.y,
        marker: { color: colors, size: circuitData.ersDeployment.map(e => e ? 6 : 3.5), opacity: circuitData.ersDeployment.map(e => e ? 1 : 0.3) },
        hovertemplate: circuitData.ersDeployment.map(
          (e, i) => `${e ? "ERS DEPLOYING" : "No deploy"}<br>Speed: ${circuitData.speed[i]?.toFixed(0)} km/h<br>Accel: ${i > 0 ? (circuitData.speed[i] - circuitData.speed[i-1]).toFixed(1) : 0} km/h<extra></extra>`
        ),
        showlegend: false,
      };
    }

    if (colorMode === "liftCoast" && circuitData.liftCoast) {
      const colors = circuitData.liftCoast.map((l) => l ? "#3b82f6" : "#ffffff10");
      return {
        type: "scatter", mode: "markers",
        x: circuitData.x, y: circuitData.y,
        marker: { color: colors, size: circuitData.liftCoast.map(l => l ? 7 : 3.5), opacity: circuitData.liftCoast.map(l => l ? 1 : 0.3) },
        hovertemplate: circuitData.liftCoast.map(
          (l, i) => `${l ? "LIFT & COAST" : "Normal"}<br>Speed: ${circuitData.speed[i]?.toFixed(0)} km/h<br>Throttle: ${circuitData.throttle[i]?.toFixed(0)}%<extra></extra>`
        ),
        showlegend: false,
      };
    }

    if (colorMode === "drs" && circuitData.drs) {
      const colors = circuitData.drs.map((d) => d ? "#a855f7" : "#ffffff10");
      return {
        type: "scatter", mode: "markers",
        x: circuitData.x, y: circuitData.y,
        marker: { color: colors, size: circuitData.drs.map(d => d ? 7 : 3.5), opacity: circuitData.drs.map(d => d ? 1 : 0.3) },
        hovertemplate: circuitData.drs.map(
          (d, i) => `${d ? "DRS OPEN" : "DRS Closed"}<br>Speed: ${circuitData.speed[i]?.toFixed(0)} km/h<br>Gear: ${circuitData.gear?.[i] ?? "?"}<extra></extra>`
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
  const overallClipping = circuitData?.overallClipping;
  const overallErs = circuitData?.overallErs;

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
              {overallClipping != null && overallClipping > 0 && (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/60 backdrop-blur-md border border-red-500/30">
                  <AlertTriangle className="w-3 h-3 text-red-400" />
                  <span className="text-xs text-zinc-400">Clipping</span>
                  <span className={`text-xs font-bold ${overallClipping > 15 ? "text-red-400" : overallClipping > 5 ? "text-orange-400" : "text-green-400"}`}>
                    {overallClipping}%
                  </span>
                </div>
              )}
              {overallErs != null && (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/60 backdrop-blur-md border border-green-500/30">
                  <Battery className="w-3 h-3 text-green-400" />
                  <span className="text-xs text-zinc-400">ERS Deploy</span>
                  <span className="text-xs font-bold text-green-400">{Math.round(overallErs * 100)}%</span>
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

          {(() => {
            if (!circuitData?.x) {
              return (
                <div className="h-[520px] flex items-center justify-center text-zinc-500">
                  No track data available
                </div>
              );
            }

            const isReplay = colorMode === "replay";
            const isOverlayMode = ["zones","clipping","ersDeployment","liftCoast","drs"].includes(colorMode);
            const usesPlotly = !isReplay && !isOverlayMode; // speed/throttle/brake/gear use Plotly for hover+colorbar

            // Build colored segments for overlay modes + replay
            const buildOverlaySegments = () => {
              const segs = [];
              const n = circuitData.x.length;
              const limit = isReplay ? Math.min(replayIndex, n - 1) : n;

              const getColor = (i) => {
                if (colorMode === "zones") return ZONE_COLORS[circuitData.zones?.[i]] || "#88888840";
                if (colorMode === "clipping") return circuitData.clipping?.[i] ? "#ef4444cc" : "#22c55e20";
                if (colorMode === "ersDeployment") return circuitData.ersDeployment?.[i] ? "#4ade80cc" : "#ffffff08";
                if (colorMode === "liftCoast") return circuitData.liftCoast?.[i] ? "#3b82f6cc" : "#ffffff08";
                if (colorMode === "drs") return circuitData.drs?.[i] ? "#a855f7cc" : "#ffffff08";
                // Replay trail
                if (isReplay && i >= limit) return null;
                const isClip = circuitData.clipping?.[i];
                const isErs = circuitData.ersDeployment?.[i];
                const isLift = circuitData.liftCoast?.[i];
                const isDrs = circuitData.drs?.[i];
                if (isClip) return "#ef444490";
                if (isDrs) return "#a855f790";
                if (isErs) return "#4ade8070";
                if (isLift) return "#3b82f670";
                return "#ffffff12";
              };

              for (let i = 0; i < limit; i++) {
                const c = getColor(i);
                if (!c) continue;
                if (segs.length > 0 && segs[segs.length - 1].color === c) {
                  segs[segs.length - 1].endIdx = i;
                } else {
                  segs.push({ startIdx: i, endIdx: i, color: c });
                }
              }
              return segs;
            };

            // ── Plotly modes (speed/throttle/brake/gear) — keep hover tooltips + colorbar ──
            if (usesPlotly && trackTrace) {
              return (
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
              );
            }

            // ── Overlay + Replay modes: thick CircuitSVG ──
            // Smart layout based on track aspect ratio
            const xRange = Math.max(...circuitData.x) - Math.min(...circuitData.x);
            const yRange = Math.max(...circuitData.y) - Math.min(...circuitData.y);
            const isWideTrack = xRange > yRange * 1.3;

            // ERS status from real telemetry — no fake battery %
            const ersDeploying = !!(circuitData.ersDeployment?.[replayIndex]);
            const ersHarvesting = !ersDeploying && (circuitData.brake?.[replayIndex] || 0) > 20;

            const gaugePanel = isReplay && (
              <div className="flex flex-col items-center gap-3">
                <SpeedometerGauge
                  speed={circuitData.speed?.[replayIndex] || 0}
                  gear={circuitData.gear?.[replayIndex] ?? "—"}
                  throttle={circuitData.throttle?.[replayIndex] || 0}
                  brake={circuitData.brake?.[replayIndex] || 0}
                  driverColor={circuitData.color || "#E10600"}
                  size={170}
                  flag={
                    circuitData.clipping?.[replayIndex] ? "CLIPPING" :
                    circuitData.drs?.[replayIndex] ? "DRS OPEN" :
                    circuitData.ersDeployment?.[replayIndex] ? "ERS DEPLOY" :
                    circuitData.liftCoast?.[replayIndex] ? "LIFT & COAST" : null
                  }
                  flagColor={
                    circuitData.clipping?.[replayIndex] ? "#ef4444" :
                    circuitData.drs?.[replayIndex] ? "#a855f7" :
                    circuitData.ersDeployment?.[replayIndex] ? "#22c55e" :
                    circuitData.liftCoast?.[replayIndex] ? "#3b82f6" : "#666"
                  }
                />
                {/* Distance */}
                <div className="text-center">
                  <p className="text-sm font-mono text-white font-bold">
                    {Math.round(circuitData.distance?.[replayIndex] || 0)}
                    <span className="text-[9px] text-zinc-500 ml-0.5">m</span>
                  </p>
                  <div className="w-16 h-1 rounded-full bg-white/[0.06] overflow-hidden mt-0.5">
                    <div className="h-full rounded-full transition-all duration-75"
                      style={{
                        width: `${((circuitData.distance?.[replayIndex] || 0) / (circuitData.distance?.[circuitData.distance.length - 1] || 1)) * 100}%`,
                        background: circuitData.color || "#E10600",
                      }} />
                  </div>
                </div>
              </div>
            );

            const ersPanel = isReplay && (
              <ERSStatusIndicator
                deploying={ersDeploying}
                harvesting={ersHarvesting}
              />
            );

            const circuitSVGElement = (h) => (
              <CircuitSVG
                outline={{ x: circuitData.x, y: circuitData.y }}
                drivers={isReplay ? [{
                  id: selectedDriver,
                  x: circuitData.x[replayIndex] || 0,
                  y: circuitData.y[replayIndex] || 0,
                  color: circuitData.color || "#E10600",
                  label: selectedDriver,
                }] : []}
                highlightDriver={isReplay ? selectedDriver : undefined}
                showStartFinish thick
                corners={(circuitData.corners || []).map(c => ({ number: `T${c.number}`, x: c.x, y: c.y }))}
                trackSegments={buildOverlaySegments()}
                height={h}
              />
            );

            if (!isReplay) {
              // Overlay modes (zones/clipping/ERS/DRS/liftCoast) — just thick SVG, no gauges
              return <div className="p-2">{circuitSVGElement(540)}</div>;
            }

            // Replay mode — smart gauge positioning
            return (
              <div className="p-2">
                {isWideTrack ? (
                  // Wide track: circuit on top, gauges below
                  <>
                    {circuitSVGElement(480)}
                    <div className="flex items-center justify-center gap-6 pt-3">
                      {gaugePanel}
                      {ersPanel}
                    </div>
                  </>
                ) : (
                  // Tall track: circuit left, gauges right
                  <div className="flex items-start gap-4">
                    <div className="flex-1 min-w-0">
                      {circuitSVGElement(560)}
                    </div>
                    <div className="flex items-start gap-3 pt-4 shrink-0">
                      {gaugePanel}
                      {ersPanel}
                    </div>
                  </div>
                )}
              </div>
            );
          })()}
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
              {COLOR_MODES.filter((m) => m.key !== "drs" || circuitData?.drsAvailable).map((m) => (
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
            {/* Replay button — standalone, prominent */}
            <button
              onClick={() => setColorMode(colorMode === "replay" ? "speed" : "replay")}
              className={`w-full mt-2 flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-bold transition-all
                ${colorMode === "replay"
                  ? "bg-f1-red text-white shadow-lg shadow-red-500/20"
                  : "bg-white/5 text-zinc-400 hover:bg-white/10 hover:text-white border border-dashed border-white/10"
                }`}
            >
              <Play className="w-3.5 h-3.5" />
              {colorMode === "replay" ? "Exit Replay" : "Lap Replay"}
            </button>
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
            {colorMode === "clipping" && (
              <div className="mt-3 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
                  <span className="text-[9px] text-zinc-400">Clipping zone</span>
                </div>
                <p className="text-[9px] text-zinc-600">Throttle 100% + no speed gain = power limited</p>
                {overallClipping != null && <p className="text-[10px] text-red-400 font-semibold">Overall: {overallClipping}%</p>}
              </div>
            )}
            {colorMode === "ersDeployment" && (
              <div className="mt-3 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-green-400" />
                  <span className="text-[9px] text-zinc-400">ERS deploying</span>
                </div>
                <p className="text-[9px] text-zinc-600">Full throttle + accelerating = battery boost</p>
                {overallErs != null && <p className="text-[10px] text-green-400 font-semibold">Deploy ratio: {Math.round(overallErs * 100)}%</p>}
              </div>
            )}
            {colorMode === "liftCoast" && (
              <div className="mt-3 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-blue-500" />
                  <span className="text-[9px] text-zinc-400">Lift & coast</span>
                </div>
                <p className="text-[9px] text-zinc-600">Off throttle + off brake at speed = fuel/energy saving</p>
              </div>
            )}
            {colorMode === "drs" && (
              <div className="mt-3 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: "#a855f7" }} />
                  <span className="text-[9px] text-zinc-400">DRS open</span>
                </div>
                <p className="text-[9px] text-zinc-600">Rear wing flap open — reduced drag on straights</p>
                {!circuitData?.drsAvailable && (
                  <p className="text-[10px] text-amber-400">No DRS data for this session (2026+ uses X/Z mode instead)</p>
                )}
                {circuitData?.drs && (
                  <p className="text-[10px] text-purple-400 font-semibold">
                    DRS usage: {Math.round((circuitData.drs.filter(d => d).length / circuitData.drs.length) * 100)}% of lap
                  </p>
                )}
              </div>
            )}
            {colorMode === "replay" && (
              <div className="mt-3 space-y-3">
                {/* Play / Pause / Reset */}
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      if (replayIndex >= (circuitData?.x?.length || 1) - 1) {
                        indexRef.current = 0;
                        setReplayIndex(0);
                      }
                      setReplayPlaying(!replayPlaying);
                    }}
                    className="w-8 h-8 rounded-lg bg-f1-red flex items-center justify-center hover:bg-f1-red/80 transition-colors"
                  >
                    {replayPlaying
                      ? <Pause className="w-4 h-4 text-white" />
                      : <Play className="w-4 h-4 text-white ml-0.5" />}
                  </button>
                  <button
                    onClick={() => { setReplayPlaying(false); indexRef.current = 0; setReplayIndex(0); }}
                    className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center hover:bg-white/10 border border-white/10"
                  >
                    <RotateCcw className="w-3.5 h-3.5 text-zinc-400" />
                  </button>
                </div>

                {/* Speed buttons */}
                <div className="flex gap-1">
                  {[0.5, 1, 2, 4].map((s) => (
                    <button
                      key={s}
                      onClick={() => setReplaySpeed(s)}
                      className={`flex-1 py-1 rounded text-[10px] font-bold transition-all
                        ${replaySpeed === s ? "bg-f1-red text-white" : "bg-white/5 text-zinc-500 hover:bg-white/10"}`}
                    >
                      {s}x
                    </button>
                  ))}
                </div>

                {/* Scrubber */}
                <input
                  type="range"
                  min={0}
                  max={(circuitData?.x?.length || 1) - 1}
                  value={replayIndex}
                  onChange={(e) => {
                    const v = parseInt(e.target.value, 10);
                    indexRef.current = v;
                    setReplayIndex(v);
                    setReplayPlaying(false);
                  }}
                  className="w-full h-1.5 rounded-full appearance-none cursor-pointer bg-white/10 accent-f1-red
                    [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3
                    [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full
                    [&::-webkit-slider-thumb]:bg-f1-red [&::-webkit-slider-thumb]:cursor-pointer"
                />

                {/* Legend */}
                <div className="space-y-1 pt-1 border-t border-white/[0.06]">
                  <p className="text-[9px] text-zinc-500 font-semibold uppercase">Trail colors</p>
                  <div className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-red-500" />
                    <span className="text-[8px] text-zinc-500">Clipping</span>
                  </div>
                  {circuitData.drsAvailable && (
                    <div className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: "#a855f7" }} />
                      <span className="text-[8px] text-zinc-500">DRS Open</span>
                    </div>
                  )}
                  <div className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-green-400" />
                    <span className="text-[8px] text-zinc-500">ERS Deploy</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-blue-500" />
                    <span className="text-[8px] text-zinc-500">Lift & Coast</span>
                  </div>
                </div>
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
              const ca = (circuitData.cornerAnalysis || []).find((a) => a.corner === c.number);
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
                  {ca && (
                    <div className="mt-2 pt-2 border-t border-white/[0.06] space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-[8px] text-zinc-500">Entry</span>
                        <span className="text-[9px] text-zinc-300 font-mono">{Math.round(ca.entrySpeed)}</span>
                        <span className="text-[8px] text-zinc-500">Exit</span>
                        <span className="text-[9px] text-zinc-300 font-mono">{Math.round(ca.exitSpeed)}</span>
                      </div>
                      {ca.clippingPct > 0 && (
                        <div className="flex items-center gap-1">
                          <AlertTriangle className="w-2.5 h-2.5 text-red-400" />
                          <span className="text-[8px] text-red-400 font-semibold">Clip {ca.clippingPct}%</span>
                        </div>
                      )}
                      {ca.ersDeployPct > 0 && (
                        <div className="flex items-center gap-1">
                          <ZapIcon className="w-2.5 h-2.5 text-green-400" />
                          <span className="text-[8px] text-green-400 font-semibold">ERS {ca.ersDeployPct}%</span>
                        </div>
                      )}
                      {ca.liftCoastSamples > 0 && (
                        <div className="flex items-center gap-1">
                          <Wind className="w-2.5 h-2.5 text-blue-400" />
                          <span className="text-[8px] text-blue-400 font-semibold">L&C ×{ca.liftCoastSamples}</span>
                        </div>
                      )}
                    </div>
                  )}
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
