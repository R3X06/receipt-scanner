import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { getAccounts, getCashflow, getEntries, deleteEntry } from "./api";
import IncomeForm from "./IncomeForm";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Plus, ChevronDown, Trash2, Wallet as WalletIcon } from "lucide-react";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";

export default function WalletCard({ reloadKey, onChange }) {
  const { token, user } = useAuth();
  const base = user?.primary_currency || "SGD";
  const [walletBal, setWalletBal] = useState(null);
  const [cf, setCf] = useState(null);
  const [income, setIncome] = useState([]);
  const [adding, setAdding] = useState(false);
  const [histOpen, setHistOpen] = useState(false);

  function load() {
    getAccounts(token)
      .then((d) => {
        const w = (d.accounts || []).find((a) => a.type === "spending");
        setWalletBal(w ? w.balance : 0);
      })
      .catch(() => {});
    getCashflow(token).then(setCf).catch(() => {});
    getEntries(token)
      .then((es) => setIncome(es.filter((e) => e.kind === "income")))
      .catch(() => {});
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [token, reloadKey]);

  const fmt = (n) =>
    `${base} ${(n ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  async function removeIncome(id) {
    try { await deleteEntry(token, id); load(); onChange?.(); } catch { /* ignore */ }
  }

  return (
    <Card className={`${GLASS} rounded-2xl`}>
      <CardContent className="space-y-3">
        <div className="flex items-baseline justify-between">
          <div className="flex items-center gap-2">
            <WalletIcon className="h-4 w-4 text-primary" />
            <h2 className="text-base font-medium">Wallet</h2>
          </div>
          {cf?.monthly_income_avg ? (
            <span className="text-xs text-muted-foreground">avg {fmt(cf.monthly_income_avg)} / mo</span>
          ) : null}
        </div>

        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-semibold tabular-nums">{fmt(walletBal)}</span>
          {cf?.income ? <span className="text-xs text-muted-foreground">+{fmt(cf.income)} in this month</span> : null}
        </div>

        {cf && (
          <div className="grid grid-cols-3 gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-3 text-sm">
            <Stat label="Income" value={fmt(cf.income)} className="text-primary" />
            <Stat label="Spending" value={fmt(cf.spending)} />
            <Stat label="Surplus" value={fmt(cf.surplus)} className={cf.surplus < 0 ? "text-destructive" : ""} />
          </div>
        )}

        {adding ? (
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
            <IncomeForm onDone={() => { setAdding(false); load(); onChange?.(); }} />
            <Button variant="ghost" size="sm" onClick={() => setAdding(false)} className="mt-2 w-full text-muted-foreground">
              Cancel
            </Button>
          </div>
        ) : (
          <Button variant="outline" onClick={() => setAdding(true)} className="w-full border-white/10">
            <Plus className="mr-1.5 h-4 w-4" /> Add income
          </Button>
        )}

        <div className="border-t border-white/5 pt-2">
          <button onClick={() => setHistOpen((o) => !o)} className="flex w-full items-center gap-2 text-left text-sm">
            <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${histOpen ? "" : "-rotate-90"}`} />
            <span className="font-medium">Income history</span>
            <span className="text-muted-foreground">{income.length}</span>
          </button>
          {histOpen && (
            <div className="mt-2 space-y-1.5">
              {income.length === 0 && <p className="text-xs text-muted-foreground">No income recorded yet.</p>}
              {income.map((e) => (
                <div key={e.id} className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm">
                  <span className="truncate">{e.counterparty || "Income"}</span>
                  <span className="text-xs text-muted-foreground">{e.date || e.fx_date}</span>
                  <span className="ml-auto tabular-nums">{fmt(e.amount_base ?? e.amount)}</span>
                  <button onClick={() => removeIncome(e.id)} aria-label="Delete income" className="rounded p-1 text-muted-foreground hover:text-destructive">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value, className = "" }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`tabular-nums ${className}`}>{value}</p>
    </div>
  );
}
