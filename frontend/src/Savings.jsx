import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { CURRENCIES } from "./constants";
import { getGoals, savingsDeposit, savingsWithdraw } from "./api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";

const pill = (active) =>
  `flex-1 rounded-full px-2 py-1 text-xs transition ${active ? "bg-primary font-medium text-primary-foreground" : "text-muted-foreground"}`;

export default function Savings({ onChange }) {
  const { token, user } = useAuth();
  const base = user?.primary_currency || "SGD";
  const [data, setData] = useState(null);          // { savings_balance, unallocated, goals }
  const [mode, setMode] = useState("deposit");     // 'deposit' | 'withdraw'
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState(base);
  const [source, setSource] = useState("surplus"); // deposit: 'surplus' | 'external'
  const [dest, setDest] = useState("spending");    // withdraw: 'spending' | 'world'
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  function load() {
    getGoals(token).then(setData).catch(() => {});
  }
  useEffect(() => { load(); }, [token]);

  const fmt = (n) =>
    `${base} ${(n ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  async function submit() {
    const n = parseFloat(amount);
    if (isNaN(n) || n <= 0) return setErr("Enter an amount.");
    setBusy(true);
    setErr("");
    try {
      if (mode === "deposit") {
        await savingsDeposit(token, { amount: n, currency, source, note });
      } else {
        await savingsWithdraw(token, { amount: n, currency, to: dest, note });
      }
      setAmount(""); setNote("");
      load();
      onChange?.();
    } catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <Card className={`${GLASS} rounded-2xl`}>
      <CardContent className="space-y-4">
        <div>
          <h2 className="text-base font-medium">Savings</h2>
          <p className="text-sm text-muted-foreground">A pool you set aside — independent of any goal.</p>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
          <div className="flex items-baseline justify-between">
            <span className="text-sm text-muted-foreground">Balance</span>
            <span className="text-lg font-semibold tabular-nums">{fmt(data?.savings_balance)}</span>
          </div>
          {data?.unallocated != null && (
            <div className="mt-1 flex items-baseline justify-between text-xs text-muted-foreground">
              <span>Unallocated (not earmarked to a goal)</span>
              <span className="tabular-nums">{fmt(data.unallocated)}</span>
            </div>
          )}
        </div>

        <div className="flex gap-1 rounded-full border border-white/10 p-1">
          <button type="button" onClick={() => setMode("deposit")} className={pill(mode === "deposit")}>Add to savings</button>
          <button type="button" onClick={() => setMode("withdraw")} className={pill(mode === "withdraw")}>Withdraw</button>
        </div>

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
        <Button onClick={submit} disabled={busy} className="w-full font-medium">
          {busy ? "Saving…" : mode === "deposit" ? "Add to savings" : "Withdraw"}
        </Button>
      </CardContent>
    </Card>
  );
}
