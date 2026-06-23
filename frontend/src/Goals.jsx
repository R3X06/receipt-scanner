import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { getGoals, createGoalConfig, updateGoalConfig, deleteGoalConfig } from "./api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Trash2, Plus, Pencil } from "lucide-react";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";
const pill = (active) =>
  `flex-1 rounded-full px-2 py-1 text-xs transition ${active ? "bg-primary font-medium text-primary-foreground" : "text-muted-foreground"}`;

function GoalForm({ initial, onSubmit, onCancel, busy, defaultRank }) {
  const [name, setName] = useState(initial?.name || "");
  const [fundingType, setFundingType] = useState(initial?.funding_type || "algorithmic");
  const [forcedAmount, setForcedAmount] = useState(initial?.forced_amount != null ? String(initial.forced_amount) : "");
  const [target, setTarget] = useState(initial?.target_amount != null ? String(initial.target_amount) : "");
  const [deadline, setDeadline] = useState(initial?.deadline || "");
  const [priority, setPriority] = useState(initial?.priority != null ? String(initial.priority) : String(defaultRank || 1));
  const [isEmergency, setIsEmergency] = useState(!!initial?.is_emergency);
  const [err, setErr] = useState("");

  function submit() {
    if (!name.trim()) return setErr("Name your goal.");
    if (fundingType === "forced") {
      const f = parseFloat(forcedAmount);
      if (isNaN(f) || f <= 0) return setErr("Forced goals need a reserved amount.");
    }
    setErr("");
    onSubmit({
      name: name.trim(),
      funding_type: fundingType,
      forced_amount: fundingType === "forced" ? parseFloat(forcedAmount) : null,
      target_amount: target ? parseFloat(target) : null,
      deadline: deadline || null,
      priority: Math.max(1, parseInt(priority, 10) || 1),
      is_emergency: isEmergency,
    });
  }

  return (
    <div className="space-y-3 rounded-xl border border-white/10 bg-white/[0.03] p-3">
      <Input placeholder="Goal name (e.g. Camera, Emergency)" value={name} onChange={(e) => setName(e.target.value)} />
      <div className="flex gap-1 rounded-full border border-white/10 p-1">
        <button type="button" onClick={() => setFundingType("algorithmic")} className={pill(fundingType === "algorithmic")}>Auto (shares the rest)</button>
        <button type="button" onClick={() => setFundingType("forced")} className={pill(fundingType === "forced")}>Forced (reserve fixed)</button>
      </div>
      {fundingType === "forced" && (
        <Input type="number" step="0.01" min="0" placeholder="Reserved amount" value={forcedAmount} onChange={(e) => setForcedAmount(e.target.value)} />
      )}
      <div className="grid grid-cols-2 gap-2">
        <Input type="number" step="0.01" min="0" placeholder="Target (optional)" value={target} onChange={(e) => setTarget(e.target.value)} />
        <Input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} className="[&::-webkit-calendar-picker-indicator]:invert" />
      </div>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Rank</span>
          <Input type="number" min="1" step="1" className="w-16" value={priority} onChange={(e) => setPriority(e.target.value)} />
        </div>
        <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
          <input type="checkbox" checked={isEmergency} onChange={(e) => setIsEmergency(e.target.checked)} className="h-3.5 w-3.5 rounded border-white/20 bg-white/[0.04] accent-primary" />
          Emergency fund
        </label>
      </div>
      {err && <p className="text-xs text-destructive">{err}</p>}
      <div className="flex gap-2">
        <Button onClick={submit} disabled={busy} className="flex-1 font-medium">{busy ? "Saving…" : "Save goal"}</Button>
        {onCancel && <Button type="button" variant="outline" onClick={onCancel} className="border-white/10">Cancel</Button>}
      </div>
    </div>
  );
}

export default function Goals({ onChange }) {
  const { token, user } = useAuth();
  const base = user?.primary_currency || "SGD";
  const [data, setData] = useState(null);
  const [adding, setAdding] = useState(false);
  const [editId, setEditId] = useState(null);
  const [busy, setBusy] = useState(false);

  function load() { getGoals(token).then(setData).catch(() => {}); }
  useEffect(() => { load(); }, [token]);

  const fmt = (n) =>
    `${base} ${(n ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  async function create(payload) {
    setBusy(true);
    try { await createGoalConfig(token, payload); setAdding(false); load(); onChange?.(); }
    finally { setBusy(false); }
  }
  async function update(id, payload) {
    setBusy(true);
    try { await updateGoalConfig(token, id, payload); setEditId(null); load(); onChange?.(); }
    finally { setBusy(false); }
  }
  async function remove(id) {
    setBusy(true);
    try { await deleteGoalConfig(token, id); load(); onChange?.(); }
    finally { setBusy(false); }
  }

  const goals = data?.goals || [];

  return (
    <Card className={`${GLASS} rounded-2xl`}>
      <CardContent className="space-y-4">
        <div>
          <h2 className="text-base font-medium">Goals</h2>
          <p className="text-sm text-muted-foreground">Optional earmarks over your savings — they hold no money of their own.</p>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3 text-sm">
          <div className="flex justify-between"><span className="text-muted-foreground">Savings</span><span className="tabular-nums">{fmt(data?.savings_balance)}</span></div>
          <div className="mt-1 flex justify-between text-xs text-muted-foreground"><span>Unallocated</span><span className="tabular-nums">{fmt(data?.unallocated)}</span></div>
        </div>

        <div className="space-y-2">
          {goals.length === 0 && !adding && (
            <p className="text-sm text-muted-foreground">No goals yet. Savings sits unallocated until you add one.</p>
          )}
          {goals.map((g) =>
            editId === g.id ? (
              <GoalForm key={g.id} initial={g} busy={busy} onSubmit={(p) => update(g.id, p)} onCancel={() => setEditId(null)} />
            ) : (
              <div key={g.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium truncate">{g.name}</span>
                      {g.is_emergency && <span className="rounded-full border border-primary/30 bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">Emergency</span>}
                      <span className="rounded-full border border-white/10 px-1.5 py-0.5 text-[10px] text-muted-foreground">{g.funding_type === "forced" ? `Forced ${fmt(g.forced_amount)}` : "Auto"}</span>
                    </div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      Holding <span className="tabular-nums text-foreground">{fmt(g.allocated)}</span>
                      {g.target_amount ? <> of {fmt(g.target_amount)}</> : null}
                      {typeof g.priority === "number" ? <> · rank {g.priority}</> : null}
                    </div>
                    {g.target_amount > 0 && (
                      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
                        <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min((g.progress || 0) * 100, 100)}%` }} />
                      </div>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <button type="button" onClick={() => setEditId(g.id)} className="rounded-lg p-1.5 text-muted-foreground hover:bg-white/5 hover:text-foreground"><Pencil className="h-4 w-4" /></button>
                    <button type="button" onClick={() => remove(g.id)} className="rounded-lg p-1.5 text-muted-foreground hover:bg-white/5 hover:text-destructive"><Trash2 className="h-4 w-4" /></button>
                  </div>
                </div>
              </div>
            )
          )}
        </div>

        {adding ? (
          <GoalForm busy={busy} defaultRank={goals.length + 1} onSubmit={create} onCancel={() => setAdding(false)} />
        ) : (
          <Button type="button" variant="outline" onClick={() => setAdding(true)} className="w-full border-white/10">
            <Plus className="mr-1.5 h-4 w-4" /> New goal
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
