import { useState, useEffect } from "react";
import { useAuth } from "./AuthContext";
import { CURRENCIES } from "./constants";
import { getSavings, addSaving, deleteSaving } from "./api";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ArrowDownLeft, ArrowUpRight, Trash2 } from "lucide-react";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";

const baseAmount = (e) => (e.amount_base != null ? e.amount_base : e.amount);

function avgMonthlySpend(expenses) {
  const byMonth = {};
  for (const e of expenses) {
    const d = e.fx_date || "";
    if (typeof d === "string" && d.length >= 7) {
      const m = d.slice(0, 7);
      byMonth[m] = (byMonth[m] || 0) + baseAmount(e);
    }
  }
  const months = Object.values(byMonth);
  if (!months.length) return 0;
  return months.reduce((a, b) => a + b, 0) / months.length;
}

export default function Savings({ expenses = [] }) {
  const { token, user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const baseCurrency = user?.primary_currency || "SGD";
  const income = user?.monthly_income;

  const [direction, setDirection] = useState("in");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState(baseCurrency);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      setData(await getSavings(token));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [token]);

  async function add() {
    const amt = parseFloat(amount);
    if (isNaN(amt) || amt <= 0) {
      setError("Enter a valid amount.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await addSaving(token, {
        direction,
        amount: amt,
        currency,
        note: note.trim(),
        date: new Date().toISOString().split("T")[0],
      });
      setAmount("");
      setNote("");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function remove(id) {
    try {
      await deleteSaving(token, id);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  const balance = data?.balance ?? 0;
  const txns = data?.transactions || [];

  const sbase = (t) => (t.amount_base != null ? t.amount_base : t.amount);

  const now = new Date();
  const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const thisMonthIn = txns
    .filter((t) => t.direction === "in" && (t.date || "").startsWith(ym))
    .reduce((s, t) => s + sbase(t), 0);

  const avgSpend = avgMonthlySpend(expenses);
  const coverage = avgSpend > 0 ? balance / avgSpend : null;
  const ratePct = income && income > 0 ? Math.round((thisMonthIn / income) * 100) : null;

  return (
    <Card className={`${GLASS} rounded-2xl`}>
      <CardContent className="space-y-4">
        <div>
          <h2 className="text-base font-medium">Savings</h2>
          <p className="text-sm text-muted-foreground">Money set aside, separate from your spending.</p>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
          <p className="text-xs text-muted-foreground">Balance</p>
          <p className="text-3xl font-semibold tabular-nums tracking-tight">
            {baseCurrency} {balance.toFixed(2)}
          </p>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span>In: {baseCurrency} {(data?.total_in ?? 0).toFixed(2)}</span>
            <span>Out: {baseCurrency} {(data?.total_out ?? 0).toFixed(2)}</span>
          </div>
        </div>

        {(coverage != null || ratePct != null) && (
          <div className="grid grid-cols-2 gap-3">
            {coverage != null && (
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                <p className="text-xs text-muted-foreground">Covers</p>
                <p className="text-lg font-semibold tabular-nums">{coverage.toFixed(1)} mo</p>
                <p className="text-xs text-muted-foreground">of average spend</p>
              </div>
            )}
            {ratePct != null && (
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
                <p className="text-xs text-muted-foreground">Saved this month</p>
                <p className="text-lg font-semibold tabular-nums text-primary">{ratePct}%</p>
                <p className="text-xs text-muted-foreground">of monthly income</p>
              </div>
            )}
          </div>
        )}

        <div className="space-y-3 rounded-xl border border-white/10 bg-white/[0.03] p-3">
          <div className="flex gap-1 rounded-full border border-white/10 p-1">
            <button
              onClick={() => setDirection("in")}
              className={`flex-1 rounded-full px-3 py-1.5 text-sm transition-colors ${
                direction === "in" ? "bg-primary font-medium text-primary-foreground" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Deposit
            </button>
            <button
              onClick={() => setDirection("out")}
              className={`flex-1 rounded-full px-3 py-1.5 text-sm transition-colors ${
                direction === "out" ? "bg-primary font-medium text-primary-foreground" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Withdraw
            </button>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Input
              className="col-span-2"
              type="number"
              step="0.01"
              min="0"
              placeholder="Amount"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
            <Select value={currency} onValueChange={setCurrency}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                {CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <Input
            placeholder="Note (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <Button onClick={add} disabled={saving} className="w-full font-medium">
            {saving ? "Saving..." : direction === "in" ? "Add deposit" : "Record withdrawal"}
          </Button>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        {loading ? (
          <p className="py-4 text-center text-sm text-muted-foreground">Loading...</p>
        ) : !txns.length ? (
          <p className="py-4 text-center text-sm text-muted-foreground">No savings activity yet.</p>
        ) : (
          <div className="divide-y divide-white/5">
            {txns.map((t) => {
              const converted = t.currency && t.currency !== baseCurrency && t.amount_base != null;
              return (
                <div key={t.id} className="flex items-center justify-between gap-3 py-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <span
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                        t.direction === "in" ? "bg-primary/10 text-primary" : "bg-white/5 text-muted-foreground"
                      }`}
                    >
                      {t.direction === "in" ? <ArrowDownLeft className="h-4 w-4" /> : <ArrowUpRight className="h-4 w-4" />}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {t.note || (t.direction === "in" ? "Deposit" : "Withdrawal")}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">{t.date || ""}</p>
                    </div>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className={`text-sm font-semibold tabular-nums ${t.direction === "in" ? "text-primary" : "text-muted-foreground"}`}>
                      {t.direction === "in" ? "+" : "−"}{t.currency || baseCurrency} {Number(t.amount).toFixed(2)}
                    </p>
                    {converted && (
                      <p className="text-xs text-muted-foreground tabular-nums">
                        ≈ {baseCurrency} {Number(t.amount_base).toFixed(2)}
                      </p>
                    )}
                  </div>
                  <button onClick={() => remove(t.id)} aria-label="Delete" className="shrink-0 text-muted-foreground hover:text-destructive">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}