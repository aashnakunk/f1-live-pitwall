import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Timer, AlertTriangle, Flag } from "lucide-react";
import Plot from "react-plotly.js";
import GlassCard from "../components/GlassCard";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import { useApi } from "../hooks/useApi";

const darkLayout = {
  template: "plotly_dark",
  paper_bgcolor: "transparent",
  plot_bgcolor: "rgba(255,255,255,0.02)",
  font: { color: "#a1a1aa" },
};

const plotConfig = { displayModeBar: false, responsive: true };

const SC_COLORS = { SC: "#FFC300", VSC: "#FF8800" };

export default function PitStrategy() {
  const { call } = useApi();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const result = await call("/api/session/pitstrategy");
        setData(result);
      } catch (e) {
        console.error("Failed to load pit strategy:", e);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  if (loading) return <LoadingSpinner text="Loading pit strategy..." />;
  if (!data) {
    return (
      <div className="text-center text-zinc-500 py-20">
        No pit strategy data available.
      </div>
    );
  }

  const { stints, pitStops, strategies, scEvents, maxLap } = data;

  // Build stint timeline traces for Plotly
  const stintTraces = [];
  stints.forEach((drvData, drvIdx) => {
    drvData.stints.forEach((stint) => {
      stintTraces.push({
        type: "bar",
        orientation: "h",
        y: [drvData.driver],
        x: [stint.endLap - stint.startLap + 1],
        base: stint.startLap - 1,
        marker: { color: stint.color, line: { color: "rgba(0,0,0,0.3)", width: 1 } },
        hovertemplate: `${drvData.driver}<br>${stint.compound}<br>Laps ${stint.startLap}-${stint.endLap} (${stint.laps} laps)<extra></extra>`,
        showlegend: false,
      });
    });
  });

  // SC/VSC shapes for the timeline
  const scShapes = (scEvents || []).map((ev) => ({
    type: "rect",
    xref: "x",
    yref: "paper",
    x0: ev.startLap - 0.5,
    x1: ev.endLap + 0.5,
    y0: 0,
    y1: 1,
    fillcolor: ev.type === "SC" ? "rgba(255,195,0,0.12)" : "rgba(255,136,0,0.12)",
    line: { color: SC_COLORS[ev.type] || "#888", width: 1, dash: "dot" },
  }));

  // SC annotations
  const scAnnotations = (scEvents || []).map((ev) => ({
    x: (ev.startLap + ev.endLap) / 2,
    y: 1.02,
    xref: "x",
    yref: "paper",
    text: ev.type,
    showarrow: false,
    font: { size: 10, color: SC_COLORS[ev.type] || "#888", family: "monospace" },
  }));

  // Pit stop duration chart
  const allStopsFlat = [];
  Object.values(pitStops).forEach((d) => {
    d.stops.forEach((s) => {
      if (s.duration) {
        allStopsFlat.push({ ...s, driver: d.driver, color: d.color });
      }
    });
  });

  return (
    <div className="space-y-8">
      <PageHeader
        title="Pit Strategy"
        subtitle="Pit stops, tyre stints, undercut/overcut detection, SC/VSC"
        icon={Timer}
      />

      {/* Stint Timeline */}
      <GlassCard className="p-6" hover delay={0.1}>
        <h3 className="text-sm font-semibold text-white pb-3 uppercase tracking-widest">
          Tyre Stint Timeline
        </h3>
        <Plot
          data={stintTraces}
          layout={{
            ...darkLayout,
            barmode: "stack",
            height: Math.max(300, stints.length * 28 + 80),
            xaxis: {
              title: { text: "Lap", font: { color: "#71717a", size: 12 } },
              range: [0, maxLap + 1],
              gridcolor: "rgba(255,255,255,0.04)",
              color: "#a1a1aa",
            },
            yaxis: {
              autorange: "reversed",
              color: "#a1a1aa",
              tickfont: { size: 11 },
            },
            margin: { l: 55, r: 20, t: 10, b: 45 },
            shapes: scShapes,
            annotations: scAnnotations,
          }}
          config={plotConfig}
          useResizeHandler
          style={{ width: "100%" }}
        />
        {/* Legend */}
        <div className="flex items-center gap-4 mt-2 flex-wrap">
          {[
            ["SOFT", "#FF3333"],
            ["MEDIUM", "#FFC300"],
            ["HARD", "#FFFFFF"],
            ["INTER", "#39B54A"],
            ["WET", "#0067FF"],
          ].map(([label, color]) => (
            <div key={label} className="flex items-center gap-1.5">
              <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: color }} />
              <span className="text-xs text-zinc-400">{label}</span>
            </div>
          ))}
          {scEvents?.length > 0 && (
            <>
              <span className="text-zinc-600">|</span>
              {Object.entries(SC_COLORS).map(([label, color]) => (
                <div key={label} className="flex items-center gap-1.5">
                  <span
                    className="w-3 h-3 rounded-sm border"
                    style={{ borderColor: color, backgroundColor: `${color}20` }}
                  />
                  <span className="text-xs text-zinc-400">{label}</span>
                </div>
              ))}
            </>
          )}
        </div>
      </GlassCard>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Pit Stop Details */}
        <GlassCard className="p-5 overflow-hidden" hover delay={0.15}>
          <h3 className="text-sm font-semibold text-white pb-3 uppercase tracking-widest">
            Pit Stops
          </h3>
          <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table className="w-full text-sm text-left">
              <thead className="sticky top-0 bg-f1-card">
                <tr className="border-b border-f1-border text-zinc-500 uppercase text-xs tracking-wider">
                  <th className="px-3 py-2">Driver</th>
                  <th className="px-3 py-2">Lap</th>
                  <th className="px-3 py-2">Duration</th>
                  <th className="px-3 py-2">Tyre Change</th>
                </tr>
              </thead>
              <tbody>
                {Object.values(pitStops)
                  .flatMap((d) =>
                    d.stops.map((s) => ({ ...s, driver: d.driver, driverColor: d.color }))
                  )
                  .sort((a, b) => a.lap - b.lap)
                  .map((s, i) => (
                    <motion.tr
                      key={`${s.driver}-${s.lap}`}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: i * 0.02 }}
                      className="border-b border-f1-border/40 hover:bg-white/[0.03]"
                    >
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                          <span
                            className="w-2 h-2 rounded-full"
                            style={{ backgroundColor: s.driverColor }}
                          />
                          <span className="text-white font-medium">{s.driver}</span>
                        </div>
                      </td>
                      <td className="px-3 py-2 text-zinc-300 font-mono">{s.lap}</td>
                      <td className="px-3 py-2">
                        {s.duration ? (
                          <span
                            className={`font-mono font-bold ${
                              s.duration < 25 ? "text-green-400" : s.duration < 30 ? "text-yellow-400" : "text-red-400"
                            }`}
                          >
                            {s.duration}s
                          </span>
                        ) : (
                          <span className="text-zinc-600">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-1">
                          <span
                            className="text-xs font-bold px-1.5 py-0.5 rounded"
                            style={{
                              color: s.colorBefore,
                              backgroundColor: `${s.colorBefore}15`,
                            }}
                          >
                            {s.compoundBefore?.[0] || "?"}
                          </span>
                          <span className="text-zinc-600 text-xs">&rarr;</span>
                          <span
                            className="text-xs font-bold px-1.5 py-0.5 rounded"
                            style={{
                              color: s.colorAfter,
                              backgroundColor: `${s.colorAfter}15`,
                            }}
                          >
                            {s.compoundAfter?.[0] || "?"}
                          </span>
                        </div>
                      </td>
                    </motion.tr>
                  ))}
              </tbody>
            </table>
          </div>
        </GlassCard>

        {/* Pit Stop Duration Bar Chart */}
        <GlassCard className="p-5" hover delay={0.2}>
          <h3 className="text-sm font-semibold text-white pb-3 uppercase tracking-widest">
            Pit Stop Durations
          </h3>
          {allStopsFlat.length > 0 ? (
            <Plot
              data={[
                {
                  type: "bar",
                  x: allStopsFlat.map((s) => `${s.driver} L${s.lap}`),
                  y: allStopsFlat.map((s) => s.duration),
                  marker: {
                    color: allStopsFlat.map((s) =>
                      s.duration < 25 ? "#22c55e" : s.duration < 30 ? "#facc15" : "#ef4444"
                    ),
                  },
                  hovertemplate: "%{x}<br>%{y:.1f}s<extra></extra>",
                },
              ]}
              layout={{
                ...darkLayout,
                height: 340,
                xaxis: {
                  tickangle: -45,
                  tickfont: { size: 10 },
                  color: "#a1a1aa",
                  gridcolor: "rgba(255,255,255,0.04)",
                },
                yaxis: {
                  title: { text: "Duration (s)", font: { color: "#71717a", size: 12 } },
                  color: "#a1a1aa",
                  gridcolor: "rgba(255,255,255,0.04)",
                },
                margin: { l: 50, r: 20, t: 10, b: 80 },
              }}
              config={plotConfig}
              useResizeHandler
              style={{ width: "100%" }}
            />
          ) : (
            <p className="text-zinc-500 text-sm py-8 text-center">
              No pit stop duration data available.
            </p>
          )}
        </GlassCard>
      </div>

      {/* Undercut / Overcut Detections */}
      {strategies && strategies.length > 0 && (
        <GlassCard className="p-5" hover delay={0.25}>
          <div className="flex items-center gap-2 pb-3">
            <AlertTriangle className="w-4 h-4 text-yellow-400" />
            <h3 className="text-sm font-semibold text-white uppercase tracking-widest">
              Undercut / Overcut Detected
            </h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {strategies.map((s, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
                className={`glass p-4 rounded-xl border ${
                  s.type === "Undercut"
                    ? "border-green-500/30 bg-green-500/5"
                    : "border-blue-500/30 bg-blue-500/5"
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span
                    className={`text-xs font-bold px-2 py-0.5 rounded ${
                      s.type === "Undercut"
                        ? "bg-green-500/20 text-green-400"
                        : "bg-blue-500/20 text-blue-400"
                    }`}
                  >
                    {s.type}
                  </span>
                  <span className="text-xs text-zinc-500">
                    P{s.posBefore} &rarr; P{s.posAfter}
                  </span>
                </div>
                <p className="text-white font-medium text-sm">
                  {s.driver}{" "}
                  <span className="text-zinc-400">
                    {s.type === "Undercut" ? "undercut" : "overcut"}
                  </span>{" "}
                  {s.rival}
                </p>
                <p className="text-zinc-500 text-xs mt-1">
                  {s.driver} pitted lap {s.pitLap}, {s.rival} pitted lap {s.rivalPitLap}
                </p>
              </motion.div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* SC/VSC Events */}
      {scEvents && scEvents.length > 0 && (
        <GlassCard className="p-5" hover delay={0.3}>
          <div className="flex items-center gap-2 pb-3">
            <Flag className="w-4 h-4 text-yellow-400" />
            <h3 className="text-sm font-semibold text-white uppercase tracking-widest">
              Safety Car / VSC Periods
            </h3>
          </div>
          <div className="flex flex-wrap gap-3">
            {scEvents.map((ev, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: i * 0.05 }}
                className="glass px-4 py-3 rounded-xl border"
                style={{
                  borderColor: `${SC_COLORS[ev.type]}40`,
                  backgroundColor: `${SC_COLORS[ev.type]}08`,
                }}
              >
                <span
                  className="text-xs font-bold mr-2"
                  style={{ color: SC_COLORS[ev.type] }}
                >
                  {ev.type}
                </span>
                <span className="text-zinc-300 text-sm font-mono">
                  {ev.startLap === ev.endLap
                    ? `Lap ${ev.startLap}`
                    : `Laps ${ev.startLap}–${ev.endLap}`}
                </span>
                <span className="text-zinc-500 text-xs ml-2">
                  ({ev.endLap - ev.startLap + 1} lap{ev.endLap - ev.startLap > 0 ? "s" : ""})
                </span>
              </motion.div>
            ))}
          </div>
        </GlassCard>
      )}
    </div>
  );
}
