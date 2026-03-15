import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  LayoutDashboard, Activity, Gauge, Zap, Play,
  Radio, MessageSquare, ChevronRight, Timer, Map,
  GitCompareArrows,
} from "lucide-react";
import SessionLoader from "../components/SessionLoader";

const GROUPS = [
  {
    heading: "Race Analysis",
    items: [
      {
        to: "/command", icon: LayoutDashboard, label: "Race Overview",
        desc: "Results, tyre strategy and weather conditions.",
      },
      {
        to: "/telemetry", icon: Activity, label: "Telemetry",
        desc: "Speed, throttle and brake traces. Compare any two drivers.",
      },
      {
        to: "/circuit", icon: Map, label: "Circuit Map",
        desc: "Track position replay and sector analysis.",
      },
      {
        to: "/performance", icon: Gauge, label: "Pace Analysis",
        desc: "Lap evolution, tyre degradation and adjusted pace.",
      },
      {
        to: "/pitstrategy", icon: Timer, label: "Strategy",
        desc: "Pit stops, undercut/overcut detection and safety car phases.",
      },
      {
        to: "/energy", icon: Zap, label: "Energy Analysis",
        desc: "Harvesting zones, lift-and-coast detection and deployment patterns.",
      },
      {
        to: "/replay", icon: Play, label: "Race Replay",
        desc: "Lap-by-lap replay with probability modelling.",
      },
    ],
  },
  {
    heading: "Live",
    items: [
      {
        to: "/live", icon: Radio, label: "Live Pit Wall",
        desc: "Real-time timing stream during sessions.",
      },
    ],
  },
  {
    heading: "Models",
    items: [
      {
        to: "/debrief", icon: MessageSquare, label: "AI Debrief",
        desc: "Automated race analysis and predictions.",
      },
      {
        to: "/compare", icon: GitCompareArrows, label: "Compare Races",
        desc: "Compare Grands Prix across seasons.",
      },
    ],
  },
];

export default function Home() {
  const navigate = useNavigate();
  const [sessionLoaded, setSessionLoaded] = useState(
    () => !!sessionStorage.getItem("sessionLoaded")
  );

  const handleLoaded = (data) => {
    sessionStorage.setItem("sessionLoaded", JSON.stringify(data));
    setSessionLoaded(true);
  };

  let itemIdx = 0;

  return (
    <div className="min-h-screen bg-f1-dark relative overflow-hidden">
      {/* Subtle grid */}
      <div className="absolute inset-0 bg-grid opacity-30 pointer-events-none" />

      {/* Neon red streak */}
      <div className="absolute top-0 left-0 right-0 h-[1px] overflow-hidden pointer-events-none">
        <div className="neon-streak" />
      </div>

      {/* ── Header ── */}
      <motion.header
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative z-10 flex items-center justify-between px-8 py-5 border-b border-white/[0.04]"
      >
        <h1 className="text-xl font-extrabold tracking-tight">
          <span className="text-f1-red">F1</span>
          <span className="text-white ml-1.5">Telemetry Lab</span>
        </h1>

        {sessionLoaded && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-[11px] text-emerald-400 font-medium">Session active</span>
          </div>
        )}
      </motion.header>

      <div className="relative z-10 max-w-5xl mx-auto px-8 py-12">
        {/* ── Session loader ── */}
        {!sessionLoaded && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.15 }}
            className="flex justify-center mb-12"
          >
            <SessionLoader onLoaded={handleLoaded} />
          </motion.div>
        )}

        {/* ── Grouped navigation ── */}
        {GROUPS.map((group, gi) => (
          <motion.div
            key={group.heading}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 * gi + 0.2, duration: 0.5 }}
            className="mb-10"
          >
            <h2 className="text-xs font-semibold text-zinc-400 uppercase tracking-widest mb-3 px-1">
              {group.heading}
            </h2>
            <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] divide-y divide-white/[0.04] overflow-hidden
                          border-t-f1-red/40" style={{ borderTopWidth: 2 }}>
              {group.items.map(({ to, icon: Icon, label, desc }) => {
                const i = itemIdx++;
                return (
                  <button
                    key={to}
                    onClick={() => navigate(to)}
                    className="group w-full flex items-center gap-5 px-6 py-5 text-left
                               hover:bg-white/[0.04] transition-colors duration-200"
                  >
                    <Icon size={20} className="text-f1-red flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-[15px] font-medium text-white group-hover:text-white/90 transition-colors">
                        {label}
                      </p>
                      <p className="text-[13px] text-zinc-400 mt-0.5">
                        {desc}
                      </p>
                    </div>
                    <ChevronRight
                      size={16}
                      className="text-zinc-700 group-hover:text-zinc-400 group-hover:translate-x-0.5 transition-all flex-shrink-0"
                    />
                  </button>
                );
              })}
            </div>
          </motion.div>
        ))}

        {/* ── Footer stats ── */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8 }}
          className="mt-10 flex justify-center gap-10 text-center"
        >
          {[
            { val: "10", label: "modules" },
            { val: "2014\u201326", label: "seasons" },
            { val: "FastF1 + React + FastAPI", label: "" },
          ].map((s, i) => (
            <div key={i} className="flex items-baseline gap-1.5">
              <span className="text-sm font-semibold text-zinc-400">{s.val}</span>
              {s.label && <span className="text-[10px] text-zinc-600">{s.label}</span>}
            </div>
          ))}
        </motion.div>
      </div>
    </div>
  );
}
