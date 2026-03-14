import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  LayoutDashboard, Activity, Gauge, Zap, Play,
  Radio, MessageSquare, ChevronRight, Timer,
} from "lucide-react";
import SessionLoader from "../components/SessionLoader";

const SECTIONS = [
  {
    to: "/command", icon: LayoutDashboard, label: "Race Command Center",
    desc: "Results, tyre strategy, weather — the full race briefing",
    color: "#E10600",
  },
  {
    to: "/telemetry", icon: Activity, label: "Telemetry Lab",
    desc: "Speed, throttle, brake traces — compare any two drivers",
    color: "#3671C6",
  },
  {
    to: "/performance", icon: Gauge, label: "Performance Studio",
    desc: "Lap time evolution, tyre degradation, pace-adjusted standings",
    color: "#FF8000",
  },
  {
    to: "/pitstrategy", icon: Timer, label: "Pit Strategy",
    desc: "Pit stops, undercut/overcut detection, safety car periods",
    color: "#52E252",
  },
  {
    to: "/energy", icon: Zap, label: "Energy Map",
    desc: "Braking zones, coasting, energy harvesting — 2026 reg ready",
    color: "#FFC300",
  },
  {
    to: "/replay", icon: Play, label: "Race Replay",
    desc: "Lap-by-lap simulation with live win probability model",
    color: "#27F4D2",
  },
  {
    to: "/live", icon: Radio, label: "Live Pit Wall",
    desc: "Real-time F1 timing stream during live sessions",
    color: "#FF3333",
  },
  {
    to: "/debrief", icon: MessageSquare, label: "AI Debrief Agent",
    desc: "Claude-powered race analysis and next-race predictions",
    color: "#BB86FC",
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

  return (
    <div className="min-h-screen bg-f1-dark bg-grid relative overflow-hidden">
      {/* Background glow effects */}
      <div className="absolute top-[-200px] right-[-200px] w-[600px] h-[600px] bg-f1-red/5 rounded-full blur-[150px] pointer-events-none" />
      <div className="absolute bottom-[-100px] left-[-100px] w-[400px] h-[400px] bg-blue-500/5 rounded-full blur-[120px] pointer-events-none" />

      {/* Top bar */}
      <motion.header
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative z-10 flex items-center justify-between px-8 py-5 border-b border-white/5"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-f1-red flex items-center justify-center glow-red">
            <span className="text-white font-black text-lg">F1</span>
          </div>
          <div>
            <h1 className="text-lg font-bold text-white tracking-tight">PIT WALL</h1>
            <p className="text-[11px] text-f1-muted -mt-0.5">Race Engineer Dashboard</p>
          </div>
        </div>
        {sessionLoaded && (
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs text-emerald-400 font-medium">Session loaded</span>
          </div>
        )}
      </motion.header>

      <div className="relative z-10 max-w-7xl mx-auto px-8 py-12">
        {/* Hero */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.4, 0, 0.2, 1] }}
          className="text-center mb-16"
        >
          <h2 className="text-5xl font-extrabold text-gradient leading-tight mb-4">
            Your Race Engineer
            <br />
            <span className="text-f1-red">Command Center</span>
          </h2>
          <p className="text-f1-muted text-lg max-w-xl mx-auto">
            Telemetry analysis, real-time predictions, energy management, and AI-powered
            race debriefs — all in one place.
          </p>
        </motion.div>

        {/* Session loader (if not loaded) */}
        {!sessionLoaded && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.3 }}
            className="flex justify-center mb-16"
          >
            <SessionLoader onLoaded={handleLoaded} />
          </motion.div>
        )}

        {/* Navigation grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {SECTIONS.map(({ to, icon: Icon, label, desc, color }, i) => (
            <motion.button
              key={to}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 * i + 0.4, duration: 0.5 }}
              onClick={() => navigate(to)}
              className="glass glass-hover p-6 text-left group relative overflow-hidden"
            >
              {/* Colored accent line at top */}
              <div
                className="absolute top-0 left-0 right-0 h-[2px] opacity-60 group-hover:opacity-100 transition"
                style={{ background: `linear-gradient(90deg, ${color}, transparent)` }}
              />

              <div className="flex items-start justify-between">
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center mb-4"
                  style={{ background: `${color}15`, border: `1px solid ${color}30` }}
                >
                  <Icon size={20} style={{ color }} />
                </div>
                <ChevronRight
                  size={16}
                  className="text-zinc-600 group-hover:text-zinc-400 group-hover:translate-x-1 transition-all"
                />
              </div>

              <h3 className="text-white font-semibold mb-1">{label}</h3>
              <p className="text-f1-muted text-sm leading-relaxed">{desc}</p>
            </motion.button>
          ))}
        </div>

        {/* Footer note */}
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.2 }}
          className="text-center text-f1-muted/50 text-xs mt-16"
        >
          Built with FastF1 + React + FastAPI + Claude
        </motion.p>
      </div>
    </div>
  );
}
