import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { MessageSquare, Key, Send, Sparkles, AlertCircle } from "lucide-react";
import GlassCard from "../components/GlassCard";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import { useApi } from "../hooks/useApi";

export default function AIDebrief() {
  const api = useApi();
  const [apiKey, setApiKey] = useState("");
  const [debrief, setDebrief] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const sessionLoaded = !!sessionStorage.getItem("sessionLoaded");

  const handleGenerate = async () => {
    if (!apiKey.trim()) {
      setError("Please enter your API key.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const result = await api.call("/api/session/debrief", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ apiKey: apiKey.trim() }),
      });
      setDebrief(result?.debrief || "No analysis returned.");
    } catch (e) {
      setError(e?.message || "Failed to generate debrief. Please check your API key and try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8 relative">
      {/* Subtle gradient glow behind content */}
      <div className="absolute top-40 left-1/2 -translate-x-1/2 w-[700px] h-[400px] bg-purple-500/[0.04] rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute top-60 right-0 w-[300px] h-[300px] bg-f1-red/[0.03] rounded-full blur-[100px] pointer-events-none" />

      <div className="relative z-10 space-y-8">
        <PageHeader
          title="AI Debrief Agent"
          subtitle="Claude-powered race analysis and predictions"
          icon={MessageSquare}
        />

        {/* No session warning */}
        {!sessionLoaded && (
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <GlassCard className="p-5" hover delay={0.1}>
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-yellow-500/10 border border-yellow-500/20 flex items-center justify-center flex-shrink-0">
                  <AlertCircle className="w-5 h-5 text-yellow-400" />
                </div>
                <div>
                  <h3 className="text-white font-semibold text-sm">
                    No Session Loaded
                  </h3>
                  <p className="text-zinc-500 text-sm">
                    Load a race session from the home page first, then return
                    here for AI analysis.
                  </p>
                </div>
              </div>
            </GlassCard>
          </motion.div>
        )}

        {/* API key input card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
        >
          <GlassCard className="p-6" hover delay={0.15}>
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center flex-shrink-0">
                <Key className="w-5 h-5 text-purple-400" />
              </div>
              <div className="flex-1 space-y-4">
                <div>
                  <h3 className="text-white font-semibold mb-1">
                    Claude API Key
                  </h3>
                  <p className="text-zinc-500 text-sm">
                    Enter your Anthropic API key to generate an AI-powered race
                    debrief. Your key is not stored.
                  </p>
                </div>
                <div className="flex gap-3">
                  <div className="relative flex-1">
                    <input
                      type="password"
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleGenerate()}
                      placeholder="sk-ant-..."
                      className="w-full px-4 py-3 rounded-xl bg-white/[0.04] border border-f1-border
                                 text-white placeholder-zinc-600 text-sm font-mono
                                 focus:outline-none focus:border-f1-red/50 focus:ring-1 focus:ring-f1-red/20
                                 transition-all"
                    />
                  </div>
                  <button
                    onClick={handleGenerate}
                    disabled={loading || !sessionLoaded}
                    className="px-6 py-3 rounded-xl bg-f1-red text-white font-semibold text-sm
                               flex items-center gap-2
                               hover:bg-f1-red/80 transition-colors glow-red
                               disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-f1-red"
                  >
                    <Send className="w-4 h-4" />
                    Generate Debrief
                  </button>
                </div>
                <AnimatePresence>
                  {error && (
                    <motion.p
                      initial={{ opacity: 0, y: -5 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      className="text-red-400 text-sm"
                    >
                      {error}
                    </motion.p>
                  )}
                </AnimatePresence>
              </div>
            </div>
          </GlassCard>
        </motion.div>

        {/* Loading state */}
        {loading && (
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
          >
            <GlassCard className="p-12" delay={0}>
              <div className="flex flex-col items-center gap-4">
                <div className="relative">
                  <div className="w-14 h-14 rounded-2xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
                    <Sparkles className="w-6 h-6 text-purple-400 animate-pulse" />
                  </div>
                </div>
                <LoadingSpinner text="Claude is analyzing the race..." />
              </div>
            </GlassCard>
          </motion.div>
        )}

        {/* Debrief result */}
        <AnimatePresence>
          {debrief && !loading && (
            <motion.div
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
            >
              <GlassCard className="racing-stripe relative overflow-hidden" hover delay={0.1}>
                {/* Premium gradient overlay */}
                <div className="absolute inset-0 bg-gradient-to-br from-purple-500/[0.03] via-transparent to-f1-red/[0.02] pointer-events-none" />

                <div className="relative p-8">
                  <div className="flex items-center gap-3 mb-6">
                    <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
                      <Sparkles className="w-4 h-4 text-purple-400" />
                    </div>
                    <h3 className="text-white font-semibold">
                      Race Debrief
                    </h3>
                    <span className="text-xs text-zinc-600 ml-auto font-mono">
                      Powered by Claude
                    </span>
                  </div>

                  <div className="space-y-4">
                    {debrief.split("\n\n").map((paragraph, i) => (
                      <motion.p
                        key={i}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.05 * i }}
                        className="text-zinc-300 text-sm leading-relaxed"
                      >
                        {paragraph}
                      </motion.p>
                    ))}
                  </div>
                </div>
              </GlassCard>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
