import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { getReconciliation, setWalletLink } from "./api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Link2Off } from "lucide-react";

export default function ReconciliationCard({ reloadKey, onAddIncome, onChange }) {
  const { token, user } = useAuth();
  const base = user?.primary_currency || "SGD";
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(null);

  function load() { getReconciliation(token).then(setData).catch(() => {}); }
  useEffect(() => { load(); }, [token, reloadKey]);

  const fmt = (n) =>
    `${base} ${(n ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  async function unlink(id) {
    setBusy(id);
    try { await setWalletLink(token, id, false); load(); onChange?.(); }
    finally { setBusy(null); }
  }

  if (!data || !(data.shortfall > 0)) return null;

  const items = data.contributing || [];

  return (
    <Card className="rounded-2xl border-amber-500/30 bg-amber-500/[0.06] backdrop-blur-xl">
      <CardContent className="space-y-3">
        <div className="flex items-start gap-2">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
          <div>
            <p className="text-sm font-medium text-amber-200">Wallet short by {fmt(data.shortfall)}</p>
            <p className="text-xs text-muted-foreground">Your tracked income doesn't cover this spending. Add the income you're missing, or unlink an expense paid from money you don't track.</p>
          </div>
        </div>

        <Button size="sm" onClick={onAddIncome} className="w-full font-medium">Add missing income</Button>

        {items.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs text-muted-foreground">Expenses drawing on the wallet — unlink any you're unsure of:</p>
            {items.map((e) => (
              <div key={e.id} className="flex items-center justify-between gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5">
                <div className="min-w-0 truncate text-xs">
                  <span className="text-foreground">{e.merchant || e.category || "Expense"}</span>
                  <span className="text-muted-foreground"> · {fmt(e.amount)}{e.date ? ` · ${e.date}` : ""}</span>
                </div>
                <button type="button" onClick={() => unlink(e.id)} disabled={busy === e.id}
                  className="flex shrink-0 items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-xs text-muted-foreground hover:bg-white/5 hover:text-foreground disabled:opacity-50">
                  <Link2Off className="h-3 w-3" /> {busy === e.id ? "…" : "Unlink"}
                </button>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
