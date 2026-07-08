import { useState, useEffect, lazy, Suspense } from "react";
import { useAuth } from "./AuthContext";
import { getExpenses } from "./api";
import { CATEGORIES } from "./constants";
import ExpenseForm from "./ExpenseForm";
const ScanImport = lazy(() => import("./ScanImport"));
const Charts = lazy(() => import("./Charts"));
const AskAI = lazy(() => import("./AskAI"));
const Insights = lazy(() => import("./Insights"));
const Loading = () => (
  <div className="py-10 text-center text-sm text-muted-foreground">Loading…</div>
);
import ProfileCard from "./ProfileCard";
import ExpenseList from "./ExpenseList";
const Settings = lazy(() => import("./Settings"));
import WalletCard from "./WalletCard";
import SavingsCard from "./SavingsCard";
import ReconciliationCard from "./ReconciliationCard";

import KallaLogo from "./components/ui/KallaLogo";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import {
  LogOut,
  ScanLine,
  Plus,
  Sparkles,
  Lightbulb,
  SlidersHorizontal,
  ChevronDown,
  Wallet,
  PiggyBank,
} from "lucide-react";

const GLASS = "border-white/10 bg-white/[0.04] backdrop-blur-xl shadow-xl shadow-black/20";
const DIALOG = "max-w-lg border-0 bg-transparent p-0 shadow-none";

const baseAmount = (e) => (e.amount_base != null ? e.amount_base : e.amount);

export default function Dashboard() {
  const { user, token, logout } = useAuth();
  const [expenses, setExpenses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ start: "", end: "", category: "" });

  const [openDialog, setOpenDialog] = useState(null); // 'scan'|'add'|'ask'|'insights'|'filter'|'settings'
  const [expensesOpen, setExpensesOpen] = useState(true);
  const [ledgerReload, setLedgerReload] = useState(0);

  const bump = () => setLedgerReload((k) => k + 1);

  useEffect(() => {
    setLoading(true);
    getExpenses(token, filters)
      .then(setExpenses)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [token, filters]);

  const baseCurrency = user?.primary_currency || "SGD";
  const displayName = (user?.display_name && user.display_name.trim()) || (user?.email ? user.email.split("@")[0] : "your");
  const hasFilter = !!(filters.start || filters.end || filters.category);

  // keep the list open whenever a filter is active, so results are visible
  useEffect(() => {
    if (hasFilter) setExpensesOpen(true);
  }, [hasFilter]);

  function handleExpenseAdded(expense) {
    setExpenses((prev) => [expense, ...prev]);
    bump();
  }
  function handleExpenseAddedAndClose(expense) {
    handleExpenseAdded(expense);
    setOpenDialog(null);
  }
  function handleExpenseUpdated(updated) {
    setExpenses((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
    bump();
  }
  function handleExpenseDeleted(id) {
    setExpenses((prev) => prev.filter((e) => e.id !== id));
    bump();
  }

  const totalBase = expenses.reduce((s, e) => s + baseAmount(e), 0);

  const currencyTotals = Object.entries(
    expenses.reduce((acc, e) => {
      const cur = e.currency || "USD";
      acc[cur] = (acc[cur] || 0) + e.amount;
      return acc;
    }, {})
  ).sort((a, b) => b[1] - a[1]);

  const actions = [
    { key: "scan", label: "Scan", icon: ScanLine },
    { key: "add", label: "Add", icon: Plus },
    { key: "wallet", label: "Wallet", icon: Wallet },
    { key: "savings", label: "Savings", icon: PiggyBank },
    { key: "ask", label: "Ask AI", icon: Sparkles },
    { key: "insights", label: "Insights", icon: Lightbulb },
  ];

  const noExpenses = !loading && expenses.length === 0 && !hasFilter;

  return (
    <div className="relative min-h-screen p-4 sm:p-6">
      <div className="relative z-10 mx-auto max-w-3xl space-y-4">
        {/* wordmark */}
        <div className="pointer-events-none select-none text-left text-glow3 leading-none" aria-hidden="true" >
          <span
            className="block font-sans capitalize"
            style={{ fontSize: "clamp(14px, 2vw, 16px)", color: "hsla(66, 100%, 98%, 0.18)", letterSpacing: "0.05em", marginLeft:"3px" }}
          >
            {displayName.toUpperCase()}'s 
          </span>
          <div style={{ filter: "drop-shadow(0 0 12px #A855F7aa) drop-shadow(0 0 32px #A855F760)", marginTop: "6px" }}>
            <KallaLogo width={230} />
          </div>
        </div>

        {/* profile + sign out */}
        <div className="flex items-start justify-between gap-3">
          <ProfileCard user={user} expenses={expenses} onOpenSettings={() => setOpenDialog("settings")} />
          <Button
            variant="outline"
            size="icon"
            onClick={logout}
            aria-label="Sign out"
            className="border-white/15 bg-transparent hover:bg-white/5"
          >
            <LogOut className="h-4 w-4" />
          </Button>
        </div>

        {/* action buttons */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-6">
          {actions.map(({ key, label, icon: Icon }) => (
            <Button
              key={key}
              variant="outline"
              onClick={() => setOpenDialog(key)}
              className="h-auto flex-col gap-1.5 border-white/10 bg-white/[0.04] py-4 backdrop-blur-xl hover:bg-white/[0.08]"
            >
              <Icon className="h-5 w-5 text-primary" />
              <span className="text-sm font-medium">{label}</span>
            </Button>
          ))}
        </div>

        <ReconciliationCard reloadKey={ledgerReload} onAddIncome={() => setOpenDialog("wallet")} onChange={bump} />

        {noExpenses ? (
          /* first-run expenses hint */
          <Card className={`${GLASS} rounded-2xl`}>
            <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-full border border-white/10 bg-white/[0.04]">
                <Wallet className="h-6 w-6 text-primary" />
              </div>
              <div>
                <p className="text-lg font-medium">No expenses yet</p>
                <p className="mt-1 text-sm text-muted-foreground">Scan a receipt or add one manually to get started.</p>
              </div>
              <div className="flex flex-wrap justify-center gap-2">
                <Button onClick={() => setOpenDialog("scan")} className="font-medium">
                  <ScanLine className="mr-1.5 h-4 w-4" /> Scan a receipt
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setOpenDialog("add")}
                  className="border-white/15 bg-transparent font-medium hover:bg-white/5"
                >
                  <Plus className="mr-1.5 h-4 w-4" /> Add manually
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : (
          <>
            {/* multi-currency total */}
            {currencyTotals.length > 0 && (
              <Card className={`${GLASS} rounded-2xl`}>
                <CardContent className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
                  {currencyTotals.map(([cur, amt], i) => (
                    <div key={cur} className="flex items-baseline gap-1.5">
                      <span className={`font-semibold tabular-nums ${i === 0 ? "text-xl text-foreground" : "text-base text-muted-foreground"}`}>
                        {amt.toFixed(2)}
                      </span>
                      <span className={i === 0 ? "text-xs text-primary" : "text-xs text-muted-foreground"}>{cur}</span>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {/* charts */}
            <Suspense fallback={<Loading />}>
              <Charts expenses={expenses} baseCurrency={baseCurrency} />
            </Suspense>

            {/* collapsible expenses */}
            <Card className={`${GLASS} overflow-hidden rounded-2xl p-0`}>
              <div className="flex items-center justify-between gap-3 px-5 py-4">
                <button onClick={() => setExpensesOpen((o) => !o)} className="flex flex-1 items-center gap-2 text-left">
                  <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${expensesOpen ? "" : "-rotate-90"}`} />
                  <span className="font-medium">Expenses</span>
                  <span className="text-sm text-muted-foreground">
                    {baseCurrency} {totalBase.toFixed(2)} · {expenses.length}
                  </span>
                </button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setOpenDialog("filter")}
                  className={hasFilter ? "text-primary hover:text-primary" : "text-muted-foreground hover:text-foreground"}
                >
                  <SlidersHorizontal className="mr-1.5 h-4 w-4" />
                  {hasFilter ? "Filtered" : "Filter"}
                </Button>
              </div>
              {expensesOpen && (
                <div className="border-t border-white/5">
                  <ExpenseList
                    expenses={expenses}
                    loading={loading}
                    hasFilter={hasFilter}
                    onUpdated={handleExpenseUpdated}
                    onDeleted={handleExpenseDeleted}
                  />
                </div>
              )}
            </Card>
          </>
        )}
      </div>

      {/* Scan & Add: close only via X or on success (no outside-click / Esc) */}
      <Dialog open={openDialog === "scan"} onOpenChange={(o) => setOpenDialog(o ? "scan" : null)}>
        <DialogContent
          className={DIALOG}
          onInteractOutside={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => e.preventDefault()}
        >
          <DialogTitle className="sr-only">Scan or import</DialogTitle>
          <Suspense fallback={<Loading />}>
            <ScanImport onExpenseAdded={handleExpenseAddedAndClose} onDone={() => setOpenDialog(null)} />
          </Suspense>
        </DialogContent>
      </Dialog>

      <Dialog open={openDialog === "add"} onOpenChange={(o) => setOpenDialog(o ? "add" : null)}>
        <DialogContent
          className={DIALOG}
          onInteractOutside={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => e.preventDefault()}
        >
          <DialogTitle className="sr-only">Add expense</DialogTitle>
          <ExpenseForm onExpenseAdded={handleExpenseAddedAndClose} />
        </DialogContent>
      </Dialog>

      <Dialog open={openDialog === "settings"} onOpenChange={(o) => setOpenDialog(o ? "settings" : null)}>
        <DialogContent
          className={DIALOG}
          onInteractOutside={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => e.preventDefault()}
        >
          <DialogTitle className="sr-only">Settings</DialogTitle>
          <Suspense fallback={<Loading />}>
            <Settings onClose={() => setOpenDialog(null)} />
          </Suspense>
        </DialogContent>
      </Dialog>

      <Dialog open={openDialog === "ask"} onOpenChange={(o) => setOpenDialog(o ? "ask" : null)}>
        <DialogContent className={DIALOG}>
          <DialogTitle className="sr-only">Ask AI</DialogTitle>
          <Suspense fallback={<Loading />}>
            <AskAI />
          </Suspense>
        </DialogContent>
      </Dialog>

      <Dialog open={openDialog === "wallet"} onOpenChange={(o) => setOpenDialog(o ? "wallet" : null)}>
        <DialogContent className={`${DIALOG} max-h-[88vh] overflow-y-auto glass-scroll`}>
          <DialogTitle className="sr-only">Wallet</DialogTitle>
          <WalletCard reloadKey={ledgerReload} onChange={bump} />
        </DialogContent>
      </Dialog>

      <Dialog open={openDialog === "savings"} onOpenChange={(o) => setOpenDialog(o ? "savings" : null)}>
        <DialogContent className={`${DIALOG} max-h-[88vh] overflow-y-auto glass-scroll`}>
          <DialogTitle className="sr-only">Savings</DialogTitle>
          <SavingsCard reloadKey={ledgerReload} onChange={bump} />
        </DialogContent>
      </Dialog>

      <Dialog open={openDialog === "insights"} onOpenChange={(o) => setOpenDialog(o ? "insights" : null)}>
        <DialogContent className={DIALOG}>
          <DialogTitle className="sr-only">Insights</DialogTitle>
          <Suspense fallback={<Loading />}>
            <Insights />
          </Suspense>
        </DialogContent>
      </Dialog>

      {/* filter */}
      <Dialog open={openDialog === "filter"} onOpenChange={(o) => setOpenDialog(o ? "filter" : null)}>
        <DialogContent className="max-w-md border-0 bg-transparent p-0 shadow-none">
          <DialogTitle className="sr-only">Filter expenses</DialogTitle>
          <Card className={`${GLASS} rounded-2xl`}>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-medium">Filter</h2>
                {hasFilter && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setFilters({ start: "", end: "", category: "" })}
                    className="text-primary hover:text-primary"
                  >
                    Clear
                  </Button>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label>From</Label>
                  <Input
                    type="date"
                    value={filters.start}
                    onChange={(e) => setFilters((f) => ({ ...f, start: e.target.value }))}
                    className="[&::-webkit-calendar-picker-indicator]:invert"
                  />
                </div>
                <div className="space-y-2">
                  <Label>To</Label>
                  <Input
                    type="date"
                    value={filters.end}
                    onChange={(e) => setFilters((f) => ({ ...f, end: e.target.value }))}
                    className="[&::-webkit-calendar-picker-indicator]:invert"
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label>Category</Label>
                <Select
                  value={filters.category || "all"}
                  onValueChange={(v) => setFilters((f) => ({ ...f, category: v === "all" ? "" : v }))}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="All categories" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All categories</SelectItem>
                    {CATEGORIES.map((c) => (
                      <SelectItem key={c} value={c}>{c}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button onClick={() => setOpenDialog(null)} className="w-full font-medium">
                Done
              </Button>
            </CardContent>
          </Card>
        </DialogContent>
      </Dialog>
    </div>
  );
}
