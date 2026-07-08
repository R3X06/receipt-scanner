import { useEffect, useRef, useState } from "react";
import { useAuth } from "./AuthContext";
import { getStatement } from "./api";
import { Card, CardContent } from "@/components/ui/card";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";

const MONTH_NAMES = [
  "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
  "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
];

function monthLabel(ym) {
  if (!ym || ym.length < 7) return "";
  const idx = parseInt(ym.slice(5, 7), 10) - 1;
  return `${MONTH_NAMES[idx] || ym} (MTD)`;
}

function fmt(n) {
  return (n ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Right-pads a label with dots up to `width` so amounts line up in the
// monospace font, regardless of how many digits the amount actually has.
function dottedLine(label, valueStr, width = 34) {
  const dots = Math.max(width - label.length - valueStr.length, 1);
  return label + ".".repeat(dots) + valueStr;
}

function buildLines(data) {
  const lines = [];
  lines.push({ text: `KALLA STATEMENT \u2014 ${monthLabel(data.month)}`, cls: "head" });
  lines.push({ text: "\u2500".repeat(32), cls: "rule" });
  lines.push({ text: dottedLine("MONTH-TO-DATE SPENDING", fmt(data.mtd_spending)), cls: "amt" });
  if (data.trailing_avg != null) {
    lines.push({ text: dottedLine("3-MO AVG", fmt(data.trailing_avg)), cls: "amt" });
  }
  lines.push({ text: "\u2500".repeat(32), cls: "rule" });

  if (data.delta_pct == null) {
    lines.push({ text: "NOT ENOUGH HISTORY YET", cls: "neg" });
  } else if (data.direction === "above") {
    lines.push({ text: `${Math.abs(data.delta_pct)}% ABOVE 3-MO AVG`, cls: "neg" });
  } else if (data.direction === "below") {
    lines.push({ text: `${Math.abs(data.delta_pct)}% BELOW 3-MO AVG`, cls: "pos" });
  } else {
    lines.push({ text: "ROUGHLY FLAT VS 3-MO AVG", cls: "amt" });
  }
  lines.push({ text: "\u2500".repeat(32), cls: "rule" });

  if (data.by_category && data.by_category.length > 0) {
    lines.push({ text: "BY CATEGORY", cls: "head" });
    data.by_category.slice(0, 6).forEach((c) => {
      lines.push({ text: dottedLine("  " + c.name.toUpperCase(), fmt(c.amount)), cls: "amt" });
    });
    lines.push({ text: "\u2500".repeat(32), cls: "rule" });
  }

  return lines;
}

export default function Statement() {
  const { token, user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const holderRef = useRef(null);
  const [animKey, setAnimKey] = useState(0);

  useEffect(() => {
    getStatement(token).then(setData).catch((e) => setError(e.message));
  }, [token]);

  useEffect(() => {
    if (!data || !holderRef.current) return;
    const holder = holderRef.current;
    holder.innerHTML = "";
    const lines = buildLines(data);
    const PER = 60;
    lines.forEach((l, i) => {
      const el = document.createElement("div");
      el.className = "kalla-stmt-line " + (l.cls || "");
      el.textContent = l.text;
      holder.appendChild(el);
      setTimeout(() => { el.style.opacity = "1"; }, i * PER);
    });
    const total = lines.length * PER;
    setTimeout(() => {
      const stamp = document.createElement("div");
      stamp.className = "kalla-stmt-stamp";
      stamp.textContent = "ISSUED \u2713";
      holder.appendChild(stamp);
      void stamp.offsetWidth;
      stamp.classList.add("show");
    }, total + 150);
  }, [data, animKey]);

  return (
    <Card className={`${GLASS} rounded-2xl`}>
      <CardContent className="space-y-3">
        <style>{`
          .kalla-stmt-line {
            font-family: ui-monospace, monospace;
            font-size: 11.5px;
            line-height: 1.7;
            white-space: pre;
            color: #8A97A6;
            opacity: 0;
            transition: opacity .1s linear;
          }
          .kalla-stmt-line.head { color: #E8EDF2; font-weight: 700; letter-spacing: 0.04em; }
          .kalla-stmt-line.rule { color: rgba(255,255,255,0.14); }
          .kalla-stmt-line.amt { color: #E8EDF2; }
          .kalla-stmt-line.neg { color: #c9a2f7; font-weight: 700; }
          .kalla-stmt-line.pos { color: #4ADE80; font-weight: 700; }
          .kalla-stmt-stamp {
            display: inline-block; margin-top: 8px;
            font-family: ui-monospace, monospace; font-size: 11.5px; font-weight: 700;
            letter-spacing: 0.1em; color: #4ADE80; border: 2px solid #4ADE80;
            border-radius: 4px; padding: 3px 10px;
            opacity: 0; transform: scale(2.2) rotate(-7deg);
            text-shadow: 0 0 10px rgba(74,222,128,0.5);
          }
          .kalla-stmt-stamp.show { animation: kalla-stmt-in .3s cubic-bezier(.2,1.4,.4,1) forwards; }
          @keyframes kalla-stmt-in {
            0% { opacity: 0; transform: scale(2.2) rotate(-7deg); }
            60% { opacity: 1; transform: scale(0.92) rotate(-7deg); }
            100% { opacity: 1; transform: scale(1) rotate(-7deg); }
          }
        `}</style>

        <div className="flex items-center justify-between">
          <h2 className="text-base font-medium">Statement</h2>
          <button
            type="button"
            onClick={() => setAnimKey((k) => k + 1)}
            className="font-mono text-[10px] text-muted-foreground hover:text-foreground"
          >
            ↻ reprint
          </button>
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}
        {!data && !error && <p className="text-xs text-muted-foreground">Loading…</p>}

        <div ref={holderRef} />
      </CardContent>
    </Card>
  );
}