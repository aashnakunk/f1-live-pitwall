import { useState, useEffect } from "react";
import { Gauge } from "lucide-react";
import Plot from "react-plotly.js";
import { motion } from "framer-motion";
import { useApi } from "../hooks/useApi";
import GlassCard from "../components/GlassCard";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";

const darkLayout = {
  template: "plotly_dark",
  paper_bgcolor: "transparent",
  plot_bgcolor: "rgba(255,255,255,0.02)",
  font: { color: "#a1a1aa" },
  margin: { l: 50, r: 20, t: 30, b: 40 },
};

const plotConfig = { displayModeBar: false, responsive: true };

export default function PerformanceLab() {
  const { call, loading, error } = useApi();
  const [lapData, setLapData] = useState(null);
  const [predictions, setPredictions] = useState(null);
  const [threshold, setThreshold] = useState(1.5);

  useEffect(() => {
    async function fetchData() {
      const [laps, preds] = await Promise.all([
        call("/api/session/laptimes"),
        call(`/api/session/predictions?threshold=${threshold}`),
      ]);
      if (laps) setLapData(laps);
      if (preds) setPredictions(preds);
    }
    fetchData();
  }, []);

  async function refetchPredictions() {
    const preds = await call(`/api/session/predictions?threshold=${threshold}`);
    if (preds) setPredictions(preds);
  }

  if (loading && !lapData) return <LoadingSpinner text="Loading performance data..." />;

  return (
    <div className="space-y-6">
      <PageHeader title="Performance Studio" subtitle="Lap times, degradation & predictions" icon={Gauge} />

      {error && (
        <div className="text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg p-3 text-sm">
          {error}
        </div>
      )}

      {/* Lap Time Evolution Chart */}
      {lapData && (
        <GlassCard className="p-4" hover delay={0.1}>
          <h3 className="text-lg font-semibold text-white mb-3">Lap Time Evolution</h3>
          <Plot
            data={[
              ...lapData.traces.map((t) => ({
                x: t.laps,
                y: t.times,
                type: "scatter",
                mode: "lines+markers",
                name: t.driver,
                line: { color: t.color, width: 2 },
                marker: { size: 4 },
              })),
              ...(lapData.pitLaps || []).map((lap) => ({
                x: [lap, lap],
                y: [
                  Math.min(...lapData.traces.flatMap((t) => t.times)) - 1,
                  Math.max(...lapData.traces.flatMap((t) => t.times)) + 1,
                ],
                type: "scatter",
                mode: "lines",
                line: { color: "#a1a1aa", width: 1, dash: "dash" },
                showlegend: false,
                hoverinfo: "skip",
              })),
            ]}
            layout={{
              ...darkLayout,
              xaxis: { title: "Lap", gridcolor: "rgba(255,255,255,0.05)" },
              yaxis: { title: "Lap Time (s)", gridcolor: "rgba(255,255,255,0.05)" },
              legend: { orientation: "h", y: -0.2 },
              height: 400,
              shapes: (lapData.scEvents || []).map((ev) => ({
                type: "rect",
                xref: "x",
                yref: "paper",
                x0: ev.startLap - 0.5,
                x1: ev.endLap + 0.5,
                y0: 0,
                y1: 1,
                fillcolor: ev.type === "SC" ? "rgba(255,195,0,0.1)" : "rgba(255,136,0,0.1)",
                line: { color: ev.type === "SC" ? "#FFC300" : "#FF8800", width: 1, dash: "dot" },
              })),
              annotations: (lapData.scEvents || []).map((ev) => ({
                x: (ev.startLap + ev.endLap) / 2,
                y: 1.02,
                xref: "x",
                yref: "paper",
                text: ev.type,
                showarrow: false,
                font: { size: 10, color: ev.type === "SC" ? "#FFC300" : "#FF8800" },
              })),
            }}
            config={plotConfig}
            useResizeHandler
            className="w-full"
          />
        </GlassCard>
      )}

      {/* Tyre Degradation Table */}
      {lapData?.degradation && (
        <GlassCard className="p-4" hover delay={0.15}>
          <h3 className="text-lg font-semibold text-white mb-3">Tyre Degradation Analysis</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="border-b border-f1-border text-zinc-400 uppercase text-xs">
                  <th className="py-3 px-4">Driver</th>
                  <th className="py-3 px-4">Stint</th>
                  <th className="py-3 px-4">Compound</th>
                  <th className="py-3 px-4">Laps</th>
                  <th className="py-3 px-4">Deg/Lap (s)</th>
                  <th className="py-3 px-4">R-squared</th>
                </tr>
              </thead>
              <tbody>
                {lapData.degradation.map((row, i) => (
                  <tr
                    key={i}
                    className="border-b border-f1-border/50 hover:bg-white/5 transition-colors"
                  >
                    <td className="py-2.5 px-4 font-medium text-white">{row.driver}</td>
                    <td className="py-2.5 px-4 text-zinc-300">{row.stint}</td>
                    <td className="py-2.5 px-4">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-bold ${
                          row.compound === "SOFT"
                            ? "bg-red-500/20 text-red-400"
                            : row.compound === "MEDIUM"
                            ? "bg-yellow-500/20 text-yellow-400"
                            : row.compound === "HARD"
                            ? "bg-zinc-500/20 text-zinc-300"
                            : "bg-blue-500/20 text-blue-400"
                        }`}
                      >
                        {row.compound}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-zinc-300">{row.laps}</td>
                    <td className="py-2.5 px-4 text-zinc-300">
                      {typeof row.degPerLap === "number" ? row.degPerLap.toFixed(3) : row.degPerLap}
                    </td>
                    <td className="py-2.5 px-4 text-zinc-300">
                      {typeof row.rSquared === "number" ? row.rSquared.toFixed(3) : row.rSquared}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassCard>
      )}

      {/* Three-Column Predictions Row */}
      {predictions && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Tyre Life Predictor */}
          <GlassCard className="p-4" hover delay={0.2}>
            <h3 className="text-lg font-semibold text-white mb-3">Tyre Life Predictor</h3>
            <div className="flex items-center gap-3 mb-4">
              <label className="text-sm text-zinc-400 whitespace-nowrap">Threshold (s)</label>
              <input
                type="range"
                min="0.5"
                max="3"
                step="0.1"
                value={threshold}
                onChange={(e) => setThreshold(parseFloat(e.target.value))}
                className="flex-1 accent-f1-red h-1.5"
              />
              <span className="text-sm text-white font-mono w-10 text-right">
                {threshold.toFixed(1)}
              </span>
              <button
                onClick={refetchPredictions}
                disabled={loading}
                className="px-3 py-1 bg-f1-red/80 hover:bg-f1-red text-white text-xs rounded transition-colors disabled:opacity-50"
              >
                Apply
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead>
                  <tr className="border-b border-f1-border text-zinc-400 uppercase text-xs">
                    <th className="py-2 px-3">Driver</th>
                    <th className="py-2 px-3">Compound</th>
                    <th className="py-2 px-3">Pred. Life</th>
                    <th className="py-2 px-3">Actual</th>
                    <th className="py-2 px-3">Deg/Lap</th>
                  </tr>
                </thead>
                <tbody>
                  {predictions.tyrePredictions?.map((row, i) => (
                    <tr
                      key={i}
                      className="border-b border-f1-border/50 hover:bg-white/5 transition-colors"
                    >
                      <td className="py-2 px-3 font-medium text-white">{row.driver}</td>
                      <td className="py-2 px-3">
                        <span
                          className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                            row.compound === "SOFT"
                              ? "bg-red-500/20 text-red-400"
                              : row.compound === "MEDIUM"
                              ? "bg-yellow-500/20 text-yellow-400"
                              : "bg-zinc-500/20 text-zinc-300"
                          }`}
                        >
                          {row.compound}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-zinc-300">{row.predictedLife}</td>
                      <td className="py-2 px-3 text-zinc-300">{row.actualStint}</td>
                      <td className="py-2 px-3 text-zinc-300">
                        {typeof row.degPerLap === "number" ? row.degPerLap.toFixed(3) : row.degPerLap}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>

          {/* Pace-Adjusted Standings */}
          <GlassCard className="p-4" hover delay={0.25}>
            <h3 className="text-lg font-semibold text-white mb-3">Pace-Adjusted Standings</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead>
                  <tr className="border-b border-f1-border text-zinc-400 uppercase text-xs">
                    <th className="py-2 px-3">Rank</th>
                    <th className="py-2 px-3">Driver</th>
                    <th className="py-2 px-3">Median</th>
                    <th className="py-2 px-3">Pos</th>
                    <th className="py-2 px-3">Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {predictions.paceAdjusted?.map((row, i) => (
                    <tr
                      key={i}
                      className="border-b border-f1-border/50 hover:bg-white/5 transition-colors"
                    >
                      <td className="py-2 px-3 text-zinc-300">{row.paceRank}</td>
                      <td className="py-2 px-3 font-medium text-white">{row.driver}</td>
                      <td className="py-2 px-3 text-zinc-300">
                        {typeof row.medianPace === "number" ? row.medianPace.toFixed(3) : row.medianPace}
                      </td>
                      <td className="py-2 px-3 text-zinc-300">P{row.actualPos}</td>
                      <td className="py-2 px-3">
                        <span
                          className={`font-mono font-bold ${
                            row.delta > 0
                              ? "text-green-400"
                              : row.delta < 0
                              ? "text-red-400"
                              : "text-zinc-400"
                          }`}
                        >
                          {row.delta > 0 ? "+" : ""}
                          {typeof row.delta === "number" ? row.delta.toFixed(1) : row.delta}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>

          {/* Overtake Scores */}
          <GlassCard className="p-4" hover delay={0.3}>
            <h3 className="text-lg font-semibold text-white mb-3">Overtake Scores</h3>
            {predictions.overtakeScores && predictions.overtakeScores.length > 0 ? (
              <Plot
                data={[
                  {
                    y: predictions.overtakeScores.map(
                      (o) => `${o.driver} -> ${o.attacking}`
                    ),
                    x: predictions.overtakeScores.map((o) => o.score),
                    type: "bar",
                    orientation: "h",
                    marker: {
                      color: predictions.overtakeScores.map((o) =>
                        o.score > 70
                          ? "#ef4444"
                          : o.score > 40
                          ? "#f59e0b"
                          : "#22c55e"
                      ),
                    },
                    text: predictions.overtakeScores.map((o) => o.score.toFixed(0)),
                    textposition: "outside",
                    textfont: { color: "#a1a1aa", size: 11 },
                    hovertemplate:
                      "%{y}<br>Score: %{x:.1f}<br>Gap: %{customdata[0]}s<br>Tyre Delta: %{customdata[1]}<extra></extra>",
                    customdata: predictions.overtakeScores.map((o) => [
                      o.gap,
                      o.tyreDelta,
                    ]),
                  },
                ]}
                layout={{
                  ...darkLayout,
                  xaxis: {
                    title: "Score",
                    gridcolor: "rgba(255,255,255,0.05)",
                    range: [0, Math.max(...predictions.overtakeScores.map((o) => o.score)) * 1.2],
                  },
                  yaxis: { automargin: true },
                  height: Math.max(250, predictions.overtakeScores.length * 35 + 60),
                  margin: { l: 120, r: 50, t: 10, b: 40 },
                }}
                config={plotConfig}
                useResizeHandler
                className="w-full"
              />
            ) : (
              <p className="text-zinc-500 text-sm">No overtake opportunities detected.</p>
            )}
          </GlassCard>
        </div>
      )}
    </div>
  );
}
