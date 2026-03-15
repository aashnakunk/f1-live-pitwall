/**
 * F1 car loading animation — car drives around a mini circuit SVG.
 * Falls back to simple spinner for very small sizes.
 */
export default function LoadingSpinner({ text = "Loading...", showTrack = true }) {
  if (!showTrack) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4">
        <div className="relative w-12 h-12">
          <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-f1-red animate-spin" />
          <div className="absolute inset-1 rounded-full border-2 border-transparent border-b-white/20 animate-spin" style={{ animationDirection: "reverse", animationDuration: "1.5s" }} />
        </div>
        <p className="text-f1-muted text-sm font-medium">{text}</p>
      </div>
    );
  }

  // Mini oval circuit path for the car to follow
  const trackPath = "M 80 30 C 130 30, 160 50, 160 80 C 160 110, 130 130, 80 130 C 30 130, 10 110, 10 80 C 10 50, 30 30, 80 30 Z";

  return (
    <div className="flex flex-col items-center justify-center py-16 gap-5">
      <div className="relative">
        <svg width="170" height="160" viewBox="0 0 170 160" className="block">
          {/* Track surface */}
          <path d={trackPath} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth={18} strokeLinecap="round" />
          {/* Track edge lines */}
          <path d={trackPath} fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth={22} strokeLinecap="round" />
          {/* Racing line */}
          <path d={trackPath} fill="none" stroke="rgba(225,6,0,0.08)" strokeWidth={2} strokeDasharray="4 6" />

          {/* Start/finish line */}
          <line x1="80" y1="20" x2="80" y2="40" stroke="rgba(255,255,255,0.15)" strokeWidth={2} />

          {/* The F1 "car" — a small red dot with glow trailing along the track */}
          <circle r="4" fill="#E10600" className="f1-car-loading" style={{ offsetPath: `path('${trackPath}')` }}>
            <animate attributeName="r" values="3.5;4.5;3.5" dur="0.6s" repeatCount="indefinite" />
          </circle>
          {/* Car glow */}
          <circle r="8" fill="none" className="f1-car-loading" style={{ offsetPath: `path('${trackPath}')` }}>
            <animate attributeName="r" values="6;10;6" dur="0.6s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.3;0.1;0.3" dur="0.6s" repeatCount="indefinite" />
            <animate attributeName="fill" values="#E10600;#ff4444;#E10600" dur="0.6s" repeatCount="indefinite" />
          </circle>
          {/* Trail effect — offset behind the car */}
          <circle r="3" fill="#E10600" opacity="0.2" className="f1-car-loading"
            style={{ offsetPath: `path('${trackPath}')`, animationDelay: "-0.15s" }} />
          <circle r="2" fill="#E10600" opacity="0.1" className="f1-car-loading"
            style={{ offsetPath: `path('${trackPath}')`, animationDelay: "-0.3s" }} />
        </svg>
      </div>

      <div className="flex flex-col items-center gap-1.5">
        <p className="text-zinc-400 text-sm font-medium">{text}</p>
        <div className="flex gap-1">
          <div className="w-1 h-1 rounded-full bg-f1-red animate-bounce" style={{ animationDelay: "0s" }} />
          <div className="w-1 h-1 rounded-full bg-f1-red animate-bounce" style={{ animationDelay: "0.15s" }} />
          <div className="w-1 h-1 rounded-full bg-f1-red animate-bounce" style={{ animationDelay: "0.3s" }} />
        </div>
      </div>
    </div>
  );
}
