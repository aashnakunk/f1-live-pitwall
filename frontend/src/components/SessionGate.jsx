import { useState, useEffect } from "react";
import { useApi } from "../hooks/useApi";
import SessionLoader from "./SessionLoader";
import LoadingSpinner from "./LoadingSpinner";

export default function SessionGate({ children }) {
  const { call } = useApi();
  const [status, setStatus] = useState(null);
  const [checking, setChecking] = useState(true);
  const [showLoader, setShowLoader] = useState(false);

  const checkSession = async () => {
    setChecking(true);
    const data = await call("/api/session/status");
    setStatus(data);
    setChecking(false);
    setShowLoader(false);
  };

  useEffect(() => {
    checkSession();
  }, []);

  if (checking) return <LoadingSpinner text="Checking session..." />;

  if (!status?.loaded || showLoader) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-6">
        <div className="text-center mb-2">
          <h2 className="text-xl font-bold text-white mb-1">
            {showLoader ? "Change Session" : "No Session Loaded"}
          </h2>
          <p className="text-f1-muted text-sm">
            {showLoader
              ? `Currently: ${status?.event} ${status?.year} — ${status?.session}`
              : "Load a race session to view this page"}
          </p>
        </div>
        <SessionLoader onLoaded={() => { checkSession(); window.location.reload(); }} />
        {showLoader && (
          <button
            onClick={() => setShowLoader(false)}
            className="text-xs text-zinc-500 hover:text-white transition-colors"
          >
            Cancel
          </button>
        )}
      </div>
    );
  }

  return (
    <>
      <div className="mb-6 flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-emerald-400" />
        <span className="text-xs text-f1-muted">
          {status.event} {status.year} — {status.session}
        </span>
        <button
          onClick={() => setShowLoader(true)}
          className="ml-2 text-[10px] text-zinc-500 hover:text-white transition-colors px-2 py-0.5 rounded border border-white/10 hover:border-white/20"
        >
          Change
        </button>
      </div>
      {children}
    </>
  );
}
