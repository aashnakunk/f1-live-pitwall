import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  LayoutDashboard, Activity, Gauge, Zap, Timer,
  Radio, Play, MessageSquare, Home, PenTool, Map, GitCompareArrows,
} from "lucide-react";
import ChatWidget from "./ChatWidget";

const NAV_ITEMS = [
  { to: "/command", label: "Race Command", icon: LayoutDashboard },
  { to: "/telemetry", label: "Telemetry Lab", icon: Activity },
  { to: "/circuit", label: "Circuit Lab", icon: Map },
  { to: "/performance", label: "Performance Studio", icon: Gauge },
  { to: "/pitstrategy", label: "Pit Strategy", icon: Timer },
  { to: "/energy", label: "Energy Map", icon: Zap },
  { to: "/replay", label: "Race Replay", icon: Play },
  { to: "/live", label: "Live Pit Wall", icon: Radio },
  { to: "/debrief", label: "AI Debrief", icon: MessageSquare },
  { to: "/compare", label: "Compare GPs", icon: GitCompareArrows },
];

export default function Layout() {
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen bg-f1-dark bg-grid">
      {/* Sidebar */}
      <nav className="w-[220px] fixed left-0 top-0 h-full glass border-r border-white/5 z-50 flex flex-col">
        {/* Logo */}
        <button
          onClick={() => navigate("/")}
          className="flex items-center gap-2 px-5 py-5 border-b border-white/5 hover:bg-white/5 transition"
        >
          <span className="text-sm font-extrabold tracking-tight">
            <span className="text-f1-red">F1</span>
            <span className="text-white ml-1">Telemetry Lab</span>
          </span>
        </button>

        {/* Nav links */}
        <div className="flex-1 py-3 px-3 space-y-0.5 overflow-y-auto">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? "nav-active text-white"
                    : "text-zinc-400 hover:text-white hover:bg-white/5"
                }`
              }
            >
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-white/5">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-xs text-f1-muted">Backend connected</span>
          </div>
        </div>
      </nav>

      {/* Main content */}
      <main className="ml-[220px] flex-1 p-8 min-h-screen">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
        >
          <Outlet />
        </motion.div>
      </main>

      {/* AI Chat Widget */}
      <ChatWidget />
    </div>
  );
}
