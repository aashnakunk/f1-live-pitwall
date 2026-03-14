import { useState, useEffect } from "react";
import { Zap, Battery, MapPin } from "lucide-react";
import Plot from "react-plotly.js";
import { motion } from "framer-motion";
import { useApi } from "../hooks/useApi";
import GlassCard from "../components/GlassCard";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";

const ZONE_COLORS = {
  "Full Throttle": "#00CC00",
  "Partial Throttle": "#88CC44",
  "Coast/Harvest": "#FFD700",
  "Full Brake": "#FF3333",
  "Trail Brake": "#FF8800",
};

const darkLayout = {
  template: "plotly_dark",
  paper_bgcolor: "transparent",
  plot_bgcolor: "rgba(255,255,255,0.02)",
  font: { color: "#a1a1aa" },
  margin: { l: 50, r: 20, t: 30, b: 40 },
};

const plotConfig = { displayModeBar: false, responsive: true };

export default function EnergyMap() {
  const { call, loading, error } = useApi();
  const [drivers, setDrivers] = useState([]);
  const [selectedDriver, setSelectedDriver] = useState("");
  const [energyData, setEnergyData] = useState(null);

  useEffect(() => {
    async function fetchDrivers() {
      const data = await call("/api/session/drivers");
      const list = data?.drivers || [];
      if (list.length > 0) {
        setDrivers(list);
        setSelectedDriver(list[0].code);
      }
    }
    fetchDrivers();
  }, []);

  async function handleAnalyze() {
    if (!selectedDriver) return;
    const data = await call(`/api/session/energy?driver=${selectedDriver}`);
    if (data) setEnergyData(data);
  }

  const driverCode = (d) => (typeof d === "string" ? d : d.code || d.abbreviation || d.name);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Energy Map"
        subtitle="Braking zones, coasting, energy harvesting"
        icon={Zap}
      />

      {error && (
        <div className="text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg p-3 text-sm">
          {error}
        </div>
      )}

      {/* Driver Selector */}
      <GlassCard className="p-4" hover delay={0.1}>
        <div className="flex items-center gap-4 flex-wrap">
          <label className="text-sm text-zinc-400 font-medium">Select Driver</label>
          <select
            value={selectedDriver}
            onChange={(e) => setSelectedDriver(e.target.value)}
            className="bg-f1-surface border border-f1-border rounded-lg px-4 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-f1-red/50 min-w-[160px]"
          >
            {drivers.map((d, i) => (
              <option key={i} value={driverCode(d)}>
                {driverCode(d)}
              </option>
            ))}
          </select>
          <button
            onClick={handleAnalyze}
            disabled={loading || !selectedDriver}
            className="px-5 py-2 bg-f1-red hover:bg-red-600 text-white font-semibold text-sm rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Analyzing..." : "Analyze"}
          </button>

          {/* Zone legend */}
          <div className="flex items-center gap-3 ml-auto flex-wrap">
            {Object.entries(ZONE_COLORS).map(([zone, color]) => (
              <div key={zone} className="flex items-center gap-1.5">
                <span
                  className="w-3 h-3 rounded-full inline-block"
                  style={{ backgroundColor: color }}
                />
                <span className="text-xs text-zinc-400">{zone}</span>
              </div>
            ))}
          </div>
        </div>
      </GlassCard>

      {loading && !energyData && <LoadingSpinner text="Analyzing energy data..." />}

      {energyData && (
        <>
          {/* Speed Trace Colored by Zone */}
          <GlassCard className="p-4" hover delay={0.15}>
            <h3 className="text-lg font-semibold text-white mb-3">
              Speed Trace — {energyData.driver}
            </h3>
            <Plot
              data={[
                {
                  x: energyData.distance,
                  y: energyData.speed,
                  type: "scatter",
                  mode: "markers",
                  marker: {
                    size: 3,
                    color: energyData.zones.map((z) => ZONE_COLORS[z] || "#888"),
                  },
                  hovertemplate:
                    "Dist: %{x:.0f}m<br>Speed: %{y:.0f} km/h<br>Zone: %{text}<extra></extra>",
                  text: energyData.zones,
                  showlegend: false,
                },
              ]}
              layout={{
                ...darkLayout,
                xaxis: { title: "Distance (m)", gridcolor: "rgba(255,255,255,0.05)" },
                yaxis: { title: "Speed (km/h)", gridcolor: "rgba(255,255,255,0.05)" },
                height: 350,
              }}
              config={plotConfig}
              useResizeHandler
              className="w-full"
            />
          </GlassCard>

          {/* Three-Row Subplot: Speed, Throttle, Brake */}
          <GlassCard className="p-4" hover delay={0.2}>
            <h3 className="text-lg font-semibold text-white mb-3">Telemetry Channels</h3>
            <Plot
              data={[
                {
                  x: energyData.distance,
                  y: energyData.speed,
                  type: "scatter",
                  mode: "lines",
                  name: "Speed",
                  line: { color: energyData.color || "#3b82f6", width: 1.5 },
                  xaxis: "x",
                  yaxis: "y",
                },
                {
                  x: energyData.distance,
                  y: energyData.throttle,
                  type: "scatter",
                  mode: "lines",
                  name: "Throttle",
                  fill: "tozeroy",
                  fillcolor: "rgba(34,197,94,0.15)",
                  line: { color: "#22c55e", width: 1.5 },
                  xaxis: "x2",
                  yaxis: "y2",
                },
                {
                  x: energyData.distance,
                  y: energyData.brake,
                  type: "scatter",
                  mode: "lines",
                  name: "Brake",
                  fill: "tozeroy",
                  fillcolor: "rgba(239,68,68,0.15)",
                  line: { color: "#ef4444", width: 1.5 },
                  xaxis: "x3",
                  yaxis: "y3",
                },
              ]}
              layout={{
                ...darkLayout,
                grid: { rows: 3, columns: 1, pattern: "independent", roworder: "top to bottom" },
                xaxis: {
                  gridcolor: "rgba(255,255,255,0.05)",
                  showticklabels: false,
                },
                yaxis: {
                  title: "Speed",
                  gridcolor: "rgba(255,255,255,0.05)",
                },
                xaxis2: {
                  gridcolor: "rgba(255,255,255,0.05)",
                  showticklabels: false,
                },
                yaxis2: {
                  title: "Throttle %",
                  gridcolor: "rgba(255,255,255,0.05)",
                  range: [0, 105],
                },
                xaxis3: {
                  title: "Distance (m)",
                  gridcolor: "rgba(255,255,255,0.05)",
                },
                yaxis3: {
                  title: "Brake %",
                  gridcolor: "rgba(255,255,255,0.05)",
                  range: [0, 105],
                },
                height: 550,
                margin: { l: 60, r: 20, t: 20, b: 50 },
                showlegend: true,
                legend: { orientation: "h", y: 1.05 },
              }}
              config={plotConfig}
              useResizeHandler
              className="w-full"
            />
          </GlassCard>

          {/* Braking Events Table */}
          {energyData.events && energyData.events.length > 0 && (
            <GlassCard className="p-4" hover delay={0.25}>
              <h3 className="text-lg font-semibold text-white mb-3">Braking &amp; Zone Events</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead>
                    <tr className="border-b border-f1-border text-zinc-400 uppercase text-xs">
                      <th className="py-3 px-4">#</th>
                      <th className="py-3 px-4">Zone</th>
                      <th className="py-3 px-4">Distance (m)</th>
                      <th className="py-3 px-4">Length (m)</th>
                      <th className="py-3 px-4">Entry Speed</th>
                      <th className="py-3 px-4">Exit Speed</th>
                      <th className="py-3 px-4">Speed Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {energyData.events.map((evt, i) => (
                      <tr
                        key={i}
                        className="border-b border-f1-border/50 hover:bg-white/5 transition-colors"
                      >
                        <td className="py-2.5 px-4 text-zinc-500">{i + 1}</td>
                        <td className="py-2.5 px-4">
                          <span
                            className="px-2 py-0.5 rounded text-xs font-bold"
                            style={{
                              backgroundColor: `${ZONE_COLORS[evt.zone] || "#888"}22`,
                              color: ZONE_COLORS[evt.zone] || "#888",
                            }}
                          >
                            {evt.zone}
                          </span>
                        </td>
                        <td className="py-2.5 px-4 text-zinc-300">
                          {typeof evt.distance === "number" ? evt.distance.toFixed(0) : evt.distance}
                        </td>
                        <td className="py-2.5 px-4 text-zinc-300">
                          {typeof evt.length === "number" ? evt.length.toFixed(0) : evt.length}
                        </td>
                        <td className="py-2.5 px-4 text-zinc-300">
                          {typeof evt.entrySpeed === "number"
                            ? `${evt.entrySpeed.toFixed(0)} km/h`
                            : evt.entrySpeed}
                        </td>
                        <td className="py-2.5 px-4 text-zinc-300">
                          {typeof evt.exitSpeed === "number"
                            ? `${evt.exitSpeed.toFixed(0)} km/h`
                            : evt.exitSpeed}
                        </td>
                        <td className="py-2.5 px-4">
                          <span
                            className={`font-mono font-bold ${
                              evt.speedDelta < 0 ? "text-red-400" : "text-green-400"
                            }`}
                          >
                            {evt.speedDelta > 0 ? "+" : ""}
                            {typeof evt.speedDelta === "number"
                              ? `${evt.speedDelta.toFixed(0)} km/h`
                              : evt.speedDelta}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </GlassCard>
          )}

          {/* Zone Summary: Pie Chart + Stats */}
          {energyData.zoneSummary && energyData.zoneSummary.length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <GlassCard className="p-4" hover delay={0.3}>
                <h3 className="text-lg font-semibold text-white mb-3">Zone Distribution</h3>
                <Plot
                  data={[
                    {
                      labels: energyData.zoneSummary.map((z) => z.zone),
                      values: energyData.zoneSummary.map((z) => z.pctOfLap),
                      type: "pie",
                      hole: 0.5,
                      marker: {
                        colors: energyData.zoneSummary.map(
                          (z) => ZONE_COLORS[z.zone] || "#888"
                        ),
                      },
                      textinfo: "label+percent",
                      textfont: { size: 11, color: "#fff" },
                      hovertemplate:
                        "%{label}<br>%{value:.1f}% of lap<br>Count: %{customdata}<extra></extra>",
                      customdata: energyData.zoneSummary.map((z) => z.count),
                    },
                  ]}
                  layout={{
                    ...darkLayout,
                    height: 320,
                    showlegend: false,
                    margin: { l: 20, r: 20, t: 20, b: 20 },
                    annotations: [
                      {
                        text: energyData.driver,
                        showarrow: false,
                        font: { size: 16, color: "#fff", family: "monospace" },
                        x: 0.5,
                        y: 0.5,
                      },
                    ],
                  }}
                  config={plotConfig}
                  useResizeHandler
                  className="w-full"
                />
              </GlassCard>

              <GlassCard className="p-4" hover delay={0.35}>
                <h3 className="text-lg font-semibold text-white mb-3">Zone Summary</h3>
                <div className="space-y-3">
                  {energyData.zoneSummary.map((z, i) => (
                    <motion.div
                      key={z.zone}
                      initial={{ opacity: 0, x: 20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.05 }}
                      className="flex items-center gap-3"
                    >
                      <span
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: ZONE_COLORS[z.zone] || "#888" }}
                      />
                      <span className="text-sm text-zinc-300 flex-1">{z.zone}</span>
                      <span className="text-sm text-zinc-400 w-16 text-right">
                        {z.count} zones
                      </span>
                      <span className="text-sm text-zinc-400 w-20 text-right">
                        {typeof z.totalDist === "number" ? `${z.totalDist.toFixed(0)}m` : z.totalDist}
                      </span>
                      <div className="w-32 h-2 bg-white/5 rounded-full overflow-hidden">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${z.pctOfLap}%` }}
                          transition={{ duration: 0.8, delay: i * 0.05 }}
                          className="h-full rounded-full"
                          style={{ backgroundColor: ZONE_COLORS[z.zone] || "#888" }}
                        />
                      </div>
                      <span className="text-sm font-mono text-white w-14 text-right">
                        {typeof z.pctOfLap === "number" ? `${z.pctOfLap.toFixed(1)}%` : z.pctOfLap}
                      </span>
                    </motion.div>
                  ))}
                </div>
              </GlassCard>
            </div>
          )}
          {/* Energy Harvest / Deploy Model (2026 Regs) */}
          {energyData.harvestKW && (
            <GlassCard className="p-4" hover delay={0.4}>
              <div className="flex items-center gap-2 mb-3">
                <Battery className="w-5 h-5 text-yellow-400" />
                <h3 className="text-lg font-semibold text-white">
                  Energy Harvest / Deploy Model
                </h3>
                <span className="text-xs text-zinc-500 ml-2">2026 Regs: 350kW MGU-K, {energyData.batteryMax} MJ battery</span>
              </div>
              <Plot
                data={[
                  {
                    x: energyData.distance,
                    y: energyData.harvestKW,
                    type: "scatter",
                    mode: "lines",
                    name: "Harvest (kW)",
                    fill: "tozeroy",
                    fillcolor: "rgba(34,197,94,0.15)",
                    line: { color: "#22c55e", width: 1.5 },
                  },
                  {
                    x: energyData.distance,
                    y: energyData.deployKW,
                    type: "scatter",
                    mode: "lines",
                    name: "Deploy (kW)",
                    fill: "tozeroy",
                    fillcolor: "rgba(239,68,68,0.1)",
                    line: { color: "#ef4444", width: 1.5 },
                  },
                ]}
                layout={{
                  ...darkLayout,
                  height: 280,
                  xaxis: { title: "Distance (m)", gridcolor: "rgba(255,255,255,0.05)" },
                  yaxis: {
                    title: "Power (kW)",
                    gridcolor: "rgba(255,255,255,0.05)",
                    zeroline: true,
                    zerolinecolor: "rgba(255,255,255,0.1)",
                  },
                  legend: { orientation: "h", y: 1.1 },
                  margin: { l: 60, r: 20, t: 10, b: 50 },
                }}
                config={plotConfig}
                useResizeHandler
                className="w-full"
              />
            </GlassCard>
          )}

          {/* Battery State of Charge */}
          {energyData.batteryMJ && (
            <GlassCard className="p-4" hover delay={0.45}>
              <h3 className="text-lg font-semibold text-white mb-3">
                Battery State of Charge
              </h3>
              <Plot
                data={[
                  {
                    x: energyData.distance,
                    y: energyData.batteryMJ,
                    type: "scatter",
                    mode: "lines",
                    name: "Battery (MJ)",
                    fill: "tozeroy",
                    fillcolor: "rgba(250,204,21,0.1)",
                    line: { color: "#facc15", width: 2 },
                  },
                  // Max battery line
                  {
                    x: [energyData.distance[0], energyData.distance[energyData.distance.length - 1]],
                    y: [energyData.batteryMax, energyData.batteryMax],
                    type: "scatter",
                    mode: "lines",
                    name: "Max Capacity",
                    line: { color: "#ef4444", width: 1, dash: "dash" },
                  },
                  // Clipping markers
                  ...(energyData.clippingZones?.length > 0
                    ? [
                        {
                          x: energyData.clippingZones,
                          y: energyData.clippingZones.map(() => 0),
                          type: "scatter",
                          mode: "markers",
                          name: "Power Clipping",
                          marker: { color: "#ef4444", size: 6, symbol: "triangle-down" },
                          hovertemplate: "Clipping at %{x:.0f}m<extra></extra>",
                        },
                      ]
                    : []),
                  // Regen clip markers
                  ...(energyData.regenClipZones?.length > 0
                    ? [
                        {
                          x: energyData.regenClipZones,
                          y: energyData.regenClipZones.map(() => energyData.batteryMax),
                          type: "scatter",
                          mode: "markers",
                          name: "Regen Clipping",
                          marker: { color: "#22c55e", size: 6, symbol: "triangle-up" },
                          hovertemplate: "Regen clip at %{x:.0f}m<extra></extra>",
                        },
                      ]
                    : []),
                ]}
                layout={{
                  ...darkLayout,
                  height: 260,
                  xaxis: { title: "Distance (m)", gridcolor: "rgba(255,255,255,0.05)" },
                  yaxis: {
                    title: "Battery (MJ)",
                    gridcolor: "rgba(255,255,255,0.05)",
                    range: [0, energyData.batteryMax * 1.1],
                  },
                  legend: { orientation: "h", y: 1.12, font: { size: 10 } },
                  margin: { l: 60, r: 20, t: 10, b: 50 },
                }}
                config={plotConfig}
                useResizeHandler
                className="w-full"
              />
              <div className="flex items-center gap-6 mt-2 text-xs text-zinc-400">
                <span>
                  <span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1" />
                  Power clipping = battery empty (less power available)
                </span>
                <span>
                  <span className="inline-block w-2 h-2 rounded-full bg-green-500 mr-1" />
                  Regen clipping = battery full (wasted regen energy)
                </span>
              </div>
            </GlassCard>
          )}

          {/* Circuit Map with Energy Zones */}
          {energyData.x && energyData.y && (
            <GlassCard className="p-4" hover delay={0.5}>
              <div className="flex items-center gap-2 mb-3">
                <MapPin className="w-4 h-4 text-f1-red" />
                <h3 className="text-lg font-semibold text-white">
                  Circuit Energy Map
                </h3>
              </div>
              <Plot
                data={[
                  {
                    x: energyData.x,
                    y: energyData.y,
                    type: "scattergl",
                    mode: "markers",
                    marker: {
                      size: 4,
                      color: energyData.zones.map((z) => ZONE_COLORS[z] || "#888"),
                    },
                    text: energyData.zones.map(
                      (z, i) =>
                        `${z}<br>Speed: ${energyData.speed[i]?.toFixed(0)} km/h<br>Harvest: ${energyData.harvestKW?.[i]?.toFixed(0) || 0} kW<br>Deploy: ${Math.abs(energyData.deployKW?.[i] || 0).toFixed(0)} kW`
                    ),
                    hovertemplate: "%{text}<extra></extra>",
                    showlegend: false,
                  },
                ]}
                layout={{
                  ...darkLayout,
                  height: 480,
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
                  margin: { l: 10, r: 10, t: 10, b: 10 },
                }}
                config={plotConfig}
                useResizeHandler
                className="w-full"
              />
              <div className="flex items-center gap-4 mt-2 justify-center flex-wrap">
                {Object.entries(ZONE_COLORS).map(([zone, color]) => (
                  <div key={zone} className="flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
                    <span className="text-xs text-zinc-400">{zone}</span>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}
        </>
      )}
    </div>
  );
}
