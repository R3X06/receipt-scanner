import { useState, useRef, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Settings, Eye, EyeOff } from "lucide-react";

const baseAmount = (e) => (e.amount_base != null ? e.amount_base : e.amount);

// Use the actual transaction date (fx_date is clean ISO), NOT created_at —
// seeded/imported rows all share a created_at, which made everything look "this month".
function inCurrentMonth(e) {
  const now = new Date();
  const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const d = e.fx_date || "";
  return typeof d === "string" && d.startsWith(ym);
}

export default function ProfileCard({ user, expenses, onOpenSettings }) {
  const [open, setOpen] = useState(false);
  const [showTotal, setShowTotal] = useState(false);
  const wrapperRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) setOpen(false);
    }
    function onKey(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const baseCurrency = user?.primary_currency || "SGD";
  const email = user?.email || "";
  const displayName = (user?.display_name && user.display_name.trim()) || (email ? email.split("@")[0] : "User");
  const initials = displayName.slice(0, 2).toUpperCase();
  const avatar = user?.avatar;

  const monthlySpent = expenses.filter(inCurrentMonth).reduce((s, e) => s + baseAmount(e), 0);
  const totalSpent = expenses.reduce((s, e) => s + baseAmount(e), 0);

  const budget = user?.monthly_budget;
  const budgetLeftPct =
    budget && budget > 0 ? Math.round(((budget - monthlySpent) / budget) * 100) : null;

  const spenderTag = "Balanced spender";

  function openSettings() {
    setOpen(false);
    onOpenSettings?.();
  }

  return (
    <div className="relative" ref={wrapperRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Open profile"
        className="flex h-14 w-14 items-center justify-center rounded-full border border-white/15 bg-white/[0.06] text-sm font-semibold text-foreground backdrop-blur-xl transition-transform hover:scale-105"
        style={{ boxShadow: "0 0 24px rgba(168,85,247,0.25)" }}
      >
        {avatar ? <span className="text-2xl leading-none">{avatar}</span> : initials}
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
                {avatar ? <span className="text-lg leading-none">{avatar}</span> : initials}
              </button>
              <div className="min-w-0">
                <p className="truncate font-medium capitalize">{displayName}</p>
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
              {budget ? (
                <div className="flex items-center justify-between">
                  <span className={`text-sm font-medium ${budgetLeftPct < 0 ? "text-destructive" : "text-primary"}`}>
                    {budgetLeftPct}% of budget left
                  </span>
                  <button onClick={openSettings} className="text-xs text-muted-foreground hover:text-foreground">
                    Edit
                  </button>
                </div>
              ) : (
                <button onClick={openSettings} className="text-sm text-primary hover:underline">
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
              <button onClick={openSettings} aria-label="Settings" className="text-muted-foreground hover:text-foreground">
                <Settings className="h-5 w-5" />
              </button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}