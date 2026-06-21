import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { CURRENCIES } from "./constants";
import { getAccounts, createGoal, deleteGoal, allocateSavings, withdrawSavings } from "./api";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Plus, Trash2, Target } from "lucide-react";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";

export default function Goals() {
  const { token, user } = useAuth();
  const base = user?.primary_currency || "SGD";
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try { setData(await getAccounts(token)); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, [token]);

  const goals = (data?.accounts || []).filter((a) => a.type === "goal");
  const totalSaved = goals.reduce((s, g) => s + (g.balance || 0), 0);

  return (
    <Card className={`${GLASS} rounded-2xl`}>
      <CardContent className="space-y-4">
        <div>
          <h2 className="text-base font-medium">Savings &amp; goals</h2>
          <p className="text-sm text-muted-foreground">Money set aside, split across what you're saving for.</p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
            <p className="text-xs text-muted-foreground">In savings</p>
            <p className="text-xl font-semibold tabular-nums">{base} {totalSaved.toFixed(2)}</p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
            <p className="text-xs text-muted-foreground">Net worth</p>
            <p className="text-xl font-semibold tabular-nums">{base} {(data?.net_worth ?? 0).toFixed(2)}</p>
          </div>
        </div>

        {loading ? (
          <p className="py-4 text-center text-sm text-muted-foreground">Loading...</p>
        ) : goals.length === 0 ? (
          <p className="py-2 text-sm text-muted-foreground">No goals yet — create one below.</p>
        ) : (
          <div className="space-y-2">
            {goals.map((g) => <GoalCard key={g.id} goal={g} base={base} token={token} onChange={load} />)}
          </div>
        )}

        <AddMoney goals={goals} base={base} token={token} user={user} onDone={load} />
        <NewGoal token={token} onDone={load} />
        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  );
}

function GoalCard({ goal, base, token, onChange }) {
  const [withdrawing, setWithdrawing] = useState(false);
  const [amt, setAmt] = useState("");
  const [busy, setBusy] = useState(false);
  const pct = goal.progress != null ? Math.round(goal.progress * 100) : null;

  async function doWithdraw() {
    const n = parseFloat(amt);
    if (isNaN(n) || n <= 0) return;
    setBusy(true);
    try {
      await withdrawSavings(token, { goal_id: goal.id, amount: n, to: "spending" });
      setAmt(""); setWithdrawing(false); onChange();
    } catch (e) { alert(e.message); }
    finally { setBusy(false); }
  }

  async function remove() {
    try { await deleteGoal(token, goal.id); onChange(); }
    catch (e) { alert(e.message); }
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 font-medium">
            {goal.is_emergency && <Target className="h-3.5 w-3.5 text-primary" />}
            {goal.name}
          </p>
          <p className="text-sm tabular-nums text-muted-foreground">
            {base} {goal.balance.toFixed(2)}{goal.target_amount ? ` / ${goal.target_amount.toFixed(2)}` : ""}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button onClick={() => setWithdrawing((w) => !w)} className="text-xs text-muted-foreground hover:text-foreground">Withdraw</button>
          <button onClick={remove} aria-label="Delete goal" className="text-muted-foreground hover:text-destructive">
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {pct != null && (
        <div className="mt-2">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
            <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(pct, 100)}%` }} />
          </div>
          <div className="mt-1 flex justify-between text-xs text-muted-foreground">
            <span>{pct}%</span>
            {goal.required_per_month != null && goal.months_left != null && (
              <span>{goal.months_left} mo left · need {base} {goal.required_per_month.toFixed(0)}/mo</span>
            )}
          </div>
        </div>
      )}

      {withdrawing && (
        <div className="mt-2 flex gap-2">
          <Input type="number" step="0.01" min="0" placeholder={`Amount (${base})`} value={amt} onChange={(e) => setAmt(e.target.value)} className="h-8" />
          <Button size="sm" onClick={doWithdraw} disabled={busy} className="h-8">Take out</Button>
        </div>
      )}
    </div>
  );
}

function AddMoney({ goals, base, token, user, onDone }) {
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState(base);
  const [source, setSource] = useState("surplus");
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  if (!goals.length) return null;

  const options = goals.map((g) => ({ value: "goal:" + g.id, label: g.name }));
  if (user?.feature_priority_waterfall && goals.length > 1) options.push({ value: "waterfall", label: "Auto — fill by priority" });
  if (user?.feature_proportional_allocation && goals.length > 1) options.push({ value: "proportional", label: "Auto — by deadline" });

  async function submit() {
    const n = parseFloat(amount);
    if (isNaN(n) || n <= 0) return setErr("Enter an amount.");
    if (!target) return setErr("Choose where it goes.");
    setBusy(true);
    setErr("");
    try {
      const payload = target.startsWith("goal:")
        ? { amount: n, currency, source, strategy: "manual", splits: [{ goal_id: target.slice(5), amount: n }] }
        : { amount: n, currency, source, strategy: target };
      await allocateSavings(token, payload);
      setAmount(""); setTarget(""); onDone();
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="space-y-3 rounded-xl border border-white/10 bg-white/[0.03] p-3">
      <p className="text-sm font-medium">Add money to savings</p>
      <div className="grid grid-cols-3 gap-2">
        <Input className="col-span-2" type="number" step="0.01" min="0" placeholder="Amount" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <Select value={currency} onValueChange={setCurrency}>
          <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
          <SelectContent>{CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <div className="flex gap-1 rounded-full border border-white/10 p-1">
        <button onClick={() => setSource("surplus")} className={`flex-1 rounded-full px-2 py-1 text-xs ${source === "surplus" ? "bg-primary font-medium text-primary-foreground" : "text-muted-foreground"}`}>From surplus</button>
        <button onClick={() => setSource("external")} className={`flex-1 rounded-full px-2 py-1 text-xs ${source === "external" ? "bg-primary font-medium text-primary-foreground" : "text-muted-foreground"}`}>External</button>
      </div>
      <Select value={target} onValueChange={setTarget}>
        <SelectTrigger className="w-full"><SelectValue placeholder="Allocate to…" /></SelectTrigger>
        <SelectContent>{options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
      </Select>
      {err && <p className="text-xs text-destructive">{err}</p>}
      <Button onClick={submit} disabled={busy} className="w-full font-medium">{busy ? "Adding…" : "Add to savings"}</Button>
    </div>
  );
}

function NewGoal({ token, onDone }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", target_amount: "", deadline: "", is_emergency: false });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function submit() {
    if (!form.name.trim()) return setErr("Name your goal.");
    setBusy(true);
    setErr("");
    try {
      await createGoal(token, {
        name: form.name.trim(),
        target_amount: form.target_amount ? parseFloat(form.target_amount) : null,
        deadline: form.deadline || null,
        is_emergency: form.is_emergency,
      });
      setForm({ name: "", target_amount: "", deadline: "", is_emergency: false });
      setOpen(false); onDone();
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  if (!open) {
    return (
      <Button variant="outline" onClick={() => setOpen(true)} className="w-full border-white/15 bg-transparent hover:bg-white/5">
        <Plus className="mr-1.5 h-4 w-4" /> New goal
      </Button>
    );
  }

  return (
    <div className="space-y-3 rounded-xl border border-white/10 bg-white/[0.03] p-3">
      <p className="text-sm font-medium">New goal</p>
      <Input placeholder="e.g. Camera, Bali trip, Emergency fund" value={form.name} onChange={(e) => set("name", e.target.value)} />
      <div className="grid grid-cols-2 gap-2">
        <Input type="number" step="0.01" min="0" placeholder="Target (optional)" value={form.target_amount} onChange={(e) => set("target_amount", e.target.value)} />
        <Input type="date" value={form.deadline} onChange={(e) => set("deadline", e.target.value)} className="[&::-webkit-calendar-picker-indicator]:invert" />
      </div>
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        <input type="checkbox" checked={form.is_emergency} onChange={(e) => set("is_emergency", e.target.checked)} />
        This is my emergency fund
      </label>
      {err && <p className="text-xs text-destructive">{err}</p>}
      <div className="flex gap-2">
        <Button variant="outline" onClick={() => { setOpen(false); setErr(""); }} className="border-white/15 bg-transparent hover:bg-white/5">Cancel</Button>
        <Button onClick={submit} disabled={busy} className="flex-1 font-medium">{busy ? "Creating…" : "Create goal"}</Button>
      </div>
    </div>
  );
}