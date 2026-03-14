import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { MessageCircle, X, Send, Loader2, Trash2, Key } from "lucide-react";
import { useLocation } from "react-router-dom";

const PAGE_MAP = {
  "/command": "command",
  "/telemetry": "telemetry",
  "/circuit": "circuit",
  "/performance": "performance",
  "/pitstrategy": "pitstrategy",
  "/energy": "energy",
  "/replay": "replay",
  "/live": "live",
  "/debrief": "debrief",
  "/compare": "compare",
};

const PAGE_LABELS = {
  command: "Race Command",
  telemetry: "Telemetry Lab",
  circuit: "Circuit Lab",
  performance: "Performance Studio",
  pitstrategy: "Pit Strategy",
  energy: "Energy Map",
  replay: "Race Replay",
  live: "Live Pit Wall",
  debrief: "AI Debrief",
  compare: "Compare GPs",
  general: "General",
};

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [apiKey, setApiKey] = useState(() => localStorage.getItem("f1_anthropic_key") || "");
  const [showKeyInput, setShowKeyInput] = useState(false);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);
  const location = useLocation();

  const currentPage = PAGE_MAP[location.pathname] || "general";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (open && inputRef.current) {
      inputRef.current.focus();
    }
  }, [open]);

  const sendMessage = async () => {
    const q = input.trim();
    if (!q || loading) return;
    if (!apiKey) {
      setShowKeyInput(true);
      return;
    }

    const userMsg = { role: "user", content: q };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch("/api/session/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          apiKey,
          question: q,
          page: currentPage,
          history: messages.slice(-6),
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Request failed");
      }
      const result = await res.json();
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: result.reply },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Error: ${e.message || "Failed to get response"}. Make sure your API key is valid and a session is loaded.`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const saveKey = () => {
    localStorage.setItem("f1_anthropic_key", apiKey);
    setShowKeyInput(false);
  };

  return (
    <>
      {/* Floating button */}
      <AnimatePresence>
        {!open && (
          <motion.button
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            onClick={() => setOpen(true)}
            className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-f1-red flex items-center justify-center
                       shadow-lg shadow-f1-red/30 hover:bg-f1-red/90 transition-colors group"
          >
            <MessageCircle className="w-6 h-6 text-white group-hover:scale-110 transition-transform" />
            {messages.length > 0 && (
              <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-white text-f1-red text-[10px] font-bold flex items-center justify-center">
                {messages.filter((m) => m.role === "assistant").length}
              </span>
            )}
          </motion.button>
        )}
      </AnimatePresence>

      {/* Chat panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            className="fixed bottom-6 right-6 z-50 w-[380px] h-[520px] flex flex-col
                       rounded-2xl glass border border-white/10 shadow-2xl shadow-black/50 overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 bg-white/[0.02]">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-f1-red flex items-center justify-center">
                  <MessageCircle className="w-4 h-4 text-white" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Race Engineer AI</h3>
                  <span className="text-[10px] text-zinc-500">
                    Context: {PAGE_LABELS[currentPage]}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setShowKeyInput(!showKeyInput)}
                  className="w-7 h-7 rounded-lg hover:bg-white/5 flex items-center justify-center transition-colors"
                  title="API Key"
                >
                  <Key className={`w-3.5 h-3.5 ${apiKey ? "text-emerald-400" : "text-zinc-500"}`} />
                </button>
                <button
                  onClick={() => setMessages([])}
                  className="w-7 h-7 rounded-lg hover:bg-white/5 flex items-center justify-center transition-colors"
                  title="Clear chat"
                >
                  <Trash2 className="w-3.5 h-3.5 text-zinc-500" />
                </button>
                <button
                  onClick={() => setOpen(false)}
                  className="w-7 h-7 rounded-lg hover:bg-white/5 flex items-center justify-center transition-colors"
                >
                  <X className="w-4 h-4 text-zinc-400" />
                </button>
              </div>
            </div>

            {/* API Key input */}
            {showKeyInput && (
              <div className="px-4 py-2 border-b border-white/5 bg-white/[0.02]">
                <div className="flex gap-2">
                  <input
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="Anthropic API key..."
                    className="flex-1 bg-white/5 text-white text-xs rounded-lg px-3 py-1.5 border border-f1-border
                               focus:outline-none focus:border-f1-red/50 placeholder-zinc-600"
                  />
                  <button
                    onClick={saveKey}
                    className="px-3 py-1.5 bg-f1-red text-white text-xs rounded-lg hover:bg-f1-red/80 transition-colors"
                  >
                    Save
                  </button>
                </div>
              </div>
            )}

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 scrollbar-thin">
              {messages.length === 0 && (
                <div className="text-center py-8">
                  <MessageCircle className="w-10 h-10 text-zinc-700 mx-auto mb-3" />
                  <p className="text-xs text-zinc-500 mb-1">Ask me anything about this session.</p>
                  <p className="text-[10px] text-zinc-600">
                    I have context from the <span className="text-f1-red">{PAGE_LABELS[currentPage]}</span> page.
                  </p>
                  <div className="mt-4 space-y-1.5">
                    {[
                      "How did Sainz perform?",
                      "What was the pit strategy difference?",
                      "Why did the safety car come out?",
                    ].map((q) => (
                      <button
                        key={q}
                        onClick={() => {
                          setInput(q);
                          inputRef.current?.focus();
                        }}
                        className="block w-full text-left text-[11px] text-zinc-400 px-3 py-1.5 rounded-lg
                                   bg-white/[0.03] hover:bg-white/[0.06] border border-f1-border/30
                                   hover:border-f1-red/20 transition-all"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] px-3 py-2 rounded-xl text-xs leading-relaxed ${
                      msg.role === "user"
                        ? "bg-f1-red/20 text-white rounded-br-sm"
                        : "bg-white/5 text-zinc-300 rounded-bl-sm border border-f1-border/30"
                    }`}
                  >
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex justify-start">
                  <div className="bg-white/5 border border-f1-border/30 px-3 py-2 rounded-xl rounded-bl-sm">
                    <Loader2 className="w-4 h-4 text-f1-red animate-spin" />
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {/* Input */}
            <div className="px-3 py-2.5 border-t border-white/5 bg-white/[0.02]">
              <div className="flex gap-2">
                <input
                  ref={inputRef}
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
                  placeholder={apiKey ? "Ask about this session..." : "Set API key first..."}
                  disabled={!apiKey}
                  className="flex-1 bg-white/5 text-white text-xs rounded-xl px-4 py-2.5 border border-f1-border
                             focus:outline-none focus:border-f1-red/50 placeholder-zinc-600
                             disabled:opacity-40 disabled:cursor-not-allowed"
                />
                <button
                  onClick={sendMessage}
                  disabled={loading || !input.trim() || !apiKey}
                  className="w-10 h-10 rounded-xl bg-f1-red flex items-center justify-center
                             hover:bg-f1-red/80 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <Send className="w-4 h-4 text-white" />
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
