import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { getCashflow } from "./api";
import { Card, CardContent } from "@/components/ui/card";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";

export default function CashFlowCard({ reloadKey }) {
  const { token, user } = useAuth();
  const base = user?.primary_currency || "SGD";
  const [cf, setCf] = useState(null);

  useEffect(() => {
    let active = true;
    getCashflow(token).then((d) => active && setCf(d)).catch(() => {});
    return () => { active = false; };
  }, [token, reloadKey]);

  const fmt = (n) => `${base} ${(n ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const rate = cf?.savings_rate != null ? Math.round(cf.savings_rate * 100) : null;
  const surplus = cf?.surplus ?? 0;

  return (
    <Card className={`${GLASS} rounded-2xl`}>
      <CardContent className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-medium text-muted-foreground">This month</h2>
          {rate != null && <span className="text-xs text-muted-foreground">{rate}% saved</span>}
        </div>
        <div className="space-y-1.5 text-sm">
          <Row label="Income" value={fmt(cf?.income)} valueClass="text-emerald-400" />
          <Row label="Spending" value={fmt(cf?.spending)} />
          <div className="my-1 h-px bg-white/10" />
          <Row label="Surplus" value={fmt(surplus)} strong valueClass={surplus < 0 ? "text-destructive" : ""} />
          <Row label="To savings" value={fmt(cf?.to_savings_net)} muted />
          <Row label="Leftover" value={fmt(cf?.leftover)} muted />
        </div>
      </CardContent>
    </Card>
  );
}

function Row({ label, value, strong, muted, valueClass = "" }) {
  return (
    <div className={`flex justify-between ${muted ? "text-muted-foreground" : ""}`}>
      <span className={strong ? "font-medium" : ""}>{label}</span>
      <span className={`tabular-nums ${strong ? "font-semibold" : ""} ${valueClass}`}>{value}</span>
    </div>
  );
}