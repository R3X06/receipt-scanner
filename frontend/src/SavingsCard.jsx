import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { CURRENCIES } from "./constants";
import {
  getGoals, getEntries, savingsDeposit, savingsWithdraw,
  createGoalConfig, updateGoalConfig, deleteGoalConfig, reorderGoals,
  updateMe, deleteEntry,
} from "./api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Pencil, Trash2, ChevronDown, GripVertical, PiggyBank } from "lucide-react";
import { DndContext, closestCenter, PointerSensor, KeyboardSensor, useSensor, useSensors } from "@dnd-kit/core";
import { SortableContext, useSortable, arrayMove, verticalListSortingStrategy, sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";
const pill = (active) =>
  `flex-1 rounded-full px-2 py-1 text-xs transition ${active ? "bg-primary font-medium text-primary-foreground" : "text-muted-foreground"}`;

const STRATEGY_LABELS = {
  proportional: "Proportional",
  waterfall: "Waterfall",
  even: "Even",
};

function fmtWith(base) {
  return (n) => `${base} ${(n ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// ---- add / edit a goal (reserve floor, no funding-type, no keyed rank) ----
function GoalForm({ initial, onSubmit, onCancel, busy }) {
  const [name, setName] = useState(initial?.name || "");
  const [target, setTarget] = useState(initial?.target_amount != null ? String(initial.target_amount) : "");
  const [reserve, setReserve] = useState(initial?.reserve ? String(initial.reserve) : "");
  const [deadline, setDeadline] = useState(initial?.deadline || "");
  const [isEmergency, setIsEmergency] = useState(!!initial?.is_emergency);
  const [err, setErr] = useState("");

  function submit() {
    if (!name.trim()) return setErr("Name your goal.");
    const t = target ? parseFloat(target) : null;
    const r = reserve ? parseFloat(reserve) : null;
    if (r != null && (isNaN(r) || r < 0)) return setErr("Reserve must be a positive amount.");
    if (r != null && t != null && r > t) return setErr("Reserve can't exceed the target.");
    setErr("");
    onSubmit({
      name: name.trim(),
      target_amount: t,
      reserve: r,
      deadline: deadline || null,
      is_emergency: isEmergency,
      priority: initial?.priority || 0,
    });
  }

  return (
    <div className="space-y-3 rounded-xl border border-white/10 bg-white/[0.03] p-3">
      <Input placeholder="Goal name (e.g. Camera, Emergency)" value={name} onChange={(e) => setName(e.target.value)} />
      <div className="grid grid-cols-2 gap-2">
        <Input type="number" step="0.01" min="0" placeholder="Target (optional)" value={target} onChange={(e) => setTarget(e.target.value)} />
        <Input type="number" step="0.01" min="0" placeholder="Reserve (optional)" value={reserve} onChange={(e) => setReserve(e.target.value)} />
      </div>
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">Deadline (optional)</label>
        <Input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} className="[&::-webkit-calendar-picker-indicator]:invert" />
      </div>
      <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
        <input type="checkbox" checked={isEmergency} onChange={(e) => setIsEmergency(e.target.checked)} className="h-3.5 w-3.5 rounded border-white/20 bg-white/[0.04] accent-primary" />
        Emergency fund
      </label>
      <p className="text-[11px] text-muted-foreground">Reserve is funded first; the rest is shared by your chosen strategy over (target − reserve).</p>
      {err && <p className="text-xs text-destructive">{err}</p>}
      <div className="flex gap-2">
        <Button onClick={submit} disabled={busy} className="flex-1 font-medium">{busy ? "Saving…" : "Save goal"}</Button>
        {onCancel && <Button type="button" variant="outline" onClick={onCancel} className="border-white/10">Cancel</Button>}
      </div>
    </div>
  );
}

// ---- one draggable goal strip ----
function SortableGoal({ g, fmt, dragEnabled, onEdit, onDelete }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: g.id, disabled: !dragEnabled });
  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 };
  return (
    <div ref={setNodeRef} style={style} className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-3">
      {dragEnabled && (
        <button {...attributes} {...listeners} aria-label="Drag to reorder" className="cursor-grab touch-none text-muted-foreground hover:text-foreground">
          <GripVertical className="h-4 w-4" />
        </button>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate font-medium">{g.name}</span>
          {g.is_emergency && <span className="rounded-full border border-primary/30 bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">Emergency</span>}
          {g.reserve > 0 && <span className="rounded-full border border-primary/30 bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">Reserve {fmt(g.reserve)}</span>}
        </div>
        <div className="mt-0.5 text-xs text-muted-foreground">
          Holding <span className="tabular-nums text-foreground">{fmt(g.allocated)}</span>
          {g.target_amount ? <> of {fmt(g.target_amount)}</> : null}
        </div>
        {g.target_amount > 0 && (
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
            <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min((g.progress || 0) * 100, 100)}%` }} />
          </div>
        )}
      </div>
      <div className="flex shrink-0 gap-1">
        <button type="button" onClick={onEdit} aria-label="Edit goal" className="rounded-lg p-1.5 text-muted-foreground hover:bg-white/5 hover:text-foreground"><Pencil className="h-4 w-4" /></button>
        <button type="button" onClick={onDelete} aria-label="Delete goal" className="rounded-lg p-1.5 text-muted-foreground hover:bg-white/5 hover:text-destructive"><Trash2 className="h-4 w-4" /></button>
      </div>
    </div>
  );
}

// ---- deposit / withdraw box (reveal on click, server-side guard surfaced) ----
function MoveBox({ base, mode, onClose, onDone }) {
  const { token } = useAuth();
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState(base);
  const [source, setSource] = useState("surplus"); // deposit: 'surplus'|'external'
  const [dest, setDest] = useState("spending");    // withdraw: 'spending'|'world'
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit() {
    const n = parseFloat(amount);
    if (isNaN(n) || n <= 0) return setErr("Enter an amount.");
    setBusy(true); setErr("");
    try {
      if (mode === "deposit") await savingsDeposit(token, { amount: n, currency, source, note });
      else await savingsWithdraw(token, { amount: n, currency, to: dest, note });
      onDone();
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="space-y-3 rounded-xl border border-white/10 bg-white/[0.03] p-3">
      <div className="grid grid-cols-3 gap-2">
        <Input className="col-span-2" type="number" step="0.01" min="0" placeholder="Amount" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <Select value={currency} onValueChange={setCurrency}>
          <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
          <SelectContent>{CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      {mode === "deposit" ? (
        <div className="flex gap-1 rounded-full border border-white/10 p-1">
          <button type="button" onClick={() => setSource("surplus")} className={pill(source === "surplus")}>From my wallet</button>
          <button type="button" onClick={() => setSource("external")} className={pill(source === "external")}>External money</button>
        </div>
      ) : (
        <div className="flex gap-1 rounded-full border border-white/10 p-1">
          <button type="button" onClick={() => setDest("spending")} className={pill(dest === "spending")}>To my wallet</button>
          <button type="button" onClick={() => setDest("world")} className={pill(dest === "world")}>Spent directly</button>
        </div>
      )}
      <Input placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
      {err && <p className="text-sm text-destructive">{err}</p>}
      <div className="flex gap-2">
        <Button onClick={submit} disabled={busy} className="flex-1 font-medium">
          {busy ? "Saving…" : mode === "deposit" ? "Add to savings" : "Withdraw"}
        </Button>
        <Button type="button" variant="outline" onClick={onClose} className="border-white/10">Cancel</Button>
      </div>
    </div>
  );
}

function histRow(e, fmt) {
  if (e.to_type === "savings") {
    return { sign: "+", label: e.from_type ? `Deposit · from ${e.from}` : "Deposit · external", amt: fmt(e.amount_base ?? e.amount) };
  }
  return { sign: "−", label: e.to_type ? `Withdraw · to ${e.to}` : "Withdraw · spent", amt: fmt(e.amount_base ?? e.amount) };
}

export default function SavingsCard({ reloadKey, onChange }) {
  const { token, user, setUser } = useAuth();
  const base = user?.primary_currency || "SGD";
  const fmt = fmtWith(base);

  const [data, setData] = useState(null);
  const [goals, setGoals] = useState([]);
  const [history, setHistory] = useState([]);
  const [strategy, setStrategy] = useState(user?.savings_strategy || "proportional");
  const [action, setAction] = useState(null);  // 'deposit' | 'withdraw' | null
  const [adding, setAdding] = useState(false);
  const [editId, setEditId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [histOpen, setHistOpen] = useState(false);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function load() {
    getGoals(token)
      .then((d) => { setData(d); setGoals(d.goals || []); if (d.strategy) setStrategy(d.strategy); })
      .catch(() => {});
    getEntries(token)
      .then((es) => setHistory(es.filter((e) => e.from_type === "savings" || e.to_type === "savings")))
      .catch(() => {});
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [token, reloadKey]);

  const dragEnabled = strategy === "waterfall" || goals.some((g) => (g.reserve || 0) > 0);

  async function changeStrategy(v) {
    setStrategy(v);
    try { const u = await updateMe(token, { savings_strategy: v }); setUser(u); } catch { /* ignore */ }
    load();
    onChange?.();
  }

  async function onDragEnd(ev) {
    const { active, over } = ev;
    if (!over || active.id === over.id) return;
    const oldI = goals.findIndex((g) => g.id === active.id);
    const newI = goals.findIndex((g) => g.id === over.id);
    if (oldI < 0 || newI < 0) return;
    const next = arrayMove(goals, oldI, newI);
    setGoals(next); // optimistic
    try {
      const d = await reorderGoals(token, next.map((g) => g.id));
      setData(d); setGoals(d.goals || []); onChange?.();
    } catch { load(); }
  }

  async function createGoal(payload) {
    setBusy(true);
    try { await createGoalConfig(token, payload); setAdding(false); load(); onChange?.(); }
    finally { setBusy(false); }
  }
  async function saveGoal(id, payload) {
    setBusy(true);
    try { await updateGoalConfig(token, id, payload); setEditId(null); load(); onChange?.(); }
    finally { setBusy(false); }
  }
  async function removeGoal(id) {
    setBusy(true);
    try { await deleteGoalConfig(token, id); load(); onChange?.(); }
    finally { setBusy(false); }
  }

  return (
    <Card className={`${GLASS} rounded-2xl`}>
      <CardContent className="space-y-4">
        <div className="flex items-baseline justify-between">
          <div className="flex items-center gap-2">
            <PiggyBank className="h-4 w-4 text-primary" />
            <h2 className="text-base font-medium">Savings</h2>
          </div>
          <span className="text-lg font-semibold tabular-nums">{fmt(data?.savings_balance)}</span>
        </div>

        {data?.unallocated != null && (
          <div className="flex items-baseline justify-between text-xs text-muted-foreground">
            <span>Unallocated (not earmarked to a goal)</span>
            <span className="tabular-nums">{fmt(data.unallocated)}</span>
          </div>
        )}

        {action ? (
          <MoveBox base={base} mode={action} onClose={() => setAction(null)} onDone={() => { setAction(null); load(); onChange?.(); }} />
        ) : (
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setAction("deposit")} className="flex-1 border-white/10"><Plus className="mr-1.5 h-4 w-4" /> Deposit</Button>
            <Button variant="outline" onClick={() => setAction("withdraw")} className="flex-1 border-white/10">Withdraw</Button>
          </div>
        )}

        {/* strategy */}
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm text-muted-foreground">Split remainder by</span>
          <Select value={strategy} onValueChange={changeStrategy}>
            <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
            <SelectContent>
              {Object.entries(STRATEGY_LABELS).map(([v, label]) => <SelectItem key={v} value={v}>{label}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <p className="-mt-2 text-[11px] text-muted-foreground">
          {strategy === "waterfall"
            ? "Drag goals to set fill order — top is funded first."
            : dragEnabled
              ? "Rank (drag order) decides which reserves win if savings fall short."
              : "Order doesn't affect this split."}
        </p>

        {/* goals */}
        <div className="space-y-2">
          {goals.length === 0 && !adding && (
            <p className="text-sm text-muted-foreground">No goals yet. Savings sits unallocated until you add one.</p>
          )}
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
            <SortableContext items={goals.map((g) => g.id)} strategy={verticalListSortingStrategy}>
              <div className="space-y-2">
                {goals.map((g) =>
                  editId === g.id ? (
                    <GoalForm key={g.id} initial={g} busy={busy} onSubmit={(p) => saveGoal(g.id, p)} onCancel={() => setEditId(null)} />
                  ) : (
                    <SortableGoal key={g.id} g={g} fmt={fmt} dragEnabled={dragEnabled}
                      onEdit={() => setEditId(g.id)} onDelete={() => removeGoal(g.id)} />
                  )
                )}
              </div>
            </SortableContext>
          </DndContext>
        </div>

        {adding ? (
          <GoalForm busy={busy} onSubmit={createGoal} onCancel={() => setAdding(false)} />
        ) : (
          <Button type="button" variant="outline" onClick={() => setAdding(true)} className="w-full border-white/10">
            <Plus className="mr-1.5 h-4 w-4" /> Add goal
          </Button>
        )}

        {/* history */}
        <div className="border-t border-white/5 pt-2">
          <button onClick={() => setHistOpen((o) => !o)} className="flex w-full items-center gap-2 text-left text-sm">
            <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${histOpen ? "" : "-rotate-90"}`} />
            <span className="font-medium">Savings history</span>
            <span className="text-muted-foreground">{history.length}</span>
          </button>
          {histOpen && (
            <div className="mt-2 space-y-1.5">
              {history.length === 0 && <p className="text-xs text-muted-foreground">No savings activity yet.</p>}
              {history.map((e) => {
                const r = histRow(e, fmt);
                return (
                  <div key={e.id} className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm">
                    <span className="truncate">{r.label}</span>
                    <span className="text-xs text-muted-foreground">{e.date || e.fx_date}</span>
                    <span className="ml-auto tabular-nums">{r.sign}{r.amt}</span>
                    <button onClick={() => deleteEntry(token, e.id).then(() => { load(); onChange?.(); })} aria-label="Delete entry" className="rounded p-1 text-muted-foreground hover:text-destructive">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
