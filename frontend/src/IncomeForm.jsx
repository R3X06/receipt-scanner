import { useState } from "react";
import { useAuth } from "./AuthContext";
import { CURRENCIES } from "./constants";
import { addLedgerIncome } from "./api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export default function IncomeForm({ onDone }) {
  const { token, user } = useAuth();
  const base = user?.primary_currency || "SGD";
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState(base);
  const [source, setSource] = useState("");
  const [date, setDate] = useState(new Date().toISOString().split("T")[0]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [pyf, setPyf] = useState(null);

  async function submit() {
    const n = parseFloat(amount);
    if (isNaN(n) || n <= 0) return setErr("Enter an amount.");
    setBusy(true);
    setErr("");
    try {
      const res = await addLedgerIncome(token, { amount: n, currency, source, date });
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
        <p className="text-sm text-muted-foreground">Take-home (net) money coming in — salary, freelance, etc.</p>
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Input className="col-span-2" type="number" step="0.01" min="0" placeholder="Amount" value={amount} onChange={(e) => setAmount(e.target.value)} />
        <Select value={currency} onValueChange={setCurrency}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>{CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <Input placeholder="Source (e.g. Salary)" value={source} onChange={(e) => setSource(e.target.value)} />
      <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="[&::-webkit-calendar-picker-indicator]:invert" />
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