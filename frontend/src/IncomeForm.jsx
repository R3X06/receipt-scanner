import { useState } from "react";
import { useAuth } from "./AuthContext";
import { CURRENCIES } from "./constants";
import { addLedgerIncome } from "./api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

function nowLocal() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

export default function IncomeForm({ onDone }) {
  const { token, user } = useAuth();
  const base = user?.primary_currency || "SGD";
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState(base);
  const [source, setSource] = useState("");
  const [when, setWhen] = useState(nowLocal());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [pyf, setPyf] = useState(null);

  async function submit() {
    const n = parseFloat(amount);
    if (isNaN(n) || n <= 0) return setErr("Enter an amount.");
    setBusy(true);
    setErr("");
    try {
      const date = (when || "").split("T")[0];
      const res = await addLedgerIncome(token, { amount: n, currency, source, date, occurred_at: when });
      setPyf(res.pay_yourself_first_suggested || null);
      setAmount(""); setSource("");
      onDone?.();
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-medium">Add income</h2>
        <p className="text-sm text-muted-foreground">Take-home (net) money coming in — salary, parents, freelance, anything.</p>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Input className="col-span-2" type="number" step="0.01" min="0" placeholder="Amount" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <Select value={currency} onValueChange={setCurrency}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>{CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <Input placeholder="Where it came from (e.g. Salary, Dad)" value={source} onChange={(e) => setSource(e.target.value)} />
      <div className="space-y-1">
        <label className="text-xs text-muted-foreground">When it arrived</label>
        <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} className="[&::-webkit-calendar-picker-indicator]:invert" />
      </div>
      {pyf && (
        <p className="rounded-lg border border-primary/30 bg-primary/10 p-2 text-xs text-muted-foreground">
          Pay yourself first: consider moving {base} {pyf.toFixed(2)} into savings now — open Savings to allocate it.
        </p>
      )}
      {err && <p className="text-sm text-destructive">{err}</p>}
      <Button onClick={submit} disabled={busy} className="w-full font-medium">{busy ? "Adding…" : "Add income"}</Button>
    </div>
  );
}
