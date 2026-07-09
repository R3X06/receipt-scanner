import { useMemo } from "react";
import { Card, CardContent } from "@/components/ui/card";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";
const HATCH_ID = "kalla-reserve-hatch-v";
const DOT_ID = "kalla-goal-dot-v";
const GRAD_ID = "kalla-tape-grad-v";

// Same read as before: reserve portion of each goal (Pass 1, senior-first)
// vs. remainder (Pass 2, split by strategy). No new endpoint — just what
// SavingsCard already has via { reserve, allocated } per goal.
function buildSegments(goals, unallocated) {
  const reserveTotal = goals.reduce(
    (s, g) => s + Math.min(g.reserve || 0, g.allocated || 0),
    0
  );
  const segments = [];
  if (reserveTotal > 0.005) {
    segments.push({ key: "reserve", name: "RESERVE", value: reserveTotal, hatch: true });
  }
  goals.forEach((g) => {
    const reservePart = Math.min(g.reserve || 0, g.allocated || 0);
    const remainder = Math.max((g.allocated || 0) - reservePart, 0);
    if (remainder > 0.005) {
      segments.push({ key: g.id, name: (g.name || "").toUpperCase(), value: remainder, hatch: false });
    }
  });
  if (unallocated > 0.005) {
    segments.push({ key: "unalloc", name: "UNALLOCATED", value: unallocated, hatch: false, muted: true });
  }
  return segments;
}

/**
 * Vertical stacked-column distribution. Reserve sits at the base (it funds
 * first, senior-first — everything else builds on top of it); goal
 * remainders stack upward in allocation order. Meant to live in its own
 * dialog (opened from a "View distribution" button in SavingsCard), not
 * inline in the card.
 * Props: { unallocated, goals, currency }
 */
export default function AllocationReceipt({ unallocated, goals, currency = "SGD" }) {
  const segments = useMemo(
    () => buildSegments(goals || [], unallocated || 0),
    [goals, unallocated]
  );
  const total = segments.reduce((s, seg) => s + seg.value, 0);

  if (total <= 0.005) {
    return (
      <Card className={`${GLASS} rounded-2xl`}>
        <CardContent className="space-y-2 py-10 text-center">
          <h2 className="text-base font-medium">Distribution</h2>
          <p className="text-xs text-muted-foreground">
            No savings allocated yet. Add a goal and deposit into savings to see the breakdown here.
          </p>
        </CardContent>
      </Card>
    );
  }
  const colX = 40;
  const colW = 70;
  const topY = 10;
  const bottomY = 300;
  const fullH = bottomY - topY;
  const perfGap = 3;
  const canvasW = 300;

  let cursor = bottomY; // stack upward from the baseline
  const positioned = segments.map((seg) => {
    const h = (seg.value / total) * fullH - perfGap;
    const segTop = cursor - h;
    const item = { ...seg, top: segTop, h, bottom: cursor };
    cursor = segTop - perfGap;
    return item;
  });

  return (
    <Card className={`${GLASS} rounded-2xl`}>
      <CardContent className="space-y-3">
        <style>{`
          @keyframes kalla-vtape-in { to { opacity: 1; transform: scaleY(1); } }
          @keyframes kalla-vtape-fade { to { opacity: 1; } }
        `}</style>

        <div className="flex items-center justify-between">
          <h2 className="text-base font-medium">Distribution</h2>
        </div>

        <p className="text-[11px] text-muted-foreground">
          Segment height = share of your {currency} balance. Reserve funds first, at the base.
        </p>

        <div className="flex justify-center">
          <svg viewBox={`0 0 ${canvasW} 340`} width={canvasW} height={340}>
            <defs>
              <pattern id={DOT_ID} width="4" height="4" patternUnits="userSpaceOnUse">
                <circle cx="1" cy="1" r="0.9" fill="#0B0F14" />
              </pattern>
              <pattern id={HATCH_ID} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width="2" height="5" fill="#0B0F14" opacity="0.55" />
              </pattern>
              <linearGradient id={GRAD_ID} x1="0" y1="1" x2="0" y2="0">
                <stop offset="0%" stopColor="#7C3AED" />
                <stop offset="100%" stopColor="#D8B4FE" />
              </linearGradient>
            </defs>

            {positioned.map((seg, i) => (
              <g
                key={seg.key}
                style={{
                  opacity: 0,
                  transform: "scaleY(0)",
                  transformOrigin: `${colX}px ${seg.bottom}px`,
                  animation: `kalla-vtape-in .5s cubic-bezier(.19,1,.22,1) ${i * 0.16}s forwards`,
                }}
              >
                <rect
                  x={colX} y={seg.top} width={colW} height={seg.h}
                  fill={seg.muted ? "rgba(255,255,255,0.08)" : `url(#${GRAD_ID})`}
                />
                <rect
                  x={colX} y={seg.top} width={colW} height={seg.h}
                  fill={seg.hatch ? `url(#${HATCH_ID})` : seg.muted ? "none" : `url(#${DOT_ID})`}
                  opacity={seg.hatch ? 0.5 : 0.35}
                />
                <rect x={colX} y={seg.top} width={colW} height={seg.h} fill="none" stroke="rgba(255,255,255,0.18)" />
              </g>
            ))}

            {positioned.slice(0, -1).map((seg) => (
              <line
                key={"perf-" + seg.key}
                x1={colX - 3} x2={colX + colW + 3}
                y1={seg.top - perfGap / 2} y2={seg.top - perfGap / 2}
                stroke="#0B0F14" strokeWidth="3" strokeDasharray="2.2,2.2"
              />
            ))}

            {positioned.map((seg, i) => {
              const midY = (seg.top + seg.bottom) / 2;
              return (
                <g
                  key={"label-" + seg.key}
                  style={{ opacity: 0, animation: `kalla-vtape-fade .3s ease ${i * 0.16 + 0.3}s forwards` }}
                >
                  <line x1={colX + colW} x2={colX + colW + 10} y1={midY} y2={midY} stroke="rgba(255,255,255,0.2)" />
                  <text x={colX + colW + 14} y={midY - 2} fill="#8A97A6" fontSize="9.5" fontFamily="ui-monospace, monospace">
                    {seg.name}
                  </text>
                  <text x={colX + colW + 14} y={midY + 11} fill="#E8EDF2" fontSize="10.5" fontWeight="700" fontFamily="ui-monospace, monospace">
                    {seg.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </text>
                  <text
                    x={colX + colW / 2} y={midY + 3} textAnchor="middle"
                    fill="#0B0F14" fontSize="10" fontWeight="700" fontFamily="ui-monospace, monospace"
                  >
                    {Math.round((seg.value / total) * 100)}%
                  </text>
                </g>
              );
            })}

            <text x={colX + colW / 2} y={bottomY + 18} textAnchor="middle" fill="#8A97A6" fontSize="9.5" fontFamily="ui-monospace, monospace">
              {currency} {total.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </text>
          </svg>
        </div>
      </CardContent>
    </Card>
  );
}
