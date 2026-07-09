import { useState, useRef, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Settings, Eye, EyeOff } from "lucide-react";
import { useAuth } from "./AuthContext";
import { getCategories } from "./api";
import SettleNumber from "./SettleNumber";
import { motion } from "motion/react";
import { NoiseOverlay } from "@/components/ui/noise-overlay";

const baseAmount = (e) => (e.amount_base != null ? e.amount_base : e.amount);

// Use the actual transaction date (fx_date is clean ISO), NOT created_at —
// seeded/imported rows all share a created_at, which made everything look "this month".
function inCurrentMonth(e) {
  const now = new Date();
  const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  const d = e.fx_date || "";
  return typeof d === "string" && d.startsWith(ym);
}

// A data-driven spending style derived from the essential-vs-discretionary split
// of actual spend (using each category's tagged kind). Returns a neutral label
// until there's enough tagged spending to judge honestly.
function spenderProfile(expenses, kindByCat) {
  if (!expenses || expenses.length < 6) {
    return { label: "Getting started", amber: false, title: "Log a few expenses to see your spending style" };
  }
  let essential = 0, discretionary = 0, total = 0;
  for (const e of expenses) {
    const v = baseAmount(e);
    if (!(v > 0)) continue;
    total += v;
    const kind = kindByCat[e.category];
    if (kind === "essential") essential += v;
    else if (kind === "discretionary") discretionary += v;
  }
  const classified = essential + discretionary;
  if (total <= 0 || classified < total * 0.35) {
    return { label: "Balanced spender", amber: false, title: "Tag more categories as essential or wants to classify your style" };
  }
  const share = discretionary / classified;            // discretionary share of classified spend
  const pct = Math.round(share * 100);
  if (share <= 0.30) {
    return { label: "Disciplined spender", amber: false, title: `${pct}% of tagged spend is on wants — mostly essentials` };
  }
  if (share >= 0.60) {
    return { label: "Lifestyle spender", amber: true, title: `${pct}% of tagged spend is on wants` };
  }
  return { label: "Balanced spender", amber: false, title: `${pct}% of tagged spend is on wants` };
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

  const { token } = useAuth();
  const [kindByCat, setKindByCat] = useState({});
  useEffect(() => {
    if (!token) return;
    let alive = true;
    getCategories(token)
      .then((d) => {
        if (alive) setKindByCat(Object.fromEntries((d.categories || []).map((c) => [c.name, c.kind])));
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [token]);

  const spender = spenderProfile(expenses, kindByCat);

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

      {open && (
        <div
          className="fixed inset-0 z-10 bg-black/40 backdrop-blur-sm"
          onClick={() => setOpen(false)}
          aria-hidden="true"
        />
      )}

      <motion.div
        initial={false}
        animate={open ? { scale: 1, opacity: 1 } : { scale: 0.9, opacity: 0 }}
        transition={{ type: "spring", stiffness: 380, damping: 30 }}
        style={{ pointerEvents: open ? "auto" : "none", willChange: "transform, opacity" }}
        className="absolute left-0 top-0 z-20 w-72 origin-top-left"
      >
        <Card className="relative overflow-hidden rounded-2xl border-white/10 bg-white/[0.06] shadow-2xl shadow-black/50 backdrop-blur-2xl">
          <NoiseOverlay />
          <CardContent className="relative z-10 space-y-4">
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
                {baseCurrency} <SettleNumber value={monthlySpent} active={open} />
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
                  <span className={`text-sm font-medium ${budgetLeftPct < 0 ? "text-destructive" : "text-primary-enhanced"}`}>
                    {budgetLeftPct}% of budget left
                  </span>
                  <button onClick={openSettings} className="text-xs text-muted-foreground hover:text-foreground">
                    Edit
                  </button>
                </div>
              ) : (
                <button onClick={openSettings} className="text-sm text-primary-enhanced hover:underline">
                  Set a monthly budget
                </button>
              )}
            </div>

            <div>
              <span
                title={spender.title}
                className={`inline-block cursor-default rounded-full border px-3 py-1 text-xs font-medium ${
                  spender.amber
                    ? "border-[#F0B14B]/30 bg-[#F0B14B]/10 text-[#F0B14B]"
                    : "border-primary/30 bg-primary/10 text-primary-enhanced"
                }`}
              >
                {spender.label}
              </span>
            </div>

            <div className="flex justify-end">
              <button onClick={openSettings} aria-label="Settings" className="text-muted-foreground hover:text-foreground">
                <Settings className="h-5 w-5" />
              </button>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}