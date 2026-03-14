import { useState, useEffect, useRef, useCallback } from "react";
import { motion } from "framer-motion";
import { Play, Pause, RotateCcw, Target, Trophy, CheckCircle, XCircle, BarChart3, Microscope } from "lucide-react";
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

const TYRE_COLORS = {
  SOFT: "#FF3333",
  MEDIUM: "#FFC300",
  HARD: "#EEEEEE",
  INTERMEDIATE: "#39B54A",
  WET: "#0072CE",
};

export default function RaceReplay() {
  const api = useApi();
  const [lap, setLap] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [sweep, setSweep] = useState(null);
  const [sweepLoading, setSweepLoading] = useState(false);
  const intervalRef = useRef(null);
  const debounceRef = useRef(null);

  const maxLap = data?.maxLap || 60;

  // Fetch replay data for a given lap
  const fetchLap = useCallback(
    async (targetLap) => {
      try {
        const result = await api.call(`/api/session/replay?lap=${targetLap}`);
        setData(result);
      } catch (e) {
        console.error("Failed to fetch replay data:", e);
      } finally {
        setLoading(false);
      }
    },
    [api]
  );

  // Initial fetch
  useEffect(() => {
    fetchLap(1);
  }, []);

  // Debounced fetch when lap changes (after initial load)
  useEffect(() => {
    if (loading) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchLap(lap);
    }, 300);
    return () => clearTimeout(debounceRef.current);
  }, [lap]);

  // Auto-play interval
  useEffect(() => {
    if (playing) {
      intervalRef.current = setInterval(() => {
        setLap((prev) => {
          if (prev >= maxLap) {
            setPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, 500);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [playing, maxLap]);

  const handleSliderChange = (e) => {
    const value = parseInt(e.target.value, 10);
    setLap(value);
  };

  const handleReset = () => {
    setPlaying(false);
    setLap(1);
  };

  if (loading && !data) {
    return <LoadingSpinner text="Loading race replay..." />;
  }

  if (!data) {
    return (
      <div className="text-center text-zinc-500 py-20">
        No session data available. Load a session first.
      </div>
    );
  }

  const { standings = [], positionHistory = {}, accuracy, modelInfo } = data;
  const top10 = standings.slice(0, 10);
  const top5Drivers = standings.slice(0, 5).map((s) => s.driver);

  const runSweep = async () => {
    setSweepLoading(true);
    try {
      const res = await api.call("/api/session/replay/sweep");
      setSweep(res);
    } catch (e) {
      console.error("Sweep failed:", e);
    } finally {
      setSweepLoading(false);
    }
  };

  // Win probability bar chart traces
  const winProbTrace = {
    type: "bar",
    orientation: "h",
    y: [...top10].reverse().map((s) => s.driver),
    x: [...top10].reverse().map((s) => s.winPct || 0),
    marker: {
      color: [...top10].reverse().map((s) => s.color || "#E10600"),
    },
    hovertemplate: "%{y}: %{x:.1f}%<extra></extra>",
  };

  // Position battle traces
  const positionTraces = top5Drivers
    .filter((d) => positionHistory[d])
    .map((driver) => {
      const history = positionHistory[driver];
      return {
        type: "scatter",
        mode: "lines",
        name: driver,
        x: history.laps,
        y: history.positions,
        line: { color: history.color || "#888", width: 2.5 },
        hovertemplate: `${driver}<br>Lap %{x}: P%{y}<extra></extra>`,
      };
    });

  return (
    <div className="space-y-8">
      <PageHeader
        title="Race Replay"
        subtitle="Lap-by-lap simulation with live win probability"
        icon={Play}
      />

      {/* Lap slider controls */}
      <GlassCard className="p-6" hover delay={0.1}>
        <div className="flex items-center gap-6">
          {/* Play / Pause / Reset buttons */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPlaying(!playing)}
              className="w-10 h-10 rounded-xl bg-f1-red flex items-center justify-center
                         hover:bg-f1-red/80 transition-colors glow-red"
            >
              {playing ? (
                <Pause className="w-5 h-5 text-white" />
              ) : (
                <Play className="w-5 h-5 text-white ml-0.5" />
              )}
            </button>
            <button
              onClick={handleReset}
              className="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center
                         hover:bg-white/10 transition-colors border border-f1-border"
            >
              <RotateCcw className="w-4 h-4 text-zinc-400" />
            </button>
          </div>

          {/* Slider */}
          <div className="flex-1">
            <input
              type="range"
              min={1}
              max={maxLap}
              value={lap}
              onChange={handleSliderChange}
              className="w-full h-2 rounded-full appearance-none cursor-pointer
                         bg-white/10 accent-f1-red
                         [&::-webkit-slider-thumb]:appearance-none
                         [&::-webkit-slider-thumb]:w-5
                         [&::-webkit-slider-thumb]:h-5
                         [&::-webkit-slider-thumb]:rounded-full
                         [&::-webkit-slider-thumb]:bg-f1-red
                         [&::-webkit-slider-thumb]:shadow-[0_0_10px_rgba(225,6,0,0.5)]
                         [&::-webkit-slider-thumb]:cursor-pointer"
            />
          </div>

          {/* Lap counter */}
          <div className="text-right min-w-[100px]">
            <span className="text-3xl font-bold text-gradient">{lap}</span>
            <span className="text-zinc-500 text-lg mx-1">/</span>
            <span className="text-zinc-500 text-lg">{maxLap}</span>
            <p className="text-xs text-zinc-600 uppercase tracking-widest">Lap</p>
          </div>
        </div>
      </GlassCard>

      {/* Main content: standings + win probability */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Left: Standings table */}
        <GlassCard className="lg:col-span-2 overflow-hidden" hover delay={0.15}>
          <h3 className="text-sm font-semibold text-white px-5 pt-4 pb-2 uppercase tracking-widest">
            Standings — Lap {lap}
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="border-b border-f1-border text-zinc-500 uppercase text-xs tracking-wider">
                  <th className="px-4 py-2">Pos</th>
                  <th className="px-4 py-2">Driver</th>
                  <th className="px-4 py-2">Tyre</th>
                  <th className="px-4 py-2">Gap</th>
                  <th className="px-4 py-2">Win %</th>
                </tr>
              </thead>
              <tbody>
                {standings.map((s, i) => (
                  <motion.tr
                    key={s.driver}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.02 * i }}
                    className="border-b border-f1-border/40 hover:bg-white/[0.03] transition-colors"
                  >
                    <td className="px-4 py-2 font-bold text-white">{s.position}</td>
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-2">
                        {s.headshot ? (
                          <img
                            src={s.headshot}
                            alt={s.driver}
                            className="w-6 h-6 rounded-full object-cover bg-white/10 flex-shrink-0"
                            onError={(e) => { e.target.style.display = "none"; }}
                          />
                        ) : (
                          <span
                            className="w-6 h-6 rounded-full flex items-center justify-center text-[8px] font-bold flex-shrink-0"
                            style={{ backgroundColor: (s.color || "#888") + "30", color: s.color || "#888" }}
                          >
                            {s.driver?.[0]}
                          </span>
                        )}
                        <span
                          className="w-0.5 h-4 rounded-full flex-shrink-0"
                          style={{ backgroundColor: s.color || "#888" }}
                        />
                        <span className="text-white font-medium text-xs">{s.driver}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className="text-xs font-bold px-1.5 py-0.5 rounded"
                        style={{
                          color: TYRE_COLORS[s.tyre] || "#ccc",
                          backgroundColor: `${TYRE_COLORS[s.tyre] || "#888"}15`,
                        }}
                      >
                        {s.tyre?.[0] || "?"}{s.tyreAge != null ? s.tyreAge : ""}
                      </span>
                    </td>
                    <td className="px-4 py-2 font-mono text-zinc-400 text-xs">
                      {s.gap || "Leader"}
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 rounded-full bg-white/5 overflow-hidden">
                          <motion.div
                            className="h-full rounded-full"
                            style={{ backgroundColor: s.color || "#E10600" }}
                            initial={{ width: 0 }}
                            animate={{ width: `${s.winPct || 0}%` }}
                            transition={{ duration: 0.4 }}
                          />
                        </div>
                        <span className="text-xs text-zinc-500 font-mono w-8">
                          {(s.winPct || 0).toFixed(0)}%
                        </span>
                      </div>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassCard>

        {/* Right: Win probability chart */}
        <GlassCard className="lg:col-span-3 p-4" hover delay={0.2}>
          <h3 className="text-sm font-semibold text-white px-2 pb-2 uppercase tracking-widest">
            Win Probability
          </h3>
          <Plot
            data={[winProbTrace]}
            layout={{
              ...plotLayout,
              height: 380,
              xaxis: {
                title: { text: "Win %", font: { color: "#71717a", size: 12 } },
                color: "#a1a1aa",
                gridcolor: "rgba(255,255,255,0.04)",
                range: [0, Math.max(100, ...top10.map((s) => s.winPct || 0))],
              },
              yaxis: {
                color: "#a1a1aa",
                gridcolor: "rgba(255,255,255,0.04)",
              },
              margin: { l: 60, r: 20, t: 10, b: 50 },
            }}
            config={plotConfig}
            useResizeHandler
            style={{ width: "100%" }}
          />
        </GlassCard>
      </div>

      {/* Prediction Accuracy Panel */}
      {accuracy && (
        <GlassCard className="p-6" hover delay={0.2}>
          <div className="flex items-center gap-2 mb-4">
            <Target className="w-4 h-4 text-f1-red" />
            <h3 className="text-sm font-semibold text-white uppercase tracking-widest">
              Prediction Accuracy — Lap {lap}
            </h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {/* Winner prediction */}
            <div className="flex flex-col items-center gap-2 p-3 rounded-lg bg-white/5 border border-f1-border">
              {accuracy.winnerCorrect ? (
                <CheckCircle className="w-6 h-6 text-emerald-400" />
              ) : (
                <XCircle className="w-6 h-6 text-red-400" />
              )}
              <span className="text-xs uppercase tracking-widest text-zinc-500">Winner</span>
              <span className={`text-lg font-bold ${accuracy.winnerCorrect ? "text-emerald-400" : "text-red-400"}`}>
                {accuracy.winnerCorrect ? "Correct" : "Wrong"}
              </span>
              <span className="text-xs text-zinc-400">
                Pred: {accuracy.predictedWinner} | Actual: {accuracy.actualWinner}
              </span>
            </div>

            {/* Top 3 overlap */}
            <div className="flex flex-col items-center gap-2 p-3 rounded-lg bg-white/5 border border-f1-border">
              <Trophy className="w-6 h-6 text-yellow-400" />
              <span className="text-xs uppercase tracking-widest text-zinc-500">Podium Match</span>
              <span className="text-2xl font-bold text-gradient">{accuracy.top3Overlap}/3</span>
              <span className="text-xs text-zinc-400">
                {accuracy.actualTop3?.join(", ")}
              </span>
            </div>

            {/* Order accuracy */}
            <div className="flex flex-col items-center gap-2 p-3 rounded-lg bg-white/5 border border-f1-border">
              <Target className="w-6 h-6 text-blue-400" />
              <span className="text-xs uppercase tracking-widest text-zinc-500">Order Accuracy</span>
              <span className={`text-2xl font-bold ${
                accuracy.orderAccuracy > 70 ? "text-emerald-400" :
                accuracy.orderAccuracy > 50 ? "text-yellow-400" : "text-red-400"
              }`}>
                {accuracy.orderAccuracy}%
              </span>
              <span className="text-xs text-zinc-400">pairwise concordance</span>
            </div>

            {/* Race progress context */}
            <div className="flex flex-col items-center gap-2 p-3 rounded-lg bg-white/5 border border-f1-border">
              <Play className="w-6 h-6 text-f1-red" />
              <span className="text-xs uppercase tracking-widest text-zinc-500">Race Progress</span>
              <span className="text-2xl font-bold text-gradient">
                {maxLap > 0 ? Math.round((lap / maxLap) * 100) : 0}%
              </span>
              <span className="text-xs text-zinc-400">Lap {lap} of {maxLap}</span>
            </div>
          </div>
        </GlassCard>
      )}

      {/* Position battle chart */}
      {positionTraces.length > 0 && (
        <GlassCard className="p-6" hover delay={0.25}>
          <h3 className="text-sm font-semibold text-white pb-3 uppercase tracking-widest">
            Position Battle — Top 5
          </h3>
          <Plot
            data={positionTraces}
            layout={{
              ...plotLayout,
              height: 340,
              xaxis: {
                title: { text: "Lap", font: { color: "#71717a", size: 12 } },
                color: "#a1a1aa",
                gridcolor: "rgba(255,255,255,0.04)",
                range: [1, maxLap],
              },
              yaxis: {
                title: { text: "Position", font: { color: "#71717a", size: 12 } },
                color: "#a1a1aa",
                gridcolor: "rgba(255,255,255,0.04)",
                autorange: "reversed",
                dtick: 1,
              },
              legend: {
                orientation: "h",
                y: -0.2,
                font: { size: 11 },
              },
              margin: { l: 50, r: 20, t: 10, b: 60 },
            }}
            config={plotConfig}
            useResizeHandler
            style={{ width: "100%" }}
          />
        </GlassCard>
      )}

      {/* ── Model Diagnostics ── */}
      {modelInfo && (
        <GlassCard className="p-6" hover delay={0.28}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Microscope className="w-4 h-4 text-purple-400" />
              <h3 className="text-sm font-semibold text-white uppercase tracking-widest">
                Model Diagnostics — Lap {lap}
              </h3>
            </div>
            <span className="text-[10px] text-zinc-500 bg-white/5 px-2 py-1 rounded-lg">
              Temp: {modelInfo.temperature} | Progress: {(modelInfo.raceProgress * 100).toFixed(0)}%
            </span>
          </div>

          {/* Feature weights */}
          <div className="grid grid-cols-5 gap-3 mb-5">
            {[
              { key: "position", label: "Position", color: "bg-blue-500" },
              { key: "pace", label: "Pace", color: "bg-emerald-500" },
              { key: "tyre", label: "Tyre", color: "bg-yellow-500" },
              { key: "gap", label: "Gap", color: "bg-purple-500" },
              { key: "leadership", label: "Lead", color: "bg-orange-500" },
            ].map((w) => (
              <div key={w.key} className="text-center">
                <div className="h-20 flex items-end justify-center mb-1">
                  <div
                    className={`w-10 ${w.color} rounded-t-lg transition-all duration-500`}
                    style={{ height: `${(modelInfo.weights[w.key] || 0) * 100 * 1.5}%` }}
                  />
                </div>
                <span className="text-xs text-zinc-400">{w.label}</span>
                <p className="text-sm font-bold text-white">{((modelInfo.weights[w.key] || 0) * 100).toFixed(0)}%</p>
              </div>
            ))}
          </div>

          {/* Top 5 feature breakdown */}
          <h4 className="text-xs text-zinc-500 uppercase tracking-widest mb-2">Top 5 Feature Scores</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="border-b border-f1-border text-zinc-500 uppercase text-[10px] tracking-wider">
                  <th className="px-3 py-1.5">Driver</th>
                  <th className="px-3 py-1.5">Position</th>
                  <th className="px-3 py-1.5">Pace</th>
                  <th className="px-3 py-1.5">Tyre</th>
                  <th className="px-3 py-1.5">Gap</th>
                  <th className="px-3 py-1.5">Lead</th>
                  <th className="px-3 py-1.5">Raw Score</th>
                  <th className="px-3 py-1.5">Win %</th>
                </tr>
              </thead>
              <tbody>
                {standings.slice(0, 5).map((s) => (
                  <tr key={s.driver} className="border-b border-f1-border/30 hover:bg-white/[0.03]">
                    <td className="px-3 py-1.5">
                      <div className="flex items-center gap-2">
                        <span className="w-1 h-4 rounded-full" style={{ backgroundColor: s.color }} />
                        <span className="text-white font-medium text-xs">{s.driver}</span>
                      </div>
                    </td>
                    {s.features && (
                      <>
                        <td className="px-3 py-1.5">
                          <span className={`font-mono text-xs ${s.features.posScore > 0.7 ? "text-blue-400" : "text-zinc-400"}`}>
                            {s.features.posScore.toFixed(2)}
                          </span>
                        </td>
                        <td className="px-3 py-1.5">
                          <span className={`font-mono text-xs ${s.features.paceScore > 0.7 ? "text-emerald-400" : "text-zinc-400"}`}>
                            {s.features.paceScore.toFixed(2)}
                          </span>
                        </td>
                        <td className="px-3 py-1.5">
                          <span className={`font-mono text-xs ${s.features.tyreScore > 0.7 ? "text-yellow-400" : s.features.tyreScore < 0.3 ? "text-red-400" : "text-zinc-400"}`}>
                            {s.features.tyreScore.toFixed(2)}
                          </span>
                        </td>
                        <td className="px-3 py-1.5">
                          <span className={`font-mono text-xs ${s.features.gapScore > 0.7 ? "text-purple-400" : "text-zinc-400"}`}>
                            {s.features.gapScore.toFixed(2)}
                          </span>
                        </td>
                        <td className="px-3 py-1.5">
                          <span className={`font-mono text-xs ${s.features.leadScore > 0.5 ? "text-orange-400" : "text-zinc-400"}`}>
                            {(s.features.leadScore || 0).toFixed(2)}
                          </span>
                          {s.leadLaps > 0 && <span className="text-[9px] text-zinc-600 ml-1">({s.leadLaps}L)</span>}
                        </td>
                        <td className="px-3 py-1.5 font-mono text-xs text-white font-bold">
                          {s.features.rawScore.toFixed(3)}
                        </td>
                      </>
                    )}
                    <td className="px-3 py-1.5 font-bold text-f1-red text-xs">{(s.winPct || 0).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassCard>
      )}

      {/* ── Accuracy Sweep ── */}
      <GlassCard className="p-6" hover delay={0.3}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-white uppercase tracking-widest">
              Full-Race Accuracy Sweep
            </h3>
          </div>
          <button
            onClick={runSweep}
            disabled={sweepLoading}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-f1-red text-white text-xs font-bold
                       hover:bg-f1-red/80 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            {sweepLoading ? (
              <>
                <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Running...
              </>
            ) : (
              "Run Sweep"
            )}
          </button>
        </div>

        {!sweep && !sweepLoading && (
          <p className="text-xs text-zinc-500 text-center py-4">
            Click "Run Sweep" to evaluate prediction accuracy at every checkpoint across the full race.
            This shows when the model converges on the correct winner.
          </p>
        )}

        {sweep && (
          <div className="space-y-4">
            {/* Convergence summary */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="text-center p-3 rounded-xl bg-white/5 border border-f1-border">
                <span className="text-[10px] text-zinc-500 uppercase tracking-widest">Actual Winner</span>
                <p className="text-lg font-bold text-white mt-1">{sweep.actualWinner}</p>
              </div>
              <div className="text-center p-3 rounded-xl bg-white/5 border border-f1-border">
                <span className="text-[10px] text-zinc-500 uppercase tracking-widest">First Correct</span>
                <p className="text-lg font-bold text-emerald-400 mt-1">
                  {sweep.firstCorrectLap ? `Lap ${sweep.firstCorrectLap}` : "Never"}
                </p>
              </div>
              <div className="text-center p-3 rounded-xl bg-white/5 border border-f1-border">
                <span className="text-[10px] text-zinc-500 uppercase tracking-widest">Locked Correct</span>
                <p className="text-lg font-bold text-cyan-400 mt-1">
                  {sweep.lockedLap ? `Lap ${sweep.lockedLap}` : "Never locked"}
                </p>
                <span className="text-[10px] text-zinc-600">stayed correct from here</span>
              </div>
              <div className="text-center p-3 rounded-xl bg-white/5 border border-f1-border">
                <span className="text-[10px] text-zinc-500 uppercase tracking-widest">Checkpoints</span>
                <p className="text-lg font-bold text-white mt-1">{sweep.totalCheckpoints}</p>
              </div>
            </div>

            {/* Accuracy over race chart */}
            <Plot
              data={[
                {
                  type: "scatter", mode: "lines+markers",
                  x: sweep.sweep.map((s) => s.lap),
                  y: sweep.sweep.map((s) => s.orderAccuracy),
                  name: "Order Accuracy %",
                  line: { color: "#22d3ee", width: 2 },
                  marker: { size: 6 },
                  hovertemplate: "Lap %{x}: %{y:.1f}% accuracy<extra></extra>",
                },
                {
                  type: "scatter", mode: "lines+markers",
                  x: sweep.sweep.map((s) => s.lap),
                  y: sweep.sweep.map((s) => s.actualWinnerPct),
                  name: `${sweep.actualWinner} Win %`,
                  line: { color: "#f59e0b", width: 2, dash: "dot" },
                  marker: { size: 6 },
                  hovertemplate: `${sweep.actualWinner} win prob: %{y:.1f}%<extra></extra>`,
                },
                {
                  type: "scatter", mode: "markers",
                  x: sweep.sweep.filter((s) => s.winnerCorrect).map((s) => s.lap),
                  y: sweep.sweep.filter((s) => s.winnerCorrect).map((s) => s.orderAccuracy),
                  name: "Winner Correct",
                  marker: { color: "#22c55e", size: 10, symbol: "circle" },
                  hovertemplate: "Lap %{x}: Winner correct!<extra></extra>",
                },
              ]}
              layout={{
                ...plotLayout,
                height: 280,
                legend: { orientation: "h", y: 1.12, font: { size: 10 } },
                xaxis: {
                  title: { text: "Lap", font: { size: 10, color: "#71717a" } },
                  color: "#71717a", gridcolor: "rgba(255,255,255,0.04)",
                },
                yaxis: {
                  title: { text: "%", font: { size: 10, color: "#71717a" } },
                  color: "#71717a", gridcolor: "rgba(255,255,255,0.04)",
                  range: [0, 105],
                },
                margin: { l: 45, r: 10, t: 35, b: 40 },
              }}
              config={plotConfig} useResizeHandler style={{ width: "100%" }}
            />

            {/* Checkpoint table */}
            <div className="overflow-x-auto max-h-[300px]">
              <table className="w-full text-sm text-left">
                <thead className="sticky top-0 bg-f1-dark">
                  <tr className="border-b border-f1-border text-zinc-500 uppercase text-[10px] tracking-wider">
                    <th className="px-3 py-1.5">Lap</th>
                    <th className="px-3 py-1.5">Progress</th>
                    <th className="px-3 py-1.5">Predicted Winner</th>
                    <th className="px-3 py-1.5">Correct?</th>
                    <th className="px-3 py-1.5">Winner Win%</th>
                    <th className="px-3 py-1.5">{sweep.actualWinner} Win%</th>
                    <th className="px-3 py-1.5">Podium</th>
                    <th className="px-3 py-1.5">Order Acc.</th>
                  </tr>
                </thead>
                <tbody>
                  {sweep.sweep.map((pt) => (
                    <tr key={pt.lap} className={`border-b border-f1-border/30 hover:bg-white/[0.03] ${pt.winnerCorrect ? "" : "opacity-60"}`}>
                      <td className="px-3 py-1.5 font-bold text-white">{pt.lap}</td>
                      <td className="px-3 py-1.5 text-zinc-400 text-xs">{pt.raceProgress}%</td>
                      <td className="px-3 py-1.5 text-white text-xs font-medium">{pt.predictedWinner}</td>
                      <td className="px-3 py-1.5">
                        {pt.winnerCorrect
                          ? <CheckCircle className="w-4 h-4 text-emerald-400" />
                          : <XCircle className="w-4 h-4 text-red-400" />
                        }
                      </td>
                      <td className="px-3 py-1.5 font-mono text-xs text-zinc-300">{pt.winnerWinPct}%</td>
                      <td className="px-3 py-1.5 font-mono text-xs text-yellow-400">{pt.actualWinnerPct}%</td>
                      <td className="px-3 py-1.5 font-mono text-xs text-zinc-300">{pt.top3Overlap}/3</td>
                      <td className="px-3 py-1.5">
                        <span className={`font-mono text-xs ${pt.orderAccuracy > 70 ? "text-emerald-400" : pt.orderAccuracy > 50 ? "text-yellow-400" : "text-red-400"}`}>
                          {pt.orderAccuracy}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </GlassCard>
    </div>
  );
}
