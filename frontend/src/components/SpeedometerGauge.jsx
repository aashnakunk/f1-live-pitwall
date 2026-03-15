import { useMemo } from "react";

/**
 * Circular speedometer gauge — F1 broadcast style.
 * Clean, minimal, no overlapping elements.
 */
export default function SpeedometerGauge({
  speed = 0,
  gear = "—",
  throttle = 0,
  brake = 0,
  driverColor = "#E10600",
  size = 200,
  label,
  flag,
  flagColor = "#ef4444",
}) {
  // Clamp inputs — FastF1 sometimes reports throttle > 100
  const clampedThrottle = Math.min(Math.max(throttle, 0), 100);
  const clampedBrake = Math.min(Math.max(brake, 0), 100);
  const clampedSpeed = Math.max(speed, 0);

  const maxSpeed = 370;
  const speedPct = Math.min(clampedSpeed / maxSpeed, 1);

  // Arc geometry — 270° sweep (7:30 to 4:30 clock positions)
  const startDeg = 225;
  const sweepDeg = 270;
  const endDeg = startDeg - sweepDeg;

  const toRad = (d) => (d * Math.PI) / 180;
  const cx = 100, cy = 105, r = 78;

  const ptAt = (deg, radius) => ({
    x: cx + radius * Math.cos(toRad(deg)),
    y: cy - radius * Math.sin(toRad(deg)),
  });

  const describeArc = (radius, start, end) => {
    const s = ptAt(start, radius);
    const e = ptAt(end, radius);
    const largeArc = start - end > 180 ? 1 : 0;
    return `M ${s.x} ${s.y} A ${radius} ${radius} 0 ${largeArc} 1 ${e.x} ${e.y}`;
  };

  const speedAngle = startDeg - speedPct * sweepDeg;
  const needleEnd = ptAt(speedAngle, r - 6);

  // Ticks — major every 50, labels every 100
  const ticks = useMemo(() => {
    const out = [];
    for (let v = 0; v <= maxSpeed; v += 10) {
      const pct = v / maxSpeed;
      const deg = startDeg - pct * sweepDeg;
      const isMajor = v % 50 === 0;
      const hasLabel = v % 100 === 0;
      out.push({
        v, deg, isMajor, hasLabel,
        o: ptAt(deg, r),
        i: ptAt(deg, r - (isMajor ? 8 : 4)),
        lbl: hasLabel ? ptAt(deg, r + 10) : null,
      });
    }
    return out;
  }, []);

  const speedColor = clampedSpeed > 300 ? "#ef4444" : clampedSpeed > 200 ? "#eab308" : clampedSpeed > 100 ? "#22c55e" : "#60a5fa";

  return (
    <div className="inline-flex flex-col items-center gap-1" style={{ width: size }}>
      <svg viewBox="0 0 200 210" width={size} height={size} className="block">
        <defs>
          <linearGradient id="spdArc" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0%" stopColor="#60a5fa" />
            <stop offset="30%" stopColor="#22c55e" />
            <stop offset="60%" stopColor="#eab308" />
            <stop offset="100%" stopColor="#ef4444" />
          </linearGradient>
        </defs>

        {/* Background arc */}
        <path d={describeArc(r, startDeg, endDeg)} fill="none"
          stroke="rgba(255,255,255,0.08)" strokeWidth={12} strokeLinecap="round" />

        {/* Speed fill arc */}
        {speedPct > 0.005 && (
          <path d={describeArc(r, startDeg, speedAngle)} fill="none"
            stroke="url(#spdArc)" strokeWidth={10} strokeLinecap="round" />
        )}
        {/* Glow */}
        {speedPct > 0.005 && (
          <path d={describeArc(r, startDeg, speedAngle)} fill="none"
            stroke={speedColor} strokeWidth={18} strokeLinecap="round" opacity={0.1} />
        )}

        {/* Tick marks — outside the arc */}
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={t.o.x} y1={t.o.y} x2={t.i.x} y2={t.i.y}
              stroke={t.isMajor ? "rgba(255,255,255,0.45)" : "rgba(255,255,255,0.1)"}
              strokeWidth={t.isMajor ? 1.5 : 0.6} />
            {t.lbl && (
              <text x={t.lbl.x} y={t.lbl.y} fill="rgba(255,255,255,0.4)"
                fontSize={7} textAnchor="middle" dominantBaseline="central" fontFamily="monospace">
                {t.v}
              </text>
            )}
          </g>
        ))}

        {/* Needle */}
        <line x1={cx} y1={cy} x2={needleEnd.x} y2={needleEnd.y}
          stroke="#fff" strokeWidth={2} strokeLinecap="round" />
        <line x1={cx} y1={cy} x2={needleEnd.x} y2={needleEnd.y}
          stroke={speedColor} strokeWidth={6} strokeLinecap="round" opacity={0.2} />
        <circle cx={cx} cy={cy} r={5} fill="#111" stroke="rgba(255,255,255,0.25)" strokeWidth={1} />

        {/* Speed number — centered in gauge */}
        <text x={cx} y={cy - 4} fill="#fff" fontSize={26} textAnchor="middle"
          dominantBaseline="central" fontFamily="monospace" fontWeight="bold">
          {Math.round(clampedSpeed)}
        </text>
        <text x={cx} y={cy + 12} fill="rgba(255,255,255,0.3)" fontSize={7}
          textAnchor="middle" fontFamily="monospace">km/h</text>

        {/* Gear — below in the open gap of the arc */}
        <text x={cx} y={cy + 38} fill={driverColor} fontSize={22} textAnchor="middle"
          fontFamily="monospace" fontWeight="bold">{gear}</text>
        <text x={cx} y={cy + 50} fill="rgba(255,255,255,0.2)" fontSize={6}
          textAnchor="middle" fontFamily="monospace" letterSpacing={2}>GEAR</text>
      </svg>

      {/* Throttle / Brake bars */}
      <div className="flex gap-2 w-full px-2">
        <div className="flex-1">
          <div className="flex justify-between mb-0.5">
            <span className="text-[7px] text-zinc-500 font-bold tracking-wide">THR</span>
            <span className="text-[9px] text-green-400 font-mono font-bold">{Math.round(clampedThrottle)}%</span>
          </div>
          <div className="w-full h-[5px] rounded-full bg-white/[0.06] overflow-hidden">
            <div className="h-full rounded-full transition-all duration-75"
              style={{
                width: `${clampedThrottle}%`,
                background: "linear-gradient(90deg, #166534, #22c55e)",
                boxShadow: clampedThrottle > 80 ? "0 0 8px #22c55e44" : "none",
              }} />
          </div>
        </div>
        <div className="flex-1">
          <div className="flex justify-between mb-0.5">
            <span className="text-[7px] text-zinc-500 font-bold tracking-wide">BRK</span>
            <span className="text-[9px] text-red-400 font-mono font-bold">{Math.round(clampedBrake)}%</span>
          </div>
          <div className="w-full h-[5px] rounded-full bg-white/[0.06] overflow-hidden">
            <div className="h-full rounded-full transition-all duration-75"
              style={{
                width: `${clampedBrake}%`,
                background: "linear-gradient(90deg, #991b1b, #ef4444)",
                boxShadow: clampedBrake > 50 ? "0 0 8px #ef444444" : "none",
              }} />
          </div>
        </div>
      </div>

      {/* Flag */}
      {flag && (
        <div className="px-2.5 py-0.5 rounded-full text-[8px] font-bold uppercase tracking-wider"
          style={{ color: flagColor, backgroundColor: `${flagColor}12`, border: `1px solid ${flagColor}25` }}>
          {flag}
        </div>
      )}
    </div>
  );
}


/**
 * ERS status indicator — shows deploy/harvest/idle from real telemetry.
 * Fixed-size to prevent layout shifts during replay.
 */
export function ERSStatusIndicator({
  deploying = false,
  harvesting = false,
}) {
  const mode = deploying ? "DEPLOY" : harvesting ? "HARVEST" : "IDLE";
  const color = deploying ? "#22c55e" : harvesting ? "#f59e0b" : "#555";

  return (
    <div className="flex flex-col items-center gap-1">
      <span className="text-[7px] font-bold tracking-widest text-zinc-500">ERS</span>

      {/* Fixed-size pill — no width changes between modes */}
      <div className="relative flex items-center justify-center rounded-md border"
        style={{
          width: 52,
          height: 24,
          borderColor: `${color}50`,
          background: `${color}10`,
        }}>
        <span className="text-[9px] font-mono font-bold tracking-wide"
          style={{ color }}>
          {mode}
        </span>

        {/* Static glow border — no animate-pulse to avoid jitter */}
        {mode !== "IDLE" && (
          <div className="absolute inset-0 rounded-md pointer-events-none"
            style={{ boxShadow: `inset 0 0 6px ${color}30, 0 0 4px ${color}20` }} />
        )}
      </div>
    </div>
  );
}
