import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Thermometer,
  Wind,
  Droplets,
  CloudRain,
  ArrowUp,
  ArrowDown,
  Minus,
  Flag,
  AlertTriangle,
  ShieldAlert,
  Zap,
  Clock,
  Users,
  ArrowRight,
  Trophy,
} from "lucide-react";
import GlassCard from "../components/GlassCard";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import { useApi } from "../hooks/useApi";

function MetricCard({ icon: Icon, label, value, sub, color = "text-f1-red", delay }) {
  return (
    <GlassCard hover delay={delay}>
      <div className="flex flex-col items-center gap-1.5 p-3">
        <Icon className={`w-5 h-5 ${color}`} />
        <span className="text-xs uppercase tracking-widest text-zinc-500">{label}</span>
        <span className="text-2xl font-bold text-gradient">{value}</span>
        {sub && <span className="text-xs text-zinc-400">{sub}</span>}
      </div>
    </GlassCard>
  );
}

function PositionDelta({ grid, finish }) {
  const diff = grid - finish;
  if (diff > 0)
    return (
      <span className="inline-flex items-center gap-0.5 text-emerald-400 text-xs font-medium">
        <ArrowUp className="w-3 h-3" />
        {diff}
      </span>
    );
  if (diff < 0)
    return (
      <span className="inline-flex items-center gap-0.5 text-red-400 text-xs font-medium">
        <ArrowDown className="w-3 h-3" />
        {Math.abs(diff)}
      </span>
    );
  return (
    <span className="inline-flex items-center gap-0.5 text-zinc-500 text-xs font-medium">
      <Minus className="w-3 h-3" />
    </span>
  );
}

export default function RaceCommand() {
  const api = useApi();
  const navigate = useNavigate();
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      setLoading(true);
      try {
        const overviewData = await api.call("/api/session/overview");
        setOverview(overviewData);
      } catch (e) {
        console.error("Failed to load race command data:", e);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  if (loading) return <LoadingSpinner text="Loading race data..." />;
  if (!overview) return <div className="text-center text-zinc-500 py-20">No session data available.</div>;

  const { results = [], weather = {}, metrics = {} } = overview;

  // Split results into podium, finishers, DNFs
  const podium = results.slice(0, 3);
  const rest = results.slice(3);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Race Command Center"
        subtitle="Session briefing — results, conditions, key metrics"
        icon={LayoutDashboard}
      />

      {/* ── SECTION: Podium ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {podium.map((r, i) => (
          <GlassCard key={r.driver} className="p-5 relative overflow-hidden" hover delay={0.05 + i * 0.03}>
            {/* Position ribbon */}
            <div className="absolute top-0 right-0 w-16 h-16">
              <div
                className={`absolute top-3 right-[-20px] w-[80px] text-center text-xs font-bold py-0.5 rotate-45 ${
                  i === 0 ? "bg-yellow-500 text-black" : i === 1 ? "bg-zinc-400 text-black" : "bg-amber-700 text-white"
                }`}
              >
                P{r.position}
              </div>
            </div>
            <div className="flex items-center gap-3">
              {r.headshot ? (
                <img
                  src={r.headshot}
                  alt={r.driver}
                  className="w-14 h-14 rounded-full object-cover bg-white/10 flex-shrink-0 ring-2"
                  style={{ ringColor: r.teamColor || "#888" }}
                  onError={(e) => { e.target.style.display = "none"; }}
                />
              ) : (
                <span
                  className="w-14 h-14 rounded-full flex items-center justify-center text-lg font-bold flex-shrink-0"
                  style={{ backgroundColor: (r.teamColor || "#888") + "30", color: r.teamColor || "#888" }}
                >
                  {r.driver?.[0]}
                </span>
              )}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="w-1 h-5 rounded-full" style={{ backgroundColor: r.teamColor || "#888" }} />
                  <span className="text-white font-bold">{r.driver}</span>
                </div>
                {r.fullName && <p className="text-xs text-zinc-500 mt-0.5 truncate">{r.fullName}</p>}
                <p className="text-xs text-zinc-400 mt-0.5">{r.team}</p>
              </div>
            </div>
            <div className="flex items-center justify-between mt-3 pt-3 border-t border-f1-border/30">
              <div className="text-xs text-zinc-500">
                Grid <span className="text-white font-medium">{r.grid}</span>
                <span className="mx-1.5"><PositionDelta grid={r.grid} finish={r.position} /></span>
              </div>
              <span className="font-mono text-xs text-zinc-300">{r.time || "—"}</span>
              <span className="text-xs text-zinc-400">{r.points} pts</span>
            </div>
          </GlassCard>
        ))}
      </div>

      {/* ── SECTION: Key Metrics ── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <MetricCard icon={Flag} label="Total Laps" value={metrics.totalLaps ?? "—"} delay={0.12} />
        <MetricCard
          icon={Users} label="Finishers"
          value={`${metrics.finishers ?? "—"} / ${metrics.totalDrivers ?? "—"}`}
          delay={0.14}
        />
        <MetricCard icon={AlertTriangle} label="DNFs" value={metrics.dnfs ?? 0} color="text-red-400" delay={0.16} />
        <MetricCard
          icon={ShieldAlert} label="Safety Cars" value={metrics.scCount ?? 0}
          sub={metrics.scCount > 0 ? `${metrics.scCount} deployment${metrics.scCount > 1 ? "s" : ""}` : "None"}
          color="text-yellow-400" delay={0.18}
        />
        <MetricCard
          icon={Zap} label="VSC" value={metrics.vscCount ?? 0}
          sub={metrics.vscCount > 0 ? `${metrics.vscCount} deployment${metrics.vscCount > 1 ? "s" : ""}` : "None"}
          color="text-orange-400" delay={0.2}
        />
        <MetricCard
          icon={Clock} label="Pit Stops" value={metrics.totalPitStops ?? 0}
          sub={metrics.fastestLapDriver ? `FL: ${metrics.fastestLapDriver}` : undefined}
          delay={0.22}
        />
      </div>

      {/* ── SECTION: Safety Car Events ── */}
      {metrics.scEvents && metrics.scEvents.length > 0 && (
        <GlassCard className="p-5" hover delay={0.24}>
          <h3 className="text-xs font-semibold text-zinc-500 mb-3 uppercase tracking-widest">
            Safety Car Events
          </h3>
          <div className="flex flex-wrap gap-2">
            {metrics.scEvents.map((ev, i) => (
              <div
                key={i}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs ${
                  ev.type === "SC"
                    ? "bg-yellow-500/10 border-yellow-500/30 text-yellow-400"
                    : "bg-orange-500/10 border-orange-500/30 text-orange-400"
                }`}
              >
                {ev.type === "SC" ? <ShieldAlert className="w-3.5 h-3.5" /> : <Zap className="w-3.5 h-3.5" />}
                <span className="font-bold">{ev.type}</span>
                <span className="text-zinc-300">
                  Lap {ev.startLap}{ev.endLap !== ev.startLap ? `–${ev.endLap}` : ""}
                  <span className="text-zinc-500 ml-1">({ev.endLap - ev.startLap + 1} lap{ev.endLap - ev.startLap > 0 ? "s" : ""})</span>
                </span>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {/* ── SECTION: Conditions ── */}
      <GlassCard className="p-5" hover delay={0.26}>
        <h3 className="text-xs font-semibold text-zinc-500 mb-3 uppercase tracking-widest">
          Race Conditions
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { icon: Thermometer, label: "Track", value: weather.trackTemp ?? "—", unit: "°C" },
            { icon: Wind, label: "Air", value: weather.airTemp ?? "—", unit: "°C" },
            { icon: Droplets, label: "Humidity", value: weather.humidity ?? "—", unit: "%" },
            { icon: CloudRain, label: "Rain", value: weather.rain ? "Yes" : "No", unit: "" },
          ].map((w) => (
            <div key={w.label} className="flex items-center gap-3 p-2">
              <w.icon className="w-5 h-5 text-zinc-500" />
              <div>
                <span className="text-xs text-zinc-500 uppercase">{w.label}</span>
                <p className="text-lg font-bold text-white">
                  {w.value}<span className="text-xs text-zinc-500 ml-0.5">{w.unit}</span>
                </p>
              </div>
            </div>
          ))}
        </div>
      </GlassCard>

      {/* ── SECTION: Full Results Table ── */}
      <GlassCard className="overflow-hidden" hover delay={0.28}>
        <h3 className="text-xs font-semibold text-zinc-500 px-6 pt-4 pb-2 uppercase tracking-widest">
          Full Classification
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="border-b border-f1-border text-zinc-500 uppercase text-[10px] tracking-wider">
                <th className="px-5 py-2">Pos</th>
                <th className="px-5 py-2">Driver</th>
                <th className="px-5 py-2">Team</th>
                <th className="px-5 py-2">Grid</th>
                <th className="px-5 py-2">+/-</th>
                <th className="px-5 py-2">Time</th>
                <th className="px-5 py-2">Pts</th>
                <th className="px-5 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <motion.tr
                  key={r.driver}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.01 * i }}
                  className={`border-b border-f1-border/30 hover:bg-white/[0.03] transition-colors ${
                    r.status !== "Finished" ? "opacity-60" : ""
                  }`}
                >
                  <td className="px-5 py-2.5">
                    <span className={`font-bold ${i < 3 ? "text-white" : "text-zinc-400"}`}>
                      {r.position}
                    </span>
                  </td>
                  <td className="px-5 py-2.5">
                    <div className="flex items-center gap-2">
                      {r.headshot ? (
                        <img
                          src={r.headshot}
                          alt={r.driver}
                          className="w-7 h-7 rounded-full object-cover bg-white/10 flex-shrink-0"
                          onError={(e) => { e.target.style.display = "none"; }}
                        />
                      ) : (
                        <span
                          className="w-7 h-7 rounded-full flex items-center justify-center text-[9px] font-bold flex-shrink-0"
                          style={{ backgroundColor: (r.teamColor || "#888") + "25", color: r.teamColor || "#888" }}
                        >
                          {r.driver?.[0]}
                        </span>
                      )}
                      <span className="w-0.5 h-5 rounded-full" style={{ backgroundColor: r.teamColor || "#888" }} />
                      <div>
                        <span className="text-white font-medium text-xs">{r.driver}</span>
                        {r.fullName && (
                          <p className="text-[9px] text-zinc-600 leading-tight">{r.fullName}</p>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-5 py-2.5 text-zinc-500 text-xs">{r.team}</td>
                  <td className="px-5 py-2.5 text-zinc-400 text-xs">{r.grid}</td>
                  <td className="px-5 py-2.5"><PositionDelta grid={r.grid} finish={r.position} /></td>
                  <td className="px-5 py-2.5 font-mono text-zinc-400 text-xs">{r.time || "—"}</td>
                  <td className="px-5 py-2.5 text-zinc-400 text-xs">{r.points}</td>
                  <td className="px-5 py-2.5">
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                        r.status === "Finished"
                          ? "bg-emerald-500/10 text-emerald-400"
                          : "bg-red-500/10 text-red-400"
                      }`}
                    >
                      {r.status}
                    </span>
                    {r.lapped && (
                      <span className="text-[10px] text-zinc-600 ml-1">{r.lapped}</span>
                    )}
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>

      {/* ── Quick Links ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {[
          { label: "Pit Strategy", desc: "Stops, stints, undercuts", to: "/pitstrategy", icon: Clock },
          { label: "Circuit Lab", desc: "Track telemetry per lap", to: "/circuit", icon: Flag },
          { label: "Race Replay", desc: "Lap-by-lap win probability", to: "/replay", icon: Trophy },
        ].map((link) => (
          <button
            key={link.to}
            onClick={() => navigate(link.to)}
            className="group flex items-center gap-3 p-4 rounded-xl glass border border-f1-border hover:border-f1-red/30 hover:bg-white/[0.03] transition-all text-left"
          >
            <link.icon className="w-5 h-5 text-zinc-500 group-hover:text-f1-red transition-colors" />
            <div className="flex-1">
              <span className="text-sm text-white font-medium">{link.label}</span>
              <p className="text-[10px] text-zinc-500">{link.desc}</p>
            </div>
            <ArrowRight className="w-4 h-4 text-zinc-600 group-hover:text-f1-red group-hover:translate-x-0.5 transition-all" />
          </button>
        ))}
      </div>
    </div>
  );
}
