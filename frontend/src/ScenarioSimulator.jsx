import { useState } from "react";
import { useAuth } from "./AuthContext";
import { simulateScenario } from "./api";
import { CATEGORIES } from "./constants";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { X, Plus } from "lucide-react";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";
const GRAD_ID = "kalla-sim-grad-v";
const DOT_ID = "kalla-sim-dot-v";

const ADJ_LABELS = {
  category_pct: "Cut a category",
  income_delta: "Add income",
  goal_coverage_months: "Change goal coverage",
};

// ---- one adjustment row: shape depends on the selected type ----
function AdjustmentRow({ adj, goals, onChange, onRemove }) {
  const selectedGoal = goals.find((g) => g.id === adj.goal_id);
  const goalIsEmergency = !!selectedGoal?.is_emergency;

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-3">
      <div className="flex items-center justify-between">
        <Select value={adj.type} onValueChange={(v) => onChange({ type: v })}>
          <SelectTrigger className="h-8 w-48 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            {Object.entries(ADJ_LABELS).map(([v, label]) => (
              <SelectItem key={v} value={v}>{label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <button type="button" onClick={onRemove} className="text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>

      {adj.type === "category_pct" && (
        <div className="flex items-center gap-2">
          <Select value={adj.category_name || ""} onValueChange={(v) => onChange({ category_name: v })}>
            <SelectTrigger className="h-8 flex-1 text-xs"><SelectValue placeholder="Category" /></SelectTrigger>
            <SelectContent>
              {CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
          <Input
            type="number" placeholder="-20"
            value={adj.pct ?? ""} onChange={(e) => onChange({ pct: e.target.value === "" ? "" : Number(e.target.value) })}
            className="h-8 w-20 text-xs"
          />
          <span className="text-xs text-muted-foreground">%</span>
        </div>
      )}

      {adj.type === "income_delta" && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Extra income / month</span>
          <Input
            type="number" placeholder="500"
            value={adj.amount ?? ""} onChange={(e) => onChange({ amount: e.target.value === "" ? "" : Number(e.target.value) })}
            className="h-8 w-24 text-xs"
          />
        </div>
      )}

      {adj.type === "goal_coverage_months" && (
        <div className="flex flex-col gap-2">
          <Select value={adj.goal_id || ""} onValueChange={(v) => onChange({ goal_id: v })}>
            <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="Goal" /></SelectTrigger>
            <SelectContent>
              {goals.map((g) => <SelectItem key={g.id} value={g.id}>{g.name}</SelectItem>)}
            </SelectContent>
          </Select>
          {adj.goal_id && !goalIsEmergency && (
            <p className="text-[11px] text-amber-400/90">
              Coverage months only affects emergency-type goals — this won't change {selectedGoal?.name}'s target.
            </p>
          )}
          {adj.goal_id && goalIsEmergency && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Coverage (months)</span>
              <Input
                type="number" placeholder="8"
                value={adj.months ?? ""} onChange={(e) => onChange({ months: e.target.value === "" ? "" : Number(e.target.value) })}
                className="h-8 w-20 text-xs"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---- chart: savings_balance across simulated months, same visual language as AllocationReceipt ----
function TimelineChart({ timeline, currency }) {
  if (!timeline?.length) return null;
  const w = 320, h = 160, padL = 44, padB = 20, padT = 10, padR = 10;
  const plotW = w - padL - padR, plotH = h - padT - padB;
  const values = timeline.map((t) => t.savings_balance);
  const max = Math.max(...values, 1);
  const min = Math.min(...values, 0);
  const range = max - min || 1;

  const points = timeline.map((t, i) => {
    const x = padL + (i / (timeline.length - 1 || 1)) * plotW;
    const y = padT + plotH - ((t.savings_balance - min) / range) * plotH;
    return `${x},${y}`;
  });

  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h}>
      <defs>
        <linearGradient id={GRAD_ID} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#7C3AED" />
          <stop offset="100%" stopColor="#D8B4FE" />
        </linearGradient>
        <pattern id={DOT_ID} width="4" height="4" patternUnits="userSpaceOnUse">
          <circle cx="1" cy="1" r="0.6" fill="rgba(255,255,255,0.15)" />
        </pattern>
      </defs>
      <rect x={padL} y={padT} width={plotW} height={plotH} fill={`url(#${DOT_ID})`} opacity="0.5" />
      <polyline points={points.join(" ")} fill="none" stroke={`url(#${GRAD_ID})`} strokeWidth="2" />
      <text x={padL} y={h - 4} fill="#8A97A6" fontSize="9" fontFamily="ui-monospace, monospace">
        Month 1
      </text>
      <text x={w - padR} y={h - 4} textAnchor="end" fill="#8A97A6" fontSize="9" fontFamily="ui-monospace, monospace">
        Month {timeline.length}
      </text>
      <text x={padL} y={padT + 8} fill="#E8EDF2" fontSize="9.5" fontWeight="700" fontFamily="ui-monospace, monospace">
        {currency} {max.toLocaleString(undefined, { maximumFractionDigits: 0 })}
      </text>
    </svg>
  );
}

/**
 * Read-only "what if" projection. Never writes anything - just calls
 * POST /scenario/simulate and renders the result. Props: { goals, currency, strategy }
 */
export default function ScenarioSimulator({ goals = [], currency = "SGD", strategy: defaultStrategy }) {
  const { token } = useAuth();
  const [months, setMonths] = useState("12");
  const [adjustments, setAdjustments] = useState([]);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  function addAdjustment() {
    setAdjustments((prev) => [...prev, { type: "category_pct" }]);
  }
  function updateAdjustment(i, patch) {
    setAdjustments((prev) => prev.map((a, idx) => (idx === i ? { ...a, ...patch } : a)));
  }
  function removeAdjustment(i) {
    setAdjustments((prev) => prev.filter((_, idx) => idx !== i));
  }

  function cleanPayloadAdjustments() {
    // drop incomplete rows and the no-op case (non-emergency goal + coverage_months)
    return adjustments
      .filter((a) => {
        if (a.type === "category_pct") return a.category_name && a.pct !== "" && a.pct != null;
        if (a.type === "income_delta") return a.amount !== "" && a.amount != null;
        if (a.type === "goal_coverage_months") {
          const g = goals.find((x) => x.id === a.goal_id);
          return g?.is_emergency && a.months !== "" && a.months != null;
        }
        return false;
      })
      .map((a) => {
        if (a.type === "category_pct") return { type: a.type, category_name: a.category_name, pct: Number(a.pct) };
        if (a.type === "income_delta") return { type: a.type, amount: Number(a.amount) };
        return { type: a.type, goal_id: a.goal_id, months: Number(a.months) };
      });
  }

  async function run() {
    setBusy(true); setErr("");
    try {
      const clampedMonths = Math.max(1, Math.min(60, Number(months) || 12));
      const payload = { months: clampedMonths, adjustments: cleanPayloadAdjustments(), strategy: defaultStrategy };
      const data = await simulateScenario(token, payload);
      setResult(data);
    } catch (e) {
      setErr(e.message || "Simulation failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Project forward</span>
        <Input
          type="number" value={months} min={1} max={60}
          onChange={(e) => setMonths(e.target.value)}
          className="h-8 w-16 text-xs"
        />
        <span className="text-xs text-muted-foreground">months</span>
      </div>

      <div className="space-y-2">
        {adjustments.map((adj, i) => (
          <AdjustmentRow
            key={i} adj={adj} goals={goals}
            onChange={(patch) => updateAdjustment(i, patch)}
            onRemove={() => removeAdjustment(i)}
          />
        ))}
      </div>

      <button
        type="button" onClick={addAdjustment}
        className="flex w-full items-center justify-center gap-1 rounded-lg border border-dashed border-white/15 py-2 text-xs text-muted-foreground hover:bg-white/[0.04]"
      >
        <Plus className="h-3.5 w-3.5" /> Add adjustment
      </button>

      <Button onClick={run} disabled={busy} className="w-full">
        {busy ? "Simulating…" : "Run simulation"}
      </Button>

      {err && <p className="text-xs text-destructive">{err}</p>}

      {result && (
        <Card className={`${GLASS} rounded-2xl`}>
          <CardContent className="space-y-3 py-4">
            <TimelineChart timeline={result.timeline} currency={currency} />

            <div className="space-y-1.5">
              {result.timeline[0]?.goals.map((g) => {
                const reachedMonth = result.goal_reached_month[g.id];
                return (
                  <div key={g.id} className="flex items-center justify-between text-xs">
                    <span>{g.name}</span>
                    <span className="text-muted-foreground">
                      {reachedMonth ? `Reached month ${reachedMonth}` : `Not reached in ${months} months`}
                    </span>
                  </div>
                );
              })}
            </div>

            <p className="text-[11px] text-muted-foreground">{result.assumptions.note}</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}