import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Activity, MapPin, Check } from "lucide-react";
import Plot from "react-plotly.js";
import GlassCard from "../components/GlassCard";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import { useApi } from "../hooks/useApi";

const ZONE_COLORS = {
  "Full Throttle": "#00CC00",
  "Partial Throttle": "#88CC44",
  "Coast/Harvest": "#FFD700",
  "Full Brake": "#FF3333",
  "Trail Brake": "#FF8800",
};

// For teammates with the same color, shift the second driver's hue
const TEAMMATE_ADJUSTMENTS = [
  { width: 2.5, opacity: 1.0 },
  { width: 2.0, opacity: 0.6 },
  { width: 1.5, opacity: 0.45 },
];

function lightenColor(hex, amount = 0.35) {
  const num = parseInt(hex.replace("#", ""), 16);
  let r = (num >> 16) & 0xff;
  let g = (num >> 8) & 0xff;
  let b = num & 0xff;
  r = Math.min(255, Math.round(r + (255 - r) * amount));
  g = Math.min(255, Math.round(g + (255 - g) * amount));
  b = Math.min(255, Math.round(b + (255 - b) * amount));
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, "0")}`;
}

const basePlotLayout = {
  template: "plotly_dark",
  paper_bgcolor: "transparent",
  plot_bgcolor: "rgba(255,255,255,0.02)",
  font: { color: "#a1a1aa" },
  margin: { l: 50, r: 20, t: 30, b: 40 },
};

const plotConfig = { displayModeBar: false, responsive: true };

function TelemetryChart({ title, traces, yLabel, height = 220, xRange }) {
  return (
    <div>
      <h3 className="text-sm font-medium text-zinc-400 mb-2 px-1">{title}</h3>
      <Plot
        data={traces}
        layout={{
          ...basePlotLayout,
          height,
          xaxis: {
            title: { text: "Distance (m)", font: { color: "#71717a", size: 11 } },
            color: "#a1a1aa",
            gridcolor: "rgba(255,255,255,0.04)",
            range: xRange || undefined,
          },
          yaxis: {
            title: { text: yLabel, font: { color: "#71717a", size: 11 } },
            color: "#a1a1aa",
            gridcolor: "rgba(255,255,255,0.04)",
          },
          showlegend: true,
          legend: {
            orientation: "h",
            y: 1.15,
            x: 0.5,
            xanchor: "center",
            font: { size: 11 },
          },
          margin: { l: 55, r: 20, t: 10, b: 45 },
        }}
        config={plotConfig}
        useResizeHandler
        style={{ width: "100%" }}
      />
    </div>
  );
}

export default function TelemetryLab() {
  const api = useApi();
  const [driverList, setDriverList] = useState([]);
  const [selectedDrivers, setSelectedDrivers] = useState([]);
  const [telemetry, setTelemetry] = useState(null);
  const [trackMaps, setTrackMaps] = useState({});
  const [activeTrackDriver, setActiveTrackDriver] = useState(null);
  const [trackColorBy, setTrackColorBy] = useState("speed");
  const [loadingDrivers, setLoadingDrivers] = useState(true);
  const [loadingTelemetry, setLoadingTelemetry] = useState(false);

  useEffect(() => {
    async function fetchDrivers() {
      try {
        const data = await api.call("/api/session/drivers");
        const list = data?.drivers || [];
        setDriverList(list);
        // Auto-select top 3 drivers
        if (list.length >= 3) {
          setSelectedDrivers(list.slice(0, 3).map((d) => d.code));
        } else if (list.length > 0) {
          setSelectedDrivers(list.map((d) => d.code));
        }
      } catch (e) {
        console.error("Failed to load drivers:", e);
      } finally {
        setLoadingDrivers(false);
      }
    }
    fetchDrivers();
  }, []);

  function toggleDriver(code) {
    setSelectedDrivers((prev) =>
      prev.includes(code) ? prev.filter((d) => d !== code) : [...prev, code]
    );
  }

  async function handleCompare() {
    if (selectedDrivers.length < 2) return;
    setLoadingTelemetry(true);
    setTelemetry(null);
    setTrackMaps({});
    try {
      // Fetch multi-driver telemetry
      const telData = await api.call(
        `/api/session/telemetry/multi?drivers=${selectedDrivers.join(",")}`
      );
      setTelemetry(telData);

      // Fetch track maps for all selected drivers in parallel
      const mapResults = await Promise.all(
        selectedDrivers.map((drv) =>
          api.call(`/api/session/trackmap?driver=${drv}`).catch(() => null)
        )
      );
      const maps = {};
      selectedDrivers.forEach((drv, i) => {
        if (mapResults[i]) maps[drv] = mapResults[i];
      });
      setTrackMaps(maps);
      setActiveTrackDriver(selectedDrivers[0]);
    } catch (e) {
      console.error("Failed to load telemetry:", e);
    } finally {
      setLoadingTelemetry(false);
    }
  }

  if (loadingDrivers) {
    return <LoadingSpinner text="Loading driver list..." />;
  }

  // Build trace styles: differentiate teammates by lightening color + adjusting width
  function getTraceStyle(trace) {
    const idx = trace.teammateIndex || 0;
    const adj = TEAMMATE_ADJUSTMENTS[Math.min(idx, TEAMMATE_ADJUSTMENTS.length - 1)];
    const color = idx > 0 ? lightenColor(trace.color, 0.3 * idx) : trace.color;
    return { color, width: adj.width, opacity: adj.opacity };
  }

  const traces = telemetry?.traces || [];
  const xRange =
    traces.length > 0 && traces[0].distance?.length > 0
      ? [traces[0].distance[0], traces[0].distance[traces[0].distance.length - 1]]
      : undefined;

  // Build plotly traces for each chart type
  function buildTraces(field) {
    return traces.map((t) => {
      const style = getTraceStyle(t);
      return {
        x: t.distance,
        y: t[field],
        type: "scattergl",
        mode: "lines",
        name: t.driver,
        line: { color: style.color, width: style.width },
        opacity: style.opacity,
      };
    });
  }

  const trackMap = activeTrackDriver ? trackMaps[activeTrackDriver] : null;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Telemetry Lab"
        subtitle="Multi-driver telemetry comparison"
        icon={Activity}
      />

      {/* Driver selector */}
      <GlassCard className="p-6" hover delay={0.1}>
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <label className="text-xs uppercase tracking-widest text-zinc-500">
              Select Drivers ({selectedDrivers.length} selected)
            </label>
            <div className="flex gap-2">
              <button
                onClick={() => setSelectedDrivers(driverList.map((d) => d.code))}
                className="px-3 py-1 text-xs bg-white/5 hover:bg-white/10 text-zinc-400 rounded transition-colors"
              >
                All
              </button>
              <button
                onClick={() => setSelectedDrivers([])}
                className="px-3 py-1 text-xs bg-white/5 hover:bg-white/10 text-zinc-400 rounded transition-colors"
              >
                None
              </button>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            {driverList.map((d) => {
              const isSelected = selectedDrivers.includes(d.code);
              return (
                <button
                  key={d.code}
                  onClick={() => toggleDriver(d.code)}
                  className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-all border ${
                    isSelected
                      ? "border-f1-red/50 bg-f1-red/15 text-white"
                      : "border-f1-border bg-white/5 text-zinc-400 hover:bg-white/10"
                  }`}
                >
                  {isSelected && <Check className="w-3.5 h-3.5 text-f1-red" />}
                  <span
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{ backgroundColor: d.color || "#888" }}
                  />
                  {d.code}
                </button>
              );
            })}
          </div>

          <motion.button
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            onClick={handleCompare}
            disabled={selectedDrivers.length < 2 || loadingTelemetry}
            className="self-start px-6 py-2.5 bg-f1-red hover:bg-red-600 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors glow-red"
          >
            {loadingTelemetry
              ? "Loading..."
              : `Compare ${selectedDrivers.length} Drivers`}
          </motion.button>
        </div>
        {selectedDrivers.length < 2 && selectedDrivers.length > 0 && (
          <p className="text-yellow-400/80 text-xs mt-3">
            Select at least 2 drivers to compare.
          </p>
        )}
      </GlassCard>

      {/* Loading state */}
      {loadingTelemetry && <LoadingSpinner text="Fetching telemetry data..." />}

      {/* Empty state */}
      {!telemetry && !loadingTelemetry && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center py-20"
        >
          <Activity className="w-12 h-12 text-zinc-700 mx-auto mb-4" />
          <p className="text-zinc-500 text-lg">
            Select drivers and hit Compare to view telemetry.
          </p>
        </motion.div>
      )}

      {/* Telemetry charts */}
      {telemetry && traces.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="space-y-6"
        >
          {/* Teammate legend note */}
          {traces.some((t) => t.teammateIndex > 0) && (
            <div className="flex items-center gap-3 px-1">
              <span className="text-xs text-zinc-500">
                Teammates differentiated by brightness — lighter = second driver on same team
              </span>
            </div>
          )}

          {/* Speed trace */}
          <GlassCard className="p-6" hover delay={0.1}>
            <TelemetryChart
              title="Speed Trace"
              yLabel="Speed (km/h)"
              xRange={xRange}
              height={280}
              traces={buildTraces("speed")}
            />
          </GlassCard>

          {/* Throttle */}
          <GlassCard className="p-6" hover delay={0.15}>
            <TelemetryChart
              title="Throttle Application"
              yLabel="Throttle (%)"
              xRange={xRange}
              traces={buildTraces("throttle")}
            />
          </GlassCard>

          {/* Brake */}
          <GlassCard className="p-6" hover delay={0.2}>
            <TelemetryChart
              title="Brake Pressure"
              yLabel="Brake"
              xRange={xRange}
              traces={buildTraces("brake")}
            />
          </GlassCard>

          {/* Circuit Track Map with driver tabs */}
          {Object.keys(trackMaps).length > 0 && (
            <GlassCard className="p-6" hover delay={0.3}>
              <div className="flex flex-col gap-4 mb-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <MapPin className="w-4 h-4 text-f1-red" />
                    <h3 className="text-sm font-semibold text-white uppercase tracking-widest">
                      Circuit Map
                    </h3>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-zinc-500">Color by:</span>
                    {["speed", "throttle", "brake", "zone"].map((opt) => (
                      <button
                        key={opt}
                        onClick={() => setTrackColorBy(opt)}
                        className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                          trackColorBy === opt
                            ? "bg-f1-red text-white"
                            : "bg-white/5 text-zinc-400 hover:bg-white/10"
                        }`}
                      >
                        {opt.charAt(0).toUpperCase() + opt.slice(1)}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Driver tabs */}
                <div className="flex flex-wrap gap-2">
                  {Object.keys(trackMaps).map((drv) => (
                    <button
                      key={drv}
                      onClick={() => setActiveTrackDriver(drv)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border ${
                        activeTrackDriver === drv
                          ? "border-f1-red bg-f1-red/20 text-white"
                          : "border-f1-border bg-white/5 text-zinc-400 hover:bg-white/10"
                      }`}
                    >
                      {drv}
                    </button>
                  ))}
                </div>
              </div>

              {trackMap && trackMap.x && (
                <>
                  <Plot
                    data={[
                      trackColorBy === "zone"
                        ? {
                            x: trackMap.x,
                            y: trackMap.y,
                            type: "scattergl",
                            mode: "markers",
                            marker: {
                              size: 4,
                              color: trackMap.zones.map(
                                (z) => ZONE_COLORS[z] || "#888"
                              ),
                            },
                            text: trackMap.zones.map(
                              (z, i) =>
                                `${z}<br>Speed: ${trackMap.speed[i]?.toFixed(
                                  0
                                )} km/h<br>Dist: ${trackMap.distance[i]?.toFixed(0)}m`
                            ),
                            hovertemplate: "%{text}<extra></extra>",
                            showlegend: false,
                          }
                        : {
                            x: trackMap.x,
                            y: trackMap.y,
                            type: "scattergl",
                            mode: "markers",
                            marker: {
                              size: 4,
                              color:
                                trackColorBy === "speed"
                                  ? trackMap.speed
                                  : trackColorBy === "throttle"
                                  ? trackMap.throttle
                                  : trackMap.brake,
                              colorscale:
                                trackColorBy === "brake"
                                  ? [
                                      [0, "#111"],
                                      [0.3, "#FF8800"],
                                      [1, "#FF3333"],
                                    ]
                                  : trackColorBy === "throttle"
                                  ? [
                                      [0, "#FF3333"],
                                      [0.5, "#FFD700"],
                                      [1, "#00CC00"],
                                    ]
                                  : "Turbo",
                              showscale: true,
                              colorbar: {
                                title: {
                                  text:
                                    trackColorBy === "speed"
                                      ? "km/h"
                                      : trackColorBy === "throttle"
                                      ? "Throttle %"
                                      : "Brake %",
                                  font: { color: "#a1a1aa", size: 11 },
                                },
                                tickfont: { color: "#71717a", size: 10 },
                                len: 0.6,
                              },
                            },
                            text: trackMap.speed.map(
                              (s, i) =>
                                `Speed: ${s?.toFixed(
                                  0
                                )} km/h<br>Throttle: ${trackMap.throttle[
                                  i
                                ]?.toFixed(0)}%<br>Brake: ${(
                                  trackMap.brake[i] * 100
                                )?.toFixed(0)}%<br>Gear: ${
                                  trackMap.gear?.[i] || "?"
                                }`
                            ),
                            hovertemplate: "%{text}<extra></extra>",
                            showlegend: false,
                          },
                      // Corner markers
                      ...(trackMap.corners
                        ? [
                            {
                              x: trackMap.corners.map((c) => c.x),
                              y: trackMap.corners.map((c) => c.y),
                              type: "scatter",
                              mode: "markers+text",
                              marker: {
                                size: 8,
                                color: "rgba(255,255,255,0.15)",
                                line: { color: "#fff", width: 1 },
                              },
                              text: trackMap.corners.map((_, i) => `${i + 1}`),
                              textposition: "top center",
                              textfont: { size: 9, color: "#a1a1aa" },
                              hovertemplate: trackMap.corners.map(
                                (c, i) =>
                                  `Turn ${i + 1}<br>Speed: ${c.speed?.toFixed(
                                    0
                                  )} km/h<br>Gear: ${
                                    c.gear || "?"
                                  }<extra></extra>`
                              ),
                              showlegend: false,
                            },
                          ]
                        : []),
                    ]}
                    layout={{
                      ...basePlotLayout,
                      height: 500,
                      xaxis: {
                        scaleanchor: "y",
                        showgrid: false,
                        zeroline: false,
                        showticklabels: false,
                      },
                      yaxis: {
                        showgrid: false,
                        zeroline: false,
                        showticklabels: false,
                      },
                      margin: { l: 10, r: 60, t: 10, b: 10 },
                    }}
                    config={plotConfig}
                    useResizeHandler
                    style={{ width: "100%" }}
                  />

                  {/* Zone legend */}
                  {trackColorBy === "zone" && (
                    <div className="flex items-center gap-4 mt-3 justify-center">
                      {Object.entries(ZONE_COLORS).map(([zone, color]) => (
                        <div key={zone} className="flex items-center gap-1.5">
                          <span
                            className="w-3 h-3 rounded-full"
                            style={{ backgroundColor: color }}
                          />
                          <span className="text-xs text-zinc-400">{zone}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </GlassCard>
          )}
        </motion.div>
      )}
    </div>
  );
}
