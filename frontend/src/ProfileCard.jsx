import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Settings, Eye, EyeOff } from "lucide-react";

const baseAmount = (e) => (e.amount_base != null ? e.amount_base : e.amount);

function inCurrentMonth(e) {
  const now = new Date();
  const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  for (const c of [e.fx_date, e.date, e.created_at]) {
    if (typeof c === "string" && c.startsWith(ym)) return true;
  }
  return false;
}

export default function ProfileCard({ user, expenses }) {
  const [open, setOpen] = useState(false);
  const [showTotal, setShowTotal] = useState(false);
  const [budget, setBudget] = useState(() => {
    const v = localStorage.getItem("kalla_budget");
    return v ? Number(v) : null;
  });
  const [editingBudget, setEditingBudget] = useState(false);
  const [budgetInput, setBudgetInput] = useState("");

  const baseCurrency = user?.primary_currency || "SGD";
  const email = user?.email || "";
  const name = email ? email.split("@")[0] : "User";
  const initials = name.slice(0, 2).toUpperCase();

  const monthlySpent = expenses.filter(inCurrentMonth).reduce((s, e) => s + baseAmount(e), 0);
  const totalSpent = expenses.reduce((s, e) => s + baseAmount(e), 0);
  const budgetLeftPct =
    budget && budget > 0 ? Math.round(((budget - monthlySpent) / budget) * 100) : null;

  function saveBudget() {
    const n = parseFloat(budgetInput);
    if (!isNaN(n) && n > 0) {
      setBudget(n);
      localStorage.setItem("kalla_budget", String(n));
    }
    setEditingBudget(false);
  }

  const spenderTag = "Balanced spender";

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(true)}
        aria-label="Open profile"
        className="flex h-14 w-14 items-center justify-center rounded-full border border-white/15 bg-white/[0.06] text-sm font-semibold text-foreground backdrop-blur-xl transition-transform hover:scale-105"
        style={{ boxShadow: "0 0 24px rgba(168,85,247,0.25)" }}
      >
        {initials}
      </button>

      <div
        className={`absolute left-0 top-0 z-20 w-72 origin-top-left transition-all duration-300 ease-out ${
          open ? "scale-100 opacity-100" : "pointer-events-none scale-90 opacity-0"
        }`}
      >
        <Card className="rounded-2xl border-white/10 bg-white/[0.06] shadow-2xl shadow-black/50 backdrop-blur-2xl">
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setOpen(false)}
                aria-label="Close profile"
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-white/15 bg-white/[0.08] text-sm font-semibold"
              >
                {initials}
              </button>
              <div className="min-w-0">
                <p className="truncate font-medium capitalize">{name}</p>
                <p className="truncate text-xs text-muted-foreground">{email}</p>
              </div>
            </div>

            <div>
              <p className="text-xs text-muted-foreground">This month</p>
              <p className="text-2xl font-semibold tabular-nums tracking-tight">
                {baseCurrency} {monthlySpent.toFixed(2)}
              </p>
              <button
                onClick={() => setShowTotal((s) => !s)}
                className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              >
                {showTotal ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                {showTotal ? `Total: ${baseCurrency} ${totalSpent.toFixed(2)}` : "Show total so far"}
              </button>
            </div>

            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
              {editingBudget ? (
                <div className="flex items-center gap-2">
                  <Input
                    type="number"
                    autoFocus
                    value={budgetInput}
                    onChange={(e) => setBudgetInput(e.target.value)}
                    placeholder="Monthly budget"
                    className="h-8"
                  />
                  <Button size="sm" onClick={saveBudget} className="h-8">
                    Save
                  </Button>
                </div>
              ) : budget ? (
                <div className="flex items-center justify-between">
                  <span
                    className={`text-sm font-medium ${
                      budgetLeftPct < 0 ? "text-destructive" : "text-primary"
                    }`}
                  >
                    {budgetLeftPct}% of budget left
                  </span>
                  <button
                    onClick={() => {
                      setBudgetInput(String(budget));
                      setEditingBudget(true);
                    }}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    Edit
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setEditingBudget(true)}
                  className="text-sm text-primary hover:underline"
                >
                  Set a monthly budget
                </button>
              )}
            </div>

            <div>
              <span className="rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
                {spenderTag}
              </span>
            </div>

            <div className="flex justify-end">
              <button aria-label="Settings" className="text-muted-foreground hover:text-foreground">
                <Settings className="h-5 w-5" />
              </button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}