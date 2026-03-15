import { useRef, useEffect, useMemo } from "react";

/**
 * Premium F1-style SVG circuit map — thick asphalt track with kerbs, glow effects,
 * DRS zones, sector markers, and large animated driver dots.
 *
 * Props:
 *  - outline: { x: number[], y: number[] }  — track path coordinates
 *  - drivers: Array<{ id, x, y, color, label }>  — driver dot positions
 *  - highlightDriver?: string  — driver id to enlarge/glow
 *  - showStartFinish?: boolean
 *  - showCheckered?: boolean
 *  - trackColor?: string  — base track outline color (default "#555")
 *  - trackSegments?: Array<{ startIdx, endIdx, color }>  — colored track sections
 *  - corners?: Array<{ number, x, y }>  — corner labels
 *  - drsZones?: Array<{ startIdx, endIdx }>  — DRS activation zones
 *  - height?: number
 *  - className?: string
 *  - thick?: boolean  — use extra-thick broadcast-style rendering (default true)
 */
export default function CircuitSVG({
  outline,
  drivers = [],
  highlightDriver,
  showStartFinish = false,
  showCheckered = false,
  trackColor = "#555",
  trackSegments,
  corners,
  drsZones,
  height = 450,
  className = "",
  thick = true,
}) {
  const svgRef = useRef(null);

  // Compute viewBox from outline bounds
  const { viewBox, toSVG, sfLine, vbW: computedVbW } = useMemo(() => {
    if (!outline?.x?.length || !outline?.y?.length) {
      return { viewBox: "0 0 100 100", toSVG: (x, y) => [50, 50], sfLine: null, vbW: 100 };
    }
    const xs = outline.x;
    const ys = outline.y;
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const pad = Math.max(maxX - minX, maxY - minY) * 0.08;
    const vbX = minX - pad;
    const vbW = maxX - minX + pad * 2;
    const vbH = maxY - minY + pad * 2;
    const flipY = (y) => maxY + minY - y;
    const convert = (x, y) => [x, flipY(y)];

    // Start/finish line — perpendicular at first point
    let sf = null;
    if (xs.length >= 2) {
      const [sx, sy] = convert(xs[0], ys[0]);
      const [nx, ny] = convert(xs[1], ys[1]);
      const dx = nx - sx;
      const dy = ny - sy;
      const len = Math.sqrt(dx * dx + dy * dy) || 1;
      const perpX = -dy / len;
      const perpY = dx / len;
      const sfLen = vbW * 0.025;
      sf = {
        x1: sx - perpX * sfLen, y1: sy - perpY * sfLen,
        x2: sx + perpX * sfLen, y2: sy + perpY * sfLen,
        cx: sx, cy: sy,
      };
    }

    return {
      viewBox: `${vbX} ${flipY(maxY) - pad} ${vbW} ${vbH}`,
      toSVG: convert,
      sfLine: sf,
      vbW,
    };
  }, [outline]);

  // Build smooth track path using Catmull-Rom spline for broadcast-quality curves
  const trackPath = useMemo(() => {
    if (!outline?.x?.length) return "";
    const pts = outline.x.map((x, i) => {
      const [sx, sy] = toSVG(x, outline.y[i]);
      return { x: sx, y: sy };
    });

    if (!thick || pts.length < 4) {
      return pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ");
    }

    // Catmull-Rom to cubic bezier for smooth curves
    const n = pts.length;
    let d = `M ${pts[0].x} ${pts[0].y}`;
    for (let i = 0; i < n - 1; i++) {
      const p0 = pts[(i - 1 + n) % n];
      const p1 = pts[i];
      const p2 = pts[(i + 1) % n];
      const p3 = pts[(i + 2) % n];
      const cp1x = p1.x + (p2.x - p0.x) / 6;
      const cp1y = p1.y + (p2.y - p0.y) / 6;
      const cp2x = p2.x - (p3.x - p1.x) / 6;
      const cp2y = p2.y - (p3.y - p1.y) / 6;
      d += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2.x} ${p2.y}`;
    }
    return d;
  }, [outline, toSVG, thick]);

  // Build colored segment paths
  const segmentPaths = useMemo(() => {
    if (!trackSegments || !outline?.x?.length) return [];
    return trackSegments.map((seg) => {
      let path = "";
      for (let i = seg.startIdx; i <= Math.min(seg.endIdx, outline.x.length - 1); i++) {
        const [sx, sy] = toSVG(outline.x[i], outline.y[i]);
        path += `${i === seg.startIdx ? "M" : "L"}${sx},${sy} `;
      }
      return { path, color: seg.color };
    });
  }, [trackSegments, outline, toSVG]);

  // DRS zone paths
  const drsPaths = useMemo(() => {
    if (!drsZones || !outline?.x?.length) return [];
    return drsZones.map((zone) => {
      let path = "";
      for (let i = zone.startIdx; i <= Math.min(zone.endIdx, outline.x.length - 1); i++) {
        const [sx, sy] = toSVG(outline.x[i], outline.y[i]);
        path += `${i === zone.startIdx ? "M" : "L"}${sx},${sy} `;
      }
      return path;
    });
  }, [drsZones, outline, toSVG]);

  // Smooth driver dot movement — update all sub-elements via transform on the group
  useEffect(() => {
    if (!svgRef.current) return;
    drivers.forEach((drv) => {
      const group = svgRef.current.querySelector(`[data-driver-group="${drv.id}"]`);
      if (group) {
        const [sx, sy] = toSVG(drv.x, drv.y);
        group.setAttribute("transform", `translate(${sx},${sy})`);
      }
    });
  }, [drivers, toSVG]);

  if (!outline?.x?.length) {
    return (
      <div className={`flex items-center justify-center text-zinc-600 ${className}`} style={{ height }}>
        No track data
      </div>
    );
  }

  // Scale factors — thick mode uses ~4x bigger strokes
  const strokeW = thick ? computedVbW * 0.02 : computedVbW * 0.004;
  const dotR = thick ? computedVbW * 0.02 : computedVbW * 0.008;
  const highlightR = thick ? computedVbW * 0.026 : computedVbW * 0.013;
  const cornerFontSize = thick ? computedVbW * 0.014 : computedVbW * 0.012;
  const labelFontSize = thick ? computedVbW * 0.022 : computedVbW * 0.012;
  const stickLen = thick ? computedVbW * 0.045 : computedVbW * 0.025;

  return (
    <svg
      ref={svgRef}
      viewBox={viewBox}
      className={`w-full ${className}`}
      style={{ height }}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        {/* Track glow filter */}
        <filter id="trackGlow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur in="SourceGraphic" stdDeviation={strokeW * 0.8} result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        {/* Driver dot glow */}
        <filter id="dotGlow" x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur in="SourceGraphic" stdDeviation={dotR * 0.6} />
        </filter>
        {/* Radial gradient for track surface */}
        <linearGradient id="trackSurface" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor={trackColor} stopOpacity="0.9" />
          <stop offset="100%" stopColor={trackColor} stopOpacity="0.7" />
        </linearGradient>
      </defs>

      {/* ── Layer 1: Track runoff / outer glow ── */}
      {thick && (
        <path
          d={trackPath}
          fill="none"
          stroke="rgba(255,255,255,0.03)"
          strokeWidth={strokeW * 3.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}

      {/* ── Layer 2: Asphalt surface (thick dark road) ── */}
      <path
        d={trackPath}
        fill="none"
        stroke={thick ? "#1a1a1a" : trackColor}
        strokeWidth={thick ? strokeW * 2.5 : strokeW * 2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={thick ? 1 : 0.3}
      />

      {/* ── Layer 3: Track edge lines (white kerb markings) ── */}
      {thick && (
        <>
          <path
            d={trackPath}
            fill="none"
            stroke="rgba(255,255,255,0.12)"
            strokeWidth={strokeW * 2.6}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d={trackPath}
            fill="none"
            stroke="#1a1a1a"
            strokeWidth={strokeW * 2.2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </>
      )}

      {/* ── Layer 4: Racing line (center line glow) ── */}
      <path
        d={trackPath}
        fill="none"
        stroke={thick ? "rgba(255,255,255,0.15)" : trackColor}
        strokeWidth={thick ? strokeW * 0.8 : strokeW}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={thick ? 1 : 0.7}
      />

      {/* ── DRS Zones — green highlighted sections ── */}
      {drsPaths.map((path, i) => (
        <path
          key={`drs-${i}`}
          d={path}
          fill="none"
          stroke="#22c55e"
          strokeWidth={strokeW * (thick ? 2.4 : 2)}
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity={0.4}
        />
      ))}

      {/* ── Colored track segments (replay trail, etc.) ── */}
      {segmentPaths.map((seg, i) => (
        <path
          key={i}
          d={seg.path}
          fill="none"
          stroke={seg.color}
          strokeWidth={strokeW * (thick ? 2.2 : 2)}
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity={0.85}
        />
      ))}

      {/* ── Start/Finish line ── */}
      {showStartFinish && sfLine && (
        <g>
          {/* Checkered pattern start/finish */}
          {thick ? (
            <>
              <line
                x1={sfLine.x1} y1={sfLine.y1}
                x2={sfLine.x2} y2={sfLine.y2}
                stroke="#ffffff"
                strokeWidth={strokeW * 2}
                opacity={0.9}
              />
              <line
                x1={sfLine.x1} y1={sfLine.y1}
                x2={sfLine.x2} y2={sfLine.y2}
                stroke="#000"
                strokeWidth={strokeW * 2}
                strokeDasharray={`${strokeW * 1.2} ${strokeW * 1.2}`}
                opacity={0.8}
              />
            </>
          ) : (
            <line
              x1={sfLine.x1} y1={sfLine.y1}
              x2={sfLine.x2} y2={sfLine.y2}
              stroke="#ffffff"
              strokeWidth={strokeW * 1.5}
              strokeDasharray={`${strokeW * 1.5} ${strokeW * 1.5}`}
            />
          )}
          <text
            x={(sfLine.x1 + sfLine.x2) / 2}
            y={(sfLine.y1 + sfLine.y2) / 2 - strokeW * (thick ? 4 : 3)}
            fill={thick ? "#fff" : "#888"}
            fontSize={cornerFontSize * (thick ? 0.9 : 0.8)}
            textAnchor="middle"
            fontFamily="monospace"
            fontWeight="bold"
            opacity={thick ? 0.7 : 1}
          >
            S/F
          </text>
        </g>
      )}

      {/* ── Corner labels ── */}
      {corners?.map((c) => {
        const [cx, cy] = toSVG(c.x, c.y);
        return (
          <g key={c.number}>
            {thick && (
              <circle cx={cx} cy={cy} r={cornerFontSize * 0.8} fill="rgba(0,0,0,0.6)" stroke="rgba(255,255,255,0.2)" strokeWidth={cornerFontSize * 0.06} />
            )}
            <text
              x={cx}
              y={cy}
              fill={thick ? "#ddd" : "#777"}
              fontSize={cornerFontSize * (thick ? 0.7 : 1)}
              textAnchor="middle"
              dominantBaseline="central"
              fontFamily="monospace"
              fontWeight="bold"
            >
              {c.number}
            </text>
          </g>
        );
      })}

      {/* ── Checkered flag at S/F ── */}
      {showCheckered && sfLine && (
        <g opacity={0.9}>
          {(() => {
            const cx = (sfLine.x1 + sfLine.x2) / 2;
            const cy = (sfLine.y1 + sfLine.y2) / 2;
            const s = computedVbW * (thick ? 0.007 : 0.005);
            const rects = [];
            for (let r = 0; r < 3; r++) {
              for (let c = 0; c < 4; c++) {
                rects.push(
                  <rect
                    key={`${r}-${c}`}
                    x={cx - s * 2 + c * s}
                    y={cy - s * 5 - r * s}
                    width={s}
                    height={s}
                    fill={(r + c) % 2 === 0 ? "#fff" : "#111"}
                  />
                );
              }
            }
            return (
              <>
                <rect
                  x={cx - s * 2} y={cy - s * 5 - s * 2}
                  width={s * 4} height={s * 3}
                  fill="none" stroke="#fff" strokeWidth={strokeW * 0.4}
                  rx={strokeW * 0.3}
                />
                {rects}
                <line
                  x1={cx} y1={cy - s * 5}
                  x2={cx} y2={cy}
                  stroke="#888" strokeWidth={strokeW * 0.6}
                />
              </>
            );
          })()}
        </g>
      )}

      {/* ── Driver dots — F1 broadcast style with stick + badge ── */}
      {drivers.map((drv) => {
        const [sx, sy] = toSVG(drv.x, drv.y);
        const isHighlight = drv.id === highlightDriver;
        const isDimmed = drv.dimmed;
        const isPitting = drv.pitting;
        const r = isHighlight ? highlightR : isDimmed ? dotR * 0.7 : dotR;
        const dotColor = isPitting ? "#eab308" : (drv.color || "#fff");
        const pillColor = isPitting ? "#eab308" : (drv.color || "#fff");
        const labelText = drv.label || drv.id;
        const pillW = labelText.length > 3 ? labelFontSize * (labelText.length * 0.7 + 0.8) : labelFontSize * 3.6;
        const pillH = labelFontSize * 1.7;
        // Stick top = where pill bottom sits, stick bottom = dot top
        const stickTop = -(r + stickLen + pillH);
        const pillY = stickTop;
        return (
          <g
            key={drv.id}
            data-driver-group={drv.id}
            transform={`translate(${sx},${sy})`}
            style={{ transition: "transform 0.2s linear" }}
            opacity={isDimmed ? 0.45 : 1}
          >
            {/* Glow blob */}
            {(isHighlight || thick) && !isDimmed && (
              <circle
                cx={0} cy={0} r={isHighlight ? r * 1.8 : r * 1.3}
                fill={dotColor}
                opacity={isHighlight ? 0.25 : 0.15}
                filter={thick ? "url(#dotGlow)" : undefined}
              />
            )}
            {/* Main dot */}
            <circle
              cx={0} cy={0} r={r}
              fill={dotColor}
            />
            {/* Stick / line from dot to label */}
            {thick ? (
              <g pointerEvents="none">
                {/* Vertical stick line */}
                <line
                  x1={0} y1={-r}
                  x2={0} y2={pillY + pillH}
                  stroke={pillColor}
                  strokeWidth={labelFontSize * 0.12}
                  opacity={isDimmed ? 0.4 : 0.8}
                />
                {/* Small circle at stick base (on dot) */}
                <circle
                  cx={0} cy={-r}
                  r={labelFontSize * 0.12}
                  fill={pillColor}
                  opacity={0.9}
                />
                {/* Label pill */}
                <rect
                  x={-pillW / 2}
                  y={pillY}
                  width={pillW}
                  height={pillH}
                  rx={labelFontSize * 0.35}
                  fill={pillColor}
                  stroke="rgba(0,0,0,0.4)"
                  strokeWidth={labelFontSize * 0.06}
                />
                {/* Label text */}
                <text
                  x={0}
                  y={pillY + pillH / 2}
                  fill="#fff"
                  fontSize={labelFontSize}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontFamily="monospace"
                  fontWeight="900"
                  letterSpacing={labelFontSize * 0.05}
                >
                  {labelText}
                </text>
              </g>
            ) : (
              <g pointerEvents="none">
                <line
                  x1={0} y1={-r}
                  x2={0} y2={-r - stickLen}
                  stroke={dotColor}
                  strokeWidth={labelFontSize * 0.1}
                  opacity={0.6}
                />
                <text
                  x={0}
                  y={-r - stickLen - labelFontSize * 0.3}
                  fill="#fff"
                  fontSize={labelFontSize}
                  textAnchor="middle"
                  fontFamily="monospace"
                  fontWeight="bold"
                >
                  {labelText}
                </text>
              </g>
            )}
          </g>
        );
      })}
    </svg>
  );
}
