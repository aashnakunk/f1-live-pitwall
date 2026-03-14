import { useRef, useEffect, useMemo } from "react";

/**
 * Shared SVG circuit map component.
 *
 * Props:
 *  - outline: { x: number[], y: number[] }  — track path coordinates
 *  - drivers: Array<{ id, x, y, color, label }>  — driver dot positions
 *  - highlightDriver?: string  — driver id to enlarge/glow
 *  - showStartFinish?: boolean
 *  - showCheckered?: boolean
 *  - trackColor?: string  — base track outline color (default "#333")
 *  - trackSegments?: Array<{ startIdx, endIdx, color }>  — colored track sections
 *  - corners?: Array<{ number, x, y }>  — corner labels
 *  - height?: number
 *  - className?: string
 */
export default function CircuitSVG({
  outline,
  drivers = [],
  highlightDriver,
  showStartFinish = false,
  showCheckered = false,
  trackColor = "#444",
  trackSegments,
  corners,
  height = 450,
  className = "",
}) {
  const svgRef = useRef(null);

  // Compute viewBox from outline bounds
  const { viewBox, toSVG, sfLine } = useMemo(() => {
    if (!outline?.x?.length || !outline?.y?.length) {
      return { viewBox: "0 0 100 100", toSVG: (x, y) => [50, 50], sfLine: null };
    }
    const xs = outline.x;
    const ys = outline.y;
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const pad = Math.max(maxX - minX, maxY - minY) * 0.06;
    const vbX = minX - pad;
    const vbY = minY - pad;
    const vbW = maxX - minX + pad * 2;
    const vbH = maxY - minY + pad * 2;

    // Y is flipped in SVG (y increases downward), but F1 coords may already be screen-oriented
    // We'll flip Y so the track looks correct (same as Plotly default)
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
      const sfLen = vbW * 0.02;
      sf = {
        x1: sx - perpX * sfLen, y1: sy - perpY * sfLen,
        x2: sx + perpX * sfLen, y2: sy + perpY * sfLen,
      };
    }

    return {
      viewBox: `${vbX} ${flipY(maxY) - pad} ${vbW} ${vbH}`,
      toSVG: convert,
      sfLine: sf,
    };
  }, [outline]);

  // Build track path
  const trackPath = useMemo(() => {
    if (!outline?.x?.length) return "";
    return outline.x
      .map((x, i) => {
        const [sx, sy] = toSVG(x, outline.y[i]);
        return `${i === 0 ? "M" : "L"}${sx},${sy}`;
      })
      .join(" ");
  }, [outline, toSVG]);

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

  // Smooth driver dot movement with CSS transitions
  useEffect(() => {
    if (!svgRef.current) return;
    drivers.forEach((drv) => {
      const el = svgRef.current.querySelector(`[data-driver="${drv.id}"]`);
      if (el) {
        const [sx, sy] = toSVG(drv.x, drv.y);
        el.setAttribute("cx", sx);
        el.setAttribute("cy", sy);
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

  // Determine track stroke width based on viewBox size
  const vbParts = viewBox.split(" ").map(Number);
  const vbW = vbParts[2] || 1000;
  const strokeW = vbW * 0.004;
  const dotR = vbW * 0.008;
  const highlightR = vbW * 0.013;
  const cornerFontSize = vbW * 0.012;

  return (
    <svg
      ref={svgRef}
      viewBox={viewBox}
      className={`w-full ${className}`}
      style={{ height }}
      preserveAspectRatio="xMidYMid meet"
    >
      {/* Track outline */}
      <path
        d={trackPath}
        fill="none"
        stroke={trackColor}
        strokeWidth={strokeW * 2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={0.3}
      />
      <path
        d={trackPath}
        fill="none"
        stroke={trackColor}
        strokeWidth={strokeW}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={0.7}
      />

      {/* Colored track segments */}
      {segmentPaths.map((seg, i) => (
        <path
          key={i}
          d={seg.path}
          fill="none"
          stroke={seg.color}
          strokeWidth={strokeW * 2}
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity={0.8}
        />
      ))}

      {/* Start/Finish line */}
      {showStartFinish && sfLine && (
        <g>
          <line
            x1={sfLine.x1} y1={sfLine.y1}
            x2={sfLine.x2} y2={sfLine.y2}
            stroke="#ffffff"
            strokeWidth={strokeW * 1.5}
            strokeDasharray={`${strokeW * 1.5} ${strokeW * 1.5}`}
          />
          <text
            x={(sfLine.x1 + sfLine.x2) / 2}
            y={(sfLine.y1 + sfLine.y2) / 2 - strokeW * 3}
            fill="#888"
            fontSize={cornerFontSize * 0.8}
            textAnchor="middle"
            fontFamily="monospace"
          >
            S/F
          </text>
        </g>
      )}

      {/* Corner labels */}
      {corners?.map((c) => {
        const [cx, cy] = toSVG(c.x, c.y);
        return (
          <text
            key={c.number}
            x={cx}
            y={cy}
            fill="#777"
            fontSize={cornerFontSize}
            textAnchor="middle"
            dominantBaseline="central"
            fontFamily="monospace"
            fontWeight="bold"
          >
            {c.number}
          </text>
        );
      })}

      {/* Checkered flag at S/F */}
      {showCheckered && sfLine && (
        <g opacity={0.9}>
          {(() => {
            const cx = (sfLine.x1 + sfLine.x2) / 2;
            const cy = (sfLine.y1 + sfLine.y2) / 2;
            const s = vbW * 0.005;
            const rects = [];
            for (let r = 0; r < 3; r++) {
              for (let c = 0; c < 4; c++) {
                rects.push(
                  <rect
                    key={`${r}-${c}`}
                    x={cx - s * 2 + c * s}
                    y={cy - s * 4 - r * s}
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
                  x={cx - s * 2} y={cy - s * 4 - s * 2}
                  width={s * 4} height={s * 3}
                  fill="none" stroke="#fff" strokeWidth={strokeW * 0.5}
                  rx={strokeW * 0.3}
                />
                {rects}
                <line
                  x1={cx} y1={cy - s * 4}
                  x2={cx} y2={cy}
                  stroke="#888" strokeWidth={strokeW * 0.8}
                />
              </>
            );
          })()}
          <animateTransform
            attributeName="transform"
            type="scale"
            from="0.8" to="1"
            dur="0.5s"
            fill="freeze"
          />
        </g>
      )}

      {/* Driver dots — CSS transitions for smooth movement */}
      {drivers.map((drv) => {
        const [sx, sy] = toSVG(drv.x, drv.y);
        const isHighlight = drv.id === highlightDriver;
        const r = isHighlight ? highlightR : dotR;
        return (
          <g key={drv.id}>
            {/* Glow */}
            {isHighlight && (
              <circle
                cx={sx} cy={sy} r={r * 1.8}
                fill={drv.color}
                opacity={0.15}
                data-driver={`${drv.id}-glow`}
                style={{ transition: "cx 0.15s linear, cy 0.15s linear" }}
              />
            )}
            {/* Dot */}
            <circle
              cx={sx} cy={sy} r={r}
              fill={drv.color || "#fff"}
              stroke="#000"
              strokeWidth={strokeW * 0.4}
              data-driver={drv.id}
              style={{ transition: "cx 0.15s linear, cy 0.15s linear" }}
            />
            {/* Label */}
            <text
              x={sx}
              y={sy - r * 1.6}
              fill="#fff"
              fontSize={cornerFontSize * 0.7}
              textAnchor="middle"
              fontFamily="monospace"
              fontWeight="bold"
              style={{ transition: "x 0.15s linear, y 0.15s linear" }}
              pointerEvents="none"
            >
              {drv.label || drv.id}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
